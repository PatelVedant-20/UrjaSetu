/**
 * Market utility functions for UrjaSetu Day-Ahead Marketplace.
 * Enforces decimal precision, IST day-ahead scheduling, and pre-flight checks.
 */

export interface DeliveryWindow {
  label: string;
  startIso: string;
  endIso: string;
  displayDate: string;
}

/**
 * Computes the day-ahead delivery window in Asia/Kolkata (IST).
 * Day-ahead delivery operates for the subsequent calendar day.
 */
export function getDayAheadDeliveryWindow(
  referenceDate: Date = new Date(),
): DeliveryWindow {
  const nextDay = new Date(referenceDate);
  nextDay.setDate(nextDay.getDate() + 1);

  const year = nextDay.getFullYear();
  const month = String(nextDay.getMonth() + 1).padStart(2, "0");
  const day = String(nextDay.getDate()).padStart(2, "0");

  const displayDate = new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(nextDay);

  const startIso = `${year}-${month}-${day}T06:30:00.000Z`;
  const endIso = `${year}-${month}-${day}T07:30:00.000Z`;
  const label = `${displayDate} · 12:00–13:00 IST`;

  return { label, startIso, endIso, displayDate };
}

/**
 * Formats a numeric input into a fixed-decimal string to prevent floating-point precision loss.
 */
export function formatDecimalString(
  val: string | number,
  decimals: number = 3,
): string {
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "0";
  return num.toFixed(decimals);
}

/**
 * Pre-flight validation for order placement.
 */
export interface PreFlightStatus {
  canProceed: boolean;
  blockers: string[];
  warnings: string[];
}

export interface EligibilityData {
  can_buy?: boolean;
  can_sell?: boolean;
  can_trade?: boolean;
  trust_level?: string;
  reasons?: string[];
}

export interface SurplusData {
  total_exportable_kwh?: string | number;
  has_exportable_energy?: boolean;
}

export function evaluateOrderPreFlight(params: {
  side: "buy" | "sell";
  energyKwh: number;
  sessionStatus: string;
  eligibility?: EligibilityData | null;
  surplus?: SurplusData | null;
}): PreFlightStatus {
  const blockers: string[] = [];
  const warnings: string[] = [];

  // Session gate
  const statusUpper = params.sessionStatus.toUpperCase();
  if (statusUpper !== "OPEN") {
    blockers.push(
      `Market session status is ${statusUpper}. Orders are only accepted when the session is OPEN.`,
    );
  }

  // Eligibility gate
  if (params.eligibility) {
    if (params.eligibility.can_trade === false) {
      blockers.push(
        `User account is ineligible to trade (${params.eligibility.reasons?.join(", ") || "verification incomplete"}).`,
      );
    } else if (params.side === "buy" && params.eligibility.can_buy === false) {
      blockers.push(
        `User is not eligible to place buy orders (${params.eligibility.reasons?.join(", ") || "restricted"}).`,
      );
    } else if (
      params.side === "sell" &&
      params.eligibility.can_sell === false
    ) {
      blockers.push(
        `User is not eligible to place sell orders (${params.eligibility.reasons?.join(", ") || "generation asset or verification required"}).`,
      );
    }
  }

  // Surplus gate (sell orders only)
  if (params.side === "sell" && params.surplus) {
    const exportable = Number(params.surplus.total_exportable_kwh ?? 0);
    if (!params.surplus.has_exportable_energy || exportable <= 0) {
      blockers.push(
        "Forecast indicates zero exportable surplus for this site during the delivery window.",
      );
    } else if (exportable < params.energyKwh) {
      warnings.push(
        `Order quantity (${params.energyKwh} kWh) exceeds forecast surplus (${exportable} kWh). Backend may reject the sell order.`,
      );
    }
  }

  return {
    canProceed: blockers.length === 0,
    blockers,
    warnings,
  };
}
