# 05 — Backend API Specification

Base URL: `/api/v1`

All timestamps are ISO-8601 UTC.

## API Principles

- REST is the authoritative command/query interface.
- WebSocket is for push updates only.
- Every mutating endpoint returns a stable resource ID and state.
- Domain errors use a consistent error envelope.
- Pagination is cursor-based for time-series/high-volume resources; simple `limit/offset` is acceptable for low-volume admin lists in MVP.
- Idempotency keys are required for trade/settlement-triggering POST requests.

## Error Envelope

```json
{
  "error": {
    "code": "ORDER_VALIDATION_FAILED",
    "message": "Sell quantity exceeds eligible available energy.",
    "details": {},
    "request_id": "..."
  }
}
```

## Health / Metadata

### `GET /health`
Process health.

### `GET /health/ready`
Checks DB connectivity and required dependencies for the current deployment mode.

### `GET /api/v1/meta`
Returns API version, enabled integrations and market mode.

---

# Users / Identity

### `POST /users`
Create demo/user identity.

### `GET /users/{user_id}`
Get user profile.

### `PATCH /users/{user_id}`
Update allowed profile fields.

### `GET /users/{user_id}/eligibility`
Return trading eligibility and trust level.

---

# Assets / Verification

### `POST /sites`
Register a site.

### `GET /sites/{site_id}`
Site details.

### `POST /sites/{site_id}/meters`
Attach a meter.

### `POST /sites/{site_id}/energy-assets`
Register PV/battery/other asset.

### `POST /assets/{asset_id}/verification`
Submit verification record.

### `GET /assets/{asset_id}/verification`
Get verification status.

### `POST /inverters`
Register inverter metadata and adapter type.

---

# Telemetry

### `POST /telemetry/readings`
Ingest one normalized meter/asset reading.

### `POST /telemetry/readings/batch`
Batch ingest readings.

### `GET /sites/{site_id}/telemetry`
Return normalized time-series.

Query:
- `start`
- `end`
- `resolution`

### `GET /sites/{site_id}/telemetry/latest`
Latest valid reading and quality metadata.

---

# Forecasting

### `POST /forecasts/runs`
Start a forecast run using the configured provider.

### `GET /forecasts/runs/{run_id}`
Forecast run status.

### `GET /sites/{site_id}/forecasts`
Return forecast points.

### `GET /sites/{site_id}/surplus`
Return estimated available surplus for a window.

Forecast provider is selected via configuration/domain policy, not hard-coded in routers.

---

# Market

### `POST /market/sessions`
Create/open a market session.

### `GET /market/sessions/{session_id}`
Session state.

### `POST /market/sessions/{session_id}/close`
Close order intake.

### `POST /orders`
Create buy/sell order.

### `GET /orders/{order_id}`
Order state.

### `POST /orders/{order_id}/cancel`
Cancel if state allows.

### `GET /market/order-book`
Current/order-session order book.

### `POST /market/sessions/{session_id}/clear`
Run matching/clearing.

Returns proposed trades; it does not silently bypass grid validation.

### `GET /trades/{trade_id}`
Trade state.

### `POST /trades/{trade_id}/validate-grid`
Run grid validation for a proposed trade set.

### `POST /trades/{trade_id}/approve`
Approve only when domain policy says safe/eligible.

### `POST /trades/{trade_id}/reject`
Record rejection and reason.

---

# Grid

### `GET /grid/nodes`
List digital-twin nodes.

### `GET /grid/feeders/{feeder_id}/snapshot`
Current grid state.

### `POST /grid/simulations`
Run a proposed scenario.

Input includes:
- node injections
- load/generation deltas
- network model version

### `GET /grid/validation/{validation_id}`
Validation result and constraint violations.

---

# Pricing

### `POST /pricing/quote`
Calculate an explainable price before trade commitment.

### `GET /trades/{trade_id}/price-breakdown`
Return components and formula version.

Pricing service owns the formula; routers never implement pricing math.

---

# Settlement

### `POST /trades/{trade_id}/reconcile`
Compare actual vs committed energy.

### `POST /trades/{trade_id}/settle`
Create final settlement after reconciliation rules are satisfied.

### `GET /settlements/{settlement_id}`
Settlement result.

### `GET /users/{user_id}/settlements`
User settlement history.

---

# Audit

### `GET /audit/entities/{entity_type}/{entity_id}`
Timeline of material business events.

### `POST /audit/anchor/{entity_type}/{entity_id}`
Optional operation to anchor a finalized hash to the configured ledger adapter.

---

# WebSockets

### `WS /ws/market`
Pushes market events:
- order accepted
- clearing started
- trade proposed
- trade approved/repriced/rejected
- market price changed

### `WS /ws/grid`
Pushes:
- feeder snapshot changes
- congestion state
- voltage/loading changes

### `WS /ws/telemetry`
Pushes demo/authorized telemetry updates.

## WebSocket Rules

- No business-critical write operation depends solely on a WebSocket message.
- Events must be serializable to a documented event schema.
- Reconnect must be safe; clients refetch authoritative REST state after reconnect.
