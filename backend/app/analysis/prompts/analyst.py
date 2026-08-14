from __future__ import annotations

import json

from app.analysis.analyst_profiles import AnalystProfile

PROMPT_VERSION = "analyst_view_v1"

ANALYST_OUTPUT_TEMPLATE = {
    "analyst_profile": "<必须等于 Profile.id>",
    "overview": "<一段中文概览，基于快照，不新增事实>",
    "profile_fit_score": 0.5,
    "confidence": 0.5,
    "key_observations": ["<关键观察>"],
    "rule_checks": [
        {
            "rule_id": "<Profile.rules[].id>",
            "status": "unknown",
            "summary": "<该规则的判断依据>",
            "evidence_ids": [],
            "financial_periods": [],
            "announcement_ids": [],
        }
    ],
    "supporting_evidence_ids": [],
    "financial_observations": ["<财务观察>"],
    "announcement_observations": ["<公告观察>"],
    "risk_flags": ["<风险>"],
    "counter_evidence": ["<最可能推翻当前判断的反方证据或待验证事实>"],
    "valuation_assumption_suggestions": ["<后续估值或安全边际判断应验证的假设>"],
    "valuation_assumption_details": [
        {
            "assumption_type": "<假设类型>",
            "reason": "<为什么需要这个假设>",
            "needed_inputs": ["<后续需要补充的输入>"],
            "source_refs": {
                "financial_periods": [],
                "announcement_ids": [],
                "external_evidence_ids": [],
            },
        }
    ],
    "data_gaps": ["<数据缺口>"],
    "follow_up_questions": ["<后续问题>"],
    "analysis_basis": {
        "financial_periods": [],
        "announcement_ids": [],
        "external_evidence_ids": [],
        "accounting_event_count": 0,
        "accounting_event_labels": [],
        "notes": [],
    },
    "accounting_events": [],
    "score_explanations": {
        "profile_relevance": {"score": 0.5, "reasons": []},
        "data_confidence": {"score": 0.5, "reasons": []},
    },
}

ANALYST_SYSTEM_PROMPT = """你是一个本地价值投资研究系统中的分析师视角引擎。

边界要求：
- 只能使用用户消息中提供的数据快照：外部证据、财务数据和公告数据。
- 每次分析师视角 run 必须完全独立；不要读取、参考或延续历史 run 的结论。
- 快照中的 evidence / external_evidence 都指 007 已入库外部信息记录；
  不要把它和财务报表、公告本身混为一类。
- 不要生成搜索 query，不要要求联网搜索，不要声称读取了快照以外的信息。
- 如果快照中包含当前价格、历史价格、目标价、市值、估值倍数、持仓成本等信息，
  可以按当前分析师框架正常读取、引用和判断，但必须说明它来自快照。
- financial_evidence_pack 是后端确定性整理的财务证据包，
  可优先用于财务质量、风险识别、数据缺口和估值假设建议；
  financial_statements 是可追溯的原始期间财务记录。
- 可以围绕商业质量、管理层、护城河、成长质量、风险、反方证据、
  估值纪律、安全边际和估值假设建议展开。
- “估值假设建议”应写后续估值或安全边际判断应补充哪些假设或口径，例如利润可持续性、
  现金流折现变量、资本开支、会计调整、情景变量、估值倍数或价格相关敏感性。
- valuation_assumption_suggestions 保持中文短句列表；
  valuation_assumption_details 用结构化方式写 assumption_type、reason、needed_inputs
  和 source_refs。
- 对证据不足的地方明确写入 data_gaps 或 follow_up_questions。
- source_coverage_matrix 表示当前快照各类证据覆盖哪些主题；
  pre_model_observations 是服务层确定性提示，不是模型结论。
- 必须先阅读 fact_ledger；如果 fact_ledger.accounting_events 非空，
  评价收入、利润或同比变化前必须说明会计口径、收入确认、追溯调整或
  非经常性因素的影响。
- profile_fit_score 代表分析师框架与公司类型的适配度；
  confidence 代表本次快照数据质量，二者不是看多/看空强度。
- 输出必须是合法 JSON，且必须符合调用方给定 schema。
- 顶层必须包含 overview、profile_fit_score、confidence。
- rule_checks 每一项必须包含 rule_id、status、summary、evidence_ids、
  financial_periods、announcement_ids。
- status 只能使用 pass、warn、fail、unknown 四个值；不要使用其他状态别名。"""


