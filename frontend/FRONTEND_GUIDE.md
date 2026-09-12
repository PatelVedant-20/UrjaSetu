# UrjaSetu frontend blueprint and team handoff

## Product and scope

A local renewable-energy community workspace for a hackathon. The interface follows the actual lifecycle: identity and assets → telemetry → forecasts and exportable surplus → day-ahead orders → matching → grid validation → price composition → commitment → meter reconciliation → settlement → audit.

This initial implementation is a complete navigable design foundation, not a declaration that the backend integration gate has passed. The backend remains untouched. All default dashboard values are explicitly illustrative; Settings provides a separate read-only API connection workspace.

## Architecture findings (12 September 2026)

The README still says Phase 0, but the source contains identity, asset, telemetry, forecast, market, grid-validation, pricing, settlement, audit and realtime implementations and tests. Follow code over stale phase labels.

FastAPI routers delegate to services, which orchestrate domain policies, repositories and adapters. SQLAlchemy/PostgreSQL is operational truth; Alembic owns schema history. The baseline forecasting provider is replaceable. Power Grid Model is isolated behind the grid adapter. Audit uses a hash chain and a local publisher; it is not a deployed blockchain. The realtime hub is in-process and drops old notifications under backpressure; there is no replay.

Entity relationships: user → utility account/consents/verification and sites; site → meter/PV/inverter and grid node; telemetry → forecast runs/points → surplus and orders; session → orders → trades; trade → grid validation + price components + reconciliation + settlement; audit events correlate to order, trade or market_session.

Critical details: latest telemetry can be stale; missing data is nullable. Sell orders require backend eligibility and forecast surplus. Clearing requires a closed session and produces proposed trades. Grid service records a judgement, not an approval. Settlement refuses unmeasured delivery. Audit access checks identity/role/participation.

## API availability

REST resources are under /api/v1. GET /health and /health/ready and WebSockets are at root. Full source-derived route and repository inventory is in ARCHITECTURE_INVENTORY.md.

| Feature    | Implemented public surface                                                        | Initial UI                                            |
| ---------- | --------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Identity   | create/get/patch user; get eligibility                                            | Community and profile preview; API record lookup      |
| Assets     | create/get site; attach meter/PV; inverter registration; verification create/read | Site cards, equipment and verification checklist      |
| Telemetry  | single/batch ingest; site series/latest                                           | Power charts, data-quality state                      |
| Forecast   | create/get run; site forecasts/surplus                                            | Forecast chart and delivery-window table              |
| Market     | session create/get/close/clear; order create/get/cancel; order-book; trade get    | Order book, local draft form, trade detail            |
| Pricing    | quote; trade price-breakdown                                                      | Explainable illustrative price components             |
| Settlement | reconcile/settle trade; settlement get; user history                              | Accounting table, breakdown, CSV export               |
| Audit      | entity timeline; anchor                                                           | Searchable event timeline and record detail           |
| Realtime   | market/grid/telemetry channels                                                    | Reconnect-safe adapter for future feature integration |
| Grid       | internal service and adapter only                                                 | Interactive illustrative topology and scenarios       |

Missing mounted routes: /grid/nodes, /grid/feeders/{id}/snapshot, /grid/simulations, /grid/validation/{id}, /trades/{id}/validate-grid, /trades/{id}/approve, /trades/{id}/reject. Also no general user/site/session/trade list, login/OIDC, price-history, community-total or carbon-impact endpoints. Documented idempotency expectations are not visibly implemented in router arguments; do not assume retries of writes are safe. The UI must not claim these capabilities are connected.

## Stack

Use the already locked React + TypeScript + Vite stack. Node 22.12+ is supported; local inspection found Node 22.23.2. TanStack Query handles cache/error/refetch, Recharts provides accessible responsive energy and price charts, React Flow provides pan/zoom topology, Motion provides reduced-motion-aware transitions, Lucide supplies consistent icons. React Router owns navigation. CSS variables and small semantic styles keep restyling easy without a second design system. Add Zustand only when cross-page state actually needs it.

References checked: [Vite guide](https://vite.dev/guide/), [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview), [Recharts responsive container](https://recharts.github.io/api/ResponsiveContainer/).

## Page plan and visual language

Warm off-white canvas, deep forest navigation, leaf-green primary action, restrained orange highlights, fine borders and generous spacing. Compact technical data sits alongside plain-language explanations. Avoid decorative dashboard clutter and fake impact metrics.

| Route        | Purpose                  | Main interactions                        | Suggested owner |
| ------------ | ------------------------ | ---------------------------------------- | --------------- |
| /            | Overview                 | time range, chart, lifecycle, links      | Vedant          |
| /market      | Marketplace              | buy/sell tabs, price chart, draft order  | Manthan         |
| /trades      | My trades                | status filtering, trade detail           | Manthan         |
| /energy      | My energy                | site equipment, telemetry, quality       | Vedant          |
| /forecasts   | Forecasts                | solar/load/surplus, horizon selection    | Vedant          |
| /grid        | Grid monitor             | draggable nodes, zoom, scenario selector | Siddhant        |
| /community   | Community                | search members, verification detail      | Vedant          |
| /settlements | Settlements              | accounting detail and CSV export         | Yagnik          |
| /audit       | Audit trail              | search, event details                    | Yagnik          |
| /settings    | Connection & preferences | persist IDs, probe API, read records     | Yagnik          |

Yagnik owns shared shell, API/types/config, package files and integration. Others should keep edits in their feature folders; shared-component changes require coordination, not backend changes.

## Development

Run `npm ci`, then `npm run dev` from frontend/. Build: `npm run build`; checks: `npm run check`; tests: `npm test`. Vite proxies /api, /health and /ws to localhost:8000. Set BACKEND_TARGET when starting Vite to use a different backend; never expose database credentials. Production hosting must supply equivalent reverse proxy rules and SPA fallback; Vite's development proxy is not part of static output.

API settings store only opaque demo IDs in localStorage. A successful health probe only establishes process availability. API record lookup displays real responses separately and never replaces failed responses with samples. The design pages intentionally remain demo previews until feature owners wire their specific queries and commands. Local order drafts never submit to the backend and disappear on reload.

## Next integration work

Generate TypeScript types from the running OpenAPI endpoint into frontend only. Connect each feature through TanStack Query and the shared client using verified IDs. Implement writes only after explicit user interaction, backend eligibility and correct session state; retain backend errors and request IDs. Do not add retry to financial mutations. Grid and approval pages remain clearly unavailable until the backend team exposes existing services through approved endpoints. Add frontend tests for wire-contract edge cases as each integration is built.
