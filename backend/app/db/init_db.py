from datetime import date
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.migrations import run_schema_migrations
from app.db.models import Company
from app.db.session import engine

CompanySeed = dict[str, Any]

MARKET_PRIORITY = {
    "SSE": 3,
    "SZSE": 3,
    "BSE": 3,
    "HKEX": 2,
    "NASDAQ": 1,
    "NYSE": 1,
    "AMEX": 1,
}


def _a_share_seed(
    ticker: str,
    exchange: str,
    name: str,
    industry: str,
    tags: list[str],
) -> CompanySeed:
    return {
        "ticker": ticker,
        "exchange": exchange,
        "name": name,
        "industry": industry,
        "description": f"A股{industry}公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["A股", *tags],
    }


ADDITIONAL_A_SHARE_SEEDS: list[CompanySeed] = [
    _a_share_seed("600941.SH", "SSE", "中国移动", "电信运营", ["通信", "运营商"]),
    _a_share_seed("601398.SH", "SSE", "工商银行", "银行", ["银行", "金融"]),
    _a_share_seed("601288.SH", "SSE", "农业银行", "银行", ["银行", "金融"]),
    _a_share_seed("601939.SH", "SSE", "建设银行", "银行", ["银行", "金融"]),
    _a_share_seed("601988.SH", "SSE", "中国银行", "银行", ["银行", "金融"]),
    _a_share_seed("601166.SH", "SSE", "兴业银行", "银行", ["银行", "金融"]),
    _a_share_seed("601601.SH", "SSE", "中国太保", "保险", ["保险", "金融"]),
    _a_share_seed("601628.SH", "SSE", "中国人寿", "保险", ["保险", "金融"]),
    _a_share_seed("600030.SH", "SSE", "中信证券", "证券", ["券商", "金融"]),
    _a_share_seed("601995.SH", "SSE", "中金公司", "证券", ["券商", "金融"]),
    _a_share_seed("601728.SH", "SSE", "中国电信", "电信运营", ["通信", "运营商"]),
    _a_share_seed("600050.SH", "SSE", "中国联通", "电信运营", ["通信", "运营商"]),
    _a_share_seed("601088.SH", "SSE", "中国神华", "煤炭", ["能源", "煤炭"]),
    _a_share_seed("601857.SH", "SSE", "中国石油", "石油石化", ["能源", "石油"]),
    _a_share_seed("600028.SH", "SSE", "中国石化", "石油石化", ["能源", "石化"]),
    _a_share_seed("601225.SH", "SSE", "陕西煤业", "煤炭", ["能源", "煤炭"]),
    _a_share_seed("601899.SH", "SSE", "紫金矿业", "有色金属", ["资源", "矿业"]),
    _a_share_seed("600887.SH", "SSE", "伊利股份", "乳制品", ["食品饮料", "消费"]),
    _a_share_seed("000568.SZ", "SZSE", "泸州老窖", "白酒", ["白酒", "消费"]),
    _a_share_seed("002304.SZ", "SZSE", "洋河股份", "白酒", ["白酒", "消费"]),
    _a_share_seed("000651.SZ", "SZSE", "格力电器", "家用电器", ["家电", "制造"]),
    _a_share_seed("600690.SH", "SSE", "海尔智家", "家用电器", ["家电", "消费"]),
    _a_share_seed("688981.SH", "SSE", "中芯国际", "半导体", ["芯片", "科技"]),
    _a_share_seed("002475.SZ", "SZSE", "立讯精密", "消费电子", ["电子", "制造"]),
    _a_share_seed("000725.SZ", "SZSE", "京东方A", "面板显示", ["电子", "显示"]),
    _a_share_seed("002415.SZ", "SZSE", "海康威视", "安防设备", ["科技", "物联网"]),
    _a_share_seed("002230.SZ", "SZSE", "科大讯飞", "人工智能", ["AI", "软件"]),
    _a_share_seed("688111.SH", "SSE", "金山办公", "软件服务", ["软件", "办公"]),
    _a_share_seed("603501.SH", "SSE", "豪威集团", "半导体", ["芯片", "图像传感器"]),
    _a_share_seed("600309.SH", "SSE", "万华化学", "化工", ["材料", "制造"]),
    _a_share_seed("600031.SH", "SSE", "三一重工", "工程机械", ["机械", "制造"]),
    _a_share_seed("601668.SH", "SSE", "中国建筑", "建筑工程", ["基建", "央企"]),
    _a_share_seed("601766.SH", "SSE", "中国中车", "轨道交通设备", ["高端制造", "央企"]),
    _a_share_seed("300274.SZ", "SZSE", "阳光电源", "光伏设备", ["新能源", "电力设备"]),
    _a_share_seed("300760.SZ", "SZSE", "迈瑞医疗", "医疗器械", ["医疗", "器械"]),
    _a_share_seed("000538.SZ", "SZSE", "云南白药", "中药", ["医药", "消费"]),
    _a_share_seed("600196.SH", "SSE", "复星医药", "医药", ["医药", "医疗"]),
]

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
] + ADDITIONAL_A_SHARE_SEEDS


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
        company = _find_company_for_seed(session, seed)

        if company is None:
            company = Company(**seed)
            session.add(company)
        else:
            identity_changed = company.ticker != ticker or company.exchange != exchange
            company.ticker = ticker
            company.exchange = exchange
            company.name = str(seed["name"])
            company.industry = seed["industry"]  # type: ignore[assignment]
            if identity_changed:
                company.description = seed["description"]  # type: ignore[assignment]
                company.listed_date = seed["listed_date"]  # type: ignore[assignment]
                _clear_listing_market_snapshot(company)
            elif _should_replace_seed_description(company.description):
                company.description = seed["description"]  # type: ignore[assignment]
            if not identity_changed and (
                seed["listed_date"] is not None or company.listed_date is None
            ):
                company.listed_date = seed["listed_date"]  # type: ignore[assignment]
            company.tags = seed["tags"]  # type: ignore[assignment]

        companies[(ticker, exchange)] = company

    return companies


def _find_company_for_seed(session: Session, seed: CompanySeed) -> Company | None:
    ticker = str(seed["ticker"])
    exchange = str(seed["exchange"])
    exact_match = session.scalar(
        select(Company).where(Company.ticker == ticker, Company.exchange == exchange)
    )
    if exact_match is not None:
        return exact_match

    seed_priority = MARKET_PRIORITY.get(exchange, 0)
    same_name_companies = session.scalars(
        select(Company).where(Company.name == str(seed["name"]))
    ).all()
    lower_priority_matches = [
        company
        for company in same_name_companies
        if MARKET_PRIORITY.get(company.exchange, 0) < seed_priority
    ]
    if not lower_priority_matches:
        return None

    return max(
        lower_priority_matches,
        key=lambda company: MARKET_PRIORITY.get(company.exchange, 0),
    )


def _clear_listing_market_snapshot(company: Company) -> None:
    company.market_cap = None
    company.current_price = None
    company.pe_ttm = None
    company.pe_dynamic = None
    company.pe_static = None
    company.pb_ratio = None
    company.ps_ratio = None
    company.dividend_yield_ttm = None
    company.dividend_yield_static = None
    company.market_data_source = None
    company.market_data_source_url = None
    company.market_data_updated_at = None


def _should_replace_seed_description(description: str | None) -> bool:
    normalized = (description or "").strip()
    return (
        not normalized
        or "真实公司主数据种子" in normalized
        or "不包含实时行情或投资建议" in normalized
    )
