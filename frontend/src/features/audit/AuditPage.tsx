import { useState, useEffect } from "react";
import {
  Search,
  Check,
  ArrowUpRight,
  ShieldCheck,
  Layers,
  RefreshCw,
  Anchor,
  FileCode,
  Key,
  Clock,
  AlertCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader, Card, Badge, Modal, Note } from "../../components/ui";
import { auditEvents as demoEvents } from "../../lib/demo";
import { readConnection, ApiError } from "../../lib/api";
import {
  getEntityTimeline,
  anchorAuditEvent,
  type AuditEvent,
  type AuditEntityType,
} from "./auditApi";
import {
  sortAuditEvents,
  truncateHash,
  verifyAuditChainContinuity,
  humanizeEventType,
  resolveAuditBadgeTone,
} from "./auditUtils";

// Illustrative demo events converted into full AuditEvent records
const fallbackDemoEvents: AuditEvent[] = [
  {
    id: "evt-a101",
    event_type: "order_created",
    entity_type: "trade",
    entity_id: "TR-2046",
    event_time: "2026-09-11T12:00:00Z",
    recorded_at: "2026-09-11T12:00:00Z",
    actor_user_id: "usr-aarav",
    payload_json: {
      action: "order_created",
      energy_kwh: 8.2,
      price_inr_per_kwh: 4.45,
    },
    event_hash:
      "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
    previous_hash: null,
    ledger_anchor_id: null,
  },
  {
    id: "evt-a102",
    event_type: "order_matched",
    entity_type: "trade",
    entity_id: "TR-2046",
    event_time: "2026-09-11T12:00:30Z",
    recorded_at: "2026-09-11T12:00:30Z",
    actor_user_id: "system-matcher",
    payload_json: {
      action: "matched",
      trade_id: "TR-2046",
      cleared_price: 4.45,
      quantity_kwh: 8.2,
    },
    event_hash:
      "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef9f8bde6b0f3",
    previous_hash:
      "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
    ledger_anchor_id: null,
  },
  {
    id: "evt-a103",
    event_type: "grid_validated",
    entity_type: "trade",
    entity_id: "TR-2046",
    event_time: "2026-09-11T12:01:00Z",
    recorded_at: "2026-09-11T12:01:00Z",
    actor_user_id: "grid-powerflow-service",
    payload_json: {
      voltage_pu: 0.992,
      transformer_loading_pct: 64.2,
      safe: true,
    },
    event_hash:
      "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
    previous_hash:
      "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef9f8bde6b0f3",
    ledger_anchor_id: "anchor-loc-9821",
  },
  {
    id: "evt-a104",
    event_type: "trade_settled",
    entity_type: "trade",
    entity_id: "TR-2046",
    event_time: "2026-09-11T13:15:00Z",
    recorded_at: "2026-09-11T13:15:00Z",
    actor_user_id: "settlement-engine",
    payload_json: {
      settled_kwh: 8.2,
      gross_amount_inr: 36.49,
      seller_credit_inr: 34.12,
    },
    event_hash:
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    previous_hash:
      "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
    ledger_anchor_id: "anchor-loc-9822",
  },
];

