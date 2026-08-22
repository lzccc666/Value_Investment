import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getPortfolioOwners: vi.fn(),
  createPortfolioOwner: vi.fn(),
  updatePortfolioOwner: vi.fn(),
  deletePortfolioOwner: vi.fn(),
  reorderPortfolioOwners: vi.fn(),
  getPortfolioSnapshots: vi.fn(),
  createPortfolioSnapshot: vi.fn(),
  updatePortfolioSnapshot: vi.fn(),
  deletePortfolioSnapshot: vi.fn(),
  reorderPortfolioSnapshots: vi.fn(),
  getPortfolioHoldings: vi.fn(),
  createPortfolioHolding: vi.fn(),
  updatePortfolioHolding: vi.fn(),
  deletePortfolioHolding: vi.fn(),
  getPortfolioValuation: vi.fn(),
  refreshPortfolioQuotes: vi.fn(),
  searchPortfolioListings: vi.fn(),
  searchAhListingCatalog: vi.fn(),
  importAhListing: vi.fn(),
  searchSecUsListingCatalog: vi.fn(),
  importSecUsListing: vi.fn(),
  getBuyMemoEntries: vi.fn(),
  searchBuyMemoCompanies: vi.fn(),
  getBuyMemoDecisions: vi.fn(),
  createBuyMemoEntry: vi.fn(),
  deleteBuyMemoEntry: vi.fn(),
  getMarketFear: vi.fn(),
  refreshMarketFear: vi.fn()
}));

vi.mock("../services/api", () => api);

import { InvestmentToolsView } from "../app/InvestmentToolsView";

const owner = {
  id: 1,
  name: "李先生",
  owner_type: "investor" as const,
  notes: "公开披露",
  display_order: 0,
  created_at: "2026-08-22T01:00:00Z",
  updated_at: "2026-08-22T01:00:00Z"
};

const snapshot = {
  id: 10,
  owner_id: 1,
  title: "2026 年中持仓",
  as_of_date: "2026-06-30",
  base_currency: "CNY" as const,
  notes: null,
  display_order: 0,
  created_at: "2026-08-22T01:00:00Z",
  updated_at: "2026-08-22T01:00:00Z"
};

const holdings = [
  {
    id: 101,
    snapshot_id: 10,
    listing_id: 21,
    company_id: 8,
    company_name: "阿里巴巴集团",
    ticker: "BABA.US",
    exchange: "NYSE",
    market: "US",
    trading_currency: "USD",
    security_type: "ads",
    quantity: "2.50000000",
    notes: "ADS 持仓",
    display_order: 0,
    created_at: "2026-08-22T01:00:00Z",
    updated_at: "2026-08-22T01:00:00Z"
  },
  {
    id: 102,
    snapshot_id: 10,
    listing_id: 22,
    company_id: 9,
    company_name: "缺失行情公司",
    ticker: "MISS.US",
    exchange: "NASDAQ",
    market: "US",
    trading_currency: "USD",
    security_type: "common_stock",
    quantity: "1.00000000",
    notes: null,
    display_order: 1,
    created_at: "2026-08-22T01:00:00Z",
    updated_at: "2026-08-22T01:00:00Z"
  }
];

function valuation(total = "1000.000000", quantity = "2.50000000", weight = "1.00000000") {
  return {
    snapshot,
    owner,
    priced_total: total,
    base_currency: "CNY" as const,
    holding_count: 2,
    priced_count: 1,
    unpriced_count: 1,
    valuation_status: "incomplete" as const,
    items: [
      {
        holding_id: 101,
        listing_id: 21,
        company_id: 8,
        company_name: "阿里巴巴集团",
        ticker: "BABA.US",
        exchange: "NYSE",
        market: "US",
        trading_currency: "USD",
        security_type: "ads",
        quantity,
        latest_price: "80.000000",
        quote_currency: "USD",
        quote_as_of: "2026-08-21T20:00:00Z",
        quote_source: "Yahoo Finance",
        quote_source_url: "https://example.test/baba",
        local_market_value: "200.000000",
        fx_rate: "5.000000",
        fx_rate_date: "2026-08-21",
        fx_source: "ECB",
        base_market_value: total,
        weight,
        data_status: "priced" as const,
        status_reason: "计价完成"
      },
      {
        holding_id: 102,
        listing_id: 22,
        company_id: 9,
        company_name: "缺失行情公司",
        ticker: "MISS.US",
        exchange: "NASDAQ",
        market: "US",
        trading_currency: "USD",
        security_type: "common_stock",
        quantity: "1.00000000",
        latest_price: null,
        quote_currency: null,
        quote_as_of: null,
        quote_source: null,
        quote_source_url: null,
        local_market_value: null,
        fx_rate: null,
        fx_rate_date: null,
        fx_source: null,
        base_market_value: null,
        weight: null,
        data_status: "missing_price" as const,
        status_reason: "缺少最新行情"
      }
    ]
  };
}

