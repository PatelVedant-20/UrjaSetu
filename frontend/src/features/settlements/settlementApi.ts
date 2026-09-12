import { ApiError, request } from "../../lib/api";

export interface SettlementRecord {
  id: string;
  trade_id: string;
  buyer_user_id: string;
  seller_user_id: string;
  settled_kwh: number | string;
  gross_amount_inr: number | string;
  platform_fee_inr: number | string;
  balancing_charge_inr: number | string;
  seller_credit_inr: number | string;
  buyer_debit_inr: number | string;
  status: "pending" | "reconciled" | "settled" | "disputed";
  settled_at: string;
  created_at: string;
  updated_at: string;
}

export interface MeterReconciliation {
  id: string;
  trade_id: string;
  committed_kwh: number | string;
  actual_kwh?: number | string | null;
  deviation_kwh?: number | string | null;
  within_tolerance: boolean;
  balancing_kwh: number | string;
  reconciliation_status: "matched" | "shortfall" | "excess" | "unmeasured";
  reason?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Fetches settlement history for a specific user.
 * Maps to GET /api/v1/users/{user_id}/settlements
 */
export async function getUserSettlements(
  userId: string,
  signal?: AbortSignal,
): Promise<SettlementRecord[]> {
  if (!userId.trim()) return [];
  return request<SettlementRecord[]>(
    `/api/v1/users/${encodeURIComponent(userId)}/settlements`,
    userId,
    signal,
  );
}

/**
 * Fetches a single settlement record by settlement UUID.
 * Maps to GET /api/v1/settlements/{settlement_id}
 */
export async function getSettlementById(
  settlementId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<SettlementRecord> {
  return request<SettlementRecord>(
    `/api/v1/settlements/${encodeURIComponent(settlementId)}`,
    userId,
    signal,
  );
}

/**
 * Fetches settlement by trade ID or settlement ID.
 */
export async function getTradeSettlement(
  tradeOrSettlementId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<SettlementRecord> {
  return getSettlementById(tradeOrSettlementId, userId, signal);
}

/**
 * Trigger meter reconciliation for a trade.
 * Maps to POST /api/v1/trades/{trade_id}/reconcile
 */
export async function reconcileTrade(
  tradeId: string,
  userId = "",
): Promise<MeterReconciliation> {
  const response = await fetch(
    `/api/v1/trades/${encodeURIComponent(tradeId)}/reconcile`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(userId ? { "X-User-Id": userId } : {}),
      },
    },
  );

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || `Reconciliation failed (${response.status})`,
      body?.error?.code || "RECONCILIATION_FAILED",
      body?.error?.request_id,
    );
  }

  if (body === null) {
    throw new ApiError(
      "The server did not return valid JSON for trade reconciliation.",
      "INVALID_RESPONSE",
    );
  }

  return body as MeterReconciliation;
}

/**
 * Create final financial allocation and settle a completed trade.
 * Maps to POST /api/v1/trades/{trade_id}/settle
 */
export async function settleTrade(
  tradeId: string,
  userId = "",
): Promise<SettlementRecord> {
  const response = await fetch(
    `/api/v1/trades/${encodeURIComponent(tradeId)}/settle`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(userId ? { "X-User-Id": userId } : {}),
      },
    },
  );

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message ||
        `Settlement execution failed (${response.status})`,
      body?.error?.code || "SETTLEMENT_FAILED",
      body?.error?.request_id,
    );
  }

  if (body === null) {
    throw new ApiError(
      "The server did not return valid JSON for trade settlement.",
      "INVALID_RESPONSE",
    );
  }

  return body as SettlementRecord;
}
