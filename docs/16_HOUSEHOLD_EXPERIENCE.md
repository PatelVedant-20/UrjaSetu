# The personalized household experience

Implemented 13 September 2026. This guide describes the redesigned application and supersedes the old Overview/operator-driven presentation.

## What changed for a user

| Page | What works now |
|---|---|
| My energy | Single landing page; current power, hour/day/week energy cards, five-second charts, range/interval controls, reading history and CSV |
| Marketplace | Buy/sell listings, direct offer acceptance, selection of an existing matching order, partial fills, server validation and recent order history |
| My trades | Agreement → grid check → delivery → receipt, with price components available on expansion |
| Community | Clickable household cards, profile/rooftop photos, shared day/week/month statistics and generation/demand curves |
| Grid monitor | Animated feeder edges, draggable household nodes, zoom/fit controls, persistent layout, automatic new nodes and the same household details as Community |
| Profile & settings | Photos, editable household setup, sharing preference, energy and financial summaries, history charts and connection information |
| Settlements | Savings explanation, separate earnings/purchases, charts, readable neighbour-based statements and CSV export |
| Blockchain receipts | Actual local EVM receipt verification, publication status and recent activity |
| Forecasts | Next-day production/demand and promising surplus slots |
| Ask Urja | Own-account answers about usage, savings, forecasts and buying; navigation shortcuts; optional Gemini integration |

Overview is removed; `/` redirects to `/energy`. All timestamps use IST. Operator scenario/play controls are removed from the ordinary interface. There are no “Mock Data”, “Synthetic Data” or “Simulation” banners. Account setup and connection settings explain that household readings are profile-based, the meter is not connected, and the ledger does not move bank funds. Backend source/quality fields remain intact.

## Understand the numbers

**kW means how fast energy is flowing now. kWh means how much energy flowed over a period.** A steady 2 kW appliance running for 15 minutes consumes `2 × 15/60 = 0.5 kWh`.

The five-second and one-minute views are deterministic power curves calculated on the server using the current household profile. There is no independent `Math.random()` stream in each browser. The same household, setup and timestamp produce the same point in every session. The latest point moves with the real clock.

Fifteen-minute readings are persisted in PostgreSQL and provide the evidence used for accounting. The worker closes completed intervals and reconciles due trades automatically. Reloading a page does not fabricate another settlement. A background advisory lock prevents multiple API processes from advancing the same community simultaneously.

| Chart range | Duration | Available resolutions |
|---|---|---|
| Live | Rolling 15 minutes | 5 seconds, 1 minute, 15 minutes |
| Last hour | Rolling 60 minutes | 5 seconds, 1 minute, 15 minutes |
| Last 24 hours | Rolling 24 hours | 1 minute, 15 minutes |

Each active chart requests updates every five seconds. A 15-minute historical point changes when an interval completes, rather than pretending a new settlement-grade measurement exists every five seconds. The 24-hour/5-second combination is disabled to avoid sending 17,280 chart points per refresh. The endpoint rejects oversized series requests too.

Energy cards total completed intervals: hour = 4 intervals, day = 96, week = 672, month = 2,880. “Month” here is a rolling 30-day window. Daily history bars group those records by IST calendar date, so edge dates can be partial. Financial period totals include settlements completed within the selected window. Existing historical records are preserved when upgrading or editing a profile.

## Registration and personalized generation

Registration creates a user, password credential, login session, household profile, site, meter, feeder connection, participation consent and (for a prosumer) a PV asset. The new node is part of the same database projection consumed by every logged-in browser. A new household receives 30 days of generated history and a next-day forecast.

| Input | How it is used |
|---|---|
| Monthly consumption in kWh | Sets the daily demand target to monthly usage ÷ 30 |
| People at home | Changes the base, morning and evening demand distribution |
| Air conditioners | Changes afternoon/night demand shape; already included in the monthly total |
| Daytime presence | Adds a daytime demand pattern |
| Electric vehicle | Adds an evening charging pattern; already included in the monthly total |
| City | Selects latitude/longitude for the daylight envelope |
| PV capacity | Scales generation; consumers have zero rooftop production |
| Roof direction and tilt | Apply orientation/tilt factors to rooftop production |
| Home type | Household description shown in the community profile |
| Comparison rate | User-configured savings benchmark, not an official DISCOM tariff |
| Share energy totals | Controls visibility of that household's detailed statistics to other members |
| Photos | Optional profile/household images; browser resizes before upload, server restricts format/size |

The versioned model is `gujarat-personal-2` in `household_energy.py`. Demand combines base usage and smooth morning, evening, cooling, occupancy and charging peaks. The curve is normalized so changing appliances changes *when* the monthly energy is used, rather than counting the same energy twice:

```text
daily_target_kWh = monthly_kWh / 30
normalization = sum(demand_shape_at_each_15_minute_midpoint × 0.25)
load_kW(t) = daily_target × demand_shape(t) / normalization
```

Small deterministic daily variations (±4.5%) and continuous within-day variation personalize households using their user ID. These are explicit model assumptions; they are not a representative Indian consumption dataset.

Solar uses seasonal declination, city latitude, an approximate solar noon derived from longitude, an assumed 0.82 performance ratio, orientation factors and tilt derating. It is zero below the daylight envelope. This is a simplified solar profile, not a calibrated PV engineering forecast or certified meter. Public weather remains a separately cached context source and does not silently replace household evidence.

