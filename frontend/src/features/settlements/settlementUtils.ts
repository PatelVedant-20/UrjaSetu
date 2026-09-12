import { exportCsv, money } from "../../lib/format";

export interface SettlementCalculationInput {
  energyKwh: number;
  pricePerKwh: number;
  shortfallKwh?: number;
  platformFeeRate?: number; // default 0.02 (2%)
  wheelingRatePerKwh?: number; // default 0.20 INR/kWh
  balancingRatePerKwh?: number; // default 5.20 INR/kWh
}

export interface SettlementBreakdown {
  energyKwh: number;
  pricePerKwh: number;
  grossAmount: number;
  platformFee: number;
  wheelingCharge: number;
  balancingCharge: number;
  sellerCredit: number;
  buyerDebit: number;
}

export interface SettlementExportRow extends Record<string, string | number> {
  id: string;
  trade: string;
  date: string;
  energy: number;
  gross: number;
  fee: number;
  wheeling: number;
  balancing: number;
  credit: number;
  debit: number;
  status: string;
}

/**
 * Calculates gross energy trade value.
 */
export function calculateGrossAmount(
  energyKwh: number,
  pricePerKwh: number,
): number {
  return Number((Math.max(0, energyKwh) * Math.max(0, pricePerKwh)).toFixed(2));
}

/**
 * Calculates platform transaction fee (default 2%).
 */
export function calculatePlatformFee(grossAmount: number, rate = 0.02): number {
  return Number((Math.max(0, grossAmount) * rate).toFixed(2));
}

/**
 * Calculates DISCOM wheeling charge for local grid transmission.
 */
export function calculateWheelingCharge(
  energyKwh: number,
  ratePerKwh = 0.2,
): number {
  return Number((Math.max(0, energyKwh) * ratePerKwh).toFixed(2));
}

/**
 * Calculates balancing shortfall penalty for under-delivery.
 */
export function calculateBalancingCharge(
  shortfallKwh: number,
  ratePerKwh = 5.2,
): number {
  return Number((Math.max(0, shortfallKwh) * ratePerKwh).toFixed(2));
}

/**
 * Calculates the complete accounting breakdown for a trade settlement.
 */
export function calculateSettlementBreakdown(
  input: SettlementCalculationInput,
): SettlementBreakdown {
  const gross = calculateGrossAmount(input.energyKwh, input.pricePerKwh);
  const platformFee = calculatePlatformFee(
    gross,
    input.platformFeeRate ?? 0.02,
  );
  const wheeling = calculateWheelingCharge(
    input.energyKwh,
    input.wheelingRatePerKwh ?? 0.2,
  );
  const balancing = calculateBalancingCharge(
    input.shortfallKwh ?? 0,
    input.balancingRatePerKwh ?? 5.2,
  );

  // Seller receives gross minus platform fee, wheeling, and shortfall balancing charge
  const sellerCredit = Number(
    Math.max(0, gross - platformFee - wheeling - balancing).toFixed(2),
  );

  // Buyer pays gross value + buyer portion of wheeling
  const buyerDebit = Number((gross + wheeling).toFixed(2));

  return {
    energyKwh: input.energyKwh,
    pricePerKwh: input.pricePerKwh,
    grossAmount: gross,
    platformFee,
    wheelingCharge: wheeling,
    balancingCharge: balancing,
    sellerCredit,
    buyerDebit,
  };
}

/**
 * Formats monetary amounts in INR with strict null handling.
 */
export function formatInr(val: number | string | null | undefined): string {
  if (val === null || val === undefined || isNaN(Number(val))) {
    return "Unavailable";
  }
  return money(val);
}

/**
 * Resolves UI badge tone based on settlement status.
 */
export function resolveSettlementTone(
  status: string,
): "green" | "amber" | "red" | "neutral" {
  switch (status.toLowerCase()) {
    case "settled":
    case "matched":
      return "green";
    case "reconciled":
    case "pending":
    case "excess":
      return "amber";
    case "disputed":
    case "shortfall":
      return "red";
    default:
      return "neutral";
  }
}

/**
 * Converts settlement rows into CSV text format.
 */
export function generateSettlementCsvContent(
  rows: SettlementExportRow[],
): string {
  if (!rows.length) return "";
  const escape = (v: unknown) =>
    '"' +
    String(v)
      .replace(/^[=+@-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  return [Object.keys(rows[0]), ...rows.map(Object.values)]
    .map((r) => r.map(escape).join(","))
    .join("\r\n");
}

/**
 * Triggers browser download of settlement CSV.
 */
export function exportSettlementCsv(
  rows: SettlementExportRow[],
  filename = "urjasetu-illustrative-settlements.csv",
): void {
  exportCsv(rows, filename);
}
