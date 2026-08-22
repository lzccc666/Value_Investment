from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    BuyMemoEntry,
    Company,
    PriceDecisionRun,
    SecurityListing,
    ValuationRun,
)
from app.schemas.investment_tools import (
    BuyMemoCompanyCandidate,
    BuyMemoDecisionCandidate,
    BuyMemoEntryCreate,
)
from app.services.portfolio_service import (
    PortfolioConflictError,
    PortfolioNotFoundError,
    PortfolioValidationError,
)

DELETED_PRICE_DECISION_STATUS = "deleted"


def list_buy_memo_entries(session: Session) -> list[BuyMemoEntry]:
    return list(
        session.scalars(
            select(BuyMemoEntry).order_by(
                BuyMemoEntry.created_at.desc(),
                BuyMemoEntry.id.desc(),
            )
        )
    )


def get_buy_memo_entry(session: Session, entry_id: int) -> BuyMemoEntry:
    entry = session.get(BuyMemoEntry, entry_id)
    if entry is None:
        raise PortfolioNotFoundError("买入备忘录条目不存在。")
    return entry


def search_buy_memo_companies(
    session: Session,
    query: str = "",
    limit: int = 50,
) -> list[BuyMemoCompanyCandidate]:
    normalized_query = _normalize_search_text(query)
    runs = list(
        session.scalars(
            select(PriceDecisionRun)
            .where(PriceDecisionRun.status != DELETED_PRICE_DECISION_STATUS)
            .order_by(PriceDecisionRun.created_at.desc(), PriceDecisionRun.id.desc())
        )
    )
    counts: dict[int, int] = {}
    for run in runs:
        counts[run.company_id] = counts.get(run.company_id, 0) + 1

    items: list[BuyMemoCompanyCandidate] = []
    for company_id, decision_count in counts.items():
        company = session.get(Company, company_id)
        if company is None:
            continue
        fields = [
            company.name,
            company.legal_name or "",
            company.ticker,
            *(company.aliases or []),
        ]
        if normalized_query and not any(
            normalized_query in _normalize_search_text(field) for field in fields
        ):
            continue
        items.append(
            BuyMemoCompanyCandidate(
                company_id=company.id,
                company_name=company.name,
                primary_ticker=company.ticker,
                decision_count=decision_count,
            )
        )
    items.sort(key=lambda item: (item.company_name.casefold(), item.primary_ticker))
    return items[:limit]


def list_buy_memo_decisions(
    session: Session,
    company_id: int,
) -> list[BuyMemoDecisionCandidate]:
    if session.get(Company, company_id) is None:
        raise PortfolioNotFoundError("公司不存在。")
    imported_ids = set(
        session.scalars(
            select(BuyMemoEntry.source_price_decision_run_id).where(
                BuyMemoEntry.source_price_decision_run_id.is_not(None)
            )
        )
    )
    runs = session.scalars(
        select(PriceDecisionRun)
        .where(
            PriceDecisionRun.company_id == company_id,
            PriceDecisionRun.status != DELETED_PRICE_DECISION_STATUS,
        )
        .order_by(PriceDecisionRun.created_at.desc(), PriceDecisionRun.id.desc())
    )
    return [
        _decision_to_candidate(
            session,
            run,
            already_imported=run.id in imported_ids,
        )
        for run in runs
    ]


def create_buy_memo_entry(
    session: Session,
    payload: BuyMemoEntryCreate,
) -> BuyMemoEntry:
    run = session.get(PriceDecisionRun, payload.price_decision_run_id)
    if run is None or run.status == DELETED_PRICE_DECISION_STATUS:
        raise PortfolioValidationError("选择的 011 投资决策结果不存在或已删除。")
    duplicate = session.scalar(
        select(BuyMemoEntry).where(
            BuyMemoEntry.source_price_decision_run_id == run.id
        )
    )
    if duplicate is not None:
        raise PortfolioConflictError("该 011 投资决策结果已在买入备忘录中。")
    company = session.get(Company, run.company_id)
    if company is None:
        raise PortfolioValidationError("011 投资决策结果对应的公司不存在。")
    candidate = _decision_to_candidate(session, run, already_imported=False)
    entry = BuyMemoEntry(
        company_id=company.id,
        source_price_decision_run_id=run.id,
        company_name=company.name,
        listing_ticker=candidate.listing_ticker,
        exchange=candidate.exchange,
        trading_currency=candidate.trading_currency,
        base_intrinsic_value=candidate.base_intrinsic_value,
        suggested_buy_price=candidate.suggested_buy_price,
        designed_safety_margin=candidate.designed_safety_margin,
        latest_report_period=candidate.latest_report_period,
        price_decision_version_no=run.version_no,
        price_decision_run_version=run.run_version,
        price_decision_created_at=run.created_at,
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PortfolioConflictError("该 011 投资决策结果已在买入备忘录中。") from exc
    session.refresh(entry)
    return entry


def delete_buy_memo_entry(session: Session, entry_id: int) -> None:
    entry = get_buy_memo_entry(session, entry_id)
    session.delete(entry)
    session.commit()


def _decision_to_candidate(
    session: Session,
    run: PriceDecisionRun,
    *,
    already_imported: bool,
) -> BuyMemoDecisionCandidate:
    listing = session.get(SecurityListing, run.listing_id) if run.listing_id else None
    company = session.get(Company, run.company_id)
    valuation = session.get(ValuationRun, run.valuation_run_id)
    listing_ticker = listing.ticker if listing else (company.ticker if company else "UNKNOWN")
    return BuyMemoDecisionCandidate(
        price_decision_run_id=run.id,
        version_no=run.version_no,
        run_version=run.run_version,
        listing_ticker=listing_ticker,
        exchange=listing.exchange if listing else (company.exchange if company else None),
        trading_currency=run.trading_currency or (listing.trading_currency if listing else None),
        base_intrinsic_value=_positive_decimal(
            (run.intrinsic_values_per_share or {}).get("base"),
            "011 投资决策缺少有效的中性内在价值。",
        ),
        suggested_buy_price=_positive_decimal(
            run.suggested_buy_price,
            "011 投资决策缺少有效的建议买入价。",
        ),
        designed_safety_margin=_margin_decimal(run.effective_safety_margin),
        latest_report_period=_latest_report_period(valuation),
        created_at=run.created_at,
        already_imported=already_imported,
    )


def _latest_report_period(valuation: ValuationRun | None) -> str | None:
    if valuation is None:
        return None
    latest_period = (valuation.valuation_inputs or {}).get("latest_period")
    if latest_period:
        return str(latest_period)
    snapshot_inputs = (valuation.input_snapshot or {}).get("valuation_inputs")
    if isinstance(snapshot_inputs, dict) and snapshot_inputs.get("latest_period"):
        return str(snapshot_inputs["latest_period"])
    return None


def _positive_decimal(value: object, message: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioValidationError(message) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PortfolioValidationError(message)
    return parsed


def _margin_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioValidationError("011 投资决策缺少有效的设计安全边际。") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise PortfolioValidationError("011 投资决策的设计安全边际不在 0%-100%。")
    return parsed


def _normalize_search_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())
