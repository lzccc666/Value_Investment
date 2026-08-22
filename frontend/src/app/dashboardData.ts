import {
  BarChart3,
  BookOpenText,
  Building2,
  Calculator,
  ClipboardList,
  DatabaseZap,
  FileText,
  Gauge,
  Newspaper,
  Scale,
  Search,
  SlidersHorizontal,
  UsersRound
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { CompanyWorkspaceSection } from "./CompanyWorkspaceView";

export type NavItem = {
  id: NavItemId;
  label: string;
  icon: LucideIcon;
};

export type NavItemId =
  | "dashboard"
  | "company-search"
  | "company-workspace"
  | "financials"
  | "announcements"
  | "evidence"
  | "analyst-views"
  | "memo"
  | "valuation-lab"
  | "price-decision"
  | "investment-tools"
  | "parameter-config"
  | "data-management";

export type Metric = {
  label: string;
  value: string;
  trend: string;
  tone: "green" | "blue" | "amber";
  valueStyle?: "standard" | "compact";
};

export type ResearchModule = {
  code: string;
  name: string;
  description: string;
  section: CompanyWorkspaceSection;
  icon: LucideIcon;
};

export const navigationItems: NavItem[] = [
  { id: "dashboard", label: "概览", icon: ClipboardList },
  { id: "company-search", label: "公司搜索", icon: Search },
  { id: "company-workspace", label: "公司工作台", icon: Building2 },
  { id: "financials", label: "财务底稿", icon: BarChart3 },
  { id: "announcements", label: "公司公告", icon: Newspaper },
  { id: "evidence", label: "外部证据", icon: BookOpenText },
  { id: "analyst-views", label: "分析师视角", icon: UsersRound },
  { id: "memo", label: "投资备忘录", icon: FileText },
  { id: "valuation-lab", label: "估值实验室", icon: Calculator },
  { id: "price-decision", label: "价格决策", icon: Scale },
  { id: "investment-tools", label: "投资小工具", icon: Gauge },
  { id: "parameter-config", label: "参数配置", icon: SlidersHorizontal },
  { id: "data-management", label: "数据管理", icon: DatabaseZap }
];

export const researchModules: ResearchModule[] = [
  {
    code: "004",
    name: "公司档案",
    description: "公司主数据与研究准备度",
    section: "overview",
    icon: Building2
  },
  {
    code: "005",
    name: "财务底稿",
    description: "60 期报表与财务证据包",
    section: "financials",
    icon: BarChart3
  },
  {
    code: "006",
    name: "公告",
    description: "公告同步、正文与摘要",
    section: "announcements",
    icon: Newspaper
  },
  {
    code: "007",
    name: "外部证据",
    description: "外部搜索、诊断与证据入库",
    section: "evidence",
    icon: BookOpenText
  },
  {
    code: "008",
    name: "分析师视角",
    description: "8 个 Profile 与 32 条规则",
    section: "analyst-views",
    icon: UsersRound
  },
  {
    code: "009",
    name: "投资备忘录",
    description: "多视角汇总与版本管理",
    section: "memo",
    icon: FileText
  },
  {
    code: "010",
    name: "无锚定估值",
    description: "五模型估值与参数复核",
    section: "valuation-lab",
    icon: Calculator
  },
  {
    code: "011",
    name: "价格对照与投资决策",
    description: "安全边际、价格区间与价格状态",
    section: "price-decision",
    icon: Scale
  }
];
