from datetime import date
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.migrations import run_schema_migrations
from app.db.models import Company, MarketSnapshot, SecurityListing
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

SEC_CIK_BY_TICKER = {
    "AAPL.US": "0000320193",
    "BRK.B.US": "0001067983",
    "GOOGL.US": "0001652044",
    "AXP.US": "0000004962",
    "BAC.US": "0000070858",
    "CVX.US": "0000093410",
    "CB.US": "0000896159",
    "MCO.US": "0001059556",
    "KHC.US": "0001637459",
    "DAL.US": "0000027904",
    "SIRI.US": "0000908937",
    "CRDO.US": "0001807794",
    "PDD.US": "0001737806",
    "CRCL.US": "0001876042",
    "OXY.US": "0000797468",
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


def _us_seed(
    ticker: str,
    exchange: str,
    name: str,
    industry: str,
    chinese_name: str,
    tags: list[str],
) -> CompanySeed:
    return {
        "ticker": ticker,
        "exchange": exchange,
        "name": f"{name} {chinese_name}",
        "industry": industry,
        "description": f"美股{industry}公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", *tags],
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
    _a_share_seed("002832.SZ", "SZSE", "比音勒芬", "服装", ["服装", "消费", "高端品牌"]),
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
    _us_seed(
        "AXP.US", "NYSE", "American Express Company", "消费金融", "美国运通", ["金融", "支付"]
    ),
    _us_seed(
        "BAC.US", "NYSE", "Bank of America Corporation", "银行", "美国银行", ["金融", "银行"]
    ),
    _us_seed(
        "CVX.US", "NYSE", "Chevron Corporation", "石油天然气", "雪佛龙", ["能源", "石油天然气"]
    ),
    _us_seed(
        "CB.US", "NYSE", "Chubb Limited", "保险", "安达保险", ["金融", "保险"]
    ),
    _us_seed(
        "MCO.US", "NYSE", "Moody's Corporation", "金融信息服务", "穆迪", ["评级", "金融数据"]
    ),
    _us_seed(
        "KHC.US", "NASDAQ", "The Kraft Heinz Company", "食品", "卡夫亨氏", ["食品饮料", "消费"]
    ),
    _us_seed(
        "DAL.US", "NYSE", "Delta Air Lines, Inc.", "航空运输", "达美航空", ["航空", "运输"]
    ),
    _us_seed(
        "SIRI.US", "NASDAQ", "Sirius XM Holdings Inc.", "卫星广播", "天狼星XM", ["媒体", "订阅服务"]
    ),
    _us_seed(
        "CRDO.US",
        "NASDAQ",
        "Credo Technology Group Holding Ltd",
        "半导体",
        "Credo",
        ["芯片", "高速连接"],
    ),
    {
        "ticker": "PDD.US",
        "exchange": "NASDAQ",
        "name": "PDD Holdings Inc. 拼多多",
        "industry": "互联网零售",
        "description": "美股电商平台 ADS，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "ADS", "电商"],
    },
    {
        "ticker": "CRCL.US",
        "exchange": "NYSE",
        "name": "Circle Internet Group, Inc. Circle",
        "industry": "金融科技",
        "description": "美股金融科技公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "金融科技", "支付"],
    },
    {
        "ticker": "09992.HK",
        "exchange": "HKEX",
        "name": "POP MART INTERNATIONAL GROUP LIMITED 泡泡玛特",
        "industry": "潮流玩具",
        "description": "港股潮流玩具公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["港股", "消费", "潮流玩具"],
    },
    {
        "ticker": "OXY.US",
        "exchange": "NYSE",
        "name": "Occidental Petroleum Corporation 西方石油",
        "industry": "石油天然气",
        "description": "美股石油天然气公司，真实公司主数据种子；不包含实时行情或投资建议。",
        "listed_date": None,
        "status": "未研究",
        "tags": ["美股", "能源", "石油天然气"],
    },
] + ADDITIONAL_A_SHARE_SEEDS


def init_db(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=database_engine)
    run_schema_migrations(database_engine)

    with Session(database_engine) as session:
        seed_db(session)


def seed_db(session: Session) -> None:
    companies = _upsert_company_seeds(session, REAL_COMPANY_SEEDS)
    _upsert_additional_listings(session, companies)
    session.commit()


