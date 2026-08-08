from datetime import UTC, date, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AnalysisRun, Announcement, Company, FinancialStatement
from app.db.session import engine


def init_db(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=database_engine)

    with Session(database_engine) as session:
        seed_db(session)


def seed_db(session: Session) -> None:
    has_company = session.scalar(select(Company.id).limit(1))
    if has_company is not None:
        return

    companies = [
        Company(
            ticker="VI0001",
            exchange="SIM",
            name="护城河消费样本",
            industry="消费品",
            description="用于验证公司列表、财务报表和分析结果结构的本地示例公司。",
            listed_date=date(2018, 1, 15),
            status="重点跟踪",
            tags=["护城河", "高ROIC", "现金流"],
        ),
        Company(
            ticker="VI0002",
            exchange="SIM",
            name="周期制造样本",
            industry="先进制造",
            description="用于验证周期行业研究状态和后续估值实验室联动的本地示例公司。",
            listed_date=date(2020, 6, 30),
            status="观察中",
            tags=["周期股", "资本开支", "安全边际"],
        ),
        Company(
            ticker="VI0003",
            exchange="SIM",
            name="平台科技样本",
            industry="软件服务",
            description="用于验证轻资产业务、公告摘要和多视角分析记录的本地示例公司。",
            listed_date=date(2021, 9, 10),
            status="未研究",
            tags=["平台型", "网络效应", "研发投入"],
        ),
    ]
    session.add_all(companies)
    session.flush()

    session.add_all(
        [
            FinancialStatement(
                company_id=companies[0].id,
                period="2025A",
                statement_type="income_statement",
                currency="CNY",
                fields={
                    "revenue": 100.0,
                    "gross_margin": 0.58,
                    "net_profit": 24.0,
                    "operating_cash_flow": 28.0,
                },
                source="seed_demo",
            ),
            Announcement(
                company_id=companies[0].id,
                title="年度经营摘要已导入",
                published_at=datetime(2026, 1, 15, tzinfo=UTC),
                category="annual_report",
                summary="示例公告用于验证公告列表和后续摘要工作流。",
                importance_score=0.7,
            ),
            AnalysisRun(
                company_id=companies[0].id,
                run_type="initial_snapshot",
                analyst_profile="buffett",
                input_snapshot={"source": "seed_demo", "period": "2025A"},
                result={
                    "rating": "watch",
                    "summary": "示例分析记录用于验证多视角分析结果落库。",
                    "key_points": ["现金流质量待验证", "估值区间待补充"],
                },
                confidence=0.5,
            ),
        ]
    )
    session.commit()
