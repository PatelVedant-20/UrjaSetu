import { describe, expect, it, vi } from "vitest";
import {
  getDayAheadDeliveryWindow,
  formatDecimalString,
  evaluateOrderPreFlight,
} from "./marketUtils";
import { fetchPricingQuote } from "./marketApi";

describe("Market Utils", () => {
  it("computes day-ahead delivery window in IST", () => {
    const fixedDate = new Date("2026-09-12T10:00:00Z");
    const window = getDayAheadDeliveryWindow(fixedDate);
    expect(window.displayDate).toContain("13 Sep");
    expect(window.label).toContain("12:00–13:00 IST");
    expect(window.startIso).toBe("2026-09-13T06:30:00.000Z");
    expect(window.endIso).toBe("2026-09-13T07:30:00.000Z");
  });

  it("formats numbers into fixed decimal strings without loss", () => {
    expect(formatDecimalString("12.5", 3)).toBe("12.500");
    expect(formatDecimalString(4.65, 2)).toBe("4.65");
    expect(formatDecimalString("invalid", 2)).toBe("0");
  });

  it("blocks order pre-flight when market session is not OPEN", () => {
    const check = evaluateOrderPreFlight({
      side: "buy",
      energyKwh: 10,
      sessionStatus: "CLOSED",
    });
    expect(check.canProceed).toBe(false);
    expect(check.blockers[0]).toContain("CLOSED");
  });

  it("permits buy order when session is OPEN and user is eligible", () => {
    const check = evaluateOrderPreFlight({
      side: "buy",
      energyKwh: 10,
      sessionStatus: "OPEN",
      eligibility: {
        can_buy: true,
        can_sell: false,
        can_trade: true,
      },
    });
    expect(check.canProceed).toBe(true);
    expect(check.blockers).toHaveLength(0);
  });

  it("blocks sell order when user is not eligible to sell", () => {
    const check = evaluateOrderPreFlight({
      side: "sell",
      energyKwh: 10,
      sessionStatus: "OPEN",
      eligibility: {
        can_buy: true,
        can_sell: false,
        can_trade: true,
        reasons: ["No verified solar generation asset found"],
      },
    });
    expect(check.canProceed).toBe(false);
    expect(check.blockers[0]).toContain("not eligible to place sell orders");
  });

  it("blocks sell order when forecast indicates zero exportable surplus", () => {
    const check = evaluateOrderPreFlight({
      side: "sell",
      energyKwh: 10,
      sessionStatus: "OPEN",
      eligibility: {
        can_buy: true,
        can_sell: true,
        can_trade: true,
      },
      surplus: {
        has_exportable_energy: false,
        total_exportable_kwh: "0.000",
      },
    });
    expect(check.canProceed).toBe(false);
    expect(check.blockers[0]).toContain("zero exportable surplus");
  });

  it("issues a warning when requested sell quantity exceeds forecast surplus", () => {
    const check = evaluateOrderPreFlight({
      side: "sell",
      energyKwh: 15,
      sessionStatus: "OPEN",
      eligibility: {
        can_buy: true,
        can_sell: true,
        can_trade: true,
      },
      surplus: {
        has_exportable_energy: true,
        total_exportable_kwh: "8.500",
      },
    });
    expect(check.canProceed).toBe(true);
    expect(check.warnings).toHaveLength(1);
    expect(check.warnings[0]).toContain("exceeds forecast surplus");
  });
});

describe("Market Pricing API", () => {
  it("fetches explainable pricing quote from POST /api/v1/pricing/quote", async () => {
    const mockResult = {
      formula_version: "v1.2",
      engine: "BaselinePricingEngine",
      base_market_price: "4.50",
      time_component: "0.20",
      congestion_component: "0.00",
      imbalance_component: "0.10",
      local_renewable_component: "-0.15",
      final_price: "4.65",
      components: [
        { kind: "time_of_use", amount_inr_per_kwh: "0.20", reason: "Wheeling" },
      ],
      recommended_decision: "APPROVE",
      grid_status: "VALID",
    };

    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(mockResult)));
    vi.stubGlobal("fetch", fetcher);

    const res = await fetchPricingQuote({
      base_price_inr_per_kwh: "4.50",
      quantity_kwh: "10.0",
      delivery_start: "2026-09-13T06:30:00Z",
      delivery_end: "2026-09-13T07:30:00Z",
      local_renewable: true,
    });

    expect(res.final_price).toBe("4.65");
    expect(res.engine).toBe("BaselinePricingEngine");
    expect(fetcher).toHaveBeenCalledWith("/api/v1/pricing/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: expect.stringContaining('"base_price_inr_per_kwh":"4.50"'),
      signal: undefined,
    });
    vi.unstubAllGlobals();
  });
});