const fearResponse = {
  status: "partial" as const,
  notice: "波动率指标反映市场预期波动程度，不代表价格方向，也不是买卖建议。",
  items: [
    {
      market: "A_SHARE" as const,
      indicator_code: "50ETF QVIX",
      indicator_name: "50ETF QVIX",
      value: "21.560000",
      data_date: "2026-08-21",
      daily_change: "0.320000",
      moving_average_20: "20.880000",
      percentile_3y: "62.5000",
      temperature_score: "62.5000",
      temperature_level: "恐慌",
      source: "AKShare",
      source_url: "https://akshare.akfamily.xyz/",
      fetched_at: "2026-08-22T02:00:00Z",
      observation_count: 756,
      freshness: "fresh" as const,
      refresh_error: null,
      is_proxy: true,
      proxy_notice: "第三方代理指标，非官方统一恐慌指数"
    },
    {
      market: "HK" as const,
      indicator_code: "VHSI",
      indicator_name: "恒生波幅指数 VHSI",
      value: "19.130000",
      data_date: "2026-08-20",
      daily_change: "-0.420000",
      moving_average_20: "18.900000",
      percentile_3y: "48.2000",
      temperature_score: "48.2000",
      temperature_level: "升温",
      source: "恒生指数公司",
      source_url: "https://www.hsi.com.hk/",
      fetched_at: "2026-08-20T02:00:00Z",
      observation_count: 750,
      freshness: "stale" as const,
      refresh_error: "官方数据源暂不可用",
      is_proxy: false,
      proxy_notice: null
    },
    {
      market: "US" as const,
      indicator_code: "VIX",
      indicator_name: "Cboe VIX",
      value: "15.420000",
      data_date: "2026-08-21",
      daily_change: "-0.110000",
      moving_average_20: "16.100000",
      percentile_3y: "31.0000",
      temperature_score: "31.0000",
      temperature_level: "稳定",
      source: "Cboe",
      source_url: "https://www.cboe.com/",
      fetched_at: "2026-08-22T02:00:00Z",
      observation_count: 758,
      freshness: "fresh" as const,
      refresh_error: null,
      is_proxy: false,
      proxy_notice: null
    }
  ]
};

const buyMemoEntry = {
  id: 501,
  company_id: 8,
  source_price_decision_run_id: 901,
  company_name: "阿里巴巴集团",
  listing_ticker: "BABA.US",
  exchange: "NYSE",
  trading_currency: "USD",
  base_intrinsic_value: "132.500000",
  suggested_buy_price: "92.750000",
  designed_safety_margin: "0.300000",
  latest_report_period: "2026Q2",
  price_decision_version_no: 3,
  price_decision_run_version: "price-decision-v1",
  price_decision_created_at: "2026-08-21T02:00:00Z",
  created_at: "2026-08-22T02:00:00Z",
  updated_at: "2026-08-22T02:00:00Z"
};

const buyMemoCompany = {
  company_id: 8,
  company_name: "阿里巴巴集团",
  primary_ticker: "BABA.US",
  decision_count: 2
};

