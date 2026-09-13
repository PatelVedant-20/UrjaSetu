# UrjaSetu frontend

The connected application lives in `src/features/workspace/`. Node 22.12+ is required. After the first-time setup in the root README, run `npm run dev` here to start the local FastAPI energy service and Vite together. The command waits for API/database readiness, reuses an already running API, and stops only the processes it started when you press Ctrl+C. PostgreSQL must already be running (`make up` from the repository root).

Vite proxies `/api`, `/health` and `/ws` to `BACKEND_TARGET` (default port 8000). When `BACKEND_TARGET` is set, `npm run dev` waits for that existing service instead of starting a local API. Use `npm run dev:ui` to start only Vite when managing services yourself. Extra Vite flags still work: `npm run dev -- --port 5174`.

For the full demo including blockchain receipts, use `make demo` from the repository root after starting PostgreSQL. If the website shows “Cannot connect to the energy service”, check the terminal for API/database errors; starting only Vite cannot supply the energy APIs. Initial database setup requires `make migrate bootstrap` from the repository root.

The landing page is **My energy**. The sidebar groups home, trading and community pages; Overview has been removed. Five-second queries and authenticated WebSocket invalidation update each user's dashboard and the shared market. Chart controls offer Live/Last hour/Last 24 hours and 5s/1m/15m intervals. Registration asks for household details and supports a photo. Community cards and animated, draggable React Flow nodes share a household detail dialog. Settings includes period statistics, photos and an opt-out from sharing energy totals.

`Marketplace.tsx` supports listing and directly accepting offers, including matching an existing order. `EnergyPages.tsx` contains energy, forecasts, trades, settlement statements/CSV and EVM verification. `Assistant.tsx` provides the Urja bubble, own-account answers and navigation. `Profile.tsx`, `Community.tsx`, `charts.tsx` and `ui.tsx` contain reusable views. `ConnectedApp.tsx` handles the shell, account boundary and data refresh. `experience.css` extends the base connected styles in `workspace.css`.

```bash
npm run check
npm run format:check
npm test
npm run build
# From the repository root, with the local EVM running:
make test-browser
```

The browser runner creates a disposable PostgreSQL database and launches separate servers on ports 8001 and 5174. It cleans up afterward. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` for an existing Chromium installation, or install Chromium through Playwright. `PLAYWRIGHT_BASE_URL` supports another frontend origin. Running `npm run test:e2e` directly targets the configured running app; use the isolated runner to keep test accounts out of your community.

The server computes all personalized readings and summaries. Faster curves represent the current household model; completed 15-minute readings are persisted and used for accounting. Connection details are in settings. A hosted build needs SPA fallback and a reverse proxy; no deployment is included.

The older `FRONTEND_GUIDE.md`, `IllustrativePreview.tsx` and phase pages remain as historical reference. See [the current household experience guide](../docs/16_HOUSEHOLD_EXPERIENCE.md) for data semantics and [the main README](../README.md) for setup.
