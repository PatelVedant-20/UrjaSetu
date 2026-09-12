import type { AuditEvent } from "./auditApi";

/**
 * Sorts audit events chronologically by event_time or recorded_at.
 */
export function sortAuditEvents(
  events: AuditEvent[],
  direction: "asc" | "desc" = "asc",
): AuditEvent[] {
  return [...events].sort((a, b) => {
    const timeA = new Date(a.event_time || a.recorded_at).getTime();
    const timeB = new Date(b.event_time || b.recorded_at).getTime();
    return direction === "asc" ? timeA - timeB : timeB - timeA;
  });
}

/**
 * Formats a cryptographic SHA-256 hash for human readability (e.g. 0x3a1f...9b4c).
 */
export function truncateHash(hash?: string | null, lead = 8, tail = 6): string {
  if (!hash) return "— (Genesis)";
  if (hash.length <= lead + tail) return hash;
  return `${hash.slice(0, lead)}…${hash.slice(-tail)}`;
}

export interface ChainContinuityReport {
  intact: boolean;
  evaluatedCount: number;
  brokenAtIndex: number | null;
  brokenAtEventId?: string | null;
  issues: string[];
}

/**
 * Verifies that sequential events in an audit timeline correctly reference the previous event's hash.
 */
export function verifyAuditChainContinuity(
  events: AuditEvent[],
): ChainContinuityReport {
  if (!events.length) {
    return {
      intact: true,
      evaluatedCount: 0,
      brokenAtIndex: null,
      issues: ["No events to verify."],
    };
  }

  // Ensure chronological order
  const chronological = sortAuditEvents(events, "asc");
  const issues: string[] = [];
  let brokenIndex: number | null = null;
  let brokenId: string | null = null;

  // The first event may have null previous_hash (genesis) or reference a prior state
  for (let i = 1; i < chronological.length; i++) {
    const prev = chronological[i - 1];
    const curr = chronological[i];

    if (!curr.previous_hash) {
      issues.push(
        `Event #${i} (${curr.id.slice(0, 8)}) is missing previous_hash linkage.`,
      );
      if (brokenIndex === null) {
        brokenIndex = i;
        brokenId = curr.id;
      }
    } else if (curr.previous_hash !== prev.event_hash) {
      issues.push(
        `Hash mismatch at Event #${i}: expected previous_hash ${prev.event_hash.slice(0, 10)}…, received ${curr.previous_hash.slice(0, 10)}…`,
      );
      if (brokenIndex === null) {
        brokenIndex = i;
        brokenId = curr.id;
      }
    }
  }

  return {
    intact: issues.length === 0,
    evaluatedCount: chronological.length,
    brokenAtIndex: brokenIndex,
    brokenAtEventId: brokenId,
    issues,
  };
}

/**
 * Converts snake_case event type to title case with context icon label.
 */
export function humanizeEventType(type: string): string {
  if (!type) return "Event";
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

/**
 * Resolves status badge tone for different audit lifecycle events.
 */
export function resolveAuditBadgeTone(
  eventType: string,
): "green" | "amber" | "red" | "neutral" {
  const t = eventType.toLowerCase();
  if (
    t.includes("settled") ||
    t.includes("cleared") ||
    t.includes("matched") ||
    t.includes("approved")
  ) {
    return "green";
  }
  if (
    t.includes("pending") ||
    t.includes("proposed") ||
    t.includes("submitted") ||
    t.includes("reconciled")
  ) {
    return "amber";
  }
  if (
    t.includes("rejected") ||
    t.includes("cancelled") ||
    t.includes("failed") ||
    t.includes("violation")
  ) {
    return "red";
  }
  return "neutral";
}
