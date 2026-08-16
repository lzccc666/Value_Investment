from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from app.configuration.defaults import default_parameter_config
from app.main import create_app
from app.services.parameter_config_service import (
    build_parameter_metadata,
    config_hash,
    get_runtime_parameter_config,
    publish_parameter_config,
    validate_parameter_config,
)


def _source_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "active_parameters.json"
    monkeypatch.setenv("VALUE_INVESTMENT_PARAMETER_CONFIG_PATH", str(path))
    return path


def test_default_parameter_config_is_complete_and_valid() -> None:
    result = validate_parameter_config(default_parameter_config(), compare_to_default=False)

    assert result.valid is True
    assert result.errors == []
    assert result.actual_parameter_count == 372
    assert result.audit_parameter_count == 92


def test_parameter_metadata_keeps_scores_counts_and_multipliers_as_raw_numbers() -> None:
    metadata = {
        item["path"]: item for item in build_parameter_metadata(default_parameter_config())
    }

    assert metadata["valuation_rule_matrix.status_scores.pass"]["unit"] == "数值"
    assert metadata["valuation_rule_matrix.weight_exponent"]["unit"] == "数值"
    assert metadata["analyst_engine.data_confidence.announcement_target_count"]["unit"] == "条公告"
    assert metadata["financial_flags.cagr_years.0"]["unit"] == "年"
    assert metadata["data_sampling.announcement_model_chars"]["unit"] == "字符"
    assert metadata["memo_decision.safety_margin_score_span"]["unit"] == "数值"
    assert metadata["valuation_models.scenarios.conservative.growth_spread"]["unit"] == "倍"
    assert metadata["valuation_models.base_discount_rate"]["unit"] == "%"


def test_all_visible_parameter_copy_is_chinese_specific_and_uniquely_named() -> None:
    metadata = [
        item
        for item in build_parameter_metadata(default_parameter_config())
        if ".rule_mappings." not in item["path"]
    ]

    labels = [str(item["label"]) for item in metadata]
    descriptions = [str(item["description"]) for item in metadata]

    assert len(metadata) == 269
    assert len(labels) == len(set(labels))
    assert all("_" not in label and "未审计" not in label for label in labels)
    assert all(len(description) >= 24 for description in descriptions)
    assert all("影响新生成运行的统一配置参数" not in description for description in descriptions)

    by_path = {item["path"]: item for item in metadata}
    assert by_path["analyst_engine.feature_adjustments.cash_flow_quality"]["label"] == (
        "存在经营现金流数据的质量视角加分"
    )
    assert "不是现金流质量结论" in by_path[
        "analyst_engine.feature_adjustments.cash_flow_quality"
    ]["description"]
    assert by_path["valuation_models.permanent_loss_optimistic_cap"]["label"] == (
        "停止上调乐观永续增长的永久损失风险阈值"
    )
    assert "不是增长率上限" in by_path[
        "valuation_models.permanent_loss_optimistic_cap"
    ]["description"]
    assert "与 010 状态分相互独立" in by_path[
        "memo_decision.status_scores.warn"
    ]["description"]


def test_validation_returns_all_detected_errors() -> None:
    config = default_parameter_config()
    config["valuation_models"]["model_weights"]["dcf"] = 0.9
    config["memo_decision"]["safety_margin_max"] = 0.8
    config["valuation_models"]["base_discount_rate"] = 0.01
    config["valuation_models"]["base_terminal_growth"] = 0.02
    del config["valuation_rule_matrix"]["rule_mappings"]["buffett.moat"]

    result = validate_parameter_config(config)
    codes = {issue.code for issue in result.errors}

    assert result.valid is False
    assert {
        "weight_sum",
        "safety_margin",
        "discount_terminal_gap",
        "shape",
        "rule_coverage",
    }.issubset(codes)
    assert len(result.errors) >= 5


def test_missing_source_uses_builtin_defaults_without_creating_a_file(
    tmp_path: Path, monkeypatch
) -> None:
    source_path = _source_path(tmp_path, monkeypatch)

    runtime = get_runtime_parameter_config()

    assert runtime.source == "builtin_default"
    assert runtime.snapshot == default_parameter_config()
    assert runtime.version is None
    assert source_path.exists() is False


def test_publish_atomically_replaces_the_source_file(tmp_path: Path, monkeypatch) -> None:
    source_path = _source_path(tmp_path, monkeypatch)
    config = deepcopy(default_parameter_config())
    config["valuation_models"]["default_growth"] = 0.05

    published, validation = publish_parameter_config(config, warnings_acknowledged=True)
    runtime = get_runtime_parameter_config()

    assert validation.valid is True
    assert published.source == "source_file"
    assert runtime.source == "source_file"
    assert runtime.snapshot["valuation_models"]["default_growth"] == 0.05
    assert runtime.config_hash == config_hash(config)
    assert source_path.read_text(encoding="utf-8").endswith("\n")
    assert list(tmp_path.glob("*.tmp")) == []


def test_invalid_source_falls_back_as_a_complete_snapshot(tmp_path: Path, monkeypatch) -> None:
    source_path = _source_path(tmp_path, monkeypatch)
    source_path.write_text('{"data_sampling":{"company_list_limit":1}}', encoding="utf-8")

    runtime = get_runtime_parameter_config()

    defaults = default_parameter_config()
    assert runtime.source == "builtin_fallback"
    assert runtime.fallback_reason == "source_config_invalid"
    assert runtime.snapshot == defaults
    assert runtime.config_hash == config_hash(defaults)


def test_api_validation_does_not_persist_and_publish_requires_warning_acknowledgement(
    tmp_path: Path, monkeypatch
) -> None:
    source_path = _source_path(tmp_path, monkeypatch)
    client = TestClient(create_app(initialize_database=False))
    config = client.get("/api/parameter-config/defaults").json()["config_json"]
    config["valuation_models"]["default_growth"] = 0.05

    validation = client.post(
        "/api/parameter-config/validate", json={"config_json": config}
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert len(validation.json()["warnings"]) == 1
    assert source_path.exists() is False

    conflict = client.put(
        "/api/parameter-config/current",
        json={"config_json": config, "warnings_acknowledged": False},
    )
    assert conflict.status_code == 409
    assert source_path.exists() is False

    published = client.put(
        "/api/parameter-config/current",
        json={"config_json": config, "warnings_acknowledged": True},
    )
    assert published.status_code == 200
    assert published.json()["source"] == "source_file"
    assert source_path.exists() is True

    assert client.get("/api/parameter-config/versions").status_code == 404
    assert client.post("/api/parameter-config/drafts", json={}).status_code == 404
