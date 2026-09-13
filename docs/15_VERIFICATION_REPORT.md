# Household-experience verification

Verified locally on 13 September 2026 against PostgreSQL, FastAPI, Vite and the persistent Ganache receipt registry. This updates the earlier connected-workspace report.

| Milestone | Result |
|---|---|
| Complete Python unit/API/PostgreSQL regression run | **1,117 passed**, 302 seconds; one third-party Starlette deprecation warning |
| Additional real-clock delivery check | **1 passed**; worker closes the delivery interval and settles without operator action; repeat tick is idempotent |
| Frontend unit checks | **41 passed** |
| Desktop/mobile Playwright checks | **12 passed**, 2.5 minutes; all real API/database/EVM interactions |
| Ruff lint and formatting | Passed across 236 Python files |
| mypy | Passed across 112 application modules |
| TypeScript/Vite production build | Passed |
| Frontend Prettier | Passed |
| Database migration | Existing application DB upgraded through `0015_trade_partial_fills`; history preserved |
| Normal startup | `make demo` starts the connected application and reuses the persistent contract |
| Optional external assistant provider | Adapter configured; no live Gemini request tested because no key was supplied |

The 1,117-test complete run plus the additional independent automatic-delivery check cover all 1,118 current backend tests. The application code was unchanged between those runs.

The new backend cases cover monthly-demand calibration, nonnegative energy balance, reproducible five-second values, user-specific variations, photo/profile validation, registration with 30-day history, shared/private member statistics, a working local account assistant, direct acceptance using an existing order, repeated partial fills, idempotent retries, rollback of failed matches and concurrent purchases that cannot overfill an offer. Existing forecasting, matching, grid, pricing, reconciliation, authentication and audit contracts continue to pass.

The browser suite covers these journeys on desktop and mobile:

1. Sign in, observe readings and chart points change without user actions, switch time ranges/resolutions, export household readings, visit all nine pages, check overflow and sign out.
2. Ravi creates a buy order; Asha creates the corresponding sell offer. Ravi sees it without refreshing and accepts it using his existing order. Both sessions receive the committed trade and subsequent settlement. CSV downloads and the actual EVM receipt verifies.
3. Complete registration across a five-second refresh interval; the form must retain its state. The new household appears on another user's feeder. Its node and community card show identical statistics. Disabling shared totals removes those details in the other user's open dialog.
4. Upload a profile photo, save/reload, and see it on the household's community profile.
5. Ask Urja about the caller's savings and buying energy, then follow its marketplace navigation link.
6. Capture and inspect the responsive My Energy chart/layout.

Browser trading tests use an operator-only clock acceleration solely to avoid waiting until tomorrow; the separate real-clock worker integration test proves normal automatic settlement. A fixed-profile day-ahead forecast remains separate from delivery evidence. The final price, available imports/exports and ledger allocation remain server-controlled.

The browser runner creates a migrated disposable database, API on port 8001 and Vite on 5174. It removes its database and stops those servers afterward. It leaves only non-personal test receipt hashes on the existing local EVM. Browser tests no longer populate the normal community with test households. Backend regression databases are also disposable.

Screenshots: `/tmp/urjasetu-redesign-desktop.png` and `/tmp/urjasetu-redesign-mobile.png`. Initial wider page reviews also checked Community, Grid monitor, Marketplace, Profile and Settlements. The run used Chromium at `/home/diablo/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`; set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` for another installation.

A final smoke check on the normal application confirmed real-clock mode, the new model, successful household details, and a dragged feeder node retaining its position through subsequent five-second updates. Existing community accounts and trading history were preserved.

Use `make test`, `make lint typecheck`, `make test-web`, and `make test-browser` to reproduce. The blockchain must be running for browser receipt verification. These results verify the local application, not utility meter accuracy, statistical calibration against Indian households, DISCOM permission, bank settlement or public-chain security. See [the household guide](16_HOUSEHOLD_EXPERIENCE.md) for the exact data assumptions and remaining integrations.
