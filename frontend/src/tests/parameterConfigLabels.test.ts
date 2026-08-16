import { describe, expect, it } from "vitest";

import { matrixCoefficientDescription } from "../app/parameterConfigLabels";

describe("parameter configuration copy", () => {
  it("explains a compute coefficient with its exact rule, dimension and direction", () => {
    expect(
      matrixCoefficientDescription("巴菲特", "护城河", "business_quality", 0.8, "compute")
    ).toBe(
      "商业质量贡献 = 护城河状态分 × 0.8 × 巴菲特权重；通过会提高该维度分，不通过会降低该维度分。"
    );
  });

  it("explains why a price-reference coefficient is disabled", () => {
    expect(
      matrixCoefficientDescription("格雷厄姆", "估值纪律", "permanent_loss_risk", 0.8, "price_reference")
    ).toContain("不进入 010 估值计算");
  });
});
