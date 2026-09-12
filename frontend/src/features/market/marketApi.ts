import { ApiError, request } from "../../lib/api";

export interface MarketSessionResponse {
  id: string;
  market_date: string;
  market_type: string;
  status: "pending" | "open" | "closed" | "cleared";
  opened_at?: string | null;
  closed_at?: string | null;
  cleared_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderBookEntry {
  order_id: string;
  side: "buy" | "sell";
  user_id: string;
  site_id: string;
  remaining_kwh: string | number;
  delivery_start: string;
  delivery_end: string;
  max_price_inr_per_kwh?: string | number | null;
  min_price_inr_per_kwh?: string | number | null;
}

export interface OrderBookResponse {
  market_session_id: string;
  market_date: string;
  market_type: string;
  total_demand_kwh: string | number;
  total_supply_kwh: string | number;
  buys: OrderBookEntry[];
  sells: OrderBookEntry[];
}

export interface OrderCreatePayload {
  market_session_id: string;
  user_id: string;
  site_id: string;
  node_id?: string | null;
  side: "buy" | "sell";
  energy_kwh: string;
  delivery_start: string;
  delivery_end: string;
  min_price_inr_per_kwh?: string | null;
  max_price_inr_per_kwh?: string | null;
}

export interface OrderResponse {
  id: string;
  market_session_id: string;
  user_id: string;
  site_id: string;
  side: string;
  energy_kwh: string;
  matched_kwh: string;
  min_price_inr_per_kwh?: string | null;
  max_price_inr_per_kwh?: string | null;
  delivery_start: string;
  delivery_end: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TradeResponse {
  id: string;
  buy_order_id: string;
  sell_order_id: string;
  quantity_kwh: string | number;
  clearing_price_inr_per_kwh: string | number;
  delivery_start: string;
  delivery_end: string;
  grid_validation_id?: string | null;
  status: "proposed" | "settled" | "rejected";
  committed_at?: string | null;
  matching_engine?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PriceBreakdownResponse {
  trade_id: string;
  base_rate_inr_per_kwh: string | number;
  time_component_inr_per_kwh: string | number;
  congestion_component_inr_per_kwh: string | number;
  imbalance_component_inr_per_kwh: string | number;
  local_renewable_component_inr_per_kwh: string | number;
  final_price_inr_per_kwh: string | number;
  formula_version?: string;
}

/**
 * Attempts to fetch current active market session.
 */
export async function fetchCurrentSession(
  signal?: AbortSignal,
): Promise<MarketSessionResponse> {
  return request<MarketSessionResponse>(
    "/api/v1/market/sessions/current",
    "",
    signal,
  );
}

/**
 * Fetches market session by ID.
 */
export async function fetchSessionById(
  sessionId: string,
  signal?: AbortSignal,
): Promise<MarketSessionResponse> {
  return request<MarketSessionResponse>(
    `/api/v1/market/sessions/${sessionId}`,
    "",
    signal,
  );
}

/**
 * Fetches order book for a market session.
 */
export async function fetchOrderBook(
  sessionId: string,
  signal?: AbortSignal,
): Promise<OrderBookResponse> {
  return request<OrderBookResponse>(
    `/api/v1/market/order-book?session_id=${sessionId}`,
    "",
    signal,
  );
}

/**
 * Submits an order mutation to the backend.
 * Critical safety: Zero automatic retries to prevent duplicate financial orders.
 */
export async function submitMarketOrder(
  payload: OrderCreatePayload,
  userId: string,
): Promise<OrderResponse> {
  const response = await fetch("/api/v1/orders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-User-Id": userId } : {}),
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || `Order creation failed (${response.status})`,
      body?.error?.code || "ORDER_CREATION_FAILED",
      body?.error?.request_id,
    );
  }

  if (body === null) {
    throw new ApiError(
      "The server did not return valid JSON.",
      "INVALID_RESPONSE",
    );
  }

  return body as OrderResponse;
}

/**
 * Fetches single trade detail by ID.
 */
export async function fetchTradeById(
  tradeId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<TradeResponse> {
  return request<TradeResponse>(`/api/v1/trades/${tradeId}`, userId, signal);
}

/**
 * Fetches price breakdown for a trade.
 */
export async function fetchTradePriceBreakdown(
  tradeId: string,
  signal?: AbortSignal,
): Promise<PriceBreakdownResponse> {
  return request<PriceBreakdownResponse>(
    `/api/v1/trades/${tradeId}/price-breakdown`,
    "",
    signal,
  );
}

export interface PricingQuotePayload {
  base_price_inr_per_kwh: number | string;
  quantity_kwh: number | string;
  delivery_start: string;
  delivery_end: string;
  local_renewable?: boolean;
  grid_status?: string;
  forecast_confidence?: number | string;
}

export interface PricingQuoteComponent {
  kind: string;
  amount_inr_per_kwh: number | string;
  reason: string;
}

export interface PricingQuoteResult {
  formula_version: string;
  engine: string;
  base_market_price: number | string;
  time_component: number | string;
  congestion_component: number | string;
  imbalance_component: number | string;
  local_renewable_component: number | string;
  final_price: number | string;
  components: PricingQuoteComponent[];
  recommended_decision: string;
  grid_status: string;
}

/**
 * Calculates an explainable dynamic price quote before trade commitment.
 * Maps to POST /api/v1/pricing/quote
 */
export async function fetchPricingQuote(
  payload: PricingQuotePayload,
  signal?: AbortSignal,
): Promise<PricingQuoteResult> {
  const response = await fetch("/api/v1/pricing/quote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || `Pricing quote failed (${response.status})`,
      body?.error?.code || "PRICING_QUOTE_FAILED",
      body?.error?.request_id,
    );
  }

  if (body === null) {
    throw new ApiError(
      "The server did not return valid JSON for pricing quote.",
      "INVALID_RESPONSE",
    );
  }

  return body as PricingQuoteResult;
}
