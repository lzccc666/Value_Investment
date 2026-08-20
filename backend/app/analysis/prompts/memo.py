from __future__ import annotations

import json

PROMPT_VERSION = "investment_memo_v3"

MEMO_SYSTEM_PROMPT = """
You are the 009 Investment Memo committee module in a value-investing research system.
Use only the JSON snapshot supplied by the user. Do not search, collect new data,
re-summarize announcements, recalculate financial metrics, read historical memos, or
introduce facts outside the snapshot.

Your job is to combine the latest successful analyst_view runs into one structured
InvestmentMemo. Identify consensus, dissent, key risks, counter-evidence, data gaps,
follow-up questions, and valuation assumption review items.

Hard boundaries:
- Write only fundamental research conclusions and operating or financial assumptions.
- Do not output downstream price-decision content, transaction actions, or position advice.
- 009 must not infer or generate valuation calculation signals. 010 reads structured
  rule statuses directly from the latest successful 008 analyst_view runs.
- Do not output calculated valuation results or numerical investment scores.
- 009 preserves original five-state rule judgments for narrative synthesis only. Do not
  calculate total_score, weighted_score, rule scores, or analyst scores.

Return only valid JSON. Do not wrap the answer in Markdown or code fences.
""".strip()


def build_memo_prompt(
    data_snapshot: dict[str, object],
    *,
    strict_boundary_retry: bool = False,
) -> str:
    retry_instruction = (
        "A previous response crossed the downstream decision boundary. Regenerate from "
        "scratch. Every narrative sentence and assumption_type must describe only business "
        "operations, accounting, cash flow, capital allocation, management, governance, or "
        "industry conditions. Do not discuss or name any excluded downstream concept.\n"
        if strict_boundary_retry
        else ""
    )
    return (
        retry_instruction
        + "Generate a structured JSON object for 009 InvestmentMemo from the snapshot below.\n"
        "Return exactly one top-level JSON object, not wrapped in memo, result, "
        "output, or sections.\n"
        "executive_summary is required even when evidence is limited.\n"
        "research_conclusion must be one of: 优质, 普通, 存疑, 回避, 需复核.\n"
        "price_decision_status must be not_started.\n"
        "valuation_assumption_queue is for 010 review inputs only; every item must be an "
        "operating, accounting, cash-flow, capital-allocation, management, or industry input.\n"
        "Use this top-level JSON shape; use empty arrays or objects when evidence is missing:\n"
        "{\n"
        '  "title": "Investment Memo",\n'
        '  "research_conclusion": "需复核",\n'
        '  "executive_summary": "one paragraph synthesis",\n'
        '  "core_thesis": [],\n'
        '  "consensus_points": [\n'
        "    {\n"
        '      "topic": "topic",\n'
        '      "summary": "consensus summary",\n'
        '      "supporting_profiles": [],\n'
        '      "source_run_ids": [],\n'
        '      "evidence_ids": [],\n'
        '      "announcement_ids": [],\n'
        '      "financial_periods": []\n'
        "    }\n"
        "  ],\n"
        '  "dissent_points": [],\n'
        '  "business_quality": [],\n'
        '  "financial_quality": [],\n'
        '  "management_and_capital_allocation": [],\n'
        '  "moat_and_growth": [],\n'
        '  "key_risks": [],\n'
        '  "counter_evidence": [],\n'
        '  "data_gaps": [],\n'
        '  "follow_up_questions": [],\n'
        '  "valuation_assumption_queue": [\n'
        "    {\n"
        '      "assumption_type": "base_free_cash_flow",\n'
        '      "scenario_bias": "review_only",\n'
        '      "reason": "why this input needs review",\n'
        '      "suggested_range": {},\n'
        '      "needed_inputs": [],\n'
        '      "risk_adjustments": [],\n'
        '      "source_refs": {\n'
        '        "analyst_run_ids": [],\n'
        '        "evidence_ids": [],\n'
        '        "announcement_ids": [],\n'
        '        "financial_periods": []\n'
        "      }\n"
        "    }\n"
        "  ],\n"
        '  "watch_signals": [],\n'
        '  "price_decision_status": "not_started",\n'
        '  "prohibited_actions_note": "This memo does not generate buy, sell, hold, '
        'reduce, add, or position advice; price comparison is reserved for 011.",\n'
        '  "source_map": {\n'
        '    "analyst_run_ids": [],\n'
        '    "evidence_ids": [],\n'
        '    "announcement_ids": [],\n'
        '    "financial_periods": []\n'
        "  },\n"
        '  "confidence_summary": {"level": "medium", "reasons": []}\n'
        "}\n\n"
        f"Data snapshot:\n{json.dumps(data_snapshot, ensure_ascii=False, indent=2, default=str)}"
    )
