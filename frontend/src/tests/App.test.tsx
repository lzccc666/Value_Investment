import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const company = {
    id: 1,
    ticker: "VI0001",
    exchange: "SIM",
    name: "护城河消费样本",
    industry: "消费品",
    description: "用于验证公司搜索和档案入口的本地示例公司。",
    listed_date: "2018-01-15",
    status: "重点跟踪",
    tags: ["护城河", "高ROIC"],
    created_at: "2026-08-09T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z"
  };

  return {
    company,
    getHealth: vi.fn(),
    getCompanies: vi.fn(),
    getCompany: vi.fn()
  };
});

vi.mock("../services/api", () => ({
  getHealth: mocks.getHealth,
  getCompanies: mocks.getCompanies,
  getCompany: mocks.getCompany
}));

import { App } from "../app/App";

beforeEach(() => {
  mocks.getHealth.mockResolvedValue({
    status: "ok",
    service: "Value Investment API",
    version: "0.1.0",
    environment: "development",
    checked_at: "2026-01-01T00:00:00Z"
  });
  mocks.getCompanies.mockResolvedValue({
    items: [mocks.company],
    total: 1,
    limit: 20,
    offset: 0
  });
  mocks.getCompany.mockResolvedValue(mocks.company);
  mocks.getHealth.mockClear();
  mocks.getCompanies.mockClear();
  mocks.getCompany.mockClear();
});

describe("App", () => {
  it("renders the dashboard shell", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "价值投资研究工作台" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(await screen.findByText("Value Investment API 0.1.0")).toBeInTheDocument();
  });

  it("opens company search and company workspace", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Company Search" }));

    expect(await screen.findByRole("heading", { name: "公司搜索", level: 2 })).toBeInTheDocument();
    expect(await screen.findByText("护城河消费样本")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "档案" }));

    await waitFor(() => {
      expect(mocks.getCompany).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    });

    expect(await screen.findByRole("heading", { name: "公司档案", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("基础档案")).toBeInTheDocument();
  });
});
