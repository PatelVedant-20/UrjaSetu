# UrjaSetu

A connected, local demonstration of a Gujarat community energy marketplace: sign in, view your meter and forecast, place an order, match it, validate the feeder, reconcile delivery, and verify a settlement receipt on a real local EVM blockchain.

**Energy and INR accounting are simulated.** Open-Meteo provides current weather model data. No household meter, inverter, bank or DISCOM account is connected. The fictional feeder and pricing parameters are demonstration assumptions, not approved Gujarat tariffs or an authorized electricity trading service.

## Start locally

Requires Python 3.12, Node 22.12+, PostgreSQL 18 (or the supplied Docker Compose service), and Make. Keep the existing `.env` if already configured.

```bash
# First-time setup only:
cp .env.example .env
make install
make up
npm --prefix frontend ci
npm --prefix blockchain ci

# Migrate, bootstrap, and start all three application services:
make demo
```

Open **http://127.0.0.1:5173**. API documentation: http://127.0.0.1:8000/docs.

`make demo` starts the API, managed worker, Vite website and persistent Ganache chain. It reuses existing services and the deployed contract. Ctrl+C stops processes that command started. PostgreSQL and blockchain data persist. Logs are written to `.runtime/` for processes started by the script.

For separate terminals:

```bash
make migrate bootstrap
npm --prefix blockchain run node
# In another terminal, after the chain starts:
npm --prefix blockchain run deploy
make dev
# In another terminal:
npm --prefix frontend run dev
```

## Try the complete journey

The sign-in screen has **Quick access accounts** that fill the email/password. All three use `Sunshine2026!`.

| Account | Role | Email |
|---|---|---|
| Asha Patel | Solar owner, 6 kW PV | asha@urjasetu.demo |
| Ravi Shah | Energy buyer | ravi@urjasetu.demo |
| Community operator | Development checks and community supervision | operator@urjasetu.demo |

1. Sign in as Asha and Ravi using separate browser profiles or an ordinary/private window. Tabs in one browser profile share a login cookie.
2. **My energy** is the landing page. Power and charts refresh every five seconds automatically. Choose Live, Last hour or Last 24 hours, and a 5-second, 1-minute or 15-minute reading interval.
3. As Ravi, create a buy order in **Marketplace** for tomorrow's **12:00 IST** slot, **0.05 kWh**, maximum **₹8/kWh**.
4. As Asha, choose **Sell energy → Create an order**, the same delivery slot and quantity, minimum **₹4/kWh**.
5. Ravi sees Asha's offer without refreshing. Choose **Buy energy**, select the existing buy order and **Confirm energy purchase**. An operator is no longer needed to match the trade. Price and grid checks remain mandatory.
6. Both **My trades** pages update. Normal delivery settles automatically when that real 15-minute interval finishes. **Settlements** explains credits, debits and savings; statements export to CSV.
7. After settlement, open **Blockchain receipts → Verify on blockchain**. Receipts publish automatically to the running local EVM.
8. Register another household with monthly usage, occupants, appliances, city and rooftop information. Its personalized 30-day starting history appears immediately, and its node appears in everyone else's **Grid monitor**. Household nodes and **Community** cards open the same details.
9. **Profile & settings** holds photos, household parameters, period statistics and the community-sharing preference. **Ask Urja** answers account questions and offers navigation shortcuts.

All delivery times, charts and timestamps use Asia/Kolkata; the database stores timezone-aware UTC. The current market remains day-ahead: creating a trade today schedules energy for tomorrow. For presentations and automated tests, the operator-only development API still supports accelerated delivery and scenario controls; these are no longer dashboard controls. See [the redesign guide](docs/16_HOUSEHOLD_EXPERIENCE.md).

## Verification

```bash
make test                  # backend unit/API/PostgreSQL tests; disposable databases
make lint typecheck        # Ruff and mypy
make test-web              # TypeScript, frontend unit tests and production build
make test-chain            # real Solidity and Python JSON-RPC checks (chain must run)

# Keep the local blockchain running; browser tests create their own DB/API/UI:
make test-browser
```

The [verification report](docs/15_VERIFICATION_REPORT.md) records the completed milestone results.

The browser suite exercises independent household contexts on desktop and mobile, registration, photos, privacy, automatic updates, CSV export, navigation, the assistant, direct purchasing and actual EVM verification. `make test-browser` creates a disposable database and separate API/UI on ports 8001/5174; cleanup removes its test households. The backend suite also uses disposable databases. The local EVM retains test receipt hashes.

If Chromium is already installed elsewhere, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome`. The configured database user needs permission to create the throwaway test databases.

## Understand the implementation

Start with [the household experience guide](docs/16_HOUSEHOLD_EXPERIENCE.md), then read [the connected-system walkthrough](docs/14_CONNECTED_SYSTEM_GUIDE.md) for the data sources, tables, algorithms, maths, security boundaries and implementation choices. The earlier [research plan](docs/13_DATA_RESEARCH_AND_DELIVERY_PLAN.md) remains an explicitly dated proposal; the walkthrough describes what is implemented now.

No API key is required for the energy dashboard or built-in account guide. For optional Gemini replies, set `GEMINI_API_KEY` in the root `.env`, leave/configure `GEMINI_MODEL`, and restart the API. The key stays on the server; the external provider receives only the caller’s summaries and question. A real provider call has not been validated without your key. Real household integration requires owner-authorized bidirectional meter/inverter access and appropriate data fields; weather alone cannot supply it. Public-chain deployment, utility tariffs, real payments, password recovery/email verification, production identity operations and real feeder certification are separate integrations.
