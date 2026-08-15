from datetime import date
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.migrations import run_schema_migrations
from app.db.models import Company
from app.db.session import engine

CompanySeed = dict[str, Any]

REAL_COMPANY_SEEDS: list[CompanySeed] = [
    {
        "ticker": "600519.SH",
        "exchange": "SSE",
        "name": "贵州茅台",
        "industry": "白酒",
        "description": "A股白酒公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": date(2001, 8, 27),
        "status": "未研究",
        "tags": ["A股", "白酒", "消费"],
    },
    {
        "ticker": "000858.SZ",
        "exchange": "SZSE",
        "name": "五粮液",
        "industry": "白酒",
        "description": "A股白酒公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "白酒", "消费"],
    },
    {
        "ticker": "000333.SZ",
        "exchange": "SZSE",
        "name": "美的集团",
        "industry": "家用电器",
        "description": "A股家电制造公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "家电", "制造"],
    },
    {
        "ticker": "600036.SH",
        "exchange": "SSE",
        "name": "招商银行",
        "industry": "银行",
        "description": "A股商业银行，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "银行", "金融"],
    },
    {
        "ticker": "601318.SH",
        "exchange": "SSE",
        "name": "中国平安",
        "industry": "保险",
        "description": "A股保险与综合金融公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "保险", "金融"],
    },
    {
        "ticker": "300750.SZ",
        "exchange": "SZSE",
        "name": "宁德时代",
        "industry": "动力电池",
        "description": "A股动力电池公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "新能源", "电池"],
    },
    {
        "ticker": "002594.SZ",
        "exchange": "SZSE",
        "name": "比亚迪",
        "industry": "汽车",
        "description": "A股新能源汽车公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "汽车", "新能源"],
    },
    {
        "ticker": "600900.SH",
        "exchange": "SSE",
        "name": "长江电力",
        "industry": "电力",
        "description": "A股电力公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "电力", "公用事业"],
    },
    {
        "ticker": "600276.SH",
        "exchange": "SSE",
        "name": "恒瑞医药",
        "industry": "医药",
        "description": "A股医药公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "医药", "创新药"],
    },
    {
        "ticker": "300059.SZ",
        "exchange": "SZSE",
        "name": "东方财富",
        "industry": "互联网金融",
        "description": "A股互联网金融服务公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", "金融科技", "证券服务"],
    },
    {
        "ticker": "00700.HK",
        "exchange": "HKEX",
        "name": "腾讯控股",
        "industry": "互联网",
        "description": "港股互联网公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "互联网", "游戏"],
    },
    {
        "ticker": "09988.HK",
        "exchange": "HKEX",
        "name": "阿里巴巴-W",
        "industry": "互联网",
        "description": "港股互联网平台公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "电商", "云计算"],
    },
    {
        "ticker": "03690.HK",
        "exchange": "HKEX",
        "name": "美团-W",
        "industry": "本地生活服务",
        "description": "港股本地生活服务平台公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "本地生活", "平台"],
    },
    {
        "ticker": "01810.HK",
        "exchange": "HKEX",
        "name": "小米集团-W",
        "industry": "消费电子",
        "description": "港股消费电子与智能硬件公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "消费电子", "智能硬件"],
    },
    {
        "ticker": "00941.HK",
        "exchange": "HKEX",
        "name": "中国移动",
        "industry": "电信运营",
        "description": "港股电信运营商，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "通信", "运营商"],
    },
    {
        "ticker": "AAPL.US",
        "exchange": "NASDAQ",
        "name": "Apple Inc. 苹果公司",
        "industry": "消费电子",
        "description": "美股消费电子与软件生态公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "消费电子", "软件生态"],
    },
    {
        "ticker": "MSFT.US",
        "exchange": "NASDAQ",
        "name": "Microsoft Corporation 微软",
        "industry": "软件服务",
        "description": "美股软件与云计算公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "软件", "云计算"],
    },
    {
        "ticker": "NVDA.US",
        "exchange": "NASDAQ",
        "name": "NVIDIA Corporation 英伟达",
        "industry": "半导体",
        "description": "美股半导体公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "半导体", "AI"],
    },
    {
        "ticker": "BRK.B.US",
        "exchange": "NYSE",
        "name": "Berkshire Hathaway Inc. 伯克希尔哈撒韦",
        "industry": "综合控股",
        "description": "美股综合控股公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "保险", "综合控股"],
    },
    {
        "ticker": "TSLA.US",
        "exchange": "NASDAQ",
        "name": "Tesla, Inc. 特斯拉",
        "industry": "汽车",
        "description": "美股新能源汽车公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "汽车", "新能源"],
    },
    {
        "ticker": "AMZN.US",
        "exchange": "NASDAQ",
        "name": "Amazon.com, Inc. 亚马逊",
        "industry": "互联网零售",
        "description": "美股电商与云计算公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "电商", "云计算"],
    },
    {
        "ticker": "GOOGL.US",
        "exchange": "NASDAQ",
        "name": "Alphabet Inc. 谷歌",
        "industry": "互联网",
        "description": "美股搜索、广告与云服务公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "互联网", "广告"],
    },
    {
        "ticker": "META.US",
        "exchange": "NASDAQ",
        "name": "Meta Platforms, Inc. Meta",
        "industry": "互联网",
        "description": "美股社交网络与广告平台公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "社交网络", "广告"],
    },
    {
        "ticker": "V.US",
        "exchange": "NYSE",
        "name": "Visa Inc. 维萨",
        "industry": "支付网络",
        "description": "美股支付网络公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "支付", "金融"],
    },
    {
        "ticker": "KO.US",
        "exchange": "NYSE",
        "name": "The Coca-Cola Company 可口可乐",
        "industry": "饮料",
        "description": "美股饮料公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "饮料", "消费"],
    },
]


def init_db(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=database_engine)
    run_schema_migrations(database_engine)

    with Session(database_engine) as session:
        seed_db(session)


def seed_db(session: Session) -> None:
    _upsert_company_seeds(session, REAL_COMPANY_SEEDS)
    session.commit()


def _upsert_company_seeds(
    session: Session, seeds: list[CompanySeed]
) -> dict[tuple[str, str], Company]:
    companies: dict[tuple[str, str], Company] = {}

    for seed in seeds:
        ticker = str(seed["ticker"])
        exchange = str(seed["exchange"])
        company = session.scalar(
            select(Company).where(Company.ticker == ticker, Company.exchange == exchange)
        )

        if company is None:
            company = Company(**seed)
            session.add(company)
        else:
            company.name = str(seed["name"])
            company.industry = seed["industry"]  # type: ignore[assignment]
            if _should_replace_seed_description(company.description):
                company.description = seed["description"]  # type: ignore[assignment]
            if seed["listed_date"] is not None or company.listed_date is None:
                company.listed_date = seed["listed_date"]  # type: ignore[assignment]
            company.tags = seed["tags"]  # type: ignore[assignment]

        companies[(ticker, exchange)] = company

    return companies


def _should_replace_seed_description(description: str | None) -> bool:
    normalized = (description or "").strip()
    return not normalized