def _upsert_additional_listings(
    session: Session, companies: dict[tuple[str, str], Company]
) -> None:
    alibaba = companies.get(("09988.HK", "HKEX"))
    if alibaba is not None:
        _upsert_secondary_listing(
            session,
            company=alibaba,
            ticker="BABA.US",
            exchange="NYSE",
            symbol="BABA",
            security_type="ads",
            listed_date=date(2014, 9, 19),
            underlying_shares_per_listing_unit=8.0,
            provider_identifiers={
                "sec_cik": "0001577552",
                "sec_ticker": "BABA",
                "ads_ratio_source": "alibaba_investor_information",
            },
        )
    berkshire = companies.get(("BRK.B.US", "NYSE"))
    if berkshire is not None:
        _upsert_secondary_listing(
            session,
            company=berkshire,
            ticker="BRK.A.US",
            exchange="NYSE",
            symbol="BRK.A",
            security_type="common_stock",
            listed_date=None,
            underlying_shares_per_listing_unit=1.0,
            provider_identifiers={
                "sec_cik": "0001067983",
                "sec_ticker": "BRK-A",
            },
        )
    alphabet = companies.get(("GOOGL.US", "NASDAQ"))
    if alphabet is not None:
        _upsert_secondary_listing(
            session,
            company=alphabet,
            ticker="GOOG.US",
            exchange="NASDAQ",
            symbol="GOOG",
            security_type="common_stock",
            listed_date=None,
            underlying_shares_per_listing_unit=1.0,
            provider_identifiers={
                "sec_cik": "0001652044",
                "sec_ticker": "GOOG",
            },
        )


def _upsert_secondary_listing(
    session: Session,
    *,
    company: Company,
    ticker: str,
    exchange: str,
    symbol: str,
    security_type: str,
    listed_date: date | None,
    underlying_shares_per_listing_unit: float,
    provider_identifiers: dict[str, object],
) -> None:
    listing = session.scalar(
        select(SecurityListing).where(
            SecurityListing.ticker == ticker,
            SecurityListing.exchange == exchange,
        )
    )
    market, trading_currency = _listing_market_currency(exchange)
    values = {
        "company_id": company.id,
        "symbol": symbol,
        "market": market,
        "trading_currency": trading_currency,
        "security_type": security_type,
        "listed_date": listed_date,
        "is_active": True,
        "underlying_shares_per_listing_unit": underlying_shares_per_listing_unit,
        "provider_identifiers": provider_identifiers,
    }
    if listing is None:
        session.add(
            SecurityListing(
                ticker=ticker,
                exchange=exchange,
                is_primary=False,
                **values,
            )
        )
        return
    for field_name, value in values.items():
        setattr(listing, field_name, value)


def _upsert_company_seeds(
    session: Session, seeds: list[CompanySeed]
) -> dict[tuple[str, str], Company]:
    companies: dict[tuple[str, str], Company] = {}

    for seed in seeds:
        ticker = str(seed["ticker"])
        exchange = str(seed["exchange"])
        issuer_defaults = _issuer_defaults(seed)
        company = _find_company_for_seed(session, seed, issuer_defaults["canonical_key"])

        if company is None:
            company = Company(**seed, **issuer_defaults)
            session.add(company)
            session.flush()
        else:
            identity_changed = company.ticker != ticker or company.exchange != exchange
            company.name = str(seed["name"])
            company.canonical_key = str(issuer_defaults["canonical_key"])
            if not company.legal_name:
                company.legal_name = str(issuer_defaults["legal_name"])
            if not company.aliases:
                company.aliases = list(issuer_defaults["aliases"])
            if not company.domicile_country:
                company.domicile_country = str(issuer_defaults["domicile_country"])
            if not company.reporting_currency:
                company.reporting_currency = str(issuer_defaults["reporting_currency"])
            if not company.fiscal_year_end:
                company.fiscal_year_end = str(issuer_defaults["fiscal_year_end"])
            company.external_ids = {
                **dict(issuer_defaults["external_ids"]),
                **dict(company.external_ids or {}),
            }
            company.industry = seed["industry"]  # type: ignore[assignment]
            if identity_changed:
                company.description = seed["description"]  # type: ignore[assignment]
            elif _should_replace_seed_description(company.description):
                company.description = seed["description"]  # type: ignore[assignment]
            if not identity_changed and (
                seed["listed_date"] is not None or company.listed_date is None
            ):
                company.listed_date = seed["listed_date"]  # type: ignore[assignment]
            company.tags = seed["tags"]  # type: ignore[assignment]

        listing = _upsert_seed_listing(session, company, seed)
        _set_primary_listing(session, company, listing)

        companies[(ticker, exchange)] = company

    return companies


