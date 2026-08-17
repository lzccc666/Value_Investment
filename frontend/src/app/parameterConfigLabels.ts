const MATRIX_LABELS: Record<string, string> = {
  accounting_quality: "会计质量",
  balance_sheet_risk: "资产负债表风险",
  business_quality: "商业质量",
  capital_intensity: "资本密集度",
  cash_flow_growth_rate: "现金流增长率",
  cash_flow_reliability: "现金流可靠性",
  cyclicality: "周期性",
  demand_durability: "需求持续性",
  discount_rate: "折现率",
  execution_quality: "执行质量",
  growth_runway: "增长空间",
  management_quality: "管理质量",
  moat_durability: "护城河持久性",
  owner_earnings_growth_rate: "所有者收益增长率",
  permanent_loss_risk: "永久损失风险",
  pricing_power: "定价权",
  scenario_spread: "情景宽度",
  terminal_growth_rate: "永续增长率"
};

const VALUE_LABELS: Record<string, string> = {
  equal_weight_per_rule: "每条规则等权",
  free_cash_flow_cagr_5y: "五年自由现金流复合增长率",
  free_cash_flow_cagr_3y: "三年自由现金流复合增长率",
  net_profit_cagr_5y: "五年净利润复合增长率",
  net_profit_cagr_3y: "三年净利润复合增长率",
  revenue_cagr_5y: "五年收入复合增长率",
  revenue_cagr_3y: "三年收入复合增长率",
  conservative: "保守情景",
  base: "中性情景",
  optimistic: "乐观情景"
};

export function parameterRiskLabel(risk: "low" | "medium" | "high"): string {
  return { low: "低", medium: "中", high: "高" }[risk];
}

export function parameterValueLabel(value: string): string {
  return VALUE_LABELS[value] ?? "未命名选项";
}

export function parameterValueOptions(path: string): Array<{ value: string; label: string }> {
  if (path === "memo_decision.rule_weight_mode") {
    return [{ value: "equal_weight_per_rule", label: VALUE_LABELS.equal_weight_per_rule }];
  }
  if (path.startsWith("valuation_models.growth_source_priority.")) {
    return [
      "free_cash_flow_cagr_5y",
      "free_cash_flow_cagr_3y",
      "net_profit_cagr_5y",
      "net_profit_cagr_3y",
      "revenue_cagr_5y",
      "revenue_cagr_3y"
    ].map((value) => ({ value, label: VALUE_LABELS[value] }));
  }
  if (path === "price_decision.buy_price_scenario") {
    return ["conservative", "base", "optimistic"].map((value) => ({
      value,
      label: VALUE_LABELS[value]
    }));
  }
  return [];
}

export function matrixParameterLabel(name: string): string {
  return MATRIX_LABELS[name] ?? "未命名指标";
}

export function matrixCoefficientDescription(
  analystName: string,
  ruleLabel: string,
  dimensionName: string,
  coefficient: number,
  calculationRole: string
): string {
  const dimension = matrixParameterLabel(dimensionName);
  const direction = coefficient >= 0
    ? "通过会提高该维度分，不通过会降低该维度分"
    : "通过会降低该维度分，不通过会提高该维度分";
  return `${dimension}贡献 = ${ruleLabel}状态分 × ${formatCoefficient(coefficient)} × ${analystName}权重；${direction}。`;
}

function formatCoefficient(value: number): string {
  return String(Number(value.toFixed(10)));
}

export function calculationRoleLabel(role: string): string {
  return role === "compute" ? "参与计算" : "配置错误";
}
