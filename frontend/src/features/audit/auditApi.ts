import { ApiError, request } from "../../lib/api";

export type AuditEntityType = "order" | "trade" | "market_session";

export interface AuditEvent {
  id: string;
  event_type: string;
  entity_type: AuditEntityType | string;
  entity_id: string;
  event_time: string;
  recorded_at: string;
  actor_user_id?: string | null;
  payload_json: Record<string, unknown>;
  event_hash: string;
  previous_hash?: string | null;
  ledger_anchor_id?: string | null;
}

export interface ChainVerificationResult {
  intact: boolean;
  events_checked: number;
  broken_at_event_id?: string | null;
  problems: string[];
  summary: string;
}

/**
 * Fetches the chronological audit timeline for a specific business entity.
 * Maps to GET /api/v1/audit/entities/{entity_type}/{entity_id}
 */
export async function getEntityTimeline(
  entityType: string,
  entityId: string,
  userId = "",
  signal?: AbortSignal,
): Promise<AuditEvent[]> {
  if (!entityId.trim()) return [];
  return request<AuditEvent[]>(
    `/api/v1/audit/entities/${encodeURIComponent(entityType.toLowerCase())}/${encodeURIComponent(entityId.trim())}`,
    userId,
    signal,
  );
}

/**
 * Anchors the latest audit event for an entity to the external/local ledger adapter.
 * Maps to POST /api/v1/audit/anchor/{entity_type}/{entity_id}
 */
export async function anchorAuditEvent(
  entityType: string,
  entityId: string,
  userId = "",
): Promise<AuditEvent> {
  const response = await fetch(
    `/api/v1/audit/anchor/${encodeURIComponent(entityType.toLowerCase())}/${encodeURIComponent(entityId.trim())}`,
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
      body?.error?.message || `Anchor publication failed (${response.status})`,
      body?.error?.code || "ANCHOR_FAILED",
      body?.error?.request_id,
    );
  }

  if (body === null) {
    throw new ApiError(
      "The server did not return valid JSON for audit anchoring.",
      "INVALID_RESPONSE",
    );
  }

  return body as AuditEvent;
}