def _find_company_for_seed(
    session: Session, seed: CompanySeed, canonical_key: object
) -> Company | None:
    ticker = str(seed["ticker"])
    exchange = str(seed["exchange"])
    exact_match = session.scalar(
        select(Company).where(Company.ticker == ticker, Company.exchange == exchange)
    )
    if exact_match is not None:
        return exact_match
    return session.scalar(select(Company).where(Company.canonical_key == str(canonical_key)))


def _upsert_seed_listing(
    session: Session, company: Company, seed: CompanySeed
) -> SecurityListing:
    ticker = str(seed["ticker"]).strip().upper()
    exchange = str(seed["exchange"]).strip().upper()
    listing = session.scalar(
        select(SecurityListing).where(
            SecurityListing.ticker == ticker,
            SecurityListing.exchange == exchange,
        )
    )
    market, currency = _listing_market_currency(exchange)
    provider_identifiers = _seed_provider_identifiers(ticker)
    security_type = "ads" if ticker == "PDD.US" else "common_stock"
    underlying_shares = 4.0 if ticker == "PDD.US" else 1.0
    if listing is None:
        listing = SecurityListing(
            company_id=company.id,
            ticker=ticker,
            symbol=ticker.rsplit(".", 1)[0],
            exchange=exchange,
            market=market,
            trading_currency=currency,
            security_type=security_type,
            listed_date=seed["listed_date"],
            is_primary=False,
            is_active=True,
            underlying_shares_per_listing_unit=underlying_shares,
            provider_identifiers=provider_identifiers,
        )
        session.add(listing)
        session.flush()
    else:
        listing.company_id = company.id
        listing.symbol = ticker.rsplit(".", 1)[0]
        listing.market = market
        listing.trading_currency = currency
        listing.security_type = security_type
        listing.is_active = True
        listing.underlying_shares_per_listing_unit = underlying_shares
        listing.provider_identifiers = provider_identifiers
        if seed["listed_date"] is not None or listing.listed_date is None:
            listing.listed_date = seed["listed_date"]  # type: ignore[assignment]
    return listing


def _set_primary_listing(
    session: Session, company: Company, listing: SecurityListing
) -> None:
    current_primary = session.scalar(
        select(SecurityListing).where(
            SecurityListing.company_id == company.id,
            SecurityListing.is_primary.is_(True),
            SecurityListing.is_active.is_(True),
        )
    )
    if current_primary is not None and current_primary.id != listing.id:
        current_priority = MARKET_PRIORITY.get(current_primary.exchange, 0)
        next_priority = MARKET_PRIORITY.get(listing.exchange, 0)
        if current_priority > next_priority:
            _sync_company_compatibility_mirror(session, company, current_primary)
            return
        current_primary.is_primary = False
        session.flush()

    listing.is_primary = True
    _sync_company_compatibility_mirror(session, company, listing)


def _sync_company_compatibility_mirror(
    session: Session, company: Company, listing: SecurityListing
) -> None:
    identity_changed = company.ticker != listing.ticker or company.exchange != listing.exchange
    company.ticker = listing.ticker
    company.exchange = listing.exchange
    company.listed_date = listing.listed_date
    latest_snapshot = session.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.listing_id == listing.id)
        .order_by(MarketSnapshot.fetched_at.desc(), MarketSnapshot.id.desc())
        .limit(1)
    )
    if latest_snapshot is None:
        if identity_changed:
            _clear_listing_market_snapshot(company)
        return
    company.market_cap = latest_snapshot.market_cap
    company.current_price = latest_snapshot.price
    company.pe_ttm = latest_snapshot.pe_ttm
    company.pe_dynamic = latest_snapshot.pe_dynamic
    company.pe_static = latest_snapshot.pe_static
    company.pb_ratio = latest_snapshot.pb_ratio
    company.ps_ratio = latest_snapshot.ps_ratio
    company.dividend_yield_ttm = latest_snapshot.dividend_yield_ttm
    company.dividend_yield_static = latest_snapshot.dividend_yield_static
    company.market_data_source = latest_snapshot.source
    company.market_data_source_url = latest_snapshot.source_url
    company.market_data_updated_at = latest_snapshot.fetched_at