const buyMemoDecisions = [
  {
    price_decision_run_id: 901,
    version_no: 3,
    run_version: "price-decision-v1",
    listing_ticker: "BABA.US",
    exchange: "NYSE",
    trading_currency: "USD",
    base_intrinsic_value: "132.500000",
    suggested_buy_price: "92.750000",
    designed_safety_margin: "0.300000",
    latest_report_period: "2026Q2",
    created_at: "2026-08-21T02:00:00Z",
    already_imported: true
  },
  {
    price_decision_run_id: 900,
    version_no: 2,
    run_version: "price-decision-v1",
    listing_ticker: "BABA.US",
    exchange: "NYSE",
    trading_currency: "USD",
    base_intrinsic_value: "125.000000",
    suggested_buy_price: "87.500000",
    designed_safety_margin: "0.300000",
    latest_report_period: "2026Q1",
    created_at: "2026-05-21T02:00:00Z",
    already_imported: false
  }
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  api.getPortfolioOwners.mockResolvedValue({ items: [], total: 0 });
  api.getPortfolioSnapshots.mockResolvedValue({ owner_id: owner.id, items: [], total: 0 });
  api.getPortfolioHoldings.mockResolvedValue({ snapshot_id: snapshot.id, items: holdings, total: holdings.length });
  api.getPortfolioValuation.mockResolvedValue(valuation());
  api.reorderPortfolioOwners.mockResolvedValue({ items: [owner], total: 1 });
  api.reorderPortfolioSnapshots.mockResolvedValue({ owner_id: owner.id, items: [snapshot], total: 1 });
  api.searchPortfolioListings.mockResolvedValue({ items: [], total: 0 });
  api.searchAhListingCatalog.mockResolvedValue({
    items: [],
    total: 0,
    source: "Eastmoney security suggest directory"
  });
  api.searchSecUsListingCatalog.mockResolvedValue({
    items: [],
    total: 0,
    source: "SEC company_tickers_exchange.json"
  });
  api.getBuyMemoEntries.mockResolvedValue({ items: [buyMemoEntry], total: 1 });
  api.searchBuyMemoCompanies.mockResolvedValue({ items: [buyMemoCompany], total: 1 });
  api.getBuyMemoDecisions.mockResolvedValue({
    company_id: buyMemoCompany.company_id,
    items: buyMemoDecisions,
    total: buyMemoDecisions.length
  });
  api.createBuyMemoEntry.mockResolvedValue({
    ...buyMemoEntry,
    id: 502,
    source_price_decision_run_id: 900,
    price_decision_version_no: 2
  });
  api.deleteBuyMemoEntry.mockResolvedValue({ id: buyMemoEntry.id, deleted: true });
  api.getMarketFear.mockResolvedValue(fearResponse);
  api.refreshMarketFear.mockResolvedValue({ ...fearResponse, status: "success" });
});

