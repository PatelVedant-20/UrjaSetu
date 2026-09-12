import { useState, useEffect } from "react";
import {
  Download,
  Wallet,
  CheckCheck,
  Search,
  RefreshCw,
  Layers,
  ArrowRight,
  ShieldCheck,
  Scale,
  Receipt,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Stat,
  Modal,
  Badge,
  Note,
  Status,
} from "../../components/ui";
import { readConnection, ApiError } from "../../lib/api";
import {
  getUserSettlements,
  reconcileTrade,
  settleTrade,
  type SettlementRecord,
  type MeterReconciliation,
} from "./settlementApi";
import {
  calculateSettlementBreakdown,
  exportSettlementCsv,
  formatInr,
  resolveSettlementTone,
  type SettlementExportRow,
} from "./settlementUtils";

const illustrativeRows: SettlementExportRow[] = [
  {
    id: "ST-1046",
    trade: "TR-2046",
    date: "11 Sep 2026",
    energy: 8.2,
    gross: 36.49,
    fee: 0.73,
    wheeling: 1.64,
    balancing: 0,
    credit: 34.12,
    debit: 38.13,
    status: "settled",
  },
  {
    id: "ST-1044",
    trade: "TR-2044",
    date: "10 Sep 2026",
    energy: 10.0,
    gross: 47.0,
    fee: 0.94,
    wheeling: 2.0,
    balancing: 0,
    credit: 44.06,
    debit: 49.0,
    status: "settled",
  },
  {
    id: "ST-1042",
    trade: "TR-2042",
    date: "09 Sep 2026",
    energy: 12.5,
    gross: 58.75,
    fee: 1.18,
    wheeling: 2.5,
    balancing: 5.2,
    credit: 49.87,
    debit: 61.25,
    status: "reconciled",
  },
];