def build_analyst_prompt(
    *,
    profile: AnalystProfile,
    data_snapshot: dict[str, object],
) -> str:
    profile_payload = {
        "id": profile.id,
        "name": profile.name,
        "display_name": profile.display_name,
        "description": profile.description,
        "philosophy": profile.philosophy,
        "rules": [
            {
                "id": rule.id,
                "label": rule.label,
                "description": rule.description,
            }
            for rule in profile.rules
        ],
        "prompt_focus": list(profile.prompt_focus),
    }
    return "\n".join(
        [
            "请按以下分析师 Profile 和统一规则接口生成分析师视角。",
            "",
            "Profile:",
            json.dumps(profile_payload, ensure_ascii=False, indent=2),
            "",
            "数据快照:",
            json.dumps(data_snapshot, ensure_ascii=False, indent=2, default=str),
            "",
            "输出要求:",
            "必须严格按这个 JSON 模板返回，不要新增字段名替代模板字段：",
            json.dumps(ANALYST_OUTPUT_TEMPLATE, ensure_ascii=False, indent=2),
            "",
            "- analyst_profile 必须等于 Profile.id。",
            "- overview、profile_fit_score、confidence 是必填字段。",
            (
                "- 如果数据快照包含价格、市值、估值倍数、目标价、持仓成本等信息，"
                "可以按 Profile 的分析框架正常使用，并在文字中说明依据来自快照。"
            ),
            (
                "- 输出应围绕商业质量、管理层、护城河、成长质量、风险、反方证据、"
                "估值纪律、安全边际和估值假设建议。"
            ),
            (
                "- 如果快照包含 source_coverage_matrix，应优先说明有证据覆盖的主题；"
                "不要把矩阵中缺失的主题写成确定性结论。"
            ),
            (
                "- 如果快照包含 pre_model_observations，它们是服务层按确定性规则生成的"
                "事实提示，可用于补充风险、缺口和估值假设，但不能替代引用。"
            ),
            (
                "- profile_fit_score 和 confidence 应沿用 fact_ledger 中的规则计算"
                "口径；不要按分析师名气自由打分。二者只是分层估计，不是精确概率。"
            ),
            "- rule_checks 必须覆盖 Profile.rules 中的每条 rule。",
            "- rule_checks[].status 只能是 pass、warn、fail、unknown。",
            "- rule_checks[].summary 是必填字段；不要改名为 reasoning、assessment 或 conclusion。",
            "- supporting_evidence_ids 只能引用数据快照中存在的 external_evidence/evidence id。",
            "- analysis_basis 应概括本次使用的财务期、公告、外部证据和会计事件数量。",
            (
                "- 如果数据快照包含 financial_evidence_pack，应优先用其中的 facts、"
                "metrics、trends、flags 和 data_gaps 形成财务观察、风险和估值假设建议；"
                "引用财务证据仍使用 financial_periods，不要把财务记录写入 evidence_ids。"
            ),
            (
                "- valuation_assumption_suggestions 写给人读的短句；"
                "valuation_assumption_details 写给后续估值模块消费的结构化假设。"
            ),
            (
                "- 如果 fact_ledger.accounting_events 非空，accounting_events 必须"
                "保留这些事件并在 overview、financial_observations 或 risk_flags "
                "中解释可比口径影响。"
            ),
            "- 不要新增事实；需要推断时写明这是基于快照的判断。",
            "- 如果财务、公告或外部证据为空，要把限制写入 data_gaps。",
        ]
    )