describe("InvestmentToolsView", () => {
  it("supports owner and historical snapshot CRUD including copy", async () => {
    api.getPortfolioOwners
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [owner], total: 1 });
    api.createPortfolioOwner.mockResolvedValue(owner);
    api.updatePortfolioOwner.mockResolvedValue({ ...owner, name: "李女士" });
    api.deletePortfolioOwner.mockResolvedValue({ id: owner.id, deleted: true });

    render(<InvestmentToolsView refreshToken={0} />);
    expect(await screen.findByText("先新增持仓人，再创建统计日期快照。")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("新增持仓人"));
    const ownerForm = screen.getByRole("form", { name: "新增持仓人" });
    fireEvent.change(within(ownerForm).getByLabelText("姓名"), { target: { value: "李先生" } });
    fireEvent.change(within(ownerForm).getByLabelText("类型"), { target: { value: "investor" } });
    fireEvent.click(within(ownerForm).getByRole("button", { name: "保存持仓人" }));

    await waitFor(() => expect(api.createPortfolioOwner).toHaveBeenCalledWith({
      name: "李先生",
      owner_type: "investor",
      notes: null
    }));
    expect(await screen.findByText("该持仓人还没有历史快照。")).toBeInTheDocument();

    api.getPortfolioSnapshots.mockResolvedValue({ owner_id: owner.id, items: [snapshot], total: 1 });
    api.createPortfolioSnapshot.mockResolvedValue(snapshot);
    fireEvent.click(screen.getByTitle("创建持仓快照"));
    const snapshotForm = screen.getByRole("form", { name: "创建持仓快照" });
    fireEvent.change(within(snapshotForm).getByLabelText("标题"), { target: { value: snapshot.title } });
    fireEvent.change(within(snapshotForm).getByLabelText("统计日期"), { target: { value: snapshot.as_of_date } });
    fireEvent.click(within(snapshotForm).getByRole("button", { name: "保存快照" }));
    await waitFor(() => expect(api.createPortfolioSnapshot).toHaveBeenCalledWith(
      owner.id,
      expect.objectContaining({ title: snapshot.title, copy_from_snapshot_id: null })
    ));

    expect(await screen.findByRole("heading", { name: snapshot.title })).toBeInTheDocument();
    api.createPortfolioSnapshot.mockResolvedValue({ ...snapshot, id: 11, title: "2026 年末持仓" });
    fireEvent.click(screen.getByTitle("创建持仓快照"));
    const copyForm = screen.getByRole("form", { name: "创建持仓快照" });
    fireEvent.change(within(copyForm).getByLabelText("标题"), { target: { value: "2026 年末持仓" } });
    fireEvent.change(within(copyForm).getByLabelText("复制持仓"), { target: { value: String(snapshot.id) } });
    fireEvent.click(within(copyForm).getByRole("button", { name: "保存快照" }));
    await waitFor(() => expect(api.createPortfolioSnapshot).toHaveBeenLastCalledWith(
      owner.id,
      expect.objectContaining({ copy_from_snapshot_id: snapshot.id })
    ));

    fireEvent.click(screen.getByTitle(`编辑持仓人 ${owner.name}`));
    const editOwnerForm = screen.getByRole("form", { name: "编辑持仓人" });
    fireEvent.change(within(editOwnerForm).getByLabelText("姓名"), { target: { value: "李女士" } });
    fireEvent.click(within(editOwnerForm).getByRole("button", { name: "保存持仓人" }));
    await waitFor(() => expect(api.updatePortfolioOwner).toHaveBeenCalledWith(
      owner.id,
      expect.objectContaining({ name: "李女士" })
    ));

    fireEvent.click(screen.getByTitle(`删除快照 ${snapshot.title}`));
    await waitFor(() => expect(api.deletePortfolioSnapshot).toHaveBeenCalledWith(snapshot.id));
    fireEvent.click(screen.getByTitle(`删除持仓人 ${owner.name}`));
    await waitFor(() => expect(api.deletePortfolioOwner).toHaveBeenCalledWith(owner.id));
  });

  it("keeps valuation and pie synchronized after holding CRUD and quote refresh", async () => {
    api.getPortfolioOwners.mockResolvedValue({ items: [owner], total: 1 });
    api.getPortfolioSnapshots.mockResolvedValue({ owner_id: owner.id, items: [snapshot], total: 1 });
    api.getPortfolioValuation
      .mockResolvedValueOnce(valuation())
      .mockResolvedValue(valuation("3000.000000", "7.50000000"));
    api.updatePortfolioHolding.mockResolvedValue({ ...holdings[0], quantity: "7.50000000" });
    api.deletePortfolioHolding.mockResolvedValue({ id: 101, deleted: true });
    api.createPortfolioHolding.mockResolvedValue(holdings[0]);
    api.refreshPortfolioQuotes.mockResolvedValue({
      snapshot_id: snapshot.id,
      status: "partial",
      succeeded: 1,
      failed: 1,
      quote_results: [],
      fx_results: [],
      valuation: valuation("3600.000000", "7.50000000")
    });
    api.searchPortfolioListings.mockResolvedValue({
      items: [{
        id: 21,
        company_id: 8,
        company_name: "阿里巴巴集团",
        ticker: "BABA.US",
        symbol: "BABA",
        exchange: "NYSE",
        market: "US",
        trading_currency: "USD",
        security_type: "ads",
        is_primary: true
      }],
      total: 1
    });

    render(<InvestmentToolsView refreshToken={0} />);
    expect(await screen.findByText("组合估值不完整，未计价项目不进入总市值和比例分母。")).toBeInTheDocument();
    expect(screen.getByText("缺少行情")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "已计价持仓比例图，共 1 项" })).toHaveStyle({
      background: "conic-gradient(#0f766e 0% 100%)"
    });

    fireEvent.click(screen.getByTitle("编辑 BABA.US 持仓"));
    fireEvent.change(screen.getByLabelText("编辑 BABA.US 持有数量"), { target: { value: "7.5" } });
    fireEvent.click(screen.getByTitle("保存 BABA.US"));
    await waitFor(() => expect(api.updatePortfolioHolding).toHaveBeenCalledWith(101, {
      quantity: "7.5",
      notes: "ADS 持仓"
    }));
    expect((await screen.findAllByText((text) => text.includes("3,000.00"))).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByPlaceholderText("公司名称或证券代码"), { target: { value: "阿里" } });
    const listingOption = await screen.findByRole("option", { name: /阿里巴巴集团.*BABA.US.*NYSE.*ADS/ });
    fireEvent.click(listingOption);
    fireEvent.change(screen.getByLabelText("持有数量"), { target: { value: "1.25" } });
    fireEvent.click(screen.getByRole("button", { name: "添加持仓" }));
    await waitFor(() => expect(api.createPortfolioHolding).toHaveBeenCalledWith(snapshot.id, {
      listing_id: 21,
      quantity: "1.25",
      notes: null
    }));

    fireEvent.click(screen.getByRole("button", { name: "刷新全部行情" }));
    await waitFor(() => expect(api.refreshPortfolioQuotes).toHaveBeenCalledWith(snapshot.id));
    expect(await screen.findByText("行情刷新完成：1 项成功，1 项失败。")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("删除 BABA.US 持仓"));
    await waitFor(() => expect(api.deletePortfolioHolding).toHaveBeenCalledWith(101));
  });

  it("persists owner and snapshot order after drag and drop", async () => {
    const owner2 = { ...owner, id: 2, name: "王先生", display_order: 1 };
    const snapshot2 = { ...snapshot, id: 11, title: "2025 年末持仓", display_order: 1 };
    api.getPortfolioOwners.mockResolvedValue({ items: [owner, owner2], total: 2 });
    api.getPortfolioSnapshots.mockResolvedValue({
      owner_id: owner.id,
      items: [snapshot, snapshot2],
      total: 2
    });
    api.reorderPortfolioOwners.mockResolvedValue({ items: [owner2, owner], total: 2 });
    api.reorderPortfolioSnapshots.mockResolvedValue({
      owner_id: owner.id,
      items: [snapshot2, snapshot],
      total: 2
    });

    render(<InvestmentToolsView refreshToken={0} />);
    const ownerHandle = await screen.findByTitle(`拖动持仓人 ${owner.name} 调整顺序`);
    const ownerTarget = screen.getByTitle(`拖动持仓人 ${owner2.name} 调整顺序`).closest(".directory-row");
    const dataTransfer = { effectAllowed: "none", setData: vi.fn() };
    fireEvent.dragStart(ownerHandle, { dataTransfer });
    fireEvent.dragOver(ownerTarget!);
    fireEvent.drop(ownerTarget!);
    await waitFor(() => expect(api.reorderPortfolioOwners).toHaveBeenCalledWith([owner2.id, owner.id]));

    const snapshotHandle = screen.getByTitle(`拖动快照 ${snapshot.title} 调整顺序`);
    const snapshotTarget = screen.getByTitle(`拖动快照 ${snapshot2.title} 调整顺序`).closest(".directory-row");
    fireEvent.dragStart(snapshotHandle, { dataTransfer });
    fireEvent.dragOver(snapshotTarget!);
    fireEvent.drop(snapshotTarget!);
    await waitFor(() => expect(api.reorderPortfolioSnapshots).toHaveBeenCalledWith(
      owner.id,
      [snapshot2.id, snapshot.id]
    ));
  });

  it("imports a SEC directory candidate directly from the listing dropdown", async () => {
    api.getPortfolioOwners.mockResolvedValue({ items: [owner], total: 1 });
    api.getPortfolioSnapshots.mockResolvedValue({
      owner_id: owner.id,
      items: [snapshot],
      total: 1
    });
    api.searchSecUsListingCatalog.mockResolvedValue({
      items: [{
        cik: "0001234567",
        company_name: "Example Operating Corp",
        symbol: "EXM",
        ticker: "EXM.US",
        exchange: "NYSE"
      }],
      total: 1,
      source: "SEC company_tickers_exchange.json"
    });
    api.importSecUsListing.mockResolvedValue({
      id: 77,
      company_id: 66,
      company_name: "Example Operating Corp",
      ticker: "EXM.US",
      symbol: "EXM",
      exchange: "NYSE",
      market: "US",
      trading_currency: "USD",
      security_type: "common_stock",
      is_primary: true
    });

    render(<InvestmentToolsView refreshToken={0} />);
    const search = await screen.findByPlaceholderText("公司名称或证券代码");
    fireEvent.change(search, { target: { value: "EXM" } });
    const option = await screen.findByRole("option", {
      name: /Example Operating Corp.*EXM.US.*NYSE.*SEC 目录导入/
    });
    fireEvent.click(option);

    await waitFor(() => expect(api.importSecUsListing).toHaveBeenCalledWith({
      cik: "0001234567",
      symbol: "EXM"
    }));
    expect(await screen.findByDisplayValue("Example Operating Corp · EXM.US")).toBeInTheDocument();
  });

  it("imports an A/H directory candidate directly from the listing dropdown", async () => {
    api.getPortfolioOwners.mockResolvedValue({ items: [owner], total: 1 });
    api.getPortfolioSnapshots.mockResolvedValue({
      owner_id: owner.id,
      items: [snapshot],
      total: 1
    });
    api.searchAhListingCatalog.mockResolvedValue({
      items: [{
        quote_id: "116.03750",
        company_name: "宁德时代",
        symbol: "03750",
        ticker: "03750.HK",
        exchange: "HKEX",
        market: "HK",
        trading_currency: "HKD",
        security_type: "common_stock"
      }],
      total: 1,
      source: "Eastmoney security suggest directory"
    });
    api.importAhListing.mockResolvedValue({
      id: 88,
      company_id: 18,
      company_name: "宁德时代",
      ticker: "03750.HK",
      symbol: "03750",
      exchange: "HKEX",
      market: "HK",
      trading_currency: "HKD",
      security_type: "common_stock",
      is_primary: false
    });

    render(<InvestmentToolsView refreshToken={0} />);
    const search = await screen.findByPlaceholderText("公司名称或证券代码");
    fireEvent.change(search, { target: { value: "宁德" } });
    const option = await screen.findByRole("option", {
      name: /宁德时代.*03750.HK.*HKEX.*HKD.*A\/H 证券目录导入/
    });
    fireEvent.click(option);

    await waitFor(() => expect(api.importAhListing).toHaveBeenCalledWith({
      quote_id: "116.03750"
    }));
    expect(await screen.findByDisplayValue("宁德时代 · 03750.HK")).toBeInTheDocument();
  });

  it("shows the top ten holdings plus other in the pie while retaining every detail row", async () => {
    const base = valuation().items[0];
    const totalWeight = 78;
    const manyItems = Array.from({ length: 12 }, (_, index) => {
      const rankValue = 12 - index;
      return {
        ...base,
        holding_id: 200 + index,
        listing_id: 300 + index,
        company_id: 400 + index,
        company_name: `公司 ${index + 1}`,
        ticker: `T${index + 1}.US`,
        symbol: `T${index + 1}`,
        quantity: "1.00000000",
        latest_price: String(rankValue),
        local_market_value: String(rankValue),
        fx_rate: "1.000000",
        base_market_value: String(rankValue),
        weight: String(rankValue / totalWeight),
        data_status: "priced" as const,
        status_reason: "计价完成"
      };
    });
    api.getPortfolioOwners.mockResolvedValue({ items: [owner], total: 1 });
    api.getPortfolioSnapshots.mockResolvedValue({ owner_id: owner.id, items: [snapshot], total: 1 });
    api.getPortfolioValuation.mockResolvedValue({
      ...valuation(),
      priced_total: String(totalWeight),
      holding_count: 12,
      priced_count: 12,
      unpriced_count: 0,
      valuation_status: "complete",
      items: manyItems
    });

    render(<InvestmentToolsView refreshToken={0} />);
    const legend = await screen.findByLabelText("持仓比例图例");
    expect(legend.querySelectorAll(":scope > div")).toHaveLength(11);
    expect(within(legend).getByText("公司 10 · T10.US")).toBeInTheDocument();
    expect(within(legend).queryByText("公司 11 · T11.US")).not.toBeInTheDocument();
    expect(within(legend).getByText("其他")).toBeInTheDocument();

    const detailSection = screen.getByRole("heading", { name: "持仓明细" }).closest("section");
    expect(detailSection).not.toBeNull();
    expect(within(detailSection!).getAllByRole("row")).toHaveLength(13);
    expect(within(detailSection!).getByText("公司 12")).toBeInTheDocument();
  });

  it("imports an 011 result into the buy memo table and deletes an entry", async () => {
    render(<InvestmentToolsView refreshToken={0} />);
    fireEvent.click(screen.getByRole("tab", { name: "买入备忘录" }));

    expect(await screen.findByRole("heading", { name: "买入备忘录" })).toBeInTheDocument();
    expect(screen.getByText("阿里巴巴集团")).toBeInTheDocument();
    expect(screen.getByText("BABA.US · NYSE")).toBeInTheDocument();
    expect(screen.getByText("US$132.50")).toBeInTheDocument();
    expect(screen.getByText("US$92.75")).toBeInTheDocument();
    expect(screen.getByText("30.00%")).toBeInTheDocument();
    expect(screen.getByText("2026Q2")).toBeInTheDocument();
    expect(screen.getByText("V3")).toBeInTheDocument();

    await waitFor(() => expect(api.getBuyMemoDecisions).toHaveBeenCalledWith(8, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "导入结果" }));
    await waitFor(() => expect(api.createBuyMemoEntry).toHaveBeenCalledWith(900));
    expect(await screen.findByText("011 投资决策结果已导入买入备忘录。")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("删除 阿里巴巴集团 买入备忘录"));
    await waitFor(() => expect(api.deleteBuyMemoEntry).toHaveBeenCalledWith(501));
  });

  it("explains when every 011 version for a company is already imported", async () => {
    api.getBuyMemoDecisions.mockResolvedValue({
      company_id: buyMemoCompany.company_id,
      items: [buyMemoDecisions[0]],
      total: 1
    });

    render(<InvestmentToolsView refreshToken={0} />);
    fireEvent.click(screen.getByRole("tab", { name: "买入备忘录" }));

    expect(await screen.findByRole("option", { name: "该公司全部版本已导入" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入结果" })).toBeDisabled();
  });

  it("shows three market sources, stale cache, proxy notice, and refresh actions", async () => {
    render(<InvestmentToolsView refreshToken={0} />);
    fireEvent.click(screen.getByRole("tab", { name: "市场温度" }));

    expect(await screen.findByText("三市场波动率温度")).toBeInTheDocument();
    expect(screen.getByText("Cboe VIX")).toBeInTheDocument();
    expect(screen.getByText("恒生波幅指数 VHSI")).toBeInTheDocument();
    expect(screen.getAllByText("50ETF QVIX").length).toBeGreaterThan(0);
    expect(screen.getByText("第三方代理指标，非官方统一恐慌指数")).toBeInTheDocument();
    expect(screen.getByText("官方数据源暂不可用")).toBeInTheDocument();
    expect(screen.getByText("已过期")).toBeInTheDocument();
    expect(screen.getByText(fearResponse.notice)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("刷新 港股 指标"));
    await waitFor(() => expect(api.refreshMarketFear).toHaveBeenCalledWith("HK"));
    fireEvent.click(screen.getByRole("button", { name: "刷新全部指标" }));
    await waitFor(() => expect(api.refreshMarketFear).toHaveBeenCalledWith(undefined));
  });
});
