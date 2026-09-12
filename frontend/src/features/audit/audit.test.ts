import { describe, it, expect } from "vitest";
import {
  sortAuditEvents,
  truncateHash,
  verifyAuditChainContinuity,
  humanizeEventType,
  resolveAuditBadgeTone,
} from "./auditUtils";
import type { AuditEvent } from "./auditApi";

const sampleEvents: AuditEvent[] = [
  {
    id: "evt-001",
    event_type: "order_created",
    entity_type: "order",
    entity_id: "ord-100",
    event_time: "2026-09-12T10:00:00Z",
    recorded_at: "2026-09-12T10:00:00Z",
    payload_json: { quantity_kwh: 10 },
    event_hash:
      "0x1111111111111111111111111111111111111111111111111111111111111111",
    previous_hash: null,
  },
  {
    id: "evt-002",
    event_type: "order_matched",
    entity_type: "order",
    entity_id: "ord-100",
    event_time: "2026-09-12T10:05:00Z",
    recorded_at: "2026-09-12T10:05:00Z",
    payload_json: { trade_id: "trd-200" },
    event_hash:
      "0x2222222222222222222222222222222222222222222222222222222222222222",
    previous_hash:
      "0x1111111111111111111111111111111111111111111111111111111111111111",
  },
  {
    id: "evt-003",
    event_type: "trade_settled",
    entity_type: "order",
    entity_id: "ord-100",
    event_time: "2026-09-12T10:15:00Z",
    recorded_at: "2026-09-12T10:15:00Z",
    payload_json: { settled_kwh: 10, amount_inr: 45 },
    event_hash:
      "0x3333333333333333333333333333333333333333333333333333333333333333",
    previous_hash:
      "0x2222222222222222222222222222222222222222222222222222222222222222",
  },
];

describe("Audit Timeline Sorting", () => {
  it("sorts audit events in ascending chronological order", () => {
    const unorganized = [sampleEvents[2], sampleEvents[0], sampleEvents[1]];
    const sorted = sortAuditEvents(unorganized, "asc");
    expect(sorted.map((e) => e.id)).toEqual(["evt-001", "evt-002", "evt-003"]);
  });

  it("sorts audit events in descending chronological order", () => {
    const unorganized = [sampleEvents[0], sampleEvents[2], sampleEvents[1]];
    const sorted = sortAuditEvents(unorganized, "desc");
    expect(sorted.map((e) => e.id)).toEqual(["evt-003", "evt-002", "evt-001"]);
  });
});

describe("Audit Hash Truncation", () => {
  it("truncates long SHA-256 hashes cleanly", () => {
    const truncated = truncateHash(
      "0xabcdef1234567890abcdef1234567890abcdef1234567890",
      8,
      6,
    );
    expect(truncated).toBe("0xabcdef…567890");
  });

  it("handles null or genesis hashes gracefully", () => {
    expect(truncateHash(null)).toBe("— (Genesis)");
    expect(truncateHash(undefined)).toBe("— (Genesis)");
  });
});

describe("Audit Chain Continuity Verification", () => {
  it("validates an intact sequential hash chain", () => {
    const report = verifyAuditChainContinuity(sampleEvents);
    expect(report.intact).toBe(true);
    expect(report.evaluatedCount).toBe(3);
    expect(report.brokenAtIndex).toBeNull();
    expect(report.issues).toHaveLength(0);
  });

  it("detects a broken hash linkage in the chain", () => {
    const tampered = [
      sampleEvents[0],
      {
        ...sampleEvents[1],
        previous_hash: "0xtamperedhash00000000000000000000000000000000",
      },
      sampleEvents[2],
    ];

    const report = verifyAuditChainContinuity(tampered);
    expect(report.intact).toBe(false);
    expect(report.brokenAtIndex).toBe(1);
    expect(report.issues.length).toBeGreaterThan(0);
    expect(report.issues[0]).toContain("Hash mismatch");
  });

  it("detects missing previous_hash linkage on non-genesis events", () => {
    const brokenLink = [
      sampleEvents[0],
      {
        ...sampleEvents[1],
        previous_hash: null,
      },
    ];

    const report = verifyAuditChainContinuity(brokenLink);
    expect(report.intact).toBe(false);
    expect(report.brokenAtIndex).toBe(1);
    expect(report.issues[0]).toContain("missing previous_hash");
  });
});

describe("Audit Formatting Helpers", () => {
  it("humanizes event types correctly", () => {
    expect(humanizeEventType("order_created")).toBe("Order Created");
    expect(humanizeEventType("market_cleared")).toBe("Market Cleared");
    expect(humanizeEventType("trade_settled")).toBe("Trade Settled");
  });

  it("resolves status badge tones", () => {
    expect(resolveAuditBadgeTone("trade_settled")).toBe("green");
    expect(resolveAuditBadgeTone("order_matched")).toBe("green");
    expect(resolveAuditBadgeTone("order_proposed")).toBe("amber");
    expect(resolveAuditBadgeTone("validation_failed")).toBe("red");
    expect(resolveAuditBadgeTone("unknown_event")).toBe("neutral");
  });
});
