from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelOutputValidationError,
)
from app.analysis.prompts.evidence import (
    EVIDENCE_SYSTEM_PROMPT,
    PROMPT_VERSION,
    QUERY_SYSTEM_PROMPT,
    build_evidence_prompt,
    build_query_prompt,
)
from app.data_sources.web_search_provider import (
    AShareCompanyDisclosureSearchProvider,
    CompositeWebSearchProvider,
    HttpWebPageSnapshotFetcher,
    WebPageSnapshotFetcher,
    WebSearchError,
    WebSearchProvider,
)
from app.db.models import AnalysisRun, Announcement, Company, Evidence
from app.schemas.evidence import (
    EvidenceExtractionOutput,
    EvidenceModelOutput,
    EvidenceSearchRequest,
    EvidenceUseScope,
    ModelSmokeTestOutput,
    SearchQueryPlan,
)

DEFAULT_FUNDAMENTAL_USE_SCOPE: list[EvidenceUseScope] = [
    "fundamental_analysis",
    "analyst_view",
    "intrinsic_valuation",
]

MAX_MODEL_SEARCH_RESULTS = 10

FUNDAMENTAL_SUBSTANTIVE_PATTERNS = (
    "政策",
    "监管",
    "处罚",
    "行政许可",
    "问询函",
    "监管函",
    "年报",
    "年度报告",
    "半年报",
    "半年度报告",
    "季度报告",
    "定期报告",
    "公告",
    "披露",
    "公开数据",
    "统计",
    "产量",
    "销量",
    "产能",
    "库存",
    "供需",
    "需求",
    "消费",
    "渠道",
    "经销商",
    "行业",
    "产业",
    "财报",
    "财务",
    "经营",
    "营收",
    "收入",
    "利润",
    "毛利",
    "现金流",
    "税收",
    "成本",
    "招股书",
    "审计",
    "重述",
    "诉讼",
    "召回",
    "安全生产",
    "环保",
    "反垄断",
    "public data",
    "regulation",
    "regulatory",
    "policy",
    "filing",
    "annual report",
    "10-k",
    "10-q",
    "8-k",
    "disclosure",
    "supply",
    "demand",
    "capacity",
    "inventory",
    "production",
    "revenue",
    "profit",
    "cash flow",
)

COMPANY_DISCLOSURE_DUPLICATE_PATTERNS = (
    "年度报告",
    "年报",
    "半年报",
    "半年度报告",
    "季度报告",
    "一季度报告",
    "三季度报告",
    "定期报告",
    "财报",
    "财务报告",
    "年度财务报告",
    "年度报告摘要",
    "业绩预告",
    "业绩快报",
    "分红",
    "派息",
    "利润分配",
    "权益分派",
    "回购",
    "股东大会",
    "股东会",
    "董事会",
    "监事会",
    "会议决议",
    "法律意见书",
    "法律意见",
    "律师事务所",
    "表决程序",
    "出席会议人员资格",
    "董事会秘书",
    "投资者关系活动记录",
    "投资者关系活动记录表",
    "独立董事",
    "审计报告",
    "会计师事务所",
    "内部控制",
    "公司章程",
    "定期报告披露",
    "annual report",
    "quarterly report",
    "interim report",
    "dividend",
    "share repurchase",
)

OFFICIAL_SOURCE_PATTERNS = (
    ".gov",
    "gov.cn",
    "stats.gov.cn",
    "csrc.gov.cn",
    "ndrc.gov.cn",
    "miit.gov.cn",
    "mof.gov.cn",
    "pbc.gov.cn",
    "samr.gov.cn",
    "mee.gov.cn",
    "sse.com.cn",
    "szse.cn",
    "cninfo.com.cn",
    "hkexnews.hk",
    "sfc.hk",
    "sec.gov",
    "bea.gov",
    "bls.gov",
)

SECONDARY_SOURCE_PATTERNS = (
    "baike.baidu.com",
    "百科",
    "wikipedia.org",
    "维基百科",
    "xueqiu.com",
    "雪球",
    "zhihu.com",
    "知乎",
)

FALLBACK_FUNDAMENTAL_PATTERNS = (
    "监管函",
    "问询函",
    "关注函",
    "处罚",
    "行政监管",
    "监管措施",
    "整改",
    "环保",
    "安全生产",
    "食品安全",
    "诉讼",
    "仲裁",
    "合规",
    "反垄断",
    "召回",
    "行政许可",
    "公开数据",
    "统计",
    "产量",
    "销量",
    "库存",
    "供需",
    "消费",
    "渠道",
    "行业政策",
    "政策",
    "public data",
    "regulatory",
    "regulation",
    "penalty",
    "compliance",
    "supply",
    "demand",
    "inventory",
    "production",
)

LOCAL_ANNOUNCEMENT_LEAD_PATTERNS = (
    "监管函",
    "问询函",
    "关注函",
    "处罚",
    "行政监管",
    "监管措施",
    "整改",
    "环保",
    "安全生产",
    "食品安全",
    "诉讼",
    "仲裁",
    "合规",
    "反垄断",
    "召回",
    "行政许可",
    "重大事项",
    "重大诉讼",
    "重大仲裁",
    "重大风险",
    "风险提示",
    "信息披露",
    "减值",
    "担保",
    "关联交易",
    "合同",
    "经营",
    "产能",
    "渠道",
    "经销商",
)

LIQUOR_INDUSTRY_TERMS = (
    "白酒",
    "浓香型白酒",
    "高端白酒",
    "酒类",
    "酒类流通",
    "酒业",
)

LIQUOR_COMPANY_ALIASES = {
    "五粮液": ("五粮液集团", "宜宾五粮液"),
    "贵州茅台": ("茅台集团", "贵州茅台酒"),
}


def get_model_config_status(gateway: ModelGateway | None = None) -> dict[str, object]:
    model_gateway = gateway or ModelGateway()
    return model_gateway.status()


def run_model_smoke_test(gateway: ModelGateway | None = None) -> dict[str, object]:
    model_gateway = gateway or ModelGateway()
    output = model_gateway.generate_structured(
        system_prompt=(
            "你是模型连通性自检器。只输出合法 JSON，不要输出 Markdown。"
        ),
        user_prompt=(
            '请返回 {"ok": true, "message": "model gateway ok"}，'
            "用于验证 API key、base_url、model_name 和 JSON 输出能力。"
        ),
        schema=ModelSmokeTestOutput,
        temperature=0,
    )
    return {
        **model_gateway.status(),
        "ok": output.ok,
        "message": output.message,
    }


