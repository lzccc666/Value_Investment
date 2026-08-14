from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "evidence_search_v1"

QUERY_SYSTEM_PROMPT = """你是价值投资研究系统的外部基本面信息搜索规划器。
只生成用于搜索政策驱动、监管信息、政府公开披露数据、交易所/SEC/HKEX 披露、
行业供需公开数据和公司公开披露的 query。
仅做公开资料检索规划，查询主题必须限于外部基本面公开资料。
避免生成常规年报、分红、回购、业绩预告、会议决议等公司公告类 query。
必须返回 JSON：{"queries":["..."]}。
"""

EVIDENCE_SYSTEM_PROMPT = """你是价值投资研究系统的证据结构化助手。
你的任务是判断搜索结果与目标公司/行业是否相关，并把可靠信息结构化为 Evidence。
模型只负责搜索结果相关性判断、摘要、事实提取、影响方向、风险点、待复核问题、分类、重要性评分和可信度评分。
仅结构化公开资料证据，并保留用户最终判断空间。
必须只返回 JSON，不要返回 Markdown。
顶层结构必须是：{"evidences":[...]}。
每个 evidence 必须包含这些字段，不得省略：
source_type,title,source,source_url,published_at,summary,key_facts,impact_direction,
importance_score,credibility_score,tags,requires_review,price_sensitive,use_scope,
analysis_status,analysis_note,raw_snapshot。
"""


def build_query_prompt(
    *,
    company: dict[str, Any],
    keywords: list[str],
    max_queries: int,
) -> str:
    payload = {
        "company": company,
        "keywords": keywords,
        "max_queries": max_queries,
        "requirements": [
            (
                "优先覆盖政策驱动、监管要求、政府公开数据、行业供需公开数据、"
                "社会责任、食品安全、环保、安全生产、反垄断、税务和合规事件。"
            ),
            (
                "query 应包含公司名称或证券代码，也可以包含行业词、政策、监管、"
                "统计、公示、处罚、供需、产量、库存、消费、渠道等词。"
            ),
            (
                "可以补充官方域名词或 site:gov.cn、site:stats.gov.cn、"
                "site:csrc.gov.cn、site:szse.cn、site:cninfo.com.cn、"
                "site:sec.gov、site:hkexnews.hk 等限定，但不要只生成入口页检索。"
            ),
            (
                "query 应尽量指向具体外部事实材料，例如政策文件、监管处罚、公示、"
                "政府统计、产量、库存、供需、渠道、消费、环保、食品安全或社会责任数据。"
            ),
            "query 不要围绕年报发布、分红、回购、业绩预告、会议决议等公告区已有内容。",
            "query 只围绕政策、监管、统计、行业供需和社会公开资料。",
            "query 应适合中文或英文公开网页搜索。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def build_evidence_prompt(
    *,
    company: dict[str, Any],
    search_results: list[dict[str, Any]],
) -> str:
    payload = {
        "company": company,
        "search_results": search_results,
        "schema": {
            "source_type": [
                "policy",
                "industry_news",
                "company_news",
                "public_data",
                "regulatory",
                "web",
            ],
            "impact_direction": ["positive", "neutral", "negative", "mixed", "unknown"],
            "score_range": "importance_score 和 credibility_score 必须在 0 到 1 之间",
            "analysis_status": ["model_analyzed"],
            "use_scope": [
                "fundamental_analysis",
                "analyst_view",
                "intrinsic_valuation",
            ],
            "required_fields": [
                "source_type",
                "title",
                "source",
                "source_url",
                "published_at",
                "summary",
                "key_facts",
                "impact_direction",
                "importance_score",
                "credibility_score",
                "tags",
                "requires_review",
                "price_sensitive",
                "use_scope",
                "analysis_status",
                "analysis_note",
                "raw_snapshot",
            ],
        },
        "example": {
            "evidences": [
                {
                    "source_type": "regulatory",
                    "title": "示例标题，必须来自搜索结果标题或原始网页标题",
                    "source": "example.com",
                    "source_url": "https://example.com/source-page",
                    "published_at": None,
                    "summary": "中文摘要，说明这条信息本身以及它可能影响的研究问题。",
                    "key_facts": ["只写可从搜索结果直接支持的事实"],
                    "impact_direction": "unknown",
                    "importance_score": 0.5,
                    "credibility_score": 0.6,
                    "tags": ["待复核"],
                    "requires_review": True,
                    "price_sensitive": False,
                    "use_scope": [
                        "fundamental_analysis",
                        "analyst_view",
                        "intrinsic_valuation",
                    ],
                    "analysis_status": "model_analyzed",
                    "analysis_note": "说明评分依据和仍需复核的点。",
                    "raw_snapshot": {
                        "query": "原始 query",
                        "title": "原始标题",
                        "source": "example.com",
                        "url": "https://example.com/source-page",
                        "snippet": "原始摘要片段",
                        "page_snapshot": {
                            "page_title": "抓取到的网页标题",
                            "page_description": "抓取到的网页描述",
                            "content_excerpt": "抓取到的网页正文摘录",
                            "content_fetched_at": "抓取时间",
                        },
                    },
                }
            ]
        },
        "rules": [
            "只保留与目标公司基本面、政策驱动、监管约束、政府公开数据、行业供需数据或社会公开事件直接相关的信息。",
            (
                "不要把常规财报和公告区已有内容结构化为外部信息 Evidence，"
                "例如年报、季报、半年报、分红派息、回购、业绩预告、会议决议、"
                "投资者关系活动记录、会计师事务所续聘等。"
            ),
            (
                "按内容筛选，而不是按网站名称筛选；公司官网、媒体、社区长文、百科或行业文章"
                "如果提供可复核的基本面事实、公开数据或披露线索，可以结构化为 Evidence。"
            ),
            (
                "如果来源不是原始公告、监管文件、政府数据或交易所/SEC/HKEX 披露，"
                "但内容引用了这些原始材料，必须 requires_review=true，并在 analysis_note 中写明"
                "需要追到原始公告或数据源复核。"
            ),
            (
                "如果内容主要是报价、盘口、图形指标、资金流、社区短评、二级市场评级或"
                "短期交易观点，不要生成 Evidence，返回空 evidences 或跳过该结果。"
            ),
            (
                "符合上述范围的基本面资料默认 price_sensitive=false，use_scope 包含 "
                "fundamental_analysis、analyst_view、intrinsic_valuation；"
                "不符合上述范围时返回空 evidences。"
            ),
            (
                "摘要和 key_facts 必须优先依据 page_snapshot.content_excerpt；如果没有正文摘录，"
                "再依据搜索结果 title/snippet，并在 analysis_note 中说明。"
            ),
            (
                "如果搜索结果只是入口页、列表页或信息不足，只能给 unknown/mixed "
                "和较低分，并 requires_review=true。"
            ),
            (
                "不要把搜索结果标题改写成未经正文支持的具体事实；"
                "无法从内容确认的信息必须写入 requires_review 或 analysis_note。"
            ),
            "summary 用中文，简洁说明信息内容及它可能影响的研究问题。",
            "key_facts 只写可复核事实。",
            (
                "importance_score 表示对研究判断的重要性，credibility_score "
                "表示来源和信息可信度；analysis_note 必须解释评分理由。"
            ),
            "不确定、来源不清、发布时间缺失或需要原文核对时 requires_review=true。",
            "raw_snapshot 至少保留 query、title、source、url、snippet 等原始线索。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
