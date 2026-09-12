import { useState, useEffect } from "react";
import { ArrowRight, ShieldCheck, AlertTriangle, Send } from "lucide-react";
import { Modal, Note, Badge } from "../../components/ui";
import { readConnection, ApiError, request } from "../../lib/api";
import {
  getDayAheadDeliveryWindow,
  formatDecimalString,
  evaluateOrderPreFlight,
  type EligibilityData,
  type SurplusData,
} from "./marketUtils";
import { submitMarketOrder, type OrderResponse } from "./marketApi";

interface LiveOrderModalProps {
  initialSide: string;
  initialQuantity?: string;
  initialPrice?: string;
  sessionStatus?: string;
  sessionId?: string;
  onClose: () => void;
  onSuccess?: (order: OrderResponse) => void;
}

export default function LiveOrderModal({
  initialSide,
  initialQuantity = "12.5",
  initialPrice = "4.65",
  sessionStatus = "OPEN",
  sessionId = "",
  onClose,
  onSuccess,
}: LiveOrderModalProps) {
  const [side, setSide] = useState(
    initialSide.toLowerCase().includes("buy") ? "Buy" : "Sell",
  );
  const [quantity, setQuantity] = useState(initialQuantity);
  const [price, setPrice] = useState(initialPrice);

  const conn = readConnection();
  const [customSessionId, setCustomSessionId] = useState(
    sessionId || conn.sessionId || "",
  );
  const [customUserId, setCustomUserId] = useState(conn.userId || "");
  const [customSiteId, setCustomSiteId] = useState(conn.siteId || "");

  const [submitting, setSubmitting] = useState(false);
  const [liveSuccess, setLiveSuccess] = useState<OrderResponse | null>(null);
  const [liveError, setLiveError] = useState<{
    message: string;
    code: string;
    requestId?: string;
  } | null>(null);

  const [eligibility, setEligibility] = useState<EligibilityData | null>(null);
  const [surplus, setSurplus] = useState<SurplusData | null>(null);
  const [checkingPreFlight, setCheckingPreFlight] = useState(false);

  const deliveryWindow = getDayAheadDeliveryWindow();

  useEffect(() => {
    let active = true;
    if (!customUserId) {
      setEligibility(null);
      return;
    }

    async function checkRequirements() {
      setCheckingPreFlight(true);
      try {
        const elig = await request<EligibilityData>(
          `/api/v1/users/${customUserId}/eligibility`,
          customUserId,
        ).catch(() => null);
        if (active) setEligibility(elig);

        if (customSiteId && side.toLowerCase() === "sell") {
          const sur = await request<SurplusData>(
            `/api/v1/sites/${customSiteId}/surplus`,
            customUserId,
          ).catch(() => null);
          if (active) setSurplus(sur);
        } else {
          if (active) setSurplus(null);
        }
      } finally {
        if (active) setCheckingPreFlight(false);
      }
    }

    void checkRequirements();
    return () => {
      active = false;
    };
  }, [customUserId, customSiteId, side]);

  const preFlight = evaluateOrderPreFlight({
    side: side.toLowerCase() as "buy" | "sell",
    energyKwh: parseFloat(quantity) || 0,
    sessionStatus: sessionStatus,
    eligibility,
    surplus,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLiveError(null);
    setLiveSuccess(null);

    if (!customSessionId || !customUserId || !customSiteId) {
      setLiveError({
        message:
          "Missing connection UUIDs (Session, User, or Site). Please enter them below.",
        code: "CONFIGURATION_REQUIRED",
      });
      return;
    }

    if (!preFlight.canProceed) {
      setLiveError({
        message: preFlight.blockers.join(" "),
        code: "PREFLIGHT_VALIDATION_FAILED",
      });
      return;
    }

    setSubmitting(true);
    try {
      const isBuy = side.toLowerCase() === "buy";
      const payload = {
        market_session_id: customSessionId,
        user_id: customUserId,
        site_id: customSiteId,
        side: (isBuy ? "buy" : "sell") as "buy" | "sell",
        energy_kwh: formatDecimalString(quantity, 3),
        delivery_start: deliveryWindow.startIso,
        delivery_end: deliveryWindow.endIso,
        max_price_inr_per_kwh: isBuy ? formatDecimalString(price, 2) : null,
        min_price_inr_per_kwh: !isBuy ? formatDecimalString(price, 2) : null,
      };

      const result = await submitMarketOrder(payload, customUserId);
      setLiveSuccess(result);
      if (onSuccess) onSuccess(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setLiveError({
          message: err.message,
          code: err.code,
          requestId: err.requestId,
        });
      } else {
        setLiveError({
          message:
            err instanceof Error
              ? err.message
              : "Failed to place market order.",
          code: "SUBMISSION_FAILED",
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={
        liveSuccess
          ? "Order Placed Successfully"
          : "Live Market Order Submission"
      }
      onClose={onClose}
    >
      {liveSuccess ? (
        <div>
          <Badge tone="green">ORDER ACCEPTED</Badge>
          <h3 style={{ margin: "14px 0" }}>Order {liveSuccess.id}</h3>
          <div className="simple-list">
            <div>
              <span>Side</span>
              <strong>{liveSuccess.side.toUpperCase()}</strong>
            </div>
            <div>
              <span>Energy</span>
              <strong>{liveSuccess.energy_kwh} kWh</strong>
            </div>
            <div>
              <span>Limit price</span>
              <strong>
                ₹
                {liveSuccess.max_price_inr_per_kwh ||
                  liveSuccess.min_price_inr_per_kwh}
                /kWh
              </strong>
            </div>
            <div>
              <span>Status</span>
              <Badge tone="neutral">{liveSuccess.status}</Badge>
            </div>
          </div>
          <Note>
            Order has been placed and verified by the backend. It will be
            matched upon session closing. No retries are automatically
            performed.
          </Note>
          <button className="button primary full" onClick={onClose}>
            Back to Marketplace
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          {/* Pre-flight Gate Banner */}
          <div
            style={{
              background: "#f0fdf4",
              border: "1px solid #bbf7d0",
              borderRadius: 8,
              padding: "10px 14px",
              marginBottom: 14,
              fontSize: 12,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 6,
              }}
            >
              <ShieldCheck size={16} color="#16a34a" />
              <strong>Pre-Flight Verification Gate</strong>
            </div>
            <div>
              Session Status: <strong>{sessionStatus.toUpperCase()}</strong>
            </div>
            {eligibility && (
              <div style={{ marginTop: 4 }}>
                User Eligibility:{" "}
                <Badge
                  tone={
                    (
                      side === "Buy"
                        ? eligibility.can_buy
                        : eligibility.can_sell
                    )
                      ? "green"
                      : "red"
                  }
                >
                  {side === "Buy"
                    ? eligibility.can_buy
                      ? "Can Buy"
                      : "Cannot Buy"
                    : eligibility.can_sell
                      ? "Can Sell"
                      : "Cannot Sell"}
                </Badge>
              </div>
            )}
            {checkingPreFlight && (
              <small style={{ color: "#64748b" }}>
                Checking eligibility and forecast surplus…
              </small>
            )}
          </div>

          {preFlight.blockers.length > 0 && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                padding: 10,
                borderRadius: 8,
                marginBottom: 12,
                fontSize: 12,
                color: "#991b1b",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontWeight: 600,
                  marginBottom: 4,
                }}
              >
                <AlertTriangle size={14} /> Submission Blocked
              </div>
              {preFlight.blockers.map((b, i) => (
                <div key={i}>• {b}</div>
              ))}
            </div>
          )}

          {preFlight.warnings.length > 0 && (
            <div
              style={{
                background: "#fffbeb",
                border: "1px solid #fef3c7",
                padding: 10,
                borderRadius: 8,
                marginBottom: 12,
                fontSize: 12,
                color: "#92400e",
              }}
            >
              {preFlight.warnings.map((w, i) => (
                <div key={i}>⚠ {w}</div>
              ))}
            </div>
          )}

          {liveError && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #ef4444",
                padding: 10,
                borderRadius: 8,
                marginBottom: 12,
                color: "#b91c1c",
                fontSize: 12,
              }}
            >
              <strong>Submission Error ({liveError.code}):</strong>
              <div>{liveError.message}</div>
              {liveError.requestId && (
                <div style={{ fontSize: 10, marginTop: 4, color: "#7f1d1d" }}>
                  Request ID: <code>{liveError.requestId}</code>
                </div>
              )}
            </div>
          )}

          <label>
            Order side
            <select
              name="side"
              value={side}
              onChange={(e) => setSide(e.target.value)}
            >
              <option value="Buy">Buy (Max limit price)</option>
              <option value="Sell">Sell (Min reservation price)</option>
            </select>
          </label>

          <div className="form-grid">
            <label>
              Energy (kWh)
              <input
                type="number"
                min="0.001"
                step="0.001"
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </label>
            <label>
              {side === "Buy"
                ? "Max limit price (INR/kWh)"
                : "Min reservation price (INR/kWh)"}
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </label>
          </div>

          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}
          >
            <label>
              User UUID
              <input
                type="text"
                placeholder="User UUID…"
                value={customUserId}
                onChange={(e) => setCustomUserId(e.target.value.trim())}
                required
              />
            </label>
            <label>
              Site UUID
              <input
                type="text"
                placeholder="Site UUID…"
                value={customSiteId}
                onChange={(e) => setCustomSiteId(e.target.value.trim())}
                required
              />
            </label>
          </div>

          <label>
            Market Session UUID
            <input
              type="text"
              placeholder="Session UUID…"
              value={customSessionId}
              onChange={(e) => setCustomSessionId(e.target.value.trim())}
              required
            />
          </label>

          <label>
            Delivery window (IST)
            <input value={deliveryWindow.label} readOnly />
          </label>

          <button
            className="button primary full"
            type="submit"
            disabled={submitting || !preFlight.canProceed}
          >
            {submitting ? "Placing Order…" : "Submit Order to Market"}{" "}
            <Send size={15} style={{ marginLeft: 6 }} />
          </button>
        </form>
      )}
    </Modal>
  );
}
