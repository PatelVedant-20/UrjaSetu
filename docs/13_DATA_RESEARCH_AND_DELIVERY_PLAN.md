**UrjaSetu: data research and delivery plan**

Research date: 13 September 2026. Status: historical research proposal. See [the connected-system guide](14_CONNECTED_SYSTEM_GUIDE.md) for the implemented decisions and current limitations.

This plan covers data acquisition, Indian/Gujarat context, time handling, database corrections, identity, trading, settlement, blockchain and frontend integration. It follows the user's requested sequence: understand and research first, then change the system in reviewable stages.

Evidence boundary: official documentation and selected research-project sources were inspected. Authenticated meter/inverter feeds were not tested; no accounts were registered, providers contacted, hardware controlled, contracts deployed, or application/database records changed. The earlier read-only inspection found 22 empty application tables in the configured database. That observation does not describe another environment.

**1. Proposed outcome and decisions still open**

A participant signs in, registers a site and its equipment, sees readings with their source and age, offers or requests energy for an interval, sees the resulting match and network decision, accepts applicable terms, and later sees reconciliation, accounting and a verifiable receipt in their portfolio.

Use actual measurements wherever authorized access is available. Use model estimates, historical replay or simulation where it is unavailable, carrying that distinction through storage, calculations and presentation.

Working assumptions until the user answers the pending questions: Ahmedabad/Gujarat demonstration; hardware/account access is unconfirmed; deadline and budget are unknown. Do not infer a particular distribution company from a city label. Identify the provider from the participating connection. Delivery estimates and provider choices remain conditional on these answers.

Keep the existing FastAPI, PostgreSQL and React foundation. Repair and connect the useful modules. Recommended first market design: day-ahead commitments with an updating order book and indicative quotes. A rolling intraday market is a separate later design decision if the hackathon requires immediate trading. Neither should be presented as an authorized Gujarat retail trading service.

**2. Research findings: data we can and cannot obtain**

| Input | Evidence and access route | Meaning and limitation | Proposed use |
|---|---|---|---|
| Household solar output | SolisCloud documents owner/installer credentials and third-party owner authorization; Fronius documents a local inverter REST interface | Requires an accessible compatible installation; channels vary by attached equipment | First real telemetry adapter selected from the hardware actually available |
| Household grid import/export | Authorized utility meter export/API or compatible bidirectional meter connected to the monitoring system | Inverter generation alone does not measure the household's exported energy | Reconciliation evidence after field, interval and quality checks |
| Household consumption | Separate meter channel or a derived energy balance with all required inputs | With a battery, generation minus export plus import alone is insufficient | Dashboard and load forecast; derived values retain their derivation |
| Current weather/forecast | IMD has an official API gateway and AWS/forecast reference; Open-Meteo documents global model output | A weather station/model is not a meter on a roof | Weather context and forecast inputs |
| Historical solar/weather | NASA POWER hourly service | Historical/environmental modelling data, not proof of customer delivery | Solar model evaluation and repeatable scenarios |
| Indian residential patterns | iAWE research dataset; Prayas eMARC measurements and published analysis | Old or geographically limited samples; not today's Gujarat community | Demand-model benchmarks and documented assumptions |
| Actual distribution grid | Utility topology, line/transformer ratings, operating measurements | No authenticated local-feeder feed has been secured | Real validation only with adequate evidence; otherwise labelled network simulation |
| Retail/export tariff | Applicable utility/regulator order and the site's category/agreement | A published tariff is versioned reference data, not a second-by-second feed | Baseline bill comparisons and explainable pricing inputs |
| Wholesale price | IEX Real Time Market public market snapshot | Exchange benchmark, not a household retail or P2P entitlement; automated reuse not established | Optional benchmark, not a dependency for the local marketplace |
| Bids, offers, trades | Our own authenticated participants and backend | Created by the marketplace | Authoritative local supply/demand and trade history |

