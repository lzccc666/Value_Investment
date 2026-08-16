from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.analysis.model_gateway import ModelGateway
from app.analysis.prompts.announcement import (
    ANNOUNCEMENT_SUMMARY_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_announcement_summary_prompt,
)
from app.configuration.runtime import parameter_value
from app.data_sources.announcement_content import (
    AnnouncementContentFetcher,
    AnnouncementContentFetchError,
    looks_like_eastmoney_page_shell,
)
from app.db.models import AnalysisRun, Announcement, Company
from app.schemas.announcement_summary import (
    AnnouncementSummaryBatchItem,
    AnnouncementSummaryOutput,
)

RUN_TYPE_ANNOUNCEMENT_SUMMARY = "announcement_summary"
GENERIC_TAGS = {"待复核", "其他", "公告", "公司公告", "搜索线索", "智能摘要"}


@dataclass(frozen=True)
class ResolvedAnnouncementContent:
    content: str
    source_url: str | None
    content_status: str
    summary_mode: str
    content_error: str | None = None
    raw_content_for_storage: str | None = None


@dataclass(frozen=True)
class AnnouncementClassification:
    category: str | None
    tags: list[str]


def summarize_company_announcement(
    session: Session,
    company: Company,
    announcement: Announcement,
    *,
    gateway: ModelGateway | None = None,
    content_fetcher: AnnouncementContentFetcher | None = None,
) -> tuple[Announcement, int | None]:
    _discard_announcement_summary_history(session, company_id=company.id)
    announcement.summary_status = "processing"
    session.commit()
    session.refresh(announcement)

    try:
        resolved_content = _resolve_announcement_content(
            company,
            announcement,
            content_fetcher=content_fetcher,
        )
        content_for_model, content_truncated = _truncate_for_model(resolved_content.content)
        if resolved_content.summary_mode == "metadata_keyword":
            output = _build_metadata_keyword_summary(
                company,
                announcement,
                content_error=resolved_content.content_error,
            )
            model_name = "metadata_keyword"
        else:
            model_gateway = gateway or ModelGateway()
            output = model_gateway.generate_structured(
                system_prompt=ANNOUNCEMENT_SUMMARY_SYSTEM_PROMPT,
                user_prompt=build_announcement_summary_prompt(
                    company=_company_snapshot(company),
                    announcement=_announcement_snapshot(announcement),
                    content=content_for_model,
                    content_truncated=content_truncated,
                ),
                schema=AnnouncementSummaryOutput,
                temperature=float(
                    parameter_value("analyst_engine.model_temperatures.announcement", 0.1)
                ),
            )
            model_name = model_gateway.model_name

        classification = _classify_announcement_metadata(announcement, output)
        output = _normalize_summary_output(
            output,
            announcement=announcement,
            classification=classification,
            content_status=resolved_content.content_status,
            content_error=resolved_content.content_error,
        )
        _apply_summary_to_announcement(
            announcement,
            output,
            raw_content=resolved_content.raw_content_for_storage,
            model_name=model_name,
        )
        session.commit()
        session.refresh(announcement)
        return announcement, None
    except Exception:
        _fail_summary(session, announcement)
        raise