export default function AuditPage() {
  const conn = readConnection();
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState<AuditEntityType>("trade");
  const [entityIdInput, setEntityIdInput] = useState(conn.sessionId || "");
  const [activeEntityId, setActiveEntityId] = useState("");

  const [liveEvents, setLiveEvents] = useState<AuditEvent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Anchor action states
  const [anchoring, setAnchoring] = useState(false);
  const [anchorMessage, setAnchorMessage] = useState<string | null>(null);
  const [anchorError, setAnchorError] = useState<string | null>(null);

  // Modal inspection
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const fetchTimeline = async (type: string, id: string) => {
    if (!id.trim()) {
      setLiveEvents(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getEntityTimeline(type, id.trim(), conn.userId);
      setLiveEvents(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (${err.code})`);
      } else {
        setError("Failed to fetch entity audit timeline.");
      }
      setLiveEvents(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeEntityId) {
      void fetchTimeline(entityType, activeEntityId);
    }
  }, [entityType, activeEntityId]);

  const handleAnchor = async () => {
    const targetId = activeEntityId || entityIdInput;
    if (!targetId.trim()) return;
    setAnchoring(true);
    setAnchorError(null);
    setAnchorMessage(null);
    try {
      const res = await anchorAuditEvent(
        entityType,
        targetId.trim(),
        conn.userId,
      );
      setAnchorMessage(
        `Event anchored successfully! Anchor Receipt: ${res.ledger_anchor_id || "LocalPublisherReceipt"}`,
      );
      if (activeEntityId) void fetchTimeline(entityType, activeEntityId);
    } catch (err) {
      if (err instanceof ApiError) {
        setAnchorError(`${err.message} (${err.code})`);
      } else {
        setAnchorError("Anchor publication failed.");
      }
    } finally {
      setAnchoring(false);
    }
  };

  // Active event stream
  const rawEvents = liveEvents || fallbackDemoEvents;
  const sortedEvents = sortAuditEvents(rawEvents, "asc");
  const continuity = verifyAuditChainContinuity(sortedEvents);

  const filtered = sortedEvents.filter((e) =>
    `${e.event_type} ${e.entity_type} ${e.id} ${JSON.stringify(e.payload_json)}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  return (
    <>
      <PageHeader
        eyebrow="THE STORY BEHIND EVERY DECISION"
        title="An open trail."
        description="Follow a trade from its first proposal to its final settlement with cryptographic hash linking."
        action={
          <Link to="/settings" className="button secondary">
            Look up API records <ArrowUpRight size={16} />
          </Link>
        }
      />

      {/* Entity Lookup Form */}
      <div
        className="reveal-1"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fafbf7",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: 8,
          padding: "10px 16px",
          marginBottom: 16,
          fontSize: 12,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Layers size={16} color="#475569" />
          <span>
            Audit Target:{" "}
            <strong>
              {activeEntityId
                ? `${entityType.toUpperCase()} (${activeEntityId.slice(0, 8)}…)`
                : "TR-2046 (Illustrative chain preview)"}
            </strong>
          </span>
          {liveEvents && (
            <Badge tone="green">
              {liveEvents.length} LIVE EVENT
              {liveEvents.length === 1 ? "" : "S"}
            </Badge>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setActiveEntityId(entityIdInput.trim());
          }}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <select
            value={entityType}
            onChange={(e) => setEntityType(e.target.value as AuditEntityType)}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
              background: "white",
            }}
          >
            <option value="trade">Trade</option>
            <option value="order">Order</option>
            <option value="market_session">Market Session</option>
          </select>

          <input
            type="text"
            placeholder="Enter Entity UUID…"
            value={entityIdInput}
            onChange={(e) => setEntityIdInput(e.target.value)}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              width: 190,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
            }}
          />

          <button
            type="submit"
            className="button secondary"
            style={{ padding: "4px 8px", fontSize: 11 }}
            disabled={loading}
          >
            <RefreshCw
              size={12}
              className={loading ? "spin" : ""}
              style={{ marginRight: 4 }}
            />
            {loading ? "Verifying…" : "Query Timeline"}
          </button>
        </form>
      </div>

      {error && (
        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            padding: 10,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 12,
            color: "#991b1b",
          }}
        >
          <strong>Audit Service Error:</strong> {error}
        </div>
      )}

      {/* Cryptographic Chain Integrity Card */}
      <div
        className="reveal-2"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: continuity.intact ? "#f0fdf4" : "#fef2f2",
          border: `1px solid ${continuity.intact ? "#bbf7d0" : "#fecaca"}`,
          borderRadius: 8,
          padding: "12px 18px",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {continuity.intact ? (
            <ShieldCheck size={22} color="#15803d" />
          ) : (
            <AlertCircle size={22} color="#b91c1c" />
          )}
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <strong
                style={{
                  fontSize: 13,
                  color: continuity.intact ? "#166534" : "#991b1b",
                }}
              >
                {continuity.intact
                  ? "SHA-256 Hash Chain Intact"
                  : "Chain Integrity Discontinuity"}
              </strong>
              <Badge tone={continuity.intact ? "green" : "red"}>
                {continuity.evaluatedCount} EVENTS VERIFIED
              </Badge>
            </div>
            <p style={{ fontSize: 11, color: "#475569", margin: "2px 0 0" }}>
              {continuity.intact
                ? "Every event references the cryptographic SHA-256 hash of its predecessor in tamper-evident order."
                : continuity.issues[0]}
            </p>
          </div>
        </div>

        {activeEntityId && (
          <button
            type="button"
            className="button secondary"
            style={{ fontSize: 11, padding: "5px 10px" }}
            disabled={anchoring}
            onClick={handleAnchor}
          >
            <Anchor size={12} style={{ marginRight: 4 }} />
            {anchoring ? "Anchoring…" : "Publish DLT Anchor"}
          </button>
        )}
      </div>

      {anchorMessage && (
        <div
          style={{
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            padding: 10,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 12,
            color: "#166534",
          }}
        >
          {anchorMessage}
        </div>
      )}

      {anchorError && (
        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            padding: 10,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 12,
            color: "#991b1b",
          }}
        >
          <strong>Anchor Error:</strong> {anchorError}
        </div>
      )}

      {/* Main Timeline Card */}
      <Card
        className="reveal-3"
        title="Trade event timeline"
        subtitle={
          liveEvents
            ? `Live hash chain · ${filtered.length} verified events`
            : "Illustrative history · TR-2046 · Sha-256 canonical chain"
        }
        action={
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search audit events"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search events…"
            />
          </label>
        }
      >
        <div className="timeline">
          {filtered.map((e, idx) => (
            <button
              className="timeline-event"
              key={e.id || idx}
              onClick={() => setSelected(e)}
            >
              <span className="timeline-marker">
                <Check size={15} />
              </span>
              <div>
                <small>
                  #{idx + 1} ·{" "}
                  {new Date(e.event_time || e.recorded_at).toLocaleTimeString(
                    "en-IN",
                    { hour: "2-digit", minute: "2-digit" },
                  )}{" "}
                  IST
                </small>
                <h3>{humanizeEventType(e.event_type)}</h3>
                <p>
                  Hash: <code>{truncateHash(e.event_hash, 10, 8)}</code>
                </p>
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <Badge tone={resolveAuditBadgeTone(e.event_type)}>
                    {e.event_type.toUpperCase()}
                  </Badge>
                  {e.ledger_anchor_id && <Badge tone="green">ANCHORED</Badge>}
                </div>
              </div>
              <ArrowUpRight size={17} />
            </button>
          ))}
        </div>
        {!filtered.length && <p className="empty">No matching audit events.</p>}
      </Card>

      <Note>
        <strong>Cryptographic Hash-Chain Guarantee:</strong> UrjaSetu maintains
        an immutable, tamper-evident hash chain locally using SHA-256 over
        canonical event serialization. No external gas-fee public blockchain is
        required for trusted microgrid operations, with optional anchor proofs
        periodically published to external ledger adapters.
      </Note>

      {/* Detailed Event Inspection Modal */}
      {selected && (
        <Modal
          title={`Audit Event #${sortedEvents.findIndex((x) => x.id === selected.id) + 1} · ${humanizeEventType(selected.event_type)}`}
          onClose={() => setSelected(null)}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 12,
            }}
          >
            <Badge tone={resolveAuditBadgeTone(selected.event_type)}>
              {selected.event_type.toUpperCase()}
            </Badge>
            <span style={{ fontSize: 11, color: "#6a7e6b" }}>
              Entity:{" "}
              <strong>
                {selected.entity_type} / {selected.entity_id.slice(0, 8)}
              </strong>
            </span>
          </div>

          <div className="simple-list">
            <div>
              <span>Event UUID</span>
              <code style={{ fontSize: 11 }}>{selected.id}</code>
            </div>
            <div>
              <span>Timestamp</span>
              <strong>
                {new Date(
                  selected.event_time || selected.recorded_at,
                ).toLocaleString("en-IN")}{" "}
                IST
              </strong>
            </div>
            <div>
              <span>Actor ID</span>
              <code style={{ fontSize: 11 }}>
                {selected.actor_user_id || "System Automated"}
              </code>
            </div>
            <div>
              <span>Event SHA-256 Hash</span>
              <code style={{ fontSize: 10, wordBreak: "break-all" }}>
                {selected.event_hash}
              </code>
            </div>
            <div>
              <span>Previous Event Hash</span>
              <code style={{ fontSize: 10, wordBreak: "break-all" }}>
                {selected.previous_hash || "None (Genesis Event)"}
              </code>
            </div>
            <div>
              <span>DLT Anchor Proof</span>
              <strong>
                {selected.ledger_anchor_id ? (
                  <span style={{ color: "#166534" }}>
                    {selected.ledger_anchor_id}
                  </span>
                ) : (
                  <span style={{ color: "#64748b" }}>
                    Unanchored (Local chain only)
                  </span>
                )}
              </strong>
            </div>
          </div>

          <div style={{ marginTop: 14 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: "#475569" }}>
              Canonical Payload JSON:
            </span>
            <pre
              style={{
                marginTop: 6,
                padding: "10px 14px",
                background: "#f8fafc",
                borderRadius: 6,
                border: "1px solid #e2e8f0",
                fontSize: 11,
                overflowX: "auto",
                lineHeight: 1.5,
              }}
            >
              {JSON.stringify(selected.payload_json, null, 2)}
            </pre>
          </div>

          <Note>
            This record is cryptographically tied to its preceding block.
            Modifying any past telemetry reading, price agreement, or grid
            validation breaks the hash chain and immediately alerts auditing
            nodes.
          </Note>
        </Modal>
      )}
    </>
  );
}