SolisCloud currently documents application-based API activation and a five-minute device upload frequency on its user data API. API rate limits do not imply equally frequent new readings. Treat missing home-load/export channels as unavailable. [Solis activation](https://developer.soliscloud.com/guide/quick-start.html), [Solis data API](https://developer.soliscloud.com/guide/data-access-user.html), [owner authorization](https://developer.soliscloud.com/guide/authorization.html).

Fronius provides an interface to read inverter and connected-component data over the network. Compatibility and local network access must be checked for the actual device. [Fronius Solar API](https://www.fronius.com/en/help-center/solar-energy/products/monitoring-control/solutions/open-interfaces/fronius-solar-api-json-).

UGVCL's smart-meter application advertises account usage and history. Its existence does not establish an open developer API or export access for our project. [Published UGVCL app description](https://play.google.com/store/apps/details?id=com.sew.intellismart.ugvcl).

IMD's current portal offers registration and documents weather/AWS services. Older documentation mentions IP whitelisting; confirm current account requirements instead of implementing an old URL as though it were guaranteed public access. Station availability, timestamps and supplied variables must be inspected before choosing it for solar modelling. [IMD gateway](https://api.imd.gov.in/public/index.php), [API reference](https://api.imd.gov.in/public/api_reference.html), [older API document](https://mausam.imd.gov.in/imd_latest/contents/api.pdf).

Open-Meteo's current weather is model output. Its 15-minute values outside Central Europe and North America are interpolated from hourly data, relevant to India. Preserve native resolution and interval semantics. [Forecast documentation](https://open-meteo.com/en/docs). Its free service is restricted to non-commercial use, has request limits and requires attribution; verify the intended deployment fits before choosing that tier. [Terms](https://open-meteo.com/en/terms).

NASA POWER supplies hourly solar and meteorological series with UTC/local-solar-time options. Request UTC; local solar time is not Indian Standard Time. [NASA hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/).

iAWE describes measurements from a New Delhi home collected in 2013. Check download availability and licence before ingestion. eMARC describes Indian household monitoring and permits attributed non-commercial academic/research use of published information, but its FAQ does not establish that a full raw-data download is currently available. Use the material as a limited benchmark until raw access is verified. [iAWE](https://iawe.github.io/), [Prayas eMARC](https://emarc.watchyourpower.org/).

IEX publishes a Real Time Market snapshot with 15-minute blocks. A documented public machine API and reuse terms have not been verified. [IEX snapshot](https://www.iexindia.com/market-data/real-time-market/market-snapshot). The Gujarat SLDC site could not be inspected successfully in this session; no SLDC integration is assumed. State-wide statistics would not establish a neighbourhood transformer's loading in any case.

**3. India/Gujarat context and timezone decisions**

Use 15-minute canonical trading/accounting intervals as an initial design choice, retaining native measurement resolution. CEA's AMI functional requirements describe meter-data management supporting 15-minute intervals and validation/editing trails. This does not guarantee that a particular meter delivers data to us every 15 minutes. Review the applicable current meter specifications when hardware is identified. [CEA AMI requirements](https://cea.nic.in/wp-content/uploads/2020/04/ami_func_req.pdf), [current metering regulations index](https://cea.nic.in/regulations-category/metering-regulations/?lang=en).

GERC's site lists the May 2026 distributed-renewable framework as a draft. No applicable permission for this application's household trading has been established in this research. Record draft/final status and effective dates separately. [GERC draft index](https://www.gercin.org/regulations/draft_regulations).

For a concrete tariff research candidate, Torrent publishes the Ahmedabad FY 2026–27 order. Extract only the participating customer's applicable category and subsequent amendments/surcharges; do not apply a rebate from another category. [Torrent Ahmedabad order](https://www.torrentpower.com/public/pdf/regulatory/TPL-D-A-2585-2025-Tariff-Order-of-FY-2026-27.pdf).

PVVNL's pilot describes day-ahead orders, verified meters and bill adjustment. It is a useful workflow reference in Uttar Pradesh, not Gujarat authorization. [PVVNL pilot](https://www.pvvnl.org/P2P-Energy-Trading).

Proposed time rules:

- Site and market timezone: `Asia/Kolkata`; compute local dates, tariff bands and cutoffs in that named zone.
- Database/API instants: timezone-aware UTC. Preserve original source offset where needed for provenance.
- Example: `2026-09-14 00:00 IST` is `2026-09-13T18:30:00Z`. A local calendar day must query the corresponding UTC boundaries.
- Use half-open intervals `[start, end)` and a consistent 15-minute alignment.
- Preserve observation time, receipt time, forecast issue time, forecast validity and simulation time separately.
- Correct the simulator's UTC-hour daylight curve and the frontend's browser-local date arithmetic. Existing explicit IST formatting can remain.
- Solar position comes from location and date; do not assume sunrise is always 06:00.
- Test local midnight, UTC date crossings, month/year boundaries and a browser configured outside India.

**4. Data selection gate before dependent implementation**

For every candidate feed, record owner/provider, access method, cost/licence, source meaning, fields/units, native interval, expected delay, coverage, rate limits, retry behaviour and an example payload. Documentation verified is not the same status as a successful authenticated probe.

Probe the best accessible solar/meter source and weather source. Capture at least two distinct observation timestamps, check ordering/units, and compare meter energy increments with its own dashboard or export where available. A short probe establishes connectivity; a representative history is still needed for accuracy evaluation.

If hardware access cannot be secured within the available project schedule, proceed with a hybrid demonstration: updated weather context, modelled rooftop generation, documented household profiles, simulated bidirectional meters and a simulated feeder. Keep the same ingestion contract so a real adapter can replace a simulated one later. Provider outages must never silently switch a measured household into generated readings.

Initial data-mode vocabulary has separate dimensions:

| Dimension | Examples |
|---|---|
| Origin/method | measured, derived, weather_model, synthetic |
| Time mode | wall_clock, historical_replay, scenario_clock |
| Quality | valid, missing, stale, suspect, corrected |
| Verification | owner_supplied, device_authenticated, utility_verified, demo_verified |

This supports a historical measured reading being replayed without calling it a present live measurement. Data labels belong to series/records, not one blanket badge for an entire dashboard.

**5. Proposed schema corrections**

Evolve the existing schema with migrations; final names and constraints follow the approved data contract. Keep foreign keys, Decimal money/energy values and durable business records.

| Area | Proposed additions/corrections | Purpose |
|---|---|---|
| Measurements | Explicit `generation_kwh`, `load_kwh`, `grid_import_kwh`, `grid_export_kwh`; cumulative counters separate from interval energy | Remove ambiguous settlement interpretation |
| Meter identity | Meter role/channel mapping, external source identity, site ownership | Avoid summing a main meter and its submeters twice |
| Provenance | Source connection, observation/receipt times, native interval, origin, quality, coverage, raw-payload reference/hash, correction version | Explain any value and reproduce transformations |
| Weather/forecasts | Provider, model/run, issue and valid times, location, variables/units, model/parameter version | Prevent future information leaking into historical forecasts |
| Network | Explicit nodes and edges, phase/voltage, conductor properties, line and transformer ratings in appropriate units, source/version | Replace assumed feeder physics when evidence exists |
| Tariffs/policies | Provider, category, effective window, published source, components and formula versions | Preserve historical price explanations |
| Identity | External auth issuer/subject mapped to user; site memberships; optional wallet links | Secure ownership and portfolio access |
| Market | Interval-level reservations, commitment/version, immutable accepted terms, transition events | Prevent overselling and invalid lifecycle jumps |
| Reconciliation | Per-interval meter-to-trade allocation, coverage, measurement versions, corrections | Prevent reuse of the same export across trades |
| Accounting | Balanced journal entries and reversal/correction links | Explain buyer, seller, grid/balancing and fee accounts |
| Delivery reliability | Transactional outbox, event IDs and aggregate versions | Recover notifications and blockchain jobs after failures |
| Blockchain | Network, contract, receipt/version, transaction/block reference and confirmation status | Distinguish queued, submitted and verified evidence |
| Demo runs | Run ID, scenario clock, seed, dataset and model versions | Reproduce a demonstration without mixing it with real records |

Data acceptance requires real dimensional checks: W versus kW, Wh versus kWh, interval versus cumulative counters, reset/rollover detection, duplicate prevention and interval coverage. A whole-day energy sum is not enough to establish correct 15-minute allocation. Import and export may both be positive across an aggregated interval; do not incorrectly reject such intervals simply because flow direction changed during them.

**6. A defensible simulation fallback**

Use a solar model with site latitude/longitude, date, array orientation, installed DC capacity, inverter AC limit, irradiance, temperature and explicit losses. pvlib's PVWatts DC model relates effective irradiance, rated power and cell temperature; AC output additionally needs an inverter/loss model. [pvlib PVWatts model](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvsystem.pvwatts_dc.html).

Demand uses documented appliance/occupancy scenarios and available Indian historical patterns, with explicit limits on representativeness. Correlate weather across nearby houses rather than giving each house unrelated sunshine. Use fixed seeds, different household profiles, cloudy days, evening demand and missing-device scenarios. Do not present a physics-informed generator as statistically calibrated until comparison data supports that claim.

For a system without storage, account for `generation + import = household load + export + explicitly modelled losses` at the chosen boundary. If storage is introduced, include charge, discharge and efficiency. Integrate power over actual durations. Preserve forecast, simulated realization and settlement allocation as different quantities.

Validate daylight behaviour, energy balance, capacity limits, daily totals, peaks, ramps, missing intervals and repeatability. Evaluate forecasts on later held-out days against the existing historical-average baseline; do not forecast using future observed weather or the exact generator values to be delivered. Report MAE in kW and interval-energy error, with dataset scope. Synthetic accuracy does not establish real-world performance.

**7. Backend journey and market/pricing decisions**

Recommended operational chain:

```text
ingest → validate and store → forecast → reserve offers
      → match → evaluate combined network schedule → price within limits
      → commit accepted terms → delivery interval closes
      → reconcile allocated measurements → journal settlement → publish receipt
```

Use one explicit coordinator for this lifecycle. Keep the existing pure calculation components behind their interfaces. A failed/unknown validation cannot become a commitment. Price changes after acceptance require a new accepted version; corrections should never silently rewrite terms.

Fix reservations under concurrent order placement; enforce site ownership, feeder/community membership, compatible fixed intervals, cancellation and reservation release. Validate the combined accepted schedule, not just each isolated trade against the same empty baseline.

Important physical modelling decision: financial matching by itself does not change physical generation/load. If baseline forecasts already include the seller's PV and buyer's consumption, adding the same trade again as new generation/load double counts it. Define whether a trade changes dispatch/consumption or allocates an existing schedule, and validate the actual resulting operating scenario.

Start with deterministic price-priority matching for explainability. Generate an indicative interval price from that interval's compatible order book and explainable network/policy adjustments. Define shortage/no-cross/no-liquidity behaviour; no fabricated last-traded price. Recheck buyer ceiling and seller floor after all applicable charges. Store buyer cost, seller proceeds and fee allocation explicitly; a discount requires a defined funding/accounting rule.

Keep retail tariff, export compensation, wholesale benchmark, indicative P2P quote, executed P2P price and balancing price distinct. Provisional economic coefficients must be versioned and labelled as demo policy until justified. A high price cannot make an unsafe network safe.

Settlement must require a committed trade, closed delivery interval, accepted price version and adequate permitted measurement evidence. Allocate exports across every seller trade jointly and check buyer-side import/allocation under the chosen accounting policy. Account explicitly for losses and utility-supplied shortfalls; do not claim a direct measured electron path. Missing coverage waits for evidence. Repeated requests must not create duplicate credits. Utility-validated estimated/corrected reads, if introduced, need an explicit policy distinct from our own forecasts.

Mount practical discovery/list APIs, grid history/validation APIs and an operator market workflow. Generate TypeScript contracts from implemented OpenAPI once the schemas settle. Separate participant operations from operator permissions.

**8. Accounts and portfolio**

Use an established OpenID Connect login provider. Keycloak is a candidate for a reproducible local deployment; a managed provider remains an option if hosting constraints favour it. Keycloak documents authorization-code login and logout flows. [Keycloak administration guide](https://www.keycloak.org/docs/latest/server_admin/). Provider choice is still open; do not build several authentication systems.

Proposed application behaviour: signup/login/logout, session expiry/recovery, profile, site/device onboarding, role-scoped dashboards and verification status. Prefer a same-origin backend session with Secure/HttpOnly cookies for deployment, CSRF protection for writes, and OIDC code flow with PKCE. Backend checks identity and ownership on both REST and WebSockets. Device-ingestion credentials are distinct from human logins. Registration cannot self-assign operator privileges or genuine utility verification.

Portfolio is a backend-derived view of energy generated/imported/exported/traded, active orders, commitments, settlement credits/debits, estimated savings, delivery history and linked receipts. Estimated savings must cite the applicable tariff and comparison method, including nonlinear slabs/charges where relevant. A login proves account access; utility verification proves a different claim. Demo verification stays visibly demo verification.

Wallet connection is optional for ordinary participation. If added, prove control with a fresh signed challenge bound to the site/session/domain; do not accept a typed wallet address as ownership proof. A blockchain wallet is not a household meter identity.

**9. Blockchain proposal and its trust boundary**

Recommend a small Solidity receipt registry, tested locally and demonstrated on Sepolia once the integration is ready. Ethereum currently recommends Sepolia for application development. [Ethereum network documentation](https://ethereum.org/developers/docs/networks/).

The registry stores commitments to canonical trade terms and later reconciliation/settlement versions, with an opaque receipt key, payload hash and events. Restrict publishing roles, prevent duplicate version registration, preserve prior versions, and support a verifier that recomputes the hash from an authorized receipt export. Use domain separation including network/contract and schema version. Commitments containing private material use random salt retained with authorized evidence; raw household readings, names, utility account numbers and device credentials remain off chain.

The backend writes its business result and outbox job atomically. A worker submits the transaction, tracks confirmations/failure/reorgs, and updates the UI. Database settlement and blockchain receipt status are separate: a delayed network must show “receipt pending,” never fake success. Decide and document the required confirmation/finality policy before public demonstration. Record chain ID, contract, transaction and block references so a user can verify them independently.

This proves that a particular record was committed and has not changed relative to the chain reference. It does not independently prove meter accuracy, grid safety or that a utility paid money. With a platform-controlled publisher, this remains a platform-attested receipt system. Participant signatures can strengthen evidence of agreement if that feature fits the deadline. Currency settlement remains simulated accounting.

Hyperledger Fabric is an alternative when named organizations actually need a permissioned network and endorsement governance. Its documentation describes that model. A team operating several local nodes should not claim independent utility governance. [Fabric introduction](https://hyperledger-fabric.readthedocs.io/en/latest/whatis.html). Building both Fabric and an EVM implementation is outside the proposed first release.

**10. Live charts and interaction plan**

Every meaningful change originates in persisted backend state. A single ingestion/job process updates it; transactional events notify authorized clients; TanStack Query refetches the affected REST resources. Reconnect refetches current state and recovers missed history. Background worker and API notification delivery must share a durable path; the current in-memory hub alone is insufficient across processes.

| Screen | Backend data and interaction |
|---|---|
| Home/portfolio | Personal totals, source freshness, active commitments and recent activity |
| Energy | Solar, household load, import/export; period filters, gaps and measurement details |
| Forecast | Issued prediction versus later observations; distinguish model bounds from calibrated probability |
| Market | Interval selector, supply/demand curves, order book, indicative/last executed price, validated order entry/cancel |
| Trades | Complete personal list, fill history and lifecycle timeline |
| Grid | Persisted scenario topology, validation status, voltages/loading and reasons; explicit simulation provenance |
| Settlements | Agreed, allocated and settled kWh; journal breakdown, correction history and receipt |
| Community | Permitted membership views and eligibility; no arbitrary private household data |
| Accounts/settings | Profile, site/device connection, source status, login/session controls |

Show observation time, received time and last refresh separately where useful. Suggested application refresh targets are provisional: events within a few seconds after persistence; fallback REST polling around 30 seconds; weather retrieval around 15 minutes or the provider's update schedule; device polling no faster than useful source cadence. These are engineering choices, not claims of underlying measurement frequency.

The scenario player uses a visible simulation date/clock and pause/step/speed controls. It can demonstrate tomorrow's delivery without waiting a day. It must not overwrite historical source timestamps or label accelerated readings live hardware. A user can switch data modes explicitly; API failure never silently changes mode. Every exposed action needs working validation, feedback, loading/error states, keyboard access and mobile layout.

**11. Delivery stages and evidence required to finish each**

| Stage | Work | Completion demonstration |
|---|---|---|
| A: source and contract | Select accessible sources, sample payloads, timestamps, licences, measurement semantics and fallback | Explain one reading's origin, unit, age and permitted use; document unresolved access |
| B: database and ingestion | Correct schema/timezone, source adapters, quality rules, registry bootstrap and scenario isolation | One 15-minute household interval round-trips with correct import/export and provenance |
| C: identity | One login system, ownership, participant/operator roles, onboarding | Two users can access their own records; forged identity and cross-user access fail; logout invalidates access |
| D: trading and accounting | Forecast, reservations, matching, combined grid validation, accepted price, commitment, allocation and settlement | One buyer and seller complete a correct journey through mounted APIs; an unsafe trade is blocked |
| E: blockchain receipt | Contract, publishing worker, confirmation tracking, independent verifier | A settled trade links to a verifiable transaction; altered payload fails verification; retry does not duplicate |
| F: connected frontend | Replace example arrays with queries and controls, portfolios, charts and operator journey | Two browser sessions see shared updates without refresh; reconnect and source outage remain understandable |
| G: showcase and evaluation | Repeatable scenarios, usability, performance and migration/contract checks | New user onboarding plus happy path, cloudy shortfall, congestion and delayed-data scenarios all work |

Implementation remains sequential and reviewable. Each stage ends with: a plain-language walkthrough, files/data changed, calculations involved, a runnable demonstration and relevant verification. Keep a minimal browser view available during backend work to inspect the journey; complete visual design after the underlying data contracts work. No calendar estimate is committed until deadline, budget, access and team availability are known.

**12. Definition of a working demonstration**

- Clean development setup can create its own isolated demo community without wiping another contributor's data.
- One new user can log in, register/select their site, and understand verification and data source status.
- A reading is stored once with correct units and IST delivery interval; charts display the same backend value.
- Competing sell orders cannot reserve the same export twice, including simultaneous requests.
- Grid validation evaluates the relevant combined physical scenario; unknown evidence does not pass.
- An accepted trade preserves quantity, parties, price and policy versions through delivery and corrections.
- Each measured interval is allocated once; accounting balances and repeated settlement cannot double credit.
- The buyer and seller see their own resulting history and clearly labelled simulated monetary amounts.
- A blockchain receipt is independently verifiable, with honest pending/failure status.
- Source outage, missing telemetry, expired login, reconnection and testnet outage have usable recovery paths.
- The team can explain one entire trade and the provenance of every number used in it.

**Immediate next working session:** resolve hardware/provider access and project constraints, then agree the canonical meter-reading contract with one worked Gujarat-time example. Those choices determine the first migration and adapter; they do not require an immediate frontend rewrite.