export default function SettlementsPage() {
  const conn = readConnection();
  const [userIdInput, setUserIdInput] = useState(conn.userId || "");
  const [activeUserId, setActiveUserId] = useState(conn.userId || "");

  const [liveSettlements, setLiveSettlements] = useState<
    SettlementRecord[] | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Trade action states
  const [tradeActionId, setTradeActionId] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Selected row for detail modal
  const [selected, setSelected] = useState<SettlementExportRow | null>(null);

  const fetchSettlements = async (targetUserId: string) => {
    if (!targetUserId.trim()) {
      setLiveSettlements(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getUserSettlements(targetUserId.trim());
      setLiveSettlements(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (${err.code})`);
      } else {
        setError("Failed to fetch settlement records.");
      }
      setLiveSettlements(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeUserId) {
      void fetchSettlements(activeUserId);
    }
  }, [activeUserId]);

  const handleReconcile = async () => {
    if (!tradeActionId.trim()) return;
    setActionLoading(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const res = await reconcileTrade(tradeActionId.trim(), activeUserId);
      setActionMessage(
        `Trade ${res.trade_id.slice(0, 8)} reconciled: status=${res.reconciliation_status}, committed=${res.committed_kwh} kWh, actual=${res.actual_kwh ?? "unmeasured"} kWh`,
      );
      if (activeUserId) void fetchSettlements(activeUserId);
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(`${err.message} (${err.code})`);
      } else {
        setActionError("Trade reconciliation request failed.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleSettle = async () => {
    if (!tradeActionId.trim()) return;
    setActionLoading(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const res = await settleTrade(tradeActionId.trim(), activeUserId);
      setActionMessage(
        `Trade ${res.trade_id.slice(0, 8)} settled successfully: settlement ID=${res.id.slice(0, 8)}, gross=${res.gross_amount_inr} INR`,
      );
      if (activeUserId) void fetchSettlements(activeUserId);
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(`${err.message} (${err.code})`);
      } else {
        setActionError("Trade settlement execution failed.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  // Convert live records to table rows or fall back to illustrative demo rows
  const displayRows: SettlementExportRow[] =
    liveSettlements && liveSettlements.length > 0
      ? liveSettlements.map((s) => ({
          id: `ST-${s.id.slice(0, 6).toUpperCase()}`,
          trade: `TR-${s.trade_id.slice(0, 6).toUpperCase()}`,
          date: new Date(s.settled_at || s.created_at).toLocaleDateString(
            "en-IN",
            { day: "numeric", month: "short", year: "numeric" },
          ),
          energy: Number(s.settled_kwh),
          gross: Number(s.gross_amount_inr),
          fee: Number(s.platform_fee_inr),
          wheeling: Number((Number(s.settled_kwh) * 0.2).toFixed(2)),
          balancing: Number(s.balancing_charge_inr),
          credit: Number(s.seller_credit_inr),
          debit: Number(s.buyer_debit_inr),
          status: s.status,
        }))
      : illustrativeRows;

  // Aggregate metrics
  const totalSellerCredits = displayRows.reduce((sum, r) => sum + r.credit, 0);
  const totalSettledEnergy = displayRows.reduce((sum, r) => sum + r.energy, 0);
  const totalBalancingCharges = displayRows.reduce(
    (sum, r) => sum + r.balancing,
    0,
  );

  return (
    <>
      <PageHeader
        eyebrow="CLEAR ACCOUNTS. COMPLETE CONFIDENCE."
        title="Settlements"
        description="See how measured delivery becomes an auditable financial record."
        action={
          <button
            className="button secondary"
            onClick={() =>
              exportSettlementCsv(
                displayRows,
                "urjasetu-illustrative-settlements.csv",
              )
            }
          >
            <Download size={16} /> Export demo CSV
          </button>
        }
      />

      {/* Live User Settlement Query Bar */}
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
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Layers size={16} color="#475569" />
          <span>
            Settlement Account:{" "}
            <strong>
              {activeUserId
                ? `User (${activeUserId.slice(0, 8)}…)`
                : "Aarav Residence (Illustrative preview)"}
            </strong>
          </span>
          {liveSettlements && (
            <Badge tone="green">
              {liveSettlements.length} LIVE RECORD
              {liveSettlements.length === 1 ? "" : "S"}
            </Badge>
          )}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setActiveUserId(userIdInput.trim());
          }}
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <input
            type="text"
            placeholder="Enter User UUID…"
            value={userIdInput}
            onChange={(e) => setUserIdInput(e.target.value)}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              width: 200,
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
            {loading ? "Loading…" : "Query Settlements"}
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
          <strong>Settlement Service:</strong> {error}
        </div>
      )}

      {/* Accounting Stats */}
      <div className="stats-grid three reveal-2">
        <Stat
          label={
            liveSettlements
              ? "Account seller credits"
              : "Illustrative seller credits"
          }
          value={formatInr(totalSellerCredits)}
          note={
            liveSettlements
              ? "Calculated from live settlement ledger"
              : "Sample settled records"
          }
          icon={<Wallet size={20} />}
        />
        <Stat
          label="Settled energy"
          value={totalSettledEnergy.toFixed(1)}
          unit="kWh"
          note="Measured delivery in settled records"
          icon={<CheckCheck size={20} />}
        />
        <Stat
          label="Balancing charges"
          value={formatInr(totalBalancingCharges)}
          note={
            totalBalancingCharges === 0
              ? "No shortfalls incurred"
              : "Covered by local grid balancing"
          }
          icon={<Scale size={20} />}
        />
      </div>

      {/* Settlement History Table */}
      <Card
        className="reveal-3"
        title="Settlement history"
        subtitle={
          liveSettlements
            ? `Live accounting ledger · ${displayRows.length} transactions for user`
            : "Illustrative accounting ledger · not a wallet or payment service"
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Settlement</th>
                <th>Delivered energy</th>
                <th>Seller credit</th>
                <th>Buyer debit</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.id}</strong>
                    <small>
                      {r.trade} · {r.date}
                    </small>
                  </td>
                  <td>{r.energy.toFixed(1)} kWh</td>
                  <td>
                    <strong style={{ color: "#2e7d32" }}>
                      {formatInr(r.credit)}
                    </strong>
                  </td>
                  <td>{formatInr(r.debit)}</td>
                  <td>
                    <Badge tone={resolveSettlementTone(r.status)}>
                      {r.status.replace("_", " ")}
                    </Badge>
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => setSelected(r)}
                    >
                      Breakdown →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Trade Action Console (Reconcile & Settle) */}
      <Card
        className="reveal-4"
        title="Trade reconciliation & settlement console"
        subtitle="POST /api/v1/trades/:id/reconcile and POST /api/v1/trades/:id/settle"
      >
        <div style={{ padding: "8px 0" }}>
          <p
            style={{
              fontSize: 12,
              color: "#546857",
              lineHeight: 1.6,
              marginBottom: 14,
            }}
          >
            Settlement is strictly backend-owned and enforces ledger balance
            invariants. A trade can only be settled after meter delivery has
            been reconciled against committed energy.
          </p>

          <div
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <input
              type="text"
              placeholder="Enter Trade UUID to Reconcile or Settle…"
              value={tradeActionId}
              onChange={(e) => setTradeActionId(e.target.value)}
              style={{
                padding: "8px 12px",
                fontSize: 12,
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                minWidth: 280,
                flex: 1,
              }}
            />
            <button
              type="button"
              className="button secondary"
              disabled={actionLoading || !tradeActionId.trim()}
              onClick={handleReconcile}
            >
              <Scale size={14} /> Reconcile Delivery
            </button>
            <button
              type="button"
              className="button primary"
              disabled={actionLoading || !tradeActionId.trim()}
              onClick={handleSettle}
            >
              <CheckCheck size={14} /> Finalize Settlement
            </button>
          </div>

          {actionMessage && (
            <div
              style={{
                marginTop: 14,
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                color: "#166534",
                padding: "10px 14px",
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              {actionMessage}
            </div>
          )}

          {actionError && (
            <div
              style={{
                marginTop: 14,
                background: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#991b1b",
                padding: "10px 14px",
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              <strong>Error:</strong> {actionError}
            </div>
          )}
        </div>
      </Card>

      <Note>
        <strong>Simulated Accounting Invariant:</strong> Final amounts, fee
        schedules, and reconciliation rules are strictly verified by backend
        calculators. No money is transferred by this prototype interface, and
        unmeasured delivery is never credited.
      </Note>

      {/* Itemized Financial Breakdown Modal */}
      {selected && (
        <Modal
          title={`${selected.id} · Financial Breakdown`}
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
            <Badge tone={resolveSettlementTone(selected.status)}>
              {selected.status.toUpperCase()}
            </Badge>
            <span style={{ fontSize: 11, color: "#6a7e6b" }}>
              Trade Reference: <strong>{selected.trade}</strong>
            </span>
          </div>

          <div className="simple-list">
            <div>
              <span>Delivered Energy Volume</span>
              <strong>{selected.energy.toFixed(1)} kWh</strong>
            </div>
            <div>
              <span>Gross Trade Value</span>
              <strong>{formatInr(selected.gross)}</strong>
            </div>
            <div>
              <span>Platform Fee (2%)</span>
              <span style={{ color: "#b91c1c" }}>
                - {formatInr(selected.fee)}
              </span>
            </div>
            <div>
              <span>DISCOM Wheeling Charge (₹0.20/kWh)</span>
              <span style={{ color: "#b91c1c" }}>
                - {formatInr(selected.wheeling)}
              </span>
            </div>
            <div>
              <span>Balancing Shortfall Charge</span>
              <span style={{ color: "#b91c1c" }}>
                - {formatInr(selected.balancing)}
              </span>
            </div>
            <div style={{ borderTop: "1px dashed #d1d5db", paddingTop: 8 }}>
              <span>
                <strong>Net Seller Payout</strong>
              </span>
              <strong style={{ fontSize: 14, color: "#15803d" }}>
                {formatInr(selected.credit)}
              </strong>
            </div>
            <div>
              <span>
                <strong>Total Buyer Debit</strong>
              </span>
              <strong style={{ fontSize: 14, color: "#1e293b" }}>
                {formatInr(selected.debit)}
              </strong>
            </div>
          </div>

          <Note>
            Amounts shown represent simulated peer-to-peer settlement
            allocations. Settlement ledger balance invariants ensure total buyer
            debit equals seller credit plus platform and wheeling allocations.
          </Note>
        </Modal>
      )}
    </>
  );
}
