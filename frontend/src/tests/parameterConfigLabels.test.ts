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

  it("treats every configured rule as a compute coefficient", () => {
    expect(
      matrixCoefficientDescription("李录", "永久损失韧性", "permanent_loss_risk", 1, "compute")
    ).toContain("永久损失风险贡献");
  });
});
