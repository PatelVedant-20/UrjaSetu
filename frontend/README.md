# UrjaSetu frontend

Ten responsive pages for the community energy journey. Start with [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md) for architecture, APIs, page ownership and integration gaps. Every AI contributor must follow [AGENTS.md](AGENTS.md).

## Run locally

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Node 22.12+ required. Default previews work without a backend. Settings can inspect existing API records when the existing backend is running on port 8000. To target another backend, start Vite with `BACKEND_TARGET=http://localhost:8001 npm run dev`.

## Check your changes

```bash
npm run check
npm run format:check
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser testing can use an existing Chromium installation by setting `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its executable path. Screenshot checks write review images to the system temporary directory.

## Find the right file

- `src/features/`: one folder per page, ready for teammate ownership.
- `src/components/`: shared UI primitives, chart and trade table.
- `src/styles/tokens.css`: colors, typography and base rules.
- `src/styles/app.css`: shell, components and responsive layouts.
- `src/lib/demo.ts`: clearly illustrative sample data, in one place.
- `src/lib/api.ts`: read-only request client, identity and WebSocket adapter.
- `src/lib/format.ts`: units, India-local time, currency and CSV export.
- `public/images/placeholders/`: original replacement image slots.
- `ARCHITECTURE_INVENTORY.md`: tracked-file and Python symbol inventory, including route declarations.

## Verification and limitations

Initial verification: TypeScript check, Prettier check, production build, five unit tests, ten desktop/mobile interaction tests and two screenshot captures passed. Browser tests cover all routes, page overflow, local drafts, filtering, dialog dismissal, mocked API failures/responses and CSV download. No backend tests, seeds, migrations or source modifications were performed. API browser tests use intercepted responses; end-to-end operation against a running database was not verified.

All default dashboards use illustrative data; local order drafts are not backend orders. There is no live market-price history endpoint. Settings provides real read-only API access and optional reconnecting notifications. Grid scenario controls select samples, not solver runs. Missing grid and approval routes are documented in the guide. Backend business logic, authorization, pricing and settlement are not reproduced in the UI.

Production deployment needs a reverse proxy for /api, /health and /ws, plus SPA route fallback. No deployment, commits, merges or pushes are included.
