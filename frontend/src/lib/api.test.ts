import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, request } from "./api";
import { measurement, localTime } from "./format";
afterEach(() => vi.unstubAllGlobals());
describe("API boundary", () => {
  it("preserves nullable readings and decimal strings, sending canonical identity", async () => {
    const body = { generation_kw: null, energy_kwh: "12.500" };
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(body)));
    vi.stubGlobal("fetch", fetcher);
    expect(
      await request("/api/v1/sites/site/telemetry/latest", "actor"),
    ).toEqual(body);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/sites/site/telemetry/latest",
      { headers: { "X-User-Id": "actor" }, signal: undefined },
    );
  });
  it("retains server error code and correlation ID without a demo fallback", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "USER_NOT_ELIGIBLE",
              message: "Not eligible",
              request_id: "request-1",
            },
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(request("/api/v1/orders/x")).rejects.toMatchObject({
      message: "Not eligible",
      code: "USER_NOT_ELIGIBLE",
      requestId: "request-1",
    });
  });
  it("rejects an HTML proxy fallback rather than accepting it as API data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>SPA</html>")),
    );
    await expect(request("/health")).rejects.toBeInstanceOf(ApiError);
  });
  it("does not convert missing measurements to zero", () => {
    expect(measurement(null, "kW")).toBe("Unavailable");
    expect(measurement("0", "kW")).toBe("0 kW");
  });
  it("localizes API timestamps at the display boundary", () => {
    expect(localTime("2026-09-12T06:30:00Z")).toContain("12:00");
    expect(localTime("2026-09-12T06:30:00Z")).toContain("IST");
  });
});