Three midpoint samples integrate each 15-minute reading. Import/export are integrated separately around changes in direction; rounding is reconciled so power channels remain nonnegative and satisfy:

```text
generation + import = consumption + export
interval_energy_kWh = interval_average_power_kW × 0.25
```

The earlier `gujarat-household-1` records are retained for audit continuity. Accounts upgraded from the earlier implementation can therefore show historical totals from the old profile while new indicative curves use their household settings. Settings changes do not rewrite settled readings or rebuild historical receipts. Fast historical curves reconstruct the **current** profile; use completed 15-minute records for preserved historical evidence.

## Why direct purchasing now works

Previously only the operator could call market clearing. Two households could publish compatible orders but could not complete their own match.

`POST /api/v1/workspace/orders/{offer_id}/accept` now accepts `quantity`, `price`, a UUID `request_id`, and optional `own_order_id`:

1. Acquire the community transaction lock and check for a previous execution of the same request.
2. Check that the public offer is active, belongs to someone else, and has enough unfilled energy in a future delivery slot.
3. Use the caller's compatible order, or create the opposite order within their forecast surplus/role limits.
4. Match only those two orders, capped at the requested quantity.
5. Run the existing physical grid solver and dynamic pricing engine.
6. Commit only if the final price fits both original order limits and the grid result is safe.
7. Save the trade and idempotency record together, update matched quantities and publish a shared revision.

An existing order's original price limit remains authoritative. A failure rolls back the entire direct request, including any newly created counter-order; it does not reject or consume the neighbour's offer. Concurrent requests cannot overfill it. Retrying the same request returns the same trade; reusing its ID with a different body is rejected.

Trade `fill_sequence` distinguishes repeated partial executions between the same order pair and delivery slot. A uniqueness constraint prevents inserting the same numbered fill twice. The legacy phase-clearing API retains its default first-fill behavior.

Delivery is still **day-ahead**. Acceptance confirms an agreement; it does not instantly deliver electricity. At the end of the scheduled 15-minute slot, the worker allocates available seller export and buyer import, subtracts energy already allocated to other trades, and calculates the settlement. The operator-only development `/workspace/control` endpoint retains `deliver`, `step`, stress scenarios and `live` for automated tests/presentations. `live` restores real-clock operation. These controls are not exposed to ordinary households.

## Savings and accounting

```text
solar_used_at_home = max(0, generation_kWh − export_kWh)
solar_savings = solar_used_at_home × configured_comparison_rate
purchase_savings = settled_purchased_kWh × comparison_rate − purchase_debits
total_savings_comparison = solar_savings + purchase_savings
sales_earnings = sum(settled_seller_credits)  # shown separately
```

A purchase more expensive than the comparison rate can show negative purchase savings. Seller earnings are not added to savings a second time. Fixed utility charges, taxes and official tariff slabs are not calculated. Changing the comparison rate recalculates the comparison; it does not change historical trade prices or ledger postings. CSV exports use quoted values and neutralize spreadsheet formula prefixes.

## Database and implementation map

There are now 30 application tables. Migration `0014_household_experience` adds `household_profiles` and `marketplace_actions`, plus `simulation_state.live_mode`. Migration `0015_trade_partial_fills` adds the execution sequence and extends the trade uniqueness key. The existing orders, trades, telemetry, settlements, journal, audit and receipt tables remain authoritative.

`experience_service.py` builds the authorized dashboard, shared member projections and chart series. `workspace_service.py` owns transactional trading and delivery. `workspace_worker.py` runs five-second revisions, completed-interval persistence and receipt publication. `api/v1/household.py` validates household setup, photos, series parameters and direct acceptance requests. The frontend is split into shell, profile, community/grid, marketplace, energy/settlement pages, charts, shared components and assistant modules under `frontend/src/features/workspace/`.

The application uses cookie sessions, server-side ownership checks and origin/custom-header protection for writes. Browsers share only community projections; other users do not receive private orders, settlement details or account credentials. Energy-total sharing can be disabled. Photos/name/role remain part of a registered household's community profile.

## Assistant and optional key

Without any key, Urja answers common questions using this account's current totals, settled trades and saved forecast. It offers links rather than claiming to have navigated or submitted an order. Chat state is cleared when the signed-in user changes.

For optional free-form Gemini replies, set these in the root `.env` and restart the API:

```dotenv
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.8-flash
```

The adapter follows Google's [generateContent API](https://ai.google.dev/api/generate-content). The model is configurable; current availability and account access should be checked in Google's [model documentation](https://ai.google.dev/gemini-api/docs/models). The secret stays on the server. Requests include only the caller's energy summaries and question, without other households' profiles, photos or credentials. Provider failures fall back to the local account guide. No live provider call has been verified because an API key has not been supplied.

## Verification and running

Use `make demo` for the normal application and `make test-browser` for the isolated real-browser journey. The latter creates its own database and starts separate API/Vite processes on 8001/5174, then cleans them up. It uses the existing local EVM; test receipt hashes remain on that chain. It does not add test households to your normal application database.

The latest results are recorded in [the verification report](15_VERIFICATION_REPORT.md). Backend tests cover physical balance, calibrated demand, repeatable five-second values, registration, privacy, direct partial fills, retry safety and concurrency as well as the existing engine contracts. Browser tests cover the actual household-to-household journey, registration across refresh intervals, dynamic feeder membership, photos, the assistant, CSV and blockchain verification on desktop/mobile.