def list_company_evidence(
    session: Session, company_id: int, limit: int = 20, offset: int = 0
) -> tuple[list[Evidence], int]:
    base_stmt = select(Evidence).where(Evidence.company_id == company_id)
    total_stmt = select(func.count()).select_from(Evidence).where(
        Evidence.company_id == company_id
    )

    items = session.scalars(
        base_stmt.order_by(
            Evidence.published_at.desc().nullslast(),
            Evidence.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.scalar(total_stmt) or 0
    return items, total


def get_evidence(session: Session, evidence_id: int) -> Evidence | None:
    return session.get(Evidence, evidence_id)


def mark_evidence_reviewed(session: Session, evidence: Evidence) -> Evidence:
    evidence.requires_review = False
    session.commit()
    session.refresh(evidence)
    return evidence


def delete_evidence(session: Session, evidence: Evidence) -> int:
    evidence_id = evidence.id
    session.delete(evidence)
    session.commit()
    return evidence_id


def search_company_evidence(
    session: Session,
    company: Company,
    payload: EvidenceSearchRequest,
    *,
    gateway: ModelGateway | None = None,
    search_provider: WebSearchProvider | None = None,
    fallback_search_provider: WebSearchProvider | None = None,
    page_fetcher: WebPageSnapshotFetcher | None = None,
) -> tuple[list[Evidence], AnalysisRun]:
    model_gateway = gateway or ModelGateway()
    provider = search_provider or CompositeWebSearchProvider()
    fallback_provider = fallback_search_provider or _default_fallback_search_provider(
        provider=provider,
        search_provider_was_injected=search_provider is not None,
    )
    snapshot_fetcher = (
        page_fetcher
        if page_fetcher is not None
        else HttpWebPageSnapshotFetcher()
        if search_provider is None
        else None
    )
    company_snapshot = _company_snapshot(company)
    input_snapshot = {
        "company": company_snapshot,
        "keywords": payload.keywords,
        "max_results": payload.max_results,
        "source_policy": (
            "007 external evidence search prioritizes policy, regulatory, government "
            "public data, exchange/company disclosure, and fundamental industry sources; "
            "it filters quotes, technical analysis, stock forums, recommendation articles, "
            "capital-flow pages, and price-only market pages."
        ),
    }
    run = _create_search_run(
        session,
        company_id=company.id,
        model_name=model_gateway.model_name,
        input_snapshot=input_snapshot,
    )

    executed_queries: list[str] = []

    try:
        try:
            query_plan = model_gateway.generate_structured(
                system_prompt=QUERY_SYSTEM_PROMPT,
                user_prompt=build_query_prompt(
                    company=company_snapshot,
                    keywords=payload.keywords,
                    max_queries=4,
                ),
                schema=SearchQueryPlan,
                temperature=0.2,
            )
        except (ModelGatewayError, ModelOutputValidationError, ValueError):
            query_plan = SearchQueryPlan(
                queries=_expand_queries([], company, payload.keywords)[:4]
            )
        executed_queries = _expand_queries(query_plan.queries, company, payload.keywords)
        raw_results, search_stats = _collect_search_results(
            provider,
            company=company,
            queries=executed_queries,
            limit_per_query=payload.max_results,
            page_fetcher=snapshot_fetcher,
        )
        if not raw_results and fallback_provider is not None:
            fallback_queries = _build_fallback_queries(company, payload.keywords)
            fallback_results, fallback_stats = _collect_search_results(
                fallback_provider,
                company=company,
                queries=fallback_queries,
                limit_per_query=payload.max_results,
                page_fetcher=snapshot_fetcher,
                fallback_only=True,
            )
            executed_queries = [*executed_queries, *fallback_queries]
            search_stats = _merge_search_stats(search_stats, fallback_stats)
            raw_results = fallback_results
        else:
            search_stats = _with_no_fallback_stats(search_stats)

        if not raw_results:
            deterministic_leads, lead_stats = _build_deterministic_search_leads(
                session,
                company=company,
                keywords=payload.keywords,
            )
            if deterministic_leads and search_stats.get("fallback_triggered"):
                search_stats = _with_deterministic_lead_stats(
                    search_stats,
                    lead_stats=lead_stats,
                )
                evidence_items = _create_fallback_evidence_items(
                    session, company.id, deterministic_leads
                )
                _complete_search_run(
                    session,
                    run,
                    queries=executed_queries,
                    raw_results=deterministic_leads,
                    search_stats=search_stats,
                    evidence_items=evidence_items,
                    fallback_reason=_no_candidate_message(search_stats),
                )
                return evidence_items, run
            raise EvidenceSearchError(_no_candidate_message(search_stats))
        extraction = model_gateway.generate_structured(
            system_prompt=EVIDENCE_SYSTEM_PROMPT,
            user_prompt=build_evidence_prompt(
                company=company_snapshot,
                search_results=raw_results,
            ),
            schema=EvidenceExtractionOutput,
            temperature=0.1,
        )
        evidence_items = _create_evidence_items(session, company.id, extraction.evidences)
        _complete_search_run(
            session,
            run,
            queries=executed_queries,
            raw_results=raw_results,
            search_stats=search_stats,
            evidence_items=evidence_items,
        )
        return evidence_items, run
    except (ModelOutputValidationError, ModelGatewayError) as exc:
        if isinstance(exc, ModelOutputValidationError):
            repaired = _try_repair_evidence_output(
                model_gateway=model_gateway,
                company_snapshot=company_snapshot,
                raw_results=locals().get("raw_results", []),
                validation_error=exc,
            )
            if repaired is not None:
                evidence_items = _create_evidence_items(
                    session, company.id, repaired.evidences
                )
                fallback_query_plan = locals().get("query_plan")
                repaired_queries = (
                    fallback_query_plan.queries
                    if isinstance(fallback_query_plan, SearchQueryPlan)
                    else []
                )
                _complete_search_run(
                    session,
                    run,
                    queries=executed_queries or repaired_queries,
                    raw_results=locals().get("raw_results", []),
                    search_stats=locals().get("search_stats"),
                    evidence_items=evidence_items,
                )
                return evidence_items, run

        if (
            isinstance(exc, ModelGatewayError)
            and not isinstance(exc, ModelOutputValidationError)
            and "HTTP 504" not in str(exc)
        ):
            _fail_search_run(
                session,
                run,
                exc,
                search_stats=locals().get("search_stats"),
            )
            raise
        raw_results = locals().get("raw_results", [])
        if not isinstance(raw_results, list) or not raw_results:
            _fail_search_run(
                session,
                run,
                exc,
                search_stats=locals().get("search_stats"),
            )
            raise
        evidence_items = _create_fallback_evidence_items(session, company.id, raw_results)
        fallback_query_plan = locals().get("query_plan")
        fallback_queries = (
            fallback_query_plan.queries
            if isinstance(fallback_query_plan, SearchQueryPlan)
            else []
        )
        _complete_search_run(
            session,
            run,
            queries=executed_queries or fallback_queries,
            raw_results=raw_results,
            search_stats=locals().get("search_stats"),
            evidence_items=evidence_items,
            fallback_reason=str(exc),
        )
        return evidence_items, run
    except Exception as exc:
        _fail_search_run(
            session,
            run,
            exc,
            search_stats=locals().get("search_stats"),
        )
        raise


def _create_search_run(
    session: Session,
    *,
    company_id: int,
    model_name: str | None,
    input_snapshot: dict[str, object],
) -> AnalysisRun:
    run = AnalysisRun(
        company_id=company_id,
        run_type="evidence_search",
        analyst_profile="evidence_search",
        run_version="007_v1",
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        input_snapshot=input_snapshot,
        result={},
        status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _complete_search_run(
    session: Session,
    run: AnalysisRun,
    *,
    queries: list[str],
    raw_results: list[dict[str, object]],
    search_stats: dict[str, object] | None = None,
    evidence_items: list[Evidence],
    fallback_reason: str | None = None,
) -> None:
    stats = search_stats or {}
    filtered_out_count = int(stats.get("filtered_out_count") or 0)
    run.status = "success"
    run.result = {
        "queries": queries,
        "raw_result_count": len(raw_results),
        "filtered_out_count": filtered_out_count,
        "created_evidence_ids": [item.id for item in evidence_items],
        "created_evidence_count": len(evidence_items),
        "search_stats": stats,
    }
    if fallback_reason:
        run.result["fallback_reason"] = fallback_reason
        run.status = "partial"
    session.commit()
    session.refresh(run)


def _fail_search_run(
    session: Session,
    run: AnalysisRun,
    exc: Exception,
    *,
    search_stats: dict[str, object] | None = None,
) -> None:
    run.status = "failed"
    run.result = {
        "error": str(exc),
        "error_type": exc.__class__.__name__,
    }
    if search_stats is not None:
        run.result["search_stats"] = search_stats
    session.commit()
    session.refresh(run)


def _default_fallback_search_provider(
    *,
    provider: WebSearchProvider,
    search_provider_was_injected: bool,
) -> WebSearchProvider | None:
    if search_provider_was_injected:
        return None

    providers: list[WebSearchProvider] = []
    providers.append(AShareCompanyDisclosureSearchProvider(years=3))
    if isinstance(provider, CompositeWebSearchProvider):
        providers.extend(provider.providers)
    else:
        providers.append(provider)
    return CompositeWebSearchProvider(providers=providers)


def _build_fallback_queries(company: Company, keywords: list[str]) -> list[str]:
    queries: list[str] = []
    ticker_code = company.ticker.split(".", maxsplit=1)[0] if company.ticker else ""
    company_terms = [company.name, ticker_code or company.ticker]
    company_query_prefix = " ".join(term for term in company_terms if term)

    if company_query_prefix:
        _append_unique(queries, f"{company_query_prefix} 监管函 问询函 site:sse.com.cn")
        _append_unique(queries, f"{company_query_prefix} 监管 处罚 site:cninfo.com.cn")
        _append_unique(queries, f"{company_query_prefix} 行政处罚 食品安全 市场监督管理局")
        _append_unique(queries, f"{company_query_prefix} 环保 安全生产 整改")
        _append_unique(queries, f"{company_query_prefix} 合规 诉讼 监管")

    if company.industry:
        _append_unique(queries, f"{company.industry} 产量 消费 库存 国家统计局")
        _append_unique(queries, f"{company.industry} 行业 政策 监管 供需")
        _append_unique(queries, f"{company.industry} 行业 公开数据 产量 库存 消费")

    for keyword in keywords:
        if keyword.strip() and company_query_prefix:
            _append_unique(queries, f"{company_query_prefix} {keyword} 监管 公开数据")

    return queries


def _build_official_fallback_leads(
    company: Company, keywords: list[str]
) -> list[dict[str, object]]:
    ticker_code = company.ticker.split(".", maxsplit=1)[0] if company.ticker else ""
    company_query_prefix = " ".join(
        term for term in (company.name, ticker_code or company.ticker) if term
    )
    if not company_query_prefix:
        return []

    note = (
        "通用搜索和 A 股定向外部事实 fallback 均未形成可送模型候选；"
        "系统保留官方追溯路径作为 search_lead，需人工打开来源检索原始监管文件、"
        "政府公开数据或行业公开数据后复核。"
    )
    leads = [
        {
            "query": f"{company_query_prefix} 监管函 问询函",
            "title": f"{company.name} 监管函与问询函官方追溯线索",
            "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            "source": "www.sse.com.cn",
            "snippet": (
                f"用于按证券代码 {ticker_code or company.ticker} 追溯监管函、问询函、"
                "关注函、整改等交易所公开披露。"
            ),
            "analysis_note": note,
        },
        {
            "query": f"{company_query_prefix} 监管 处罚 公示",
            "title": f"{company.name} 监管处罚与公示官方追溯线索",
            "url": "https://www.cninfo.com.cn/new/index",
            "source": "www.cninfo.com.cn",
            "snippet": "用于按证券代码追溯监管、处罚、公示、整改和重大事项公开披露。",
            "analysis_note": note,
        },
        {
            "query": f"{company_query_prefix} 食品安全 行政处罚 市场监督管理局",
            "title": f"{company.name} 食品安全与行政处罚追溯线索",
            "url": "https://www.samr.gov.cn/",
            "source": "www.samr.gov.cn",
            "snippet": "用于追溯食品安全、行政处罚、市场监管和合规公开信息。",
            "analysis_note": note,
        },
    ]
    if company.industry:
        leads.extend(
            [
                {
                    "query": f"{company.industry} 产量 消费 库存 国家统计局",
                    "title": f"{company.industry} 行业公开数据追溯线索",
                    "url": "https://data.stats.gov.cn/",
                    "source": "data.stats.gov.cn",
                    "snippet": "用于追溯行业产量、消费、库存、供需和宏观统计公开数据。",
                    "analysis_note": note,
                },
                {
                    "query": f"{company.industry} 行业 政策 监管 供需",
                    "title": f"{company.industry} 政策监管与供需线索",
                    "url": "https://www.miit.gov.cn/",
                    "source": "www.miit.gov.cn",
                    "snippet": "用于追溯行业政策、监管要求、供需变化和产业公开信息。",
                    "analysis_note": note,
                },
            ]
        )
    for keyword in keywords:
        if keyword.strip():
            leads.append(
                {
                    "query": f"{company_query_prefix} {keyword} 监管 公开数据",
                    "title": f"{company.name} {keyword} 公开资料追溯线索",
                    "url": "https://www.gov.cn/",
                    "source": "www.gov.cn",
                    "snippet": f"用于追溯 {keyword} 相关政策、监管、政府公开数据和行业公开信息。",
                    "analysis_note": note,
                }
            )
    return leads[:5]


def _build_deterministic_search_leads(
    session: Session,
    *,
    company: Company,
    keywords: list[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    local_leads = _build_local_announcement_search_leads(session, company)
    seed_leads = _build_seed_source_leads(company, keywords)
    final_leads = _build_official_fallback_leads(company, keywords)

    leads: list[dict[str, object]] = []
    for source_leads in (local_leads, seed_leads, final_leads):
        for lead in source_leads:
            dedupe_key = _search_result_dedupe_key(lead)
            if any(_search_result_dedupe_key(item) == dedupe_key for item in leads):
                continue
            leads.append(lead)
            if len(leads) >= 5:
                break
        if len(leads) >= 5:
            break

    fallback_stage = None
    if local_leads:
        fallback_stage = "local_announcement"
    elif seed_leads:
        fallback_stage = "seed_source"
    elif final_leads:
        fallback_stage = "final_search_lead"

    return leads, {
        "fallback_stage": fallback_stage,
        "local_announcement_lead_count": len(local_leads),
        "seed_source_lead_count": len(seed_leads),
        "final_search_lead_count": len(final_leads) if not local_leads and not seed_leads else 0,
        "final_search_lead_triggered": bool(final_leads and not local_leads and not seed_leads),
        "final_search_lead_queries": _string_list(
            [lead.get("query") for lead in final_leads]
        ),
    }


def _build_local_announcement_search_leads(
    session: Session,
    company: Company,
) -> list[dict[str, object]]:
    announcements = session.scalars(
        select(Announcement)
        .where(Announcement.company_id == company.id)
        .order_by(Announcement.published_at.desc())
        .limit(80)
    ).all()
    leads: list[dict[str, object]] = []
    for announcement in announcements:
        if not _is_local_announcement_lead_candidate(announcement):
            continue
        leads.append(_local_announcement_lead_snapshot(company, announcement))
        if len(leads) >= 5:
            break
    return leads


def _is_local_announcement_lead_candidate(announcement: Announcement) -> bool:
    snapshot = {
        "title": announcement.title,
        "source": announcement.source,
        "url": announcement.source_url,
        "snippet": _join_text_parts(
            announcement.category,
            announcement.summary,
            announcement.key_facts,
            announcement.tags,
            announcement.risk_tips,
            announcement.review_questions,
        ),
    }
    if _is_company_disclosure_duplicate(snapshot):
        return False
    if _is_price_sensitive_search_result(snapshot):
        return False

    text = _search_content_text(snapshot)
    return any(pattern in text for pattern in LOCAL_ANNOUNCEMENT_LEAD_PATTERNS)


def _local_announcement_lead_snapshot(
    company: Company,
    announcement: Announcement,
) -> dict[str, object]:
    source_url = announcement.source_url or announcement.raw_url
    published_at = (
        announcement.published_at.isoformat()
        if announcement.published_at is not None
        else None
    )
    return {
        "query": f"{company.name} {announcement.title} 原文复核",
        "title": announcement.title,
        "url": source_url,
        "source": announcement.source or "local_announcement",
        "snippet": _truncate_lead_text(
            announcement.summary
            or _join_text_parts(announcement.key_facts)
            or announcement.title,
            max_length=360,
        ),
        "published_at": published_at,
        "local_announcement_id": announcement.id,
        "local_announcement_category": announcement.category,
        "analysis_note": (
            "确定性 fallback 线索：来自 006 已入库公告中的监管、重大事项、"
            "诉讼、环保、食品安全、安全生产或处罚类线索。007 仅保留为 "
            "search_lead，需要人工追到原始公告、监管文件或政府公开数据复核。"
        ),
    }


def _build_seed_source_leads(
    company: Company,
    keywords: list[str],
) -> list[dict[str, object]]:
    aliases = _company_semantic_aliases(company)
    industry_terms = _industry_semantic_terms(company)
    query_prefix = " ".join(
        term
        for term in (
            company.name,
            company.ticker.split(".", maxsplit=1)[0] if company.ticker else "",
        )
        if term
    )
    note = (
        "确定性 fallback 线索：来自行业/官方种子源，需要人工追到原始政策、"
        "监管文件、政府公开数据或行业公开数据复核；本条不是模型结构化结论。"
    )

    leads: list[dict[str, object]] = []
    for alias in aliases[:3]:
        leads.append(
            {
                "query": f"{alias} 食品安全 行政处罚 市场监管",
                "title": f"{alias} 食品安全与市场监管追溯线索",
                "url": "https://www.samr.gov.cn/",
                "source": "www.samr.gov.cn",
                "snippet": f"用于追溯 {alias} 食品安全、行政处罚、市场监管和合规公开信息。",
                "analysis_note": note,
            }
        )

    if query_prefix:
        leads.append(
            {
                "query": f"{query_prefix} 渠道 经销商 库存 监管",
                "title": f"{company.name} 渠道治理与经销商体系追溯线索",
                "url": "https://www.gov.cn/",
                "source": "www.gov.cn",
                "snippet": "用于追溯渠道治理、经销商体系、库存、流通监管和地方政策公开信息。",
                "analysis_note": note,
            }
        )

    for industry_term in industry_terms[:4]:
        leads.extend(
            [
                {
                    "query": f"{industry_term} 产量 消费 库存 国家统计局",
                    "title": f"{industry_term} 产量消费库存公开数据追溯线索",
                    "url": "https://data.stats.gov.cn/",
                    "source": "data.stats.gov.cn",
                    "snippet": f"用于追溯 {industry_term} 产量、消费、库存和供需统计公开数据。",
                    "analysis_note": note,
                },
                {
                    "query": f"{industry_term} 消费税 产业政策 监管",
                    "title": f"{industry_term} 消费税与产业政策追溯线索",
                    "url": "https://www.mof.gov.cn/",
                    "source": "www.mof.gov.cn",
                    "snippet": f"用于追溯 {industry_term} 消费税、产业政策和监管政策公开信息。",
                    "analysis_note": note,
                },
                {
                    "query": f"{industry_term} 行业 政策 监管 供需",
                    "title": f"{industry_term} 行业政策监管与供需追溯线索",
                    "url": "https://www.miit.gov.cn/",
                    "source": "www.miit.gov.cn",
                    "snippet": (
                        f"用于追溯 {industry_term} 行业政策、监管要求、"
                        "供需变化和产业公开信息。"
                    ),
                    "analysis_note": note,
                },
            ]
        )

    for keyword in keywords:
        normalized = keyword.strip()
        if normalized and query_prefix:
            leads.append(
                {
                    "query": f"{query_prefix} {normalized} 政策 监管 公开数据",
                    "title": f"{company.name} {normalized} 官方资料追溯线索",
                    "url": "https://www.gov.cn/",
                    "source": "www.gov.cn",
                    "snippet": (
                        f"用于追溯 {normalized} 相关政策、监管、"
                        "政府公开数据和行业公开信息。"
                    ),
                    "analysis_note": note,
                }
            )

    return _dedupe_leads(leads)[:5]


def _company_semantic_aliases(company: Company) -> list[str]:
    aliases: list[str] = []
    for value in (company.name,):
        if value:
            _append_unique(aliases, value)
            for key, values in LIQUOR_COMPANY_ALIASES.items():
                if key in value:
                    for alias in values:
                        _append_unique(aliases, alias)
    return aliases


def _industry_semantic_terms(company: Company) -> list[str]:
    terms: list[str] = []
    if company.industry:
        _append_unique(terms, company.industry)
    text = _join_text_parts(company.name, company.industry, company.description, company.tags)
    if any(term in text for term in LIQUOR_INDUSTRY_TERMS):
        for term in LIQUOR_INDUSTRY_TERMS:
            _append_unique(terms, term)
        for term in ("食品安全", "市场监管", "渠道库存", "产量 消费 税收"):
            _append_unique(terms, term)
    return terms


def _dedupe_leads(leads: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for lead in leads:
        key = _search_result_dedupe_key(lead)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(lead)
    return deduped


def _with_no_fallback_stats(stats: dict[str, object]) -> dict[str, object]:
    stats["fallback_stage"] = None
    stats["fallback_triggered"] = False
    stats["fallback_candidate_count"] = 0
    stats["local_announcement_lead_count"] = 0
    stats["seed_source_lead_count"] = 0
    stats["final_search_lead_triggered"] = False
    stats["final_search_lead_count"] = 0
    stats["final_search_lead_queries"] = []
    stats["fallback_queries"] = []
    stats["no_candidate_reason"] = (
        _no_candidate_reason(stats)
        if int(stats.get("sent_to_model_count") or 0) <= 0
        else None
    )
    return stats


def _with_deterministic_lead_stats(
    stats: dict[str, object],
    *,
    lead_stats: dict[str, object],
) -> dict[str, object]:
    local_count = int(lead_stats.get("local_announcement_lead_count") or 0)
    seed_count = int(lead_stats.get("seed_source_lead_count") or 0)
    final_count = int(lead_stats.get("final_search_lead_count") or 0)
    stats["fallback_stage"] = lead_stats.get("fallback_stage")
    stats["fallback_candidate_count"] = local_count + seed_count + final_count
    stats["local_announcement_lead_count"] = local_count
    stats["seed_source_lead_count"] = seed_count
    stats["final_search_lead_triggered"] = bool(
        lead_stats.get("final_search_lead_triggered")
    )
    stats["final_search_lead_count"] = final_count
    stats["final_search_lead_queries"] = _string_list(
        lead_stats.get("final_search_lead_queries")
    )
    stats["no_candidate_reason"] = _no_candidate_reason(stats)
    return stats


def _merge_search_stats(
    primary_stats: dict[str, object],
    fallback_stats: dict[str, object],
) -> dict[str, object]:
    merged_filtered = _merge_filtered_reasons(
        primary_stats.get("filtered_out_by_reason"),
        fallback_stats.get("filtered_out_by_reason"),
    )
    merged = {
        "queries": [
            *_string_list(primary_stats.get("queries")),
            *_string_list(fallback_stats.get("queries")),
        ],
        "query_count": int(primary_stats.get("query_count") or 0)
        + int(fallback_stats.get("query_count") or 0),
        "provider_result_count": int(primary_stats.get("provider_result_count") or 0)
        + int(fallback_stats.get("provider_result_count") or 0),
        "deduped_result_count": int(primary_stats.get("deduped_result_count") or 0)
        + int(fallback_stats.get("deduped_result_count") or 0),
        "candidate_before_ranking_count": int(
            fallback_stats.get("candidate_before_ranking_count") or 0
        ),
        "sent_to_model_count": int(fallback_stats.get("sent_to_model_count") or 0),
        "model_candidate_limit": MAX_MODEL_SEARCH_RESULTS,
        "filtered_out_count": sum(merged_filtered.values()),
        "filtered_out_by_reason": merged_filtered,
        "query_errors": [
            *_dict_list(primary_stats.get("query_errors")),
            *_dict_list(fallback_stats.get("query_errors")),
        ],
        "provider_stats": [
            *_dict_list(primary_stats.get("provider_stats")),
            *_dict_list(fallback_stats.get("provider_stats")),
        ],
        "fallback_triggered": True,
        "fallback_candidate_count": int(fallback_stats.get("sent_to_model_count") or 0),
        "fallback_stage": "a_share_disclosure"
        if int(fallback_stats.get("sent_to_model_count") or 0) > 0
        else "a_share_disclosure_empty",
        "fallback_queries": _string_list(fallback_stats.get("queries")),
        "local_announcement_lead_count": 0,
        "seed_source_lead_count": 0,
        "final_search_lead_triggered": False,
        "final_search_lead_count": 0,
        "final_search_lead_queries": [],
        "primary_search_stats": primary_stats,
        "fallback_search_stats": fallback_stats,
    }
    merged["no_candidate_reason"] = (
        _no_candidate_reason(merged)
        if int(merged.get("sent_to_model_count") or 0) <= 0
        else None
    )
    return merged


def _merge_filtered_reasons(*values: object) -> dict[str, int]:
    merged: dict[str, int] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        for key, count in value.items():
            merged[str(key)] = merged.get(str(key), 0) + int(count or 0)
    return merged


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _join_text_parts(*parts: object) -> str:
    text_parts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, dict):
            text_parts.extend(str(value) for value in part.values() if value is not None)
        elif isinstance(part, (list, tuple, set)):
            text_parts.extend(str(value) for value in part if value is not None)
        else:
            text_parts.append(str(part))
    return " ".join(value for value in text_parts if value)


def _truncate_lead_text(value: object, *, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "确定性 fallback 线索，需要人工打开来源复核。"
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _no_candidate_message(stats: dict[str, object]) -> str:
    reason = _no_candidate_reason(stats)
    fallback_text = (
        "已自动执行 A 股定向外部事实 fallback，但仍未形成可送模型候选。"
        if stats.get("fallback_triggered")
        else "未形成可送模型候选。"
    )
    if reason == "provider_no_result":
        return f"外部搜索源暂未返回可用结果，可能是搜索源超时、被重置或返回空页；{fallback_text}"
    if reason == "all_filtered":
        return (
            "搜索源返回了结果，但均被过滤为行情/价格敏感、公告重复、入口页或"
            f"非基本面内容；{fallback_text}"
        )
    return f"搜索结果过滤后没有可送模型候选；{fallback_text}"


def _no_candidate_reason(stats: dict[str, object]) -> str:
    provider_result_count = int(stats.get("provider_result_count") or 0)
    deduped_result_count = int(stats.get("deduped_result_count") or 0)
    filtered_out_count = int(stats.get("filtered_out_count") or 0)
    if provider_result_count <= 0:
        return "provider_no_result"
    if deduped_result_count > 0 and filtered_out_count >= deduped_result_count:
        return "all_filtered"
    return "no_ranked_candidate"


def _collect_search_results(
    provider: WebSearchProvider,
    *,
    company: Company,
    queries: list[str],
    limit_per_query: int,
    page_fetcher: WebPageSnapshotFetcher | None = None,
    fallback_only: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    filtered_out_by_reason: dict[str, int] = {
        "price_sensitive": 0,
        "generic_entry": 0,
        "company_disclosure_duplicate": 0,
        "not_fundamental": 0,
        "not_fallback_fundamental": 0,
    }
    query_errors: list[dict[str, str]] = []
    provider_stats: list[dict[str, object]] = []
    provider_result_count = 0
    deduped_result_count = 0

    for query in queries:
        try:
            results = provider.search(query, limit=limit_per_query)
        except WebSearchError as exc:
            query_errors.append({"query": query, "error": str(exc)})
            continue

        provider_result_count += len(results)
        last_provider_stats = getattr(provider, "last_provider_stats", None)
        if isinstance(last_provider_stats, list) and last_provider_stats:
            provider_stats.append({"query": query, "providers": last_provider_stats})

        for result in results:
            snapshot = _compact_search_snapshot(result.to_snapshot())
            dedupe_key = _search_result_dedupe_key(snapshot)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped_result_count += 1

            filter_reason, relevance_score = _classify_search_snapshot(
                snapshot, company, fallback_only=fallback_only
            )
            if filter_reason is not None:
                filtered_out_by_reason[filter_reason] = (
                    filtered_out_by_reason.get(filter_reason, 0) + 1
                )
                continue
            snapshot["price_sensitive"] = False
            snapshot["use_scope"] = DEFAULT_FUNDAMENTAL_USE_SCOPE.copy()
            snapshot["relevance_score"] = round(relevance_score, 2)
            snapshot["relevance_basis"] = _search_relevance_basis(snapshot, company)
            if page_fetcher is not None and isinstance(snapshot.get("url"), str):
                page_snapshot = page_fetcher.fetch(str(snapshot["url"]))
                if page_snapshot is not None:
                    snapshot["page_snapshot"] = page_snapshot.to_snapshot()
            candidates.append(snapshot)

    candidates.sort(
        key=lambda item: float(item.get("relevance_score") or 0),
        reverse=True,
    )
    snapshots = candidates[:MAX_MODEL_SEARCH_RESULTS]
    filtered_out_count = sum(filtered_out_by_reason.values())
    search_stats: dict[str, object] = {
        "queries": queries,
        "query_count": len(queries),
        "provider_result_count": provider_result_count,
        "deduped_result_count": deduped_result_count,
        "candidate_before_ranking_count": len(candidates),
        "sent_to_model_count": len(snapshots),
        "model_candidate_limit": MAX_MODEL_SEARCH_RESULTS,
        "filtered_out_count": filtered_out_count,
        "filtered_out_by_reason": filtered_out_by_reason,
        "query_errors": query_errors,
        "provider_stats": provider_stats,
    }
    return snapshots, search_stats


def _classify_search_snapshot(
    snapshot: dict[str, object], company: Company, *, fallback_only: bool = False
) -> tuple[str | None, float]:
    if _is_price_sensitive_search_result(snapshot):
        return "price_sensitive", 0
    if _is_generic_search_entry(snapshot):
        return "generic_entry", 0
    if _is_company_disclosure_duplicate(snapshot):
        return "company_disclosure_duplicate", 0
    if fallback_only and not _is_fallback_fundamental_snapshot(snapshot):
        return "not_fallback_fundamental", 0

    relevance_score = _fundamental_relevance_score(snapshot, company)
    if relevance_score <= 0:
        return "not_fundamental", 0

    return None, relevance_score


def _is_fundamental_research_result(
    snapshot: dict[str, object], company: Company | None = None
) -> bool:
    return _fundamental_relevance_score(snapshot, company) > 0


def _fundamental_relevance_score(
    snapshot: dict[str, object], company: Company | None = None
) -> float:
    text = _search_text(snapshot)
    content_text = _search_content_text(snapshot)
    blocked_patterns = (
        "technical analysis",
        "技术分析",
        "k线",
        "kdj",
        "macd",
        "rsi",
        "均线",
        "当前股价",
        "实时股价",
        "历史股价",
        "股价",
        "收盘价",
        "开盘价",
        "最高价",
        "最低价",
        "实时行情",
        "股票实时行情",
        "五档盘口",
        "逐笔交易",
        "盘口",
        "交易信息",
        "个股点评",
        "社区互动",
        "股吧讨论",
        "涨跌幅",
        "涨幅",
        "跌幅",
        "涨停",
        "跌停",
        "资金流向",
        "主力资金",
        "龙虎榜",
        "短线",
        "股票交易异常波动",
        "交易异常波动",
        "回购股份价格上限",
        "回购价格上限",
        "买入评级",
        "增持评级",
        "卖出评级",
        "股票评级",
        "投资评级",
        "目标价",
        "荐股",
        "估值分位",
        "市盈率分位",
        "市净率分位",
        "市场情绪",
        "投资者情绪",
        "股票行情",
        "行情走势",
        "技术指标",
        "stock price",
        "share price",
        "price target",
        "price change",
        "valuation percentile",
        "market sentiment",
        "buy rating",
        "sell rating",
    )
    if any(pattern in text for pattern in blocked_patterns):
        return 0
    if _is_generic_search_entry(snapshot):
        return 0
    if _is_company_disclosure_duplicate(snapshot):
        return 0

    score = 0.0
    source_text = " ".join(str(snapshot.get(key) or "").lower() for key in ("source", "url"))
    title_snippet_text = " ".join(
        str(snapshot.get(key) or "").lower() for key in ("title", "snippet")
    )

    if any(pattern in source_text for pattern in OFFICIAL_SOURCE_PATTERNS):
        score += 2.0
    if _is_secondary_source(snapshot):
        score -= 1.0

    substantive_matches = _matched_patterns(
        content_text, FUNDAMENTAL_SUBSTANTIVE_PATTERNS
    )
    if substantive_matches:
        score += min(6.0, len(substantive_matches) * 1.2)

    relevance_terms = _company_relevance_terms(company)
    relevance_matches = [term for term in relevance_terms if term in title_snippet_text]
    if relevance_matches:
        score += min(5.0, len(relevance_matches) * 2.0)

    if not substantive_matches:
        return 0

    if relevance_terms and not relevance_matches:
        source_is_official = any(
            pattern in source_text for pattern in OFFICIAL_SOURCE_PATTERNS
        )
        industry_term = (company.industry or "").strip().lower() if company else ""
        is_industry_material = bool(industry_term and industry_term in title_snippet_text)
        if not source_is_official and not is_industry_material:
            score -= 1.5

    return max(score, 0)


def _search_result_dedupe_key(snapshot: dict[str, object]) -> str:
    value = str(snapshot.get("url") or snapshot.get("title") or "")
    return value.rstrip("/").lower()


def _search_text(snapshot: dict[str, object]) -> str:
    return " ".join(
        str(snapshot.get(key) or "").lower()
        for key in ("query", "title", "source", "url", "snippet")
    )


def _search_content_text(snapshot: dict[str, object]) -> str:
    return " ".join(
        str(snapshot.get(key) or "").lower()
        for key in ("title", "source", "url", "snippet")
    )


def _matched_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if pattern in text]


def _is_company_disclosure_duplicate(snapshot: dict[str, object]) -> bool:
    text = _search_content_text(snapshot)
    return any(pattern in text for pattern in COMPANY_DISCLOSURE_DUPLICATE_PATTERNS)


def _is_secondary_source(snapshot: dict[str, object]) -> bool:
    text = _search_text(snapshot)
    return any(pattern in text for pattern in SECONDARY_SOURCE_PATTERNS)


def _is_fallback_fundamental_snapshot(snapshot: dict[str, object]) -> bool:
    text = _search_content_text(snapshot)
    return any(pattern in text for pattern in FALLBACK_FUNDAMENTAL_PATTERNS)


def _company_relevance_terms(company: Company | None) -> list[str]:
    if company is None:
        return []

    terms: list[str] = []
    for value in (company.name, company.ticker, company.industry):
        if value:
            _append_unique(terms, value.lower())
    if company.ticker and "." in company.ticker:
        _append_unique(terms, company.ticker.split(".", maxsplit=1)[0].lower())
    return terms


def _search_relevance_basis(snapshot: dict[str, object], company: Company) -> dict[str, object]:
    content_text = _search_content_text(snapshot)
    title_snippet_text = " ".join(
        str(snapshot.get(key) or "").lower() for key in ("title", "snippet")
    )
    source_text = " ".join(str(snapshot.get(key) or "").lower() for key in ("source", "url"))
    return {
        "matched_company_terms": [
            term for term in _company_relevance_terms(company) if term in title_snippet_text
        ][:6],
        "matched_fundamental_terms": _matched_patterns(
            content_text, FUNDAMENTAL_SUBSTANTIVE_PATTERNS
        )[:10],
        "official_source": any(
            pattern in source_text for pattern in OFFICIAL_SOURCE_PATTERNS
        ),
        "secondary_source": _is_secondary_source(snapshot),
    }


def _is_generic_search_entry(snapshot: dict[str, object]) -> bool:
    title = str(snapshot.get("title") or "").lower()
    text = " ".join(str(snapshot.get(key) or "").lower() for key in ("source", "url", "snippet"))
    generic_entry_patterns = (
        "检索入口",
        "官网入口",
        "搜索入口",
        "查询入口",
        "数据入口",
        "首页",
        "公告检索入口",
        "监管信息检索",
        "上市公司公告检索",
        "edgar company filings",
        "company filings",
    )
    if any(pattern in title for pattern in generic_entry_patterns):
        return True

    substantive_patterns = (
        "年度报告",
        "年报",
        "半年度报告",
        "季度报告",
        "公告日期",
        "处罚",
        "行政许可",
        "问询函",
        "监管函",
        "公开数据",
        "产量",
        "消费",
        "供需",
        "行业政策",
        "政策汇总",
        "政策解读",
        "统计",
        "report",
        "10-k",
        "10-q",
        "8-k",
    )
    return any(pattern in text for pattern in generic_entry_patterns) and not any(
        pattern in text for pattern in substantive_patterns
    )


def _is_price_sensitive_search_result(snapshot: dict[str, object]) -> bool:
    return _is_price_sensitive_payload(
        title=str(snapshot.get("title") or ""),
        summary=str(snapshot.get("snippet") or ""),
        key_facts=[],
        tags=[],
        raw_snapshot=snapshot,
    )


def _is_price_sensitive_payload(
    *,
    title: str,
    summary: str,
    key_facts: list[str],
    tags: list[str],
    raw_snapshot: dict[str, object],
) -> bool:
    text = _normalize_price_sensitive_text(
        title,
        summary,
        key_facts,
        tags,
        raw_snapshot,
    )
    price_sensitive_patterns = (
        "当前股价",
        "实时股价",
        "历史股价",
        "股价",
        "收盘价",
        "开盘价",
        "最高价",
        "最低价",
        "实时行情",
        "股票实时行情",
        "五档盘口",
        "逐笔交易",
        "盘口",
        "交易信息",
        "个股点评",
        "社区互动",
        "股吧讨论",
        "涨跌幅",
        "涨幅",
        "跌幅",
        "目标价",
        "买入评级",
        "增持评级",
        "卖出评级",
        "股票评级",
        "投资评级",
        "荐股",
        "估值分位",
        "市盈率分位",
        "市净率分位",
        "市场情绪",
        "投资者情绪",
        "资金流向",
        "主力资金",
        "技术指标",
        "股票交易异常波动",
        "交易异常波动",
        "回购股份价格上限",
        "回购价格上限",
        "price target",
        "stock price",
        "share price",
        "price change",
        "upside",
        "downside",
        "buy rating",
        "sell rating",
        "valuation percentile",
        "market sentiment",
    )
    return any(pattern in text for pattern in price_sensitive_patterns)


def _normalize_price_sensitive_text(*parts: object) -> str:
    strings: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            strings.extend(_normalize_price_sensitive_text(value) for value in part.values())
        elif isinstance(part, list):
            strings.extend(_normalize_price_sensitive_text(value) for value in part)
        elif part is not None:
            strings.append(str(part).lower())
    return " ".join(strings)


def _resolve_evidence_scope(output: EvidenceModelOutput) -> tuple[bool, list[EvidenceUseScope]]:
    price_sensitive = output.price_sensitive or _is_price_sensitive_payload(
        title=output.title,
        summary=output.summary,
        key_facts=output.key_facts,
        tags=output.tags,
        raw_snapshot=output.raw_snapshot,
    )
    if price_sensitive:
        return True, []

    use_scope = output.use_scope or DEFAULT_FUNDAMENTAL_USE_SCOPE
    return False, use_scope or DEFAULT_FUNDAMENTAL_USE_SCOPE.copy()


def _expand_queries(model_queries: list[str], company: Company, keywords: list[str]) -> list[str]:
    queries: list[str] = []
    for query in model_queries:
        _append_unique(queries, query)

    ticker_code = company.ticker.split(".", maxsplit=1)[0] if company.ticker else ""
    base_terms = [company.name, company.ticker, company.industry or "", *keywords]
    cleaned_terms = [term.strip() for term in base_terms if term and term.strip()]
    if company.name:
        _append_unique(queries, f"{company.name} 政策 监管 公开数据")
        _append_unique(queries, f"{company.name} 政府 监管 处罚 公示")
        _append_unique(queries, f"{company.name} 社会责任 食品安全 环保 合规")
        if company.industry:
            _append_unique(queries, f"{company.name} {company.industry} 供需 统计 政策")
            _append_unique(queries, f"{company.name} {company.industry} 渠道 库存 供需")
    if company.ticker:
        _append_unique(queries, f"{company.name} {company.ticker} 监管 处罚 问询")
        if ticker_code and ticker_code != company.ticker:
            _append_unique(queries, f"{company.name} {ticker_code} 监管 处罚 问询")
        _append_unique(queries, f"{company.ticker} regulatory public data")
    if company.name and company.industry:
        _append_unique(queries, f"{company.industry} 政策 监管 统计 数据")
        _append_unique(queries, f"{company.industry} 行业 公开数据 供需")
        _append_unique(queries, f"{company.industry} 行业 产量 库存 渠道 消费")
    if cleaned_terms:
        _append_unique(queries, f"{' '.join(cleaned_terms[:3])} 政策 监管 公开数据")

    return queries


def _append_unique(items: list[str], value: str) -> None:
    normalized = " ".join(value.strip().split())
    if normalized and normalized not in items:
        items.append(normalized)


def _compact_search_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    compact = dict(snapshot)
    snippet = compact.get("snippet")
    if isinstance(snippet, str) and len(snippet) > 500:
        compact["snippet"] = f"{snippet[:500]}..."
    title = compact.get("title")
    if isinstance(title, str) and len(title) > 160:
        compact["title"] = f"{title[:160]}..."
    return compact


def _create_evidence_items(
    session: Session,
    company_id: int,
    outputs: list[EvidenceModelOutput],
) -> list[Evidence]:
    items: list[Evidence] = []
    for output in outputs:
        if len(items) >= MAX_MODEL_SEARCH_RESULTS:
            break
        price_sensitive, use_scope = _resolve_evidence_scope(output)
        if price_sensitive:
            continue
        if _is_company_disclosure_duplicate(
            {
                "title": output.title,
                "source": output.source,
                "url": output.source_url,
                "snippet": output.summary,
            }
        ):
            continue
        evidence = Evidence(
            company_id=company_id,
            source_type=output.source_type,
            title=output.title,
            source=output.source,
            source_url=output.source_url,
            published_at=output.published_at,
            summary=output.summary,
            key_facts=output.key_facts,
            impact_direction=output.impact_direction,
            importance_score=output.importance_score,
            credibility_score=output.credibility_score,
            tags=output.tags,
            requires_review=output.requires_review,
            price_sensitive=price_sensitive,
            use_scope=use_scope,
            analysis_status=output.analysis_status,
            analysis_note=output.analysis_note,
            raw_snapshot=output.raw_snapshot,
        )
        session.add(evidence)
        items.append(evidence)

    session.commit()
    for item in items:
        session.refresh(item)
    return items


def _create_fallback_evidence_items(
    session: Session,
    company_id: int,
    raw_results: list[dict[str, object]],
) -> list[Evidence]:
    outputs: list[EvidenceModelOutput] = []
    for raw_result in raw_results[:5]:
        title = str(raw_result.get("title") or "外部信息线索")
        source = raw_result.get("source")
        source_url = raw_result.get("url")
        analysis_note = raw_result.get("analysis_note")
        snippet = str(
            raw_result.get("snippet")
            or "模型结构化暂时失败，已保留原始搜索线索供人工复核。"
        )
        outputs.append(
            EvidenceModelOutput(
                source_type="web",
                title=title,
                source=str(source) if source else None,
                source_url=str(source_url) if source_url else None,
                published_at=None,
                summary=f"{snippet} 该条由搜索结果兜底入库，需要人工打开来源复核。",
                key_facts=["搜索结果线索已入库，尚未完成模型摘要和事实抽取。"],
                impact_direction="unknown",
                importance_score=0.3,
                credibility_score=0.4,
                tags=["待复核", "搜索线索"],
                requires_review=True,
                price_sensitive=False,
                use_scope=DEFAULT_FUNDAMENTAL_USE_SCOPE,
                analysis_status="search_lead",
                analysis_note=str(analysis_note)
                if analysis_note
                else (
                    "模型结构化失败或超时，本条仅为搜索线索，"
                    "影响方向、重要性和可信度尚未完成模型分析。"
                ),
                raw_snapshot=raw_result,
            )
        )
    return _create_evidence_items(session, company_id, outputs)


def _try_repair_evidence_output(
    *,
    model_gateway: ModelGateway,
    company_snapshot: dict[str, Any],
    raw_results: object,
    validation_error: Exception,
) -> EvidenceExtractionOutput | None:
    if not isinstance(raw_results, list) or not raw_results:
        return None

    repair_prompt = build_evidence_prompt(
        company=company_snapshot,
        search_results=raw_results,
    )
    repair_prompt = (
        f"{repair_prompt}\n\n"
        "上一次输出没有通过 Pydantic 校验。"
        f"错误摘要：{validation_error}\n"
        "请严格返回合法 JSON，且每个 evidence 必须包含："
        "source_type,title,source,source_url,published_at,summary,key_facts,"
        "impact_direction,importance_score,credibility_score,tags,requires_review,"
        "price_sensitive,use_scope,analysis_status,analysis_note,raw_snapshot。"
        "不要省略 title。"
    )

    try:
        return model_gateway.generate_structured(
            system_prompt=EVIDENCE_SYSTEM_PROMPT,
            user_prompt=repair_prompt,
            schema=EvidenceExtractionOutput,
            temperature=0,
        )
    except Exception:
        return None


def _company_snapshot(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "ticker": company.ticker,
        "exchange": company.exchange,
        "name": company.name,
        "industry": company.industry,
        "description": company.description,
        "tags": company.tags,
    }


class EvidenceSearchError(RuntimeError):
    pass