def summarize_company_announcements(
    session: Session,
    company: Company,
    announcements: list[Announcement],
    *,
    gateway: ModelGateway | None = None,
    content_fetcher: AnnouncementContentFetcher | None = None,
) -> list[AnnouncementSummaryBatchItem]:
    # Batch summarization is intentionally metadata-only so a large announcement list
    # cannot block on PDF/HTML downloads or model latency.
    _discard_announcement_summary_history(session, company_id=company.id)
    results: list[AnnouncementSummaryBatchItem] = []

    for announcement in announcements:
        try:
            output = _build_metadata_keyword_summary(
                company,
                announcement,
                content_error="一键快速摘要未读取公告原文",
            )
            classification = _classify_announcement_metadata(announcement, output)
            output = _normalize_summary_output(
                output,
                announcement=announcement,
                classification=classification,
                content_status="metadata_only",
                content_error="一键快速摘要未读取公告原文",
            )
            _apply_summary_to_announcement(
                announcement,
                output,
                raw_content=None,
                model_name="metadata_keyword",
            )
            results.append(
                AnnouncementSummaryBatchItem(
                    announcement_id=announcement.id,
                    status="success",
                    summary_status=announcement.summary_status,
                    run_id=None,
                    announcement=announcement,
                )
            )
        except Exception as exc:
            announcement.summary_status = "failed"
            results.append(
                AnnouncementSummaryBatchItem(
                    announcement_id=announcement.id,
                    status="failed",
                    summary_status=announcement.summary_status,
                    run_id=None,
                    announcement=announcement,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )

    session.commit()
    return results


def summarize_company_announcements_deep(
    session: Session,
    company: Company,
    announcements: list[Announcement],
    *,
    gateway: ModelGateway | None = None,
    content_fetcher: AnnouncementContentFetcher | None = None,
) -> list[AnnouncementSummaryBatchItem]:
    results: list[AnnouncementSummaryBatchItem] = []

    for announcement in announcements:
        if _is_deep_summarized(announcement):
            results.append(
                AnnouncementSummaryBatchItem(
                    announcement_id=announcement.id,
                    status="skipped",
                    summary_status=announcement.summary_status,
                    run_id=None,
                    announcement=announcement,
                    error="公告已深度摘要，已跳过",
                    error_type="AlreadyDeepSummarized",
                )
            )
            continue

        try:
            summarized, run_id = summarize_company_announcement(
                session,
                company,
                announcement,
                gateway=gateway,
                content_fetcher=content_fetcher,
            )
            results.append(
                AnnouncementSummaryBatchItem(
                    announcement_id=summarized.id,
                    status="success",
                    summary_status=summarized.summary_status,
                    run_id=run_id,
                    announcement=summarized,
                )
            )
        except Exception as exc:
            results.append(
                AnnouncementSummaryBatchItem(
                    announcement_id=announcement.id,
                    status="failed",
                    summary_status=announcement.summary_status,
                    run_id=None,
                    announcement=announcement,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )

    return results


def _is_deep_summarized(announcement: Announcement) -> bool:
    model_name = (announcement.summary_model_name or "").strip()
    return bool(
        model_name
        and model_name != "metadata_keyword"
        and not _has_stale_page_shell_content(announcement)
    )


def _has_stale_page_shell_content(announcement: Announcement) -> bool:
    return looks_like_eastmoney_page_shell(announcement.raw_content) or (
        not announcement.raw_content and looks_like_eastmoney_page_shell(announcement.content)
    )


def _resolve_announcement_content(
    company: Company,
    announcement: Announcement,
    *,
    content_fetcher: AnnouncementContentFetcher | None,
) -> ResolvedAnnouncementContent:
    existing_content = announcement.raw_content or announcement.content
    if (
        existing_content
        and existing_content.strip()
        and not looks_like_eastmoney_page_shell(existing_content)
    ):
        content = existing_content.strip()
        return ResolvedAnnouncementContent(
            content=content,
            source_url=announcement.source_url or announcement.raw_url,
            content_status="stored",
            summary_mode="content_keyword",
            raw_content_for_storage=content,
        )

    fetcher = content_fetcher or AnnouncementContentFetcher()
    try:
        content, source_url = fetcher.fetch_text(
            source_url=announcement.source_url,
            raw_url=announcement.raw_url,
        )
    except AnnouncementContentFetchError as exc:
        return ResolvedAnnouncementContent(
            content=_build_metadata_content(company, announcement, content_error=str(exc)),
            source_url=announcement.source_url or announcement.raw_url,
            content_status="metadata_only",
            summary_mode="metadata_keyword",
            content_error=str(exc),
        )

    normalized_content = content.strip()
    if not normalized_content:
        content_error = "公告原文为空，已改用标题、分类、时间和来源生成关键词摘要"
        return ResolvedAnnouncementContent(
            content=_build_metadata_content(
                company,
                announcement,
                content_error=content_error,
            ),
            source_url=source_url or announcement.source_url or announcement.raw_url,
            content_status="metadata_only",
            summary_mode="metadata_keyword",
            content_error=content_error,
        )

    return ResolvedAnnouncementContent(
        content=normalized_content,
        source_url=source_url,
        content_status="fetched",
        summary_mode="content_keyword",
        raw_content_for_storage=normalized_content,
    )


def _discard_announcement_summary_history(session: Session, *, company_id: int) -> None:
    session.execute(
        delete(AnalysisRun).where(
            AnalysisRun.company_id == company_id,
            AnalysisRun.run_type == RUN_TYPE_ANNOUNCEMENT_SUMMARY,
        )
    )


def _apply_summary_to_announcement(
    announcement: Announcement,
    output: AnnouncementSummaryOutput,
    *,
    raw_content: str | None,
    model_name: str | None,
) -> None:
    if raw_content:
        announcement.raw_content = raw_content
    announcement.summary = output.summary
    announcement.key_facts = output.key_facts
    announcement.category = output.category or announcement.category
    announcement.importance_score = None
    announcement.impact_direction = output.impact_direction
    announcement.sentiment = output.impact_direction
    announcement.positive_impacts = output.positive_impacts
    announcement.negative_impacts = output.negative_impacts
    announcement.neutral_impacts = output.neutral_impacts
    announcement.risk_tips = output.risk_tips
    announcement.review_questions = output.review_questions
    announcement.tags = output.tags
    announcement.summary_status = "summarized"
    announcement.summary_model_name = model_name
    announcement.summary_prompt_version = PROMPT_VERSION
    announcement.summarized_at = datetime.now(UTC)


def _fail_summary(session: Session, announcement: Announcement) -> None:
    announcement.summary_status = "failed"
    session.commit()
    session.refresh(announcement)


def _build_metadata_content(
    company: Company,
    announcement: Announcement,
    *,
    content_error: str | None,
) -> str:
    return "\n".join(
        [
            f"公司：{company.name}（{company.ticker}）",
            f"公告标题：{announcement.title}",
            f"公告分类：{announcement.category}",
            f"发布时间：{announcement.published_at.isoformat()}",
            f"来源：{announcement.source or '未知'}",
            f"来源链接：{announcement.source_url or announcement.raw_url or '无'}",
            f"正文读取状态：{content_error or '未读取到正文'}",
        ]
    )


def _build_metadata_keyword_summary(
    company: Company,
    announcement: Announcement,
    *,
    content_error: str | None,
) -> AnnouncementSummaryOutput:
    classification = _classify_announcement_metadata(announcement)
    category = classification.category or _normalize_category(announcement.category)
    tags = _clean_tags(classification.tags)
    source_url = announcement.source_url or announcement.raw_url
    summary = (
        f"类别：{category}；性质：{_infer_announcement_nature(announcement)}；"
        "影响：未知；正文：未读取"
    )
    key_facts = [
        f"标题：{announcement.title}",
        f"发布时间：{announcement.published_at.date().isoformat()}",
    ]
    if announcement.source:
        key_facts.append(f"来源：{announcement.source}")
    if source_url:
        key_facts.append(f"来源链接：{source_url}")

    review_questions = ["公告正文未读取成功，请打开来源链接复核原文后再用于深度分析。"]
    if content_error:
        review_questions.append(f"正文读取失败原因：{content_error[:160]}")

    return AnnouncementSummaryOutput(
        summary=_truncate_summary(summary),
        key_facts=key_facts[:4],
        category=category,
        impact_direction="unknown",
        confidence=0.35,
        positive_impacts=[],
        negative_impacts=[],
        neutral_impacts=["仅基于公告标题、分类、发布时间和来源生成关键词摘要。"],
        risk_tips=[],
        review_questions=review_questions[:4],
        tags=tags,
        requires_review=True,
        source_url=source_url,
    )


def _normalize_summary_output(
    output: AnnouncementSummaryOutput,
    *,
    announcement: Announcement,
    classification: AnnouncementClassification,
    content_status: str,
    content_error: str | None,
) -> AnnouncementSummaryOutput:
    category = classification.category or _normalize_category(
        output.category or announcement.category
    )
    tags = _clean_tags(classification.tags, output.tags)
    raw_summary = " ".join(output.summary.strip().split())
    summary = raw_summary
    keyword_limit = int(parameter_value("data_sampling.announcement_keyword_summary_chars", 120))
    if len(raw_summary) > keyword_limit:
        summary = (
            f"类别：{category}；性质：{_infer_announcement_nature(announcement)}；"
            f"影响：{_impact_label(output.impact_direction)}"
        )

    review_questions = list(output.review_questions)
    if content_status == "metadata_only" and not review_questions:
        review_questions.append("公告正文未读取成功，请打开来源链接复核原文。")
    if content_error and content_status == "metadata_only":
        review_questions.append(f"正文读取失败原因：{content_error[:160]}")

    return output.model_copy(
        update={
            "summary": _truncate_summary(summary),
            "category": category,
            "confidence": min(output.confidence, 0.45)
            if content_status == "metadata_only"
            else output.confidence,
            "risk_tips": _clean_text_list(output.risk_tips, max_items=8),
            "review_questions": _clean_text_list(review_questions, max_items=8),
            "tags": tags,
            "requires_review": output.requires_review
            if content_status != "metadata_only"
            else True,
            "source_url": output.source_url or announcement.source_url or announcement.raw_url,
        }
    )


def _classify_announcement_metadata(
    announcement: Announcement,
    output: AnnouncementSummaryOutput | None = None,
) -> AnnouncementClassification:
    text = " ".join(
        part
        for part in (
            announcement.title,
            announcement.category,
            output.category if output else None,
            " ".join(output.tags) if output else None,
        )
        if part
    )
    normalized_text = text.lower()

    classification_rules = (
        (
            ("年度报告", "年报", "半年度报告", "半年报", "季度报告", "季报"),
            "定期报告",
            ["财报"],
        ),
        (("业绩预告", "业绩快报", "盈利预警", "亏损"), "业绩预告", ["业绩预告"]),
        (("问询函", "监管函", "处罚", "立案", "调查", "整改"), "监管问询", ["监管问询"]),
        (("重大诉讼", "仲裁", "诉讼"), "诉讼", ["诉讼"]),
        (("重大资产重组", "并购", "收购", "合并", "重组"), "并购重组", ["并购"]),
        (("控制权", "实际控制人", "控股股东变更"), "控制权变化", ["控制权变化"]),
        (("审计意见", "保留意见", "否定意见", "无法表示意见"), "审计意见", ["审计"]),
        (
            ("会计差错", "差错更正", "追溯调整", "会计政策变更", "会计估计变更"),
            "会计口径",
            ["会计口径"],
        ),
        (("退市", "暂停上市"), "退市风险", ["退市风险"]),
        (("分红", "利润分配", "权益分派"), "分红", ["分红"]),
        (("回购",), "回购", ["回购"]),
        (("定增", "可转债", "配股", "融资", "募集资金"), "融资", ["融资"]),
        (("重大合同", "战略合作", "项目中标"), "重大合同", ["重大合同"]),
        (("关联交易",), "关联交易", ["关联交易"]),
        (("担保",), "担保", ["担保"]),
        (
            ("董事长", "总经理", "财务负责人", "高管", "管理层", "辞职", "聘任"),
            "管理层变化",
            ["管理层变化"],
        ),
        (("股权激励", "员工持股"), "股权激励", ["股权激励"]),
        (("董事会决议", "监事会决议", "股东大会决议"), "治理事项", ["治理"]),
        (("章程", "制度修订", "工作细则"), "制度修订", ["治理"]),
        (
            ("召开股东大会", "股东大会通知", "会议资料", "法律意见书"),
            "会议通知",
            ["会议通知"],
        ),
        (("提示性公告", "进展公告", "补充公告"), "提示性公告", ["提示性公告"]),
        (("独立董事意见", "核查意见", "保荐意见"), "中介意见", ["中介意见"]),
    )

    for terms, category, tags in classification_rules:
        if any(term.lower() in normalized_text for term in terms):
            return AnnouncementClassification(category=category, tags=tags)

    return AnnouncementClassification(
        category=_normalize_category(output.category if output else announcement.category),
        tags=[],
    )


def _normalize_category(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized or normalized in {"其他", "公告"}:
        return "其他事项"
    return normalized


def _infer_announcement_nature(announcement: Announcement) -> str:
    title = announcement.title
    if any(term in title for term in ("年度报告", "年报", "半年度报告", "季报", "季度报告")):
        return "定期披露"
    if any(term in title for term in ("分红", "利润分配", "回购")):
        return "资本分配"
    if any(term in title for term in ("问询", "监管", "处罚", "诉讼", "仲裁")):
        return "风险/监管事项"
    if any(term in title for term in ("董事会", "股东大会", "监事会", "章程")):
        return "治理流程"
    return "公告事项"


def _impact_label(value: str | None) -> str:
    return {
        "positive": "利好",
        "negative": "利空",
        "neutral": "中性",
        "mixed": "混合",
        "unknown": "未知",
    }.get(value or "unknown", "未知")


def _truncate_summary(value: str) -> str:
    normalized = " ".join(value.strip().split())
    keyword_limit = int(parameter_value("data_sampling.announcement_keyword_summary_chars", 120))
    if len(normalized) <= keyword_limit:
        return normalized
    return f"{normalized[: keyword_limit - 3]}..."


def _clean_tags(*tag_groups: list[str] | str | None) -> list[str]:
    tags: list[str] = []
    for group in tag_groups:
        if group is None:
            continue
        values = [group] if isinstance(group, str) else group
        for value in values:
            tag = " ".join(str(value).strip().split())
            if not tag or tag in GENERIC_TAGS or tag in tags:
                continue
            tags.append(tag)
            if len(tags) >= 12:
                return tags
    return tags


def _clean_text_list(values: list[str], *, max_items: int) -> list[str]:
    items: list[str] = []
    for value in values:
        normalized = " ".join(str(value).strip().split())
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= max_items:
            break
    return items


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


def _announcement_snapshot(announcement: Announcement) -> dict[str, Any]:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "published_at": announcement.published_at.isoformat(),
        "category": announcement.category,
        "source": announcement.source,
        "source_url": announcement.source_url,
        "raw_url": announcement.raw_url,
        "summary_status": announcement.summary_status,
    }


def _truncate_for_model(content: str) -> tuple[str, bool]:
    model_limit = int(parameter_value("data_sampling.announcement_model_chars", 12000))
    if len(content) <= model_limit:
        return content, False
    head_ratio = float(parameter_value("data_sampling.announcement_head_ratio", 0.70))
    head = content[: int(model_limit * head_ratio)]
    tail = content[-int(model_limit * (1.0 - head_ratio)) :]
    return f"{head}\n\n[中间内容因长度限制已截断]\n\n{tail}", True
