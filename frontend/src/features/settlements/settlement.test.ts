import { describe, it, expect } from "vitest";
import {
  calculateGrossAmount,
  calculatePlatformFee,
  calculateWheelingCharge,
  calculateBalancingCharge,
  calculateSettlementBreakdown,
  resolveSettlementTone,
  generateSettlementCsvContent,
  formatInr,
  type SettlementExportRow,
} from "./settlementUtils";

describe("Settlement Calculations", () => {
  it("calculates gross energy value correctly", () => {
    expect(calculateGrossAmount(10, 4.5)).toBe(45);
    expect(calculateGrossAmount(8.2, 4.45)).toBe(36.49);
    expect(calculateGrossAmount(0, 5)).toBe(0);
    expect(calculateGrossAmount(-5, 4)).toBe(0);
  });

  it("calculates platform fee at 2% rate", () => {
    expect(calculatePlatformFee(100)).toBe(2);
    expect(calculatePlatformFee(36.49)).toBe(0.73);
    expect(calculatePlatformFee(0)).toBe(0);
  });

  it("calculates DISCOM wheeling charge", () => {
    expect(calculateWheelingCharge(10, 0.2)).toBe(2);
    expect(calculateWheelingCharge(5.5, 0.2)).toBe(1.1);
    expect(calculateWheelingCharge(0)).toBe(0);
  });

  it("calculates balancing shortfall penalty", () => {
    expect(calculateBalancingCharge(2.5, 5.2)).toBe(13);
    expect(calculateBalancingCharge(0, 5.2)).toBe(0);
    expect(calculateBalancingCharge(-1, 5.2)).toBe(0);
  });

  it("produces full settlement breakdown with seller credit and buyer debit", () => {
    const breakdown = calculateSettlementBreakdown({
      energyKwh: 10,
      pricePerKwh: 4.7,
      shortfallKwh: 0,
      platformFeeRate: 0.02,
      wheelingRatePerKwh: 0.2,
      balancingRatePerKwh: 5.2,
    });

    expect(breakdown.grossAmount).toBe(47);
    expect(breakdown.platformFee).toBe(0.94);
    expect(breakdown.wheelingCharge).toBe(2);
    expect(breakdown.balancingCharge).toBe(0);
    expect(breakdown.sellerCredit).toBe(44.06); // 47 - 0.94 - 2
    expect(breakdown.buyerDebit).toBe(49); // 47 + 2
  });

  it("handles shortfall penalty deduction in seller credit", () => {
    const breakdown = calculateSettlementBreakdown({
      energyKwh: 8,
      pricePerKwh: 5.0,
      shortfallKwh: 2,
      platformFeeRate: 0.02,
      wheelingRatePerKwh: 0.2,
      balancingRatePerKwh: 5.2,
    });

    expect(breakdown.grossAmount).toBe(40);
    expect(breakdown.platformFee).toBe(0.8);
    expect(breakdown.wheelingCharge).toBe(1.6);
    expect(breakdown.balancingCharge).toBe(10.4); // 2 * 5.2
    expect(breakdown.sellerCredit).toBe(27.2); // 40 - 0.8 - 1.6 - 10.4
    expect(breakdown.buyerDebit).toBe(41.6); // 40 + 1.6
  });
});

describe("Settlement Status & Formatting", () => {
  it("resolves status tones correctly", () => {
    expect(resolveSettlementTone("settled")).toBe("green");
    expect(resolveSettlementTone("matched")).toBe("green");
    expect(resolveSettlementTone("reconciled")).toBe("amber");
    expect(resolveSettlementTone("pending")).toBe("amber");
    expect(resolveSettlementTone("disputed")).toBe("red");
    expect(resolveSettlementTone("shortfall")).toBe("red");
    expect(resolveSettlementTone("unknown")).toBe("neutral");
  });

  it("formats monetary values with currency or Unavailable", () => {
    expect(formatInr(null)).toBe("Unavailable");
    expect(formatInr(undefined)).toBe("Unavailable");
    expect(formatInr(100)).toContain("100");
  });
});

describe("Settlement CSV Generator", () => {
  it("generates formatted CSV string with headers and escaped values", () => {
    const sampleRows: SettlementExportRow[] = [
      {
        id: "ST-1001",
        trade: "TR-2001",
        date: "12 Sep 2026",
        energy: 10,
        gross: 45,
        fee: 0.9,
        wheeling: 2,
        balancing: 0,
        credit: 42.1,
        debit: 47,
        status: "settled",
      },
    ];

    const csv = generateSettlementCsvContent(sampleRows);
    expect(csv).toContain(
      '"id","trade","date","energy","gross","fee","wheeling","balancing","credit","debit","status"',
    );
    expect(csv).toContain('"ST-1001"');
    expect(csv).toContain('"TR-2001"');
    expect(csv).toContain('"42.1"');
  });

  it("returns empty string when no rows given", () => {
    expect(generateSettlementCsvContent([])).toBe("");
  });
});
