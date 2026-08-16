import {
  BarChart3,
  BookOpenText,
  Building2,
  Calculator,
  ClipboardList,
  FileText,
  Newspaper,
  Scale,
  Search,
  UsersRound
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { CompanyWorkspaceSection } from "./CompanyWorkspaceView";

export type NavItem = {
  label: string;
  icon: LucideIcon;
};

export type Metric = {
  label: string;
  value: string;
  trend: string;
  tone: "green" | "blue" | "amber";
  valueStyle?: "standard" | "compact";
};

export type ResearchModule = {
  code: string;
  label: string;
  name: string;
  description: string;
  section: CompanyWorkspaceSection;
  icon: LucideIcon;
};

export const navigationItems: NavItem[] = [
  { label: "Dashboard", icon: ClipboardList },
  { label: "Company Search", icon: Search },
  { label: "Company Workspace", icon: Building2 },
  { label: "Financials", icon: BarChart3 },
  { label: "Announcements", icon: Newspaper },
  { label: "Evidence", icon: BookOpenText },
  { label: "Analyst Views", icon: UsersRound },
  { label: "Memo", icon: FileText },
  { label: "Valuation Lab", icon: Calculator },
  { label: "Price Decision", icon: Scale }
];

export const researchModules: ResearchModule[] = [
  {
    code: "004",
    label: "Company Workspace",
    name: "公司档案",
    description: "公司主数据与研究准备度",
    section: "overview",
    icon: Building2
  },
  {
    code: "005",
    label: "Financials",
    name: "财务底稿",
    description: "60 期报表与财务证据包",
    section: "financials",
    icon: BarChart3
  },
  {
    code: "006",
    label: "Announcements",
    name: "公告",
    description: "公告同步、正文与摘要",
    section: "announcements",
    icon: Newspaper
  },
  {
    code: "007",
    label: "Evidence",
    name: "外部证据",
    description: "外部搜索、诊断与证据入库",
    section: "evidence",
    icon: BookOpenText
  },
  {
    code: "008",
    label: "Analyst Views",
    name: "分析师视角",
    description: "10 个 Profile 与 40 条规则",
    section: "analyst-views",
    icon: UsersRound
  },
  {
    code: "009",
    label: "Memo",
    name: "投资备忘录",
    description: "多视角汇总与版本管理",
    section: "memo",
    icon: FileText
  },
  {
    code: "010",
    label: "Valuation Lab",
    name: "无锚定估值",
    description: "五模型估值与参数复核",
    section: "valuation-lab",
    icon: Calculator
  },
  {
    code: "011",
    label: "Price Decision",
    name: "价格对照与投资决策",
    description: "安全边际、价格区间与行动建议",
    section: "price-decision",
    icon: Scale
  }
];
