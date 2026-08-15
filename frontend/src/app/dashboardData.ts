import {
  BarChart3,
  Bell,
  BookOpenText,
  BriefcaseBusiness,
  Building2,
  Calculator,
  ClipboardList,
  FileText,
  Newspaper,
  Search,
  Settings,
  UsersRound
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  label: string;
  icon: LucideIcon;
  active?: boolean;
};

export type Metric = {
  label: string;
  value: string;
  trend: string;
  tone: "green" | "blue" | "amber" | "red";
};

export type QueueItem = {
  title: string;
  meta: string;
  priority: "高" | "中" | "低";
};

export const navigationItems: NavItem[] = [
  { label: "Dashboard", icon: ClipboardList, active: true },
  { label: "Company Search", icon: Search },
  { label: "Company Workspace", icon: Building2 },
  { label: "Financials", icon: BarChart3 },
  { label: "Announcements", icon: Newspaper },
  { label: "Evidence", icon: BookOpenText },
  { label: "Analyst Views", icon: UsersRound },
  { label: "Memo", icon: FileText },
  { label: "Valuation Lab", icon: Calculator },
  { label: "Portfolio", icon: BriefcaseBusiness },
  { label: "Settings", icon: Settings }
];

export const metrics: Metric[] = [
  { label: "研究池", value: "0", trend: "待导入公司", tone: "green" },
  { label: "持仓", value: "0", trend: "待建立组合", tone: "blue" },
  { label: "待复核", value: "0", trend: "公告与假设", tone: "amber" },
  { label: "风险提醒", value: "0", trend: "未触发", tone: "red" }
];

export const researchQueues: QueueItem[] = [
  { title: "公司基础资料", meta: "003 后建立数据库后接入", priority: "中" },
  { title: "财务指标导入", meta: "005 对接 CSV/Excel", priority: "低" },
  { title: "公告文本处理", meta: "006 建立摘要与风险提示", priority: "低" }
];

export const hypothesisQueues: QueueItem[] = [
  { title: "护城河是否稳定", meta: "等待证据绑定", priority: "中" },
  { title: "现金流质量是否持续", meta: "等待财务数据", priority: "中" },
  { title: "估值是否有安全边际", meta: "等待估值实验室", priority: "低" }
];

export const analystViews = [
  "巴菲特",
  "彼得林奇",
  "格雷厄姆",
  "费雪",
  "林园"
];

export const evidenceBands = [
  { label: "证据", icon: BookOpenText },
  { label: "推理", icon: ClipboardList },
  { label: "反证", icon: Bell }
];
