/**
 * Telemetry and energy utility functions.
 * Enforces critical null-handling rules: missing/stale data is "Unavailable", NEVER 0.
 */

/**
 * Formats electrical power (kW). Null is never converted to 0.
 */
export function formatPowerKw(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  const num = Number(value);
  if (isNaN(num)) return "Unavailable";
  return `${num.toLocaleString("en-IN", { maximumFractionDigits: 2 })} kW`;
}

/**
 * Formats electrical energy (kWh). Null is never converted to 0.
 */
export function formatEnergyKwh(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  const num = Number(value);
  if (isNaN(num)) return "Unavailable";
  return `${num.toLocaleString("en-IN", { maximumFractionDigits: 2 })} kWh`;
}

/**
 * Formats voltage in per-unit (pu).
 */
export function formatVoltagePu(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  const num = Number(value);
  if (isNaN(num)) return "Unavailable";
  return `${num.toFixed(2)} pu`;
}

/**
 * Resolves Badge tone based on telemetry quality status.
 */
export function resolveTelemetryTone(qualityStatus: string): string {
  const normalized = qualityStatus.toLowerCase().replaceAll("-", "_");
  switch (normalized) {
    case "valid":
      return "green";
    case "stale":
    case "suspect":
      return "amber";
    case "missing":
    case "source_unavailable":
    case "invalid_value":
      return "red";
    default:
      return "neutral";
  }
}

/**
 * Filters community directory members by name or role.
 */
export function filterMembers<T extends { name: string; role: string }>(
  members: T[],
  query: string,
): T[] {
  if (!query.trim()) return members;
  const q = query.toLowerCase();
  return members.filter((m) => `${m.name} ${m.role}`.toLowerCase().includes(q));
}
