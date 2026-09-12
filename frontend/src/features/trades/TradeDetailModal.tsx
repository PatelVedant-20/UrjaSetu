import { useEffect, useState } from "react";
import { Modal, Status, Note, Badge } from "../../components/ui";
import { money } from "../../lib/format";
import {
  fetchTradePriceBreakdown,
  type PriceBreakdownResponse,
} from "../market/marketApi";
import type { TradeItem } from "../../components/TradeTable";

interface TradeDetailModalProps {
  trade: TradeItem;
  onClose: () => void;
}

export default function TradeDetailModal({
  trade,
  onClose,
}: TradeDetailModalProps) {
  const [breakdown, setBreakdown] = useState<PriceBreakdownResponse | null>(
    null,
  );
  const [loadingBreakdown, setLoadingBreakdown] = useState(false);

  const energyNum = Number(trade.energy) || 0;
  const priceNum = Number(trade.price) || 0;
  const totalValue = trade.total ? Number(trade.total) : energyNum * priceNum;

  useEffect(() => {
    // Only attempt breakdown for UUID-like IDs
    const isUuid =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        trade.id,
      );
    if (!isUuid) return;

    let active = true;
    setLoadingBreakdown(true);
    fetchTradePriceBreakdown(trade.id)
      .then((data) => {
        if (active) setBreakdown(data);
      })
      .catch(() => {
        if (active) setBreakdown(null);
      })
      .finally(() => {
        if (active) setLoadingBreakdown(false);
      });

    return () => {
      active = false;
    };
  }, [trade.id]);

  return (
    <Modal title={`Trade ${trade.id}`} onClose={onClose}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <Status value={trade.status} />
        <span
          className={`side ${trade.side.toLowerCase()}`}
          style={{ fontSize: 12, fontWeight: 600 }}
        >
          {trade.side.toLowerCase() === "sell" ? "↗" : "↙"} {trade.side}
        </span>
      </div>

      <h3 style={{ margin: "0 0 16px" }}>{trade.name}</h3>

      <div className="simple-list">
        <div>
          <span>Delivery window (IST)</span>
          <strong>{trade.window}</strong>
        </div>
        <div>
          <span>Contracted energy</span>
          <strong>{trade.energy} kWh</strong>
        </div>
        <div>
          <span>Clearing price</span>
          <strong>{money(trade.price)} / kWh</strong>
        </div>
        <div>
          <span>Total contracted value</span>
          <strong>{money(totalValue)}</strong>
        </div>
        {trade.buy_order_id && (
          <div>
            <span>Buyer order</span>
            <code style={{ fontSize: 10 }}>{trade.buy_order_id}</code>
          </div>
        )}
        {trade.sell_order_id && (
          <div>
            <span>Seller order</span>
            <code style={{ fontSize: 10 }}>{trade.sell_order_id}</code>
          </div>
        )}
        <div>
          <span>Grid validation</span>
          {trade.grid_validation_id ? (
            <Badge tone="green">
              Validated ({trade.grid_validation_id.slice(0, 8)}…)
            </Badge>
          ) : trade.status === "proposed" ? (
            <Badge tone="amber">Pending Power-Flow Solver</Badge>
          ) : (
            <Badge tone="neutral">Evaluated</Badge>
          )}
        </div>
      </div>

      {loadingBreakdown && (
        <small style={{ color: "#64748b", display: "block", margin: "8px 0" }}>
          Loading price breakdown…
        </small>
      )}

      {breakdown && (
        <div
          style={{
            background: "#fafbf7",
            border: "1px solid var(--line, #e2e8f0)",
            borderRadius: 8,
            padding: 12,
            margin: "12px 0",
            fontSize: 11,
          }}
        >
          <strong style={{ display: "block", marginBottom: 6 }}>
            Authoritative Price Breakdown:
          </strong>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Base rate:</span>
            <strong>{money(breakdown.base_rate_inr_per_kwh)}/kWh</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Time component:</span>
            <strong>{money(breakdown.time_component_inr_per_kwh)}/kWh</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Congestion charge:</span>
            <strong>
              {money(breakdown.congestion_component_inr_per_kwh)}/kWh
            </strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Local renewable incentive:</span>
            <strong>
              {money(breakdown.local_renewable_component_inr_per_kwh)}/kWh
            </strong>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              borderTop: "1px solid #e2e8f0",
              paddingTop: 4,
              marginTop: 4,
              fontWeight: 600,
            }}
          >
            <span>Final Clearing Price:</span>
            <strong>{money(breakdown.final_price_inr_per_kwh)}/kWh</strong>
          </div>
        </div>
      )}

      <Note>
        <strong>Physical & Regulatory Reality:</strong> Matching creates a{" "}
        <em>proposed trade</em>; it is not committed until power-flow grid
        validation confirms feeder capacity. Physical electricity is delivered
        through the DISCOM distribution grid, not peer-to-peer wiring. Final
        financial settlement occurs only after meter readings are reconciled.
      </Note>
    </Modal>
  );
}
