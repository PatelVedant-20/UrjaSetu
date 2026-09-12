import { useState, useEffect } from "react";
import { Plus, ArrowRight, RefreshCw, Layers, Send } from "lucide-react";
import {
  PageHeader,
  Card,
  Tabs,
  Badge,
  Note,
  Status,
} from "../../components/ui";
import EnergyChart from "../../components/EnergyChart";
import { money } from "../../lib/format";
import { readConnection, ApiError } from "../../lib/api";
import OrderModal from "./OrderModal";
import LiveOrderModal from "./LiveOrderModal";
import { getDayAheadDeliveryWindow } from "./marketUtils";
import {
  fetchCurrentSession,
  fetchSessionById,
  fetchOrderBook,
  fetchPricingQuote,
  type MarketSessionResponse,
  type OrderBookResponse,
  type PricingQuoteResult,
} from "./marketApi";

export default function MarketPage() {
  const [side, setSide] = useState("Buy energy");
  const [openDemoModal, setOpenDemoModal] = useState(false);
  const [openLiveModal, setOpenLiveModal] = useState(false);
  const [drafts, setDrafts] = useState<
    { side: string; quantity: string; price: string }[]
  >([]);
  const [saved, setSaved] = useState(false);

  // For passing a draft into live modal
  const [activeDraftForLive, setActiveDraftForLive] = useState<{
    side: string;
    quantity: string;
    price: string;
  } | null>(null);

  // Session state & awareness
  const [session, setSession] = useState<MarketSessionResponse | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [manualSessionId, setManualSessionId] = useState("");

  // Dynamic pricing calculation from backend
  const [quoteResult, setQuoteResult] = useState<PricingQuoteResult | null>(
    null,
  );
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const calculateLiveQuote = async () => {
    setQuoteLoading(true);
    setQuoteError(null);
    try {
      const window = getDayAheadDeliveryWindow();
      const res = await fetchPricingQuote({
        base_price_inr_per_kwh: "4.50",
        quantity_kwh: "10.0",
        delivery_start: window.startIso,
        delivery_end: window.endIso,
        local_renewable: true,
      });
      setQuoteResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setQuoteError(`${err.message} (${err.code})`);
      } else {
        setQuoteError("Failed to calculate quote from pricing engine.");
      }
    } finally {
      setQuoteLoading(false);
    }
  };

  // Live order book
  const [orderBook, setOrderBook] = useState<OrderBookResponse | null>(null);

  const deliveryWindow = getDayAheadDeliveryWindow();
  const conn = readConnection();
  const activeSessionId = manualSessionId || conn.sessionId;

  const loadSession = async () => {
    if (!activeSessionId) {
      // Try current session route if present
      setSessionLoading(true);
      setSessionError(null);
      try {
        const current = await fetchCurrentSession();
        setSession(current);
      } catch (err) {
        if (err instanceof ApiError) {
          setSessionError(
            "Backend route /market/sessions/current is not mounted. Connect a Session UUID below or in Settings.",
          );
        }
      } finally {
        setSessionLoading(false);
      }
      return;
    }

    setSessionLoading(true);
    setSessionError(null);
    try {
      const data = await fetchSessionById(activeSessionId);
      setSession(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setSessionError(`${err.message} (${err.code})`);
      } else {
        setSessionError("Failed to load market session.");
      }
    } finally {
      setSessionLoading(false);
    }
  };

  useEffect(() => {
    if (activeSessionId) {
      void loadSession();
    }
  }, [activeSessionId]);

  // Load order book when session is active
  useEffect(() => {
    if (!session?.id) return;
    let active = true;

    fetchOrderBook(session.id)
      .then((data) => {
        if (active) setOrderBook(data);
      })
      .catch(() => {
        if (active) setOrderBook(null);
      });

    return () => {
      active = false;
    };
  }, [session?.id]);

  const effectiveStatus = session?.status || "open";

  return (
    <>
      <PageHeader
        eyebrow="LOCAL SUPPLY. SHARED OPPORTUNITY."
        title="Energy marketplace"
        description="Explore tomorrow’s energy offers and find a place for your surplus."
        action={
          <div style={{ display: "flex", gap: 10 }}>
            <button
              className="button primary"
              onClick={() => {
                setSaved(false);
                setOpenDemoModal(true);
              }}
            >
              <Plus size={17} /> Create demo order
            </button>
            <button
              className="button secondary"
              onClick={() => {
                setActiveDraftForLive(null);
                setOpenLiveModal(true);
              }}
            >
              <Send size={15} /> Live order
            </button>
          </div>
        }
      />

      <div className="market-banner">
        <div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Badge tone="green">DAY-AHEAD MARKET</Badge>
            <Status value={effectiveStatus} />
          </div>
          <h2>Tomorrow starts with today’s sunshine.</h2>
          <p>
            Delivery window: 13 September 2026 · Asia/Kolkata · Session state:{" "}
            <strong>{effectiveStatus.toUpperCase()}</strong>
          </p>
          {sessionError && (
            <div style={{ marginTop: 8, fontSize: 11, color: "#854d0e" }}>
              ℹ {sessionError}
            </div>
          )}
        </div>
        <div className="market-price">
          <small>INDICATIVE PRICE</small>
          <strong>
            ₹4.65 <span>/ kWh</span>
          </strong>
          <div style={{ fontSize: 9, color: "#64748b", marginTop: 4 }}>
            Next-day settlement
          </div>
        </div>
      </div>

      {/* Session inspector & helper */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fafbf7",
          border: "1px solid var(--line, #e2e8f0)",
          borderRadius: 8,
          padding: "10px 16px",
          margin: "16px 0",
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Layers size={16} color="#475569" />
          <span>
            Market Session:{" "}
            <strong>
              {session?.id
                ? `Active (${session.id.slice(0, 8)}…)`
                : "Illustrative Preview"}
            </strong>
          </span>
          <Badge tone={effectiveStatus === "open" ? "green" : "neutral"}>
            {effectiveStatus.toUpperCase()}
          </Badge>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="text"
            placeholder="Load Session UUID…"
            value={manualSessionId}
            onChange={(e) => setManualSessionId(e.target.value.trim())}
            style={{
              padding: "4px 8px",
              fontSize: 11,
              width: 190,
              borderRadius: 4,
              border: "1px solid #cbd5e1",
            }}
          />
          <button
            className="button secondary"
            style={{ padding: "4px 8px", fontSize: 11 }}
            disabled={sessionLoading}
            onClick={() => void loadSession()}
          >
            <RefreshCw
              size={12}
              className={sessionLoading ? "spin" : ""}
              style={{ marginRight: 4 }}
            />
            {sessionLoading ? "Checking…" : "Query Session"}
          </button>
        </div>
      </div>

      <div className="split-main">
        <Card
          title="Market price trend"
          subtitle="Illustrative INR/kWh · not a live price feed"
        >
          <EnergyChart kind="price" />
        </Card>
        <Card
          title="What makes up the price?"
          subtitle={
            quoteResult
              ? `Dynamic quote · Engine: ${quoteResult.engine} (${quoteResult.formula_version})`
              : "Illustrative composition · INR/kWh"
          }
          action={
            <button
              className="button secondary"
              style={{ fontSize: 11, padding: "4px 8px" }}
              disabled={quoteLoading}
              onClick={() => void calculateLiveQuote()}
              aria-label="Calculate live explainable quote"
            >
              <RefreshCw
                size={11}
                className={quoteLoading ? "spin" : ""}
                style={{ marginRight: 4 }}
              />
              {quoteLoading ? "Calculating…" : "Live quote"}
            </button>
          }
        >
          <div className="price-breakdown">
            {[
              [
                "Base market price",
                quoteResult
                  ? `₹${Number(quoteResult.base_market_price).toFixed(2)}`
                  : "₹4.50",
              ],
              [
                "Time component (wheeling)",
                quoteResult
                  ? `${Number(quoteResult.time_component) >= 0 ? "+ " : ""}${money(quoteResult.time_component)}`
                  : "+ ₹0.20",
              ],
              [
                "Congestion component",
                quoteResult
                  ? `${Number(quoteResult.congestion_component) >= 0 ? "+ " : ""}${money(quoteResult.congestion_component)}`
                  : "₹0.00",
              ],
              [
                "Imbalance component",
                quoteResult
                  ? `${Number(quoteResult.imbalance_component) >= 0 ? "+ " : ""}${money(quoteResult.imbalance_component)}`
                  : "+ ₹0.10",
              ],
              [
                "Local renewable incentive",
                quoteResult
                  ? `${Number(quoteResult.local_renewable_component) <= 0 ? "− " : "+ "}${money(Math.abs(Number(quoteResult.local_renewable_component)))}`
                  : "− ₹0.15",
              ],
            ].map(([k, v]) => (
              <div className="metric-line" key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
              </div>
            ))}
            <div className="price-total">
              <span>
                {quoteResult
                  ? "Calculated final price"
                  : "Indicative final price"}
              </span>
              <strong>
                {quoteResult
                  ? `₹${Number(quoteResult.final_price).toFixed(2)}`
                  : "₹4.65"}
              </strong>
            </div>
          </div>
          {quoteError && (
            <p className="error-text" style={{ fontSize: 11, marginTop: 6 }}>
              Quote note: {quoteError}
            </p>
          )}
          <Note>
            {quoteResult
              ? "Authoritative pricing breakdown calculated by backend dynamic pricing engine (POST /pricing/quote)."
              : "Final prices and decisions come from the backend pricing engine. The price chart is an illustrative composition, not a live market-wide feed."}
          </Note>
        </Card>
      </div>

      <Card
        title="Community order book"
        subtitle={`Offers & bids · delivery 13 Sep, 12:00–13:00 IST`}
        action={
          <Tabs
            items={["Buy energy", "Sell energy"]}
            value={side}
            onChange={setSide}
          />
        }
      >
        {orderBook &&
        (side === "Buy energy" ? orderBook.sells : orderBook.buys).length >
          0 ? (
          <div className="offer-grid">
            {(side === "Buy energy" ? orderBook.sells : orderBook.buys).map(
              (entry) => (
                <div className="offer" key={entry.order_id}>
                  <div className="offer-top">
                    <span className="avatar pale">
                      {entry.user_id.slice(0, 2).toUpperCase()}
                    </span>
                    <Badge tone={side === "Buy energy" ? "green" : "neutral"}>
                      {side === "Buy energy" ? "SELL OFFER" : "BUY BID"}
                    </Badge>
                  </div>
                  <h3>Site {entry.site_id.slice(0, 8)}</h3>
                  <p>Grid node · Connected Feeder</p>
                  <div className="offer-values">
                    <div>
                      <strong>{entry.remaining_kwh}</strong>
                      <small>kWh available</small>
                    </div>
                    <div>
                      <strong>
                        {money(
                          entry.max_price_inr_per_kwh ||
                            entry.min_price_inr_per_kwh ||
                            "4.65",
                        )}
                      </strong>
                      <small>per kWh</small>
                    </div>
                  </div>
                  <button
                    className="button secondary full"
                    onClick={() => {
                      setSaved(false);
                      setOpenDemoModal(true);
                    }}
                  >
                    Prepare demo {side === "Buy energy" ? "buy" : "sell"} order{" "}
                    <ArrowRight size={15} />
                  </button>
                </div>
              ),
            )}
          </div>
        ) : (
          <div className="offer-grid">
            {(side === "Buy energy"
              ? [
                  [
                    "Mehta Rooftop",
                    "8.2",
                    "4.45",
                    "/images/sites/mehta-rooftop.jpg",
                  ],
                  [
                    "Patel Residence",
                    "10.0",
                    "4.70",
                    "/images/sites/patel-residence.jpg",
                  ],
                  [
                    "Aarav Residence",
                    "12.5",
                    "4.65",
                    "/images/sites/aarav-residence.jpg",
                  ],
                ]
              : [
                  [
                    "Greenview Society",
                    "18.0",
                    "4.80",
                    "/images/sites/greenview-society.jpg",
                  ],
                  [
                    "Community Library",
                    "6.0",
                    "4.60",
                    "/images/sites/community-library.jpg",
                  ],
                ]
            ).map(([name, energy, price, imgUrl]) => (
              <div className="offer" key={name}>
                <div className="offer-top">
                  <span
                    className="avatar pale"
                    style={{
                      overflow: "hidden",
                      border: "1px solid #e2e8f0",
                    }}
                  >
                    {imgUrl ? (
                      <img
                        src={imgUrl}
                        alt={name}
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "cover",
                        }}
                        loading="lazy"
                      />
                    ) : (
                      name
                        .split(" ")
                        .map((s) => s[0])
                        .join("")
                    )}
                  </span>
                  <Badge tone="neutral">
                    {side === "Buy energy" ? "SELL OFFER" : "BUY BID"}
                  </Badge>
                </div>
                <h3>{name}</h3>
                <p>Community feeder · Solar energy</p>
                <div className="offer-values">
                  <div>
                    <strong>{energy}</strong>
                    <small>kWh available</small>
                  </div>
                  <div>
                    <strong>{money(price)}</strong>
                    <small>per kWh</small>
                  </div>
                </div>
                <button
                  className="button secondary full"
                  onClick={() => {
                    setSaved(false);
                    setOpenDemoModal(true);
                  }}
                >
                  Prepare demo {side === "Buy energy" ? "buy" : "sell"} order{" "}
                  <ArrowRight size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {drafts.length > 0 && (
        <Card
          title="Your local drafts"
          subtitle="Browser memory only · not submitted"
        >
          <div className="simple-list">
            {drafts.map((d, i) => (
              <div key={i}>
                <div>
                  <strong>{d.side}</strong>
                  <span style={{ marginLeft: 8 }}>
                    {d.quantity} kWh · {money(d.price)}/kWh
                  </span>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge tone="neutral">Local draft</Badge>
                  <button
                    className="text-button"
                    style={{ fontSize: 11 }}
                    onClick={() => {
                      setActiveDraftForLive(d);
                      setOpenLiveModal(true);
                    }}
                  >
                    Submit to Market →
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {openDemoModal && (
        <OrderModal
          initialSide={side}
          onClose={() => setOpenDemoModal(false)}
          saved={saved}
          setSaved={setSaved}
          onSaveDraft={(d) => {
            setDrafts((prev) => [...prev, d]);
          }}
        />
      )}

      {openLiveModal && (
        <LiveOrderModal
          initialSide={activeDraftForLive?.side || side}
          initialQuantity={activeDraftForLive?.quantity || "12.5"}
          initialPrice={activeDraftForLive?.price || "4.65"}
          sessionStatus={effectiveStatus}
          sessionId={activeSessionId}
          onClose={() => setOpenLiveModal(false)}
        />
      )}
    </>
  );
}
