import { afterEach, describe, expect, it, vi } from "vitest";

import { summarizeCompanyAnnouncements } from "../services/api";

describe("api service errors", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("formats object detail errors without [object Object]", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            message: "公告快速摘要失败：后端返回对象错误"
          }
        }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" }
        }
      )
    );

    await expect(summarizeCompanyAnnouncements(1, { limit: 50 })).rejects.toThrow(
      "公告快速摘要失败：后端返回对象错误"
    );
  });
});