def _issuer_defaults(seed: CompanySeed) -> dict[str, object]:
    ticker = str(seed["ticker"]).strip().upper()
    exchange = str(seed["exchange"]).strip().upper()
    canonical_key = {
        "00700.HK": "tencent-holdings",
        "09988.HK": "alibaba-group",
        "600941.SH": "china-mobile",
        "AAPL.US": "apple-inc",
        "GOOGL.US": "alphabet-inc",
        "AXP.US": "american-express",
        "BAC.US": "bank-of-america",
        "CVX.US": "chevron-corporation",
        "CB.US": "chubb-limited",
        "MCO.US": "moodys-corporation",
        "KHC.US": "kraft-heinz",
        "DAL.US": "delta-air-lines",
        "SIRI.US": "sirius-xm-holdings",
        "CRDO.US": "credo-technology-group",
        "PDD.US": "pdd-holdings",
        "CRCL.US": "circle-internet-group",
        "09992.HK": "pop-mart-international",
        "OXY.US": "occidental-petroleum",
    }.get(ticker, f"issuer-{exchange.lower()}-{ticker.lower().replace('.', '-')}")
    market, trading_currency = _listing_market_currency(exchange)
    reporting_currency = trading_currency
    if ticker in {"00700.HK", "09988.HK", "01810.HK", "03690.HK"}:
        reporting_currency = "CNY"
    domicile = {"A_SHARE": "CN", "HK": "HK", "US": "US"}.get(market, "ZZ")
    name = str(seed["name"])
    search_aliases = {
        "09988.HK": ["阿里巴巴", "Alibaba", "Alibaba Group"],
        "BRK.B.US": [
            "Berkshire Hathaway",
            "伯克希尔",
            "伯克希尔哈撒韦",
        ],
        "GOOGL.US": ["Alphabet", "Google", "谷歌", "GOOG", "GOOGL"],
        "AXP.US": ["American Express", "AmEx", "美国运通", "AXP"],
        "BAC.US": ["Bank of America", "BofA", "美国银行", "美银", "BAC"],
        "CVX.US": ["Chevron", "雪佛龙", "CVX"],
        "CB.US": ["Chubb", "安达", "安达保险", "CB"],
        "MCO.US": ["Moody's", "Moodys", "穆迪", "MCO"],
        "KHC.US": ["Kraft Heinz", "卡夫亨氏", "KHC"],
        "DAL.US": ["Delta Air Lines", "Delta", "达美航空", "DAL"],
        "SIRI.US": ["Sirius XM", "SiriusXM", "天狼星XM", "SIRI"],
        "CRDO.US": ["Credo", "Credo Technology", "CRDO"],
        "PDD.US": ["PDD Holdings", "Pinduoduo", "拼多多", "拼多多控股", "PDD"],
        "CRCL.US": ["Circle", "Circle Internet Group", "circl", "CRCL"],
        "09992.HK": ["泡泡玛特", "POP MART", "Pop Mart International Group", "09992"],
        "OXY.US": ["Occidental Petroleum", "西方石油", "OXY"],
    }
    return {
        "canonical_key": canonical_key,
        "legal_name": name,
        "aliases": list(dict.fromkeys([name, *search_aliases.get(ticker, [])])),
        "domicile_country": domicile,
        "reporting_currency": reporting_currency,
        "fiscal_year_end": {
            "09988.HK": "03-31",
            "AAPL.US": "09-26",
        }.get(ticker, "12-31"),
        "external_ids": _seed_external_ids(ticker),
    }


def _listing_market_currency(exchange: str) -> tuple[str, str]:
    if exchange in {"SSE", "SZSE", "BSE"}:
        return "A_SHARE", "CNY"
    if exchange == "HKEX":
        return "HK", "HKD"
    if exchange in {"NASDAQ", "NYSE", "AMEX"}:
        return "US", "USD"
    return "OTHER", "XXX"


def _seed_provider_identifiers(ticker: str) -> dict[str, object]:
    if ticker == "00700.HK":
        return {"hkex_stock_id": "7609", "eastmoney_symbol": "00700"}
    sec_cik = SEC_CIK_BY_TICKER.get(ticker)
    if sec_cik:
        return {"sec_cik": sec_cik, "sec_ticker": ticker.removesuffix(".US")}
    if ticker == "09992.HK":
        return {"eastmoney_symbol": "09992"}
    return {}


def _seed_external_ids(ticker: str) -> dict[str, object]:
    if ticker == "09988.HK":
        return {"sec_cik": "0001577552"}
    sec_cik = SEC_CIK_BY_TICKER.get(ticker)
    if sec_cik:
        return {"sec_cik": sec_cik}
    return {}


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
