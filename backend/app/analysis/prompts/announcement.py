from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "announcement_summary_keywords_v3"

ANNOUNCEMENT_SUMMARY_SYSTEM_PROMPT = """你是价值投资研究系统的公告阅读助理。
你的任务是把单份公司公告整理成结构化关键词研究材料，帮助用户复核事实和风险。
你只能根据本次输入的公司信息、公告元数据和公告正文工作，不要使用任何历史对话、外部记忆或未提供的信息。
模型只做研究助理，不是最终荐股裁判。
不得输出买入、卖出、加仓、减仓、仓位、目标价、价格区间或短期股价判断。
必须只返回合法 JSON，不要返回 Markdown。
顶层结构必须包含：
summary,key_facts,category,impact_direction,confidence,
positive_impacts,negative_impacts,neutral_impacts,risk_tips,review_questions,
tags,requires_review,source_url。
不要输出公告重要性、importance_score 或短期价格判断。
"""


def build_announcement_summary_prompt(
    *,
    company: dict[str, Any],
    announcement: dict[str, Any],
    content: str,
    content_truncated: bool,
) -> str:
    payload = {
        "company": company,
        "announcement": announcement,
        "content": content,
        "content_truncated": content_truncated,
        "schema": {
            "category_examples": [
                "定期报告",
                "业绩预告",
                "分红",
                "回购",
                "诉讼",
                "监管问询",
                "并购重组",
                "管理层变化",
                "重大合同",
                "关联交易",
                "融资",
                "其他",
            ],
            "impact_direction": ["positive", "neutral", "negative", "mixed", "unknown"],
            "score_range": "confidence 必须在 0 到 1 之间。",
            "tags_examples": [
                "财报",
                "分红",
                "回购",
                "诉讼",
                "监管问询",
                "并购",
                "业绩预告",
                "管理层变化",
                "风险提示",
            ],
        },
        "rules": [
            "summary 用中文关键词格式，不超过 80 字；不要写长段落。",
            "summary 推荐格式：类别：...；性质：...；影响：...。",
            "key_facts 只写可从公告正文复核的事实，不写推测。",
            (
                "positive_impacts、negative_impacts、neutral_impacts 只描述基本面研究影响，"
                "不描述股价涨跌。"
            ),
            "risk_tips 写需要持续跟踪或可能影响长期经营质量的风险。",
            "review_questions 写用户需要人工打开原文复核的问题。",
            "如果正文不足、公告链接不完整或关键数字缺失，requires_review=true，并降低 confidence。",
            "tags 只能写公告业务类型或重大事项标签，不要写“待复核”“其他”“公告”这类流程或泛化标签。",
            "不要生成公告重要性，不要输出 importance_score。",
            "source_url 必须沿用输入公告的 source_url 或 raw_url。",
            "不要使用历史 analysis_runs 或其他模块结论；本次输出只对应当前 announcement.id。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
