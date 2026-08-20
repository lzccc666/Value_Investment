from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.analysis.valuation_parameter_matrix import VALUATION_DIMENSIONS
from app.configuration.defaults import default_parameter_config
from app.configuration.parameter_copy import parameter_copy
from app.schemas.parameter_config import ParameterValidationIssue, ParameterValidationResult

logger = logging.getLogger(__name__)

CONFIG_DOMAINS = (
    "data_sampling",
    "financial_flags",
    "analyst_engine",
    "valuation_rule_matrix",
    "memo_decision",
    "valuation_models",
    "price_decision",
)
FORBIDDEN_CONFIG_KEYS = {
    "price_blind",
    "price_blind_enabled",
    "allow_price_inputs",
    "calculate_without_confirmation",
    "immutable_history",
    "rule_status_enum",
}


class ParameterConfigError(ValueError):
    pass


class ParameterConfigValidationError(ParameterConfigError):
    def __init__(self, result: ParameterValidationResult) -> None:
        super().__init__("参数配置校验失败。")
        self.result = result


class ParameterConfigWarningConfirmationRequired(ParameterConfigError):
    def __init__(self, result: ParameterValidationResult) -> None:
        super().__init__("配置包含警告，发布前必须二次确认。")
        self.result = result


@dataclass(frozen=True)
class RuntimeParameterConfig:
    version: int | None
    config_hash: str
    snapshot: dict[str, object]
    source: str
    fallback_reason: str | None = None


