import { useState } from "react";
import { Search, RefreshCw, Layers } from "lucide-react";
import { PageHeader, Card, Tabs, Note } from "../../components/ui";
import TradeTable, { type TradeItem } from "../../components/TradeTable";
import TradeDetailModal from "./TradeDetailModal";
import { trades as demoTrades } from "../../lib/demo";
import { localTime } from "../../lib/format";
import { fetchTradeById } from "../market/marketApi";
import { readConnection, ApiError } from "../../lib/api";

export default function TradesPage() {
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState<TradeItem | null>(null);

  // Live trade lookup
  const [lookupId, setLookupId] = useState("");
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<{
    message: string;
    code: string;
    requestId?: string;
  } | null>(null);

  const conn = readConnection();

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lookupId.trim()) return;

    setLookupLoading(true);
    setLookupError(null);
    try {
      const realTrade = await fetchTradeById(
        lookupId.trim(),
        conn.userId || "",
      );

      const mappedItem: TradeItem = {
        id: realTrade.id,
        name: `Matched Trade (${realTrade.id.slice(0, 8)}…)`,
        side: "Settlement",
        energy: realTrade.quantity_kwh,
        price: realTrade.clearing_price_inr_per_kwh,
        status: realTrade.status,
        window: `${localTime(realTrade.delivery_start)} – ${localTime(realTrade.delivery_end)}`,
        buy_order_id: realTrade.buy_order_id,
        sell_order_id: realTrade.sell_order_id,
        grid_validation_id: realTrade.grid_validation_id,
      };

      setSelected(mappedItem);
    } catch (err) {
      if (err instanceof ApiError) {
        setLookupError({
          message: err.message,
          code: err.code,
          requestId: err.requestId,
        });
      } else {
        setLookupError({
          message:
            err instanceof Error ? err.message : "Failed to load trade record.",
          code: "LOOKUP_FAILED",
        });
      }
    } finally {
      setLookupLoading(false);
    }
  };

  const filteredRows = demoTrades.filter(
    (t) => filter === "All" || t.status.toLowerCase() === filter.toLowerCase(),
  );

  return (
    <>
      <PageHeader
        eyebrow="YOUR MARKET ACTIVITY"
        title="Every trade, in view."
        description="Follow proposals, delivery windows and final outcomes in one place."
      />

      {/* Trade UUID Lookup Card */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fafbf7",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: 8,
          padding: "12px 18px",
          marginBottom: 16,
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Layers size={16} color="#475569" />
          <span>
            Inspect Specific Trade: <strong>GET /api/v1/trades/:id</strong>
          </span>
        </div>
        <form
          onSubmit={handleLookup}
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <input
            type="text"
            placeholder="Enter Trade UUID…"
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            style={{
              padding: "5px 10px",
              fontSize: 11,
              width: 240,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
            }}
          />
          <button
            type="submit"
            className="button secondary"
            style={{ padding: "5px 10px", fontSize: 11 }}
            disabled={lookupLoading || !lookupId.trim()}
          >
            {lookupLoading ? (
              <RefreshCw
                size={12}
                className="spin"
                style={{ marginRight: 4 }}
              />
            ) : (
              <Search size={12} style={{ marginRight: 4 }} />
            )}
            {lookupLoading ? "Loading…" : "Inspect"}
          </button>
        </form>
      </div>

      {lookupError && (
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
          <strong>Trade Inspection Failed ({lookupError.code}):</strong>
          <div>{lookupError.message}</div>
          {lookupError.requestId && (
            <div style={{ fontSize: 10, marginTop: 4, color: "#7f1d1d" }}>
              Request ID: <code>{lookupError.requestId}</code>
            </div>
          )}
        </div>
      )}

      <Card
        title="Trade history"
        subtitle="Illustrative community trades"
        action={
          <Tabs
            items={["All", "Proposed", "Settled", "Rejected"]}
            value={filter}
            onChange={setFilter}
          />
        }
      >
        <TradeTable rows={filteredRows} onSelect={setSelected} />
      </Card>

      <Note>
        Matching creates a proposal. Grid validation, pricing and commitment
        must complete before a trade can move toward delivery and settlement.
      </Note>

      {selected && (
        <TradeDetailModal trade={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
