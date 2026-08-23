import { afterEach, describe, expect, it, vi } from "vitest";

import { requestLocalShutdown, summarizeCompanyAnnouncements } from "../services/api";

describe("api service errors", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
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

  it("sends the launcher token in the local shutdown header", async () => {
    vi.stubEnv("VITE_LOCAL_CONTROL_TOKEN", "local-session-token");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "accepted", message: "closing" }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      )
    );

    await expect(requestLocalShutdown()).resolves.toEqual({
      status: "accepted",
      message: "closing"
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/system/shutdown",
      expect.objectContaining({
        method: "POST",
        headers: { "X-Local-Control-Token": "local-session-token" }
      })
    );
  });

  it("rejects shutdown when the frontend was not started by the launcher", async () => {
    vi.stubEnv("VITE_LOCAL_CONTROL_TOKEN", "");

    await expect(requestLocalShutdown()).rejects.toThrow("无法关闭服务");
  });
});