def config_hash(config_json: dict[str, object]) -> str:
    payload = json.dumps(config_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def active_parameter_config_path() -> Path:
    override = os.getenv("VALUE_INVESTMENT_PARAMETER_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "configuration" / "active_parameters.json"


def get_runtime_parameter_config(session: Session | None = None) -> RuntimeParameterConfig:
    del session  # Existing 004-011 callers can keep passing their database session.
    source_path = active_parameter_config_path()
    if not source_path.exists():
        config = default_parameter_config()
        return RuntimeParameterConfig(
            version=None,
            config_hash=config_hash(config),
            snapshot=config,
            source="builtin_default",
        )

    try:
        loaded = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("源码配置根节点必须是对象。")
        result = validate_parameter_config(loaded, compare_to_default=False)
        if not result.valid:
            raise ValueError("源码配置未通过完整校验。")
        return RuntimeParameterConfig(
            version=None,
            config_hash=config_hash(loaded),
            snapshot=deepcopy(loaded),
            source="source_file",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        fallback = default_parameter_config()
        logger.error(
            "Parameter config fallback activated: source_config_invalid path=%s error=%s",
            source_path,
            exc,
        )
        return RuntimeParameterConfig(
            version=None,
            config_hash=config_hash(fallback),
            snapshot=fallback,
            source="builtin_fallback",
            fallback_reason="source_config_invalid",
        )


def publish_parameter_config(
    config_json: dict[str, object], *, warnings_acknowledged: bool
) -> tuple[RuntimeParameterConfig, ParameterValidationResult]:
    normalized = deepcopy(config_json)
    result = validate_parameter_config(normalized)
    if not result.valid:
        raise ParameterConfigValidationError(result)
    if result.warnings and not warnings_acknowledged:
        raise ParameterConfigWarningConfirmationRequired(result)

    source_path = active_parameter_config_path()
    source_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=source_path.parent,
            prefix=f".{source_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, source_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise ParameterConfigError(f"源码参数文件写入失败：{exc}") from exc

    runtime = RuntimeParameterConfig(
        version=None,
        config_hash=config_hash(normalized),
        snapshot=normalized,
        source="source_file",
    )
    return runtime, result


def validate_parameter_config(
    config: dict[str, object], *, compare_to_default: bool = True
) -> ParameterValidationResult:
    errors: list[ParameterValidationIssue] = []
    warnings: list[ParameterValidationIssue] = []

    actual_domains = set(config) if isinstance(config, dict) else set()
    if actual_domains != set(CONFIG_DOMAINS):
        missing_domains = sorted(set(CONFIG_DOMAINS) - actual_domains)
        extra_domains = sorted(actual_domains - set(CONFIG_DOMAINS))
        _issue(
            errors,
            "",
            (
                f"配置域必须精确为 {', '.join(CONFIG_DOMAINS)}；"
                f"缺失={missing_domains}，多出={extra_domains}。"
            ),
            "domain_coverage",
        )
    _validate_finite(config, errors)
    _validate_forbidden_keys(config, errors)

    defaults = default_parameter_config()
    _validate_shape(config, defaults, errors)

    _sum_to_one(config, "valuation_models.model_weights", errors)
    _sum_to_one(config, "analyst_engine.evidence_ranking", errors)
    _sum_selected_to_one(
        config,
        "analyst_engine.profile_fit",
        ("industry_weight", "rule_coverage_weight", "evidence_support_weight"),
        errors,
    )
    _sum_selected_to_one(
        config,
        "analyst_engine.data_confidence",
        ("financial_weight", "announcement_weight", "external_weight", "source_balance_weight"),
        errors,
    )
    _sum_selected_to_one(
        config,
        "valuation_rule_matrix",
        ("confidence_weight", "profile_fit_weight"),
        errors,
    )
    for group in ("quality", "risk"):
        _sum_to_one(config, f"valuation_models.composite_weights.{group}", errors)
    _sum_selected_to_one(
        config,
        "valuation_models.composite_weights.growth",
        ("growth_runway", "pricing_power", "demand_durability", "execution_quality"),
        errors,
    )

    _validate_range(config, "valuation_models.model_weights", 0.0, 1.0, errors)
    _validate_range(config, "analyst_engine.model_temperatures", 0.0, 1.0, errors)
    _validate_safety_margin(config, "valuation_rule_matrix", errors)
    _validate_safety_margin(config, "price_decision", errors)
    _validate_discount_terminal(config, errors)
    _validate_scenarios(config, errors)
    _validate_rule_mappings(config, errors)
    _validate_status_policies(config, errors)
    _validate_dynamic_safety_margin(config, errors)
    _validate_tiers(config, errors)
    _validate_normalization_year_weights(config, errors)

    if compare_to_default and config_hash(config) != config_hash(defaults):
        changed = _changed_leaf_paths(defaults, config)
        _issue(
            warnings,
            "",
            f"相对内置默认配置有 {len(changed)} 个叶子值变化；发布后只影响新运行。",
            "non_default_values",
            severity="warning",
        )

    actual_count, audit_count = count_parameter_values(config)
    return ParameterValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        actual_parameter_count=actual_count,
        audit_parameter_count=audit_count,
    )


def count_parameter_values(config: dict[str, object]) -> tuple[int, int]:
    actual = 0
    audit = 0

    def walk(value: object, path: tuple[str, ...]) -> None:
        nonlocal actual, audit
        if isinstance(value, dict):
            for key, nested in value.items():
                walk(nested, (*path, str(key)))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, (*path, str(index)))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if not any(part in {"profile_id", "rule_id"} for part in path):
                actual += 1

    walk(config, ())
    return actual, audit


LABELS = {
    "data_sampling": "数据采样",
    "financial_flags": "财务预警",
    "analyst_engine": "分析师引擎",
    "valuation_rule_matrix": "估值规则矩阵",
    "memo_decision": "备忘录决策",
    "valuation_models": "估值模型",
    "price_decision": "价格决策",
    "forecast_years": "预测期",
    "model_weights": "五模型权重",
    "status_scores": "规则状态分",
    "safety_margin_min": "安全边际最小值",
    "safety_margin_max": "安全边际最大值",
    "model_temperatures": "模型温度",
    "rule_mappings": "32 条规则矩阵",
    "dimensions": "估值维度映射",
}


def build_parameter_metadata(config: dict[str, object]) -> list[dict[str, object]]:
    defaults = default_parameter_config()
    items: list[dict[str, object]] = []

    def walk(value: object, default: object, path: list[str]) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                default_nested = default.get(key) if isinstance(default, dict) else None
                walk(nested, default_nested, [*path, str(key)])
            return
        if isinstance(value, list):
            for index, nested in enumerate(value):
                default_nested = (
                    default[index] if isinstance(default, list) and index < len(default) else None
                )
                walk(nested, default_nested, [*path, str(index)])
            return
        if not path:
            return
        dotted = ".".join(path)
        audit_only = False
        expert = path[0] in {"analyst_engine", "valuation_rule_matrix", "valuation_models"}
        unit = _parameter_unit(path)
        percent = unit == "%"
        label_key = path[-1]
        copy = parameter_copy(tuple(path), config)
        items.append(
            {
                "path": dotted,
                "domain": path[0],
                "label": copy.label,
                "code_name": dotted,
                "description": copy.description,
                "unit": unit,
                "default_value": default,
                "current_value": value,
                "minimum": 0.0 if percent and "min" not in label_key else None,
                "maximum": 1.0 if percent else None,
                "editable": True,
                "expert": expert,
                "audit_only": audit_only,
                "risk": "high" if expert or audit_only else "medium",
            }
        )

    walk(config, defaults, [])
    return items


def _validate_shape(
    value: object, default: object, errors: list[ParameterValidationIssue], path: str = ""
) -> None:
    if isinstance(default, dict):
        if not isinstance(value, dict):
            _issue(errors, path, "应为对象。", "type")
            return
        missing = set(default) - set(value)
        extra = set(value) - set(default)
        if missing or extra:
            _issue(
                errors, path, f"字段不完整：缺失={sorted(missing)}，多出={sorted(extra)}。", "shape"
            )
        for key in set(default) & set(value):
            _validate_shape(value[key], default[key], errors, f"{path}.{key}".strip("."))
    elif isinstance(default, list):
        if not isinstance(value, list):
            _issue(errors, path, "应为数组。", "type")
    elif isinstance(default, bool):
        if not isinstance(value, bool):
            _issue(errors, path, "应为布尔值。", "type")
    elif isinstance(default, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _issue(errors, path, "应为有限数字。", "type")
    elif isinstance(default, str) and not isinstance(value, str):
        _issue(errors, path, "应为字符串。", "type")


def _validate_finite(value: object, errors: list[ParameterValidationIssue], path: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _validate_finite(nested, errors, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_finite(nested, errors, f"{path}.{index}".strip("."))
    elif (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not math.isfinite(float(value))
    ):
        _issue(errors, path, "必须是有限数字。", "finite_number")


def _validate_forbidden_keys(
    value: object, errors: list[ParameterValidationIssue], path: str = ""
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}".strip(".")
            if str(key).lower() in FORBIDDEN_CONFIG_KEYS:
                _issue(errors, nested_path, "该结构性约束不允许配置。", "structural_constraint")
            _validate_forbidden_keys(nested, errors, nested_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_forbidden_keys(nested, errors, f"{path}.{index}".strip("."))


def _validate_rule_mappings(
    config: dict[str, object], errors: list[ParameterValidationIssue]
) -> None:
    mappings = _at(config, "valuation_rule_matrix.rule_mappings")
    defaults = _at(default_parameter_config(), "valuation_rule_matrix.rule_mappings")
    if not isinstance(mappings, dict) or not isinstance(defaults, dict):
        return
    if set(mappings) != set(defaults):
        _issue(
            errors,
            "valuation_rule_matrix.rule_mappings",
            "32 条规则映射不得缺失或多出。",
            "rule_coverage",
        )
        return
    compute = 0
    dimension_coefficients = 0
    valid_dimensions = set(VALUATION_DIMENSIONS)
    for key, raw in mappings.items():
        if not isinstance(raw, dict):
            continue
        role = raw.get("calculation_role")
        if role == "compute":
            compute += 1
            if raw.get("price_blind_compatible") is not True:
                _issue(
                    errors,
                    f"valuation_rule_matrix.rule_mappings.{key}",
                    "compute 规则必须兼容 price-blind。",
                    "price_blind",
                )
        else:
            _issue(
                errors,
                f"valuation_rule_matrix.rule_mappings.{key}.calculation_role",
                "所有规则的角色只能是 compute。",
                "rule_role",
            )
        dimensions = raw.get("dimensions")
        if isinstance(dimensions, dict):
            dimension_coefficients += len(dimensions)
            if not set(dimensions).issubset(valid_dimensions):
                _issue(
                    errors,
                    f"valuation_rule_matrix.rule_mappings.{key}.dimensions",
                    "包含未知估值维度。",
                    "dimension",
                )
    if compute != 32:
        _issue(
            errors,
            "valuation_rule_matrix.rule_mappings",
            f"32 条规则必须全部参与计算，当前参与计算={compute}。",
            "rule_roles",
        )
    if dimension_coefficients != 117:
        _issue(
            errors,
            "valuation_rule_matrix.rule_mappings",
            f"维度映射系数必须为 117 个，当前为 {dimension_coefficients}。",
            "dimension_count",
        )


def _validate_status_policies(
    config: dict[str, object], errors: list[ParameterValidationIssue]
) -> None:
    expected = {"pass", "neutral", "unknown", "warn", "fail"}
    for path in (
        "valuation_rule_matrix.status_scores",
        "valuation_rule_matrix.safety_margin_additions",
    ):
        policy = _at(config, path)
        if not isinstance(policy, dict) or set(policy) != expected:
            _issue(
                errors,
                path,
                "状态策略必须精确包含 pass/neutral/unknown/warn/fail。",
                "status_policy",
            )


def _validate_dynamic_safety_margin(
    config: dict[str, object], errors: list[ParameterValidationIssue]
) -> None:
    additions = _at(config, "valuation_rule_matrix.safety_margin_additions")
    scale = _number(_at(config, "valuation_rule_matrix.safety_margin_analyst_scale"))
    if not isinstance(additions, dict) or scale is None:
        return
    values = [_number(value) for value in additions.values()]
    if any(value is None or value < 0 for value in values):
        _issue(
            errors,
            "valuation_rule_matrix.safety_margin_additions",
            "五状态安全边际加点必须是非负有限数。",
            "safety_margin_addition",
        )
        return
    if scale <= 0:
        _issue(
            errors,
            "valuation_rule_matrix.safety_margin_analyst_scale",
            "安全边际分析师数量缩放值必须大于 0。",
            "safety_margin_scale",
        )
        return
    maximum = max(float(value) for value in values if value is not None) * 4 * scale
    if maximum > 1.0 + 1e-9:
        _issue(
            errors,
            "valuation_rule_matrix.safety_margin_additions",
            f"默认最坏状态的理论动态安全边际为 {maximum:.2%}，不得超过 100%。",
            "dynamic_safety_margin_maximum",
        )


def _validate_discount_terminal(
    config: dict[str, object], errors: list[ParameterValidationIssue]
) -> None:
    discount = _number(_at(config, "valuation_models.base_discount_rate"))
    terminal = _number(_at(config, "valuation_models.base_terminal_growth"))
    gap = _number(_at(config, "valuation_models.discount_terminal_gap"))
    if None not in (discount, terminal, gap) and discount < terminal + max(gap, 0.01):
        _issue(
            errors,
            "valuation_models.base_discount_rate",
            "折现率必须至少高于永续增长率 1 个百分点。",
            "discount_terminal_gap",
        )


def _validate_scenarios(config: dict[str, object], errors: list[ParameterValidationIssue]) -> None:
    conservative = _at(config, "valuation_models.scenarios.conservative")
    optimistic = _at(config, "valuation_models.scenarios.optimistic")
    if not isinstance(conservative, dict) or not isinstance(optimistic, dict):
        return
    for key in ("growth_spread", "owner_growth_spread", "terminal_spread"):
        if (
            _number(conservative.get(key)) is not None
            and _number(optimistic.get(key)) is not None
            and float(conservative[key]) > float(optimistic[key])
        ):
            _issue(
                errors,
                f"valuation_models.scenarios.{key}",
                "保守到乐观必须单调不下降。",
                "scenario_monotonic",
            )
    if (
        _number(conservative.get("discount_spread")) is not None
        and _number(optimistic.get("discount_spread")) is not None
        and float(conservative["discount_spread"]) < float(optimistic["discount_spread"])
    ):
        _issue(
            errors,
            "valuation_models.scenarios.discount_spread",
            "保守折现率调整不得低于乐观调整。",
            "scenario_monotonic",
        )
    for haircut_path in (
        "valuation_models.non_cash_asset_haircuts",
        "valuation_models.equity_fallback_haircuts",
    ):
        item = _at(config, haircut_path)
        if isinstance(item, dict):
            values = [_number(item.get(name)) for name in ("conservative", "base", "optimistic")]
            if (
                all(value is not None for value in values)
                and not values[0] <= values[1] <= values[2]
            ):
                _issue(errors, haircut_path, "保守/中性/乐观折扣必须单调。", "scenario_monotonic")


def _validate_safety_margin(
    config: dict[str, object], domain: str, errors: list[ParameterValidationIssue]
) -> None:
    minimum = _number(_at(config, f"{domain}.safety_margin_min"))
    maximum = _number(_at(config, f"{domain}.safety_margin_max"))
    if minimum is not None and maximum is not None and not (0 <= minimum <= maximum <= 1.0):
        _issue(errors, domain, "安全边际范围必须位于 0%-100%。", "safety_margin")


def _validate_tiers(config: dict[str, object], errors: list[ParameterValidationIssue]) -> None:
    high = _number(_at(config, "analyst_engine.tier_thresholds.high"))
    medium = _number(_at(config, "analyst_engine.tier_thresholds.medium"))
    if high is not None and medium is not None and not (0 <= medium < high <= 1):
        _issue(
            errors,
            "analyst_engine.tier_thresholds",
            "等级阈值必须满足 0 <= medium < high <= 1。",
            "tier_order",
        )


def _validate_normalization_year_weights(
    config: dict[str, object], errors: list[ParameterValidationIssue]
) -> None:
    path = "valuation_models.normalization_year_weights"
    raw = _at(config, path)
    if not isinstance(raw, list) or len(raw) != 3:
        _issue(errors, path, "正常化年度权重必须恰好包含最近三年三个权重。", "weight_shape")
        return
    values = [_number(item) for item in raw]
    if any(value is None or value < 0 for value in values):
        _issue(errors, path, "正常化年度权重必须是非负有限数字。", "weight_range")
        return
    if abs(sum(value for value in values if value is not None) - 1.0) > 0.000001:
        _issue(errors, path, "正常化年度权重合计必须等于 100%。", "weight_sum")


def _sum_to_one(
    config: dict[str, object], path: str, errors: list[ParameterValidationIssue]
) -> None:
    value = _at(config, path)
    if isinstance(value, dict):
        _validate_sum(path, list(value.values()), errors)


def _sum_selected_to_one(
    config: dict[str, object],
    path: str,
    keys: tuple[str, ...],
    errors: list[ParameterValidationIssue],
) -> None:
    value = _at(config, path)
    if isinstance(value, dict):
        _validate_sum(path, [value.get(key) for key in keys], errors)


def _validate_sum(path: str, values: list[object], errors: list[ParameterValidationIssue]) -> None:
    numbers = [_number(value) for value in values]
    if any(value is None for value in numbers):
        return
    if (
        any(value < 0 for value in numbers if value is not None)
        or abs(sum(value for value in numbers if value is not None) - 1.0) > 0.000001
    ):
        _issue(errors, path, "组合权重必须非负且合计等于 100%。", "weight_sum")


def _validate_range(
    config: dict[str, object],
    path: str,
    low: float,
    high: float,
    errors: list[ParameterValidationIssue],
) -> None:
    value = _at(config, path)
    if isinstance(value, dict):
        for key, nested in value.items():
            number = _number(nested)
            if number is not None and not low <= number <= high:
                _issue(errors, f"{path}.{key}", f"必须位于 {low} 到 {high}。", "range")


def _changed_leaf_paths(left: object, right: object, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        paths: list[str] = []
        for key in set(left) | set(right):
            paths.extend(
                _changed_leaf_paths(left.get(key), right.get(key), f"{path}.{key}".strip("."))
            )
        return paths
    if isinstance(left, list) and isinstance(right, list):
        paths = []
        for index in range(max(len(left), len(right))):
            paths.extend(
                _changed_leaf_paths(
                    left[index] if index < len(left) else None,
                    right[index] if index < len(right) else None,
                    f"{path}.{index}".strip("."),
                )
            )
        return paths
    return [] if left == right else [path]


def _at(config: dict[str, object], path: str) -> object:
    value: object = config
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _issue(
    items: list[ParameterValidationIssue],
    path: str,
    message: str,
    code: str,
    *,
    severity: str = "error",
) -> None:
    items.append(ParameterValidationIssue(path=path, message=message, severity=severity, code=code))


def _looks_like_percent_path(path: list[str]) -> bool:
    token = "_".join(path).lower()
    return any(
        part in token
        for part in (
            "rate",
            "ratio",
            "weight",
            "score",
            "margin",
            "penalty",
            "bonus",
            "confidence",
            "haircut",
            "growth",
            "spread",
            "minimum",
            "maximum",
        )
    )


def _parameter_unit(path: list[str]) -> str:
    label_key = path[-1]
    dotted = ".".join(path)
    explicit_units = {
        "data_sampling.company_list_limit": "家公司",
        "data_sampling.company_list_limit_max": "家公司",
        "data_sampling.financial_display_periods": "期",
        "data_sampling.analysis_financial_periods": "期",
        "data_sampling.valuation_financial_records": "条记录",
        "data_sampling.announcement_lookback_years": "年",
        "data_sampling.announcement_retention_limit": "条公告",
        "data_sampling.announcement_page_size": "条/页",
        "data_sampling.announcement_max_pages": "页",
        "data_sampling.analysis_announcement_pool": "条公告",
        "data_sampling.analysis_announcement_items": "条公告",
        "data_sampling.analysis_evidence_items": "条证据",
        "data_sampling.external_evidence_limit": "条证据",
        "data_sampling.external_search_default_results": "条候选",
        "data_sampling.announcement_model_chars": "字符",
        "data_sampling.announcement_keyword_summary_chars": "字符",
        "data_sampling.analysis_excerpt_chars": "字符",
        "data_sampling.manual_import_model_chars": "字符",
        "data_sampling.manual_import_snapshot_chars": "字符",
        "data_sampling.evidence_excerpt_chars": "字符",
        "data_sampling.search_snippet_chars": "字符",
        "data_sampling.search_title_chars": "字符",
        "data_sampling.memo_list_items": "条",
        "data_sampling.price_decision_history_limit": "条记录",
        "analyst_engine.profile_fit.few_financial_periods": "期",
        "analyst_engine.data_confidence.financial_periods_required": "期",
        "analyst_engine.data_confidence.announcement_target_count": "条公告",
        "memo_decision.min_successful_analysts": "位分析师",
        "price_decision.buy_price_scenario": "选项",
    }
    if dotted in explicit_units:
        return explicit_units[dotted]
    if "cagr_years" in path:
        return "年"
    if "growth_source_priority" in path:
        return "选项"
    raw_value_paths = {
        "analyst_engine.data_confidence.financial_periods_required",
        "analyst_engine.data_confidence.few_financial_periods",
        "analyst_engine.data_confidence.announcement_target_count",
        "valuation_rule_matrix.weight_exponent",
        "valuation_rule_matrix.dimension_score_min",
        "valuation_rule_matrix.dimension_score_max",
        "valuation_rule_matrix.safety_margin_analyst_scale",
        "valuation_models.dispersion_ratio",
    }
    if dotted in raw_value_paths or "status_scores" in path or "rule_mappings" in path:
        return "数值"
    if "scenarios" in path and label_key.endswith("_spread"):
        return "倍"
    if "years" in label_key:
        return "年"
    return "%" if _looks_like_percent_path(path) else "数值"
