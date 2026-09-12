import { describe, expect, it } from "vitest";
import {
  getDayAheadDeliveryWindow,
  formatDecimalString,
  evaluateOrderPreFlight,
} from "./marketUtils";

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
