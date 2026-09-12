# 04 — Database Schema and Domain Model

## Database Strategy

PostgreSQL is the source of operational truth. Use SQLAlchemy models + Alembic migrations. All schema changes are migration-first.

## Core Entities

### 1. `users`
Represents a platform identity.

Fields:
- `id UUID PK`
- `email` unique nullable for demo auth modes
- `display_name`
- `role` (`consumer`, `prosumer`, `operator`, `regulator_viewer`, `admin`)
- `status`
- `created_at`, `updated_at`

### 2. `utility_accounts`
Represents DISCOM-facing identity metadata.

Fields:
- `id`
- `user_id FK users`
- `discom_code`
- `consumer_number_hash`
- `verification_level`
- `verified_at`

Do not store raw production consumer numbers in demo databases.

### 3. `sites`
Physical/community location entity.

Fields:
- `id`
- `owner_user_id`
- `name`
- `latitude`, `longitude` (approximate/demo-safe)
- `grid_node_id`
- `timezone`
- `created_at`

### 4. `grid_nodes`
Electrical network nodes in the digital twin.

Fields:
- `id`
- `external_ref`
- `node_type`
- `nominal_voltage_kv`
- `parent_node_id`
- `feeder_id`

### 5. `meters`
Smart/net meter representation.

Fields:
- `id`
- `site_id`
- `meter_type`
- `vendor`
- `external_meter_ref`
- `verification_level`
- `active`

### 6. `energy_assets`
Generation or flexible-energy assets.

Fields:
- `id`
- `site_id`
- `asset_type` (`pv`, later `battery`, `ev`, etc.)
- `capacity_kw`
- `commissioned_at`
- `status`

### 7. `inverter_devices`
Device metadata for PV systems.

Fields:
- `id`
- `energy_asset_id`
- `manufacturer`
- `model`
- `protocol`
- `external_device_ref`
- `adapter_type`

### 8. `verification_records`
Trust and eligibility evidence.

Fields:
- `id`
- `user_id`
- `asset_id` nullable
- `verification_type`
- `source`
- `verification_level`
- `status`
- `verified_at`
- `expires_at`

### 9. `consents`
Consent trail for device/meter data.

Fields:
- `id`
- `user_id`
- `scope`
- `granted_at`
- `revoked_at`

### 10. `telemetry_readings`
Normalized energy measurements.

Fields:
- `id BIGINT/UUID`
- `meter_id`
- `energy_asset_id` nullable
- `timestamp`
- `interval_start`, `interval_end`
- `generation_kw`
- `load_kw`
- `grid_import_kw`
- `grid_export_kw`
- `energy_kwh`
- `battery_soc` nullable
- `quality_status`
- `source`

Indexes:
- `(site/meter, timestamp)`
- `(grid_node, timestamp)` via join where useful

#### Telemetry domain decisions

> **Status: LOCKED (Phase 2).**
>
> Changes require Yagnik's explicit approval and a documented architecture decision.

**`quality_status` vocabulary.** Exactly these seven values, and no others:

`source_unavailable`, `invalid_value`, `missing`, `duplicate`, `out_of_order`,
`stale`, `valid`

Exactly one status is stored per reading. Where several conditions apply, the
classifier resolves them by this fixed precedence, so classification is
deterministic:

```text
source_unavailable -> invalid_value -> missing -> duplicate
-> out_of_order -> stale -> valid
```

`duplicate` and `invalid_value` readings are classified and reported to the
caller but never written: each would violate a database invariant (the natural
key and a CHECK constraint respectively), and attempting the write would break
ingestion. `stale`, `out_of_order`, `missing` and `source_unavailable` are
stored with their status, so the gap stays visible.

**`source` vocabulary.** Exactly these five values, and no others:

`meter`, `inverter`, `simulator`, `import`, `manual`

These name the **ingestion channel, not the vendor**. No vendor- or
adapter-specific value may be added; an adapter maps itself onto one of these,
so adding an adapter never requires a migration.

**Staleness threshold.** Default **15 minutes** — one CEA AMI metering block, so
a reading is stale once a whole block has passed without fresher data. This is
a default, not a rule: it remains a parameter on the classifier and on every
service entry point, and later phases may supply a different threshold.

**Natural key.** `UNIQUE NULLS NOT DISTINCT (meter_id, energy_asset_id,
interval_start)`. `NULLS NOT DISTINCT` is required: by default PostgreSQL
treats every NULL `energy_asset_id` as unique, which would let whole-site
readings be recorded twice for the same interval and double-count energy at
settlement.

**NULL versus zero.** Every measurement column is nullable and the two cases are
never collapsed:

- `NULL` — the channel was not measured, or was unavailable.
- `0` — the channel was measured and its value was zero.

**Query resolution.** When `GET /sites/{site_id}/telemetry` is given a
`resolution`, readings are resampled into fixed buckets anchored at the window
start:

- power channels (`*_kw`) are **averaged** over the bucket
- energy (`energy_kwh`) is **summed**
- only valid/usable readings are aggregated — averaging a stale or invalid
  reading into a summary would launder it into apparent truth

This is the baseline. Time-weighted aggregation may be added later for unevenly
spaced intervals without changing the stored schema.

**Production hardening — not implemented in Phase 2.** Telemetry ingestion does
not check the ingesting party's `METER_DATA` consent. Consent enforcement on
ingestion is a production-deployment requirement, deliberately out of scope for
the prototype.

### 11. `forecast_runs`
A forecast execution.

Fields:
- `id`
- `forecast_type` (`solar`, `load`, `surplus`)
- `provider`
- `model_version`
- `horizon_start`
- `horizon_end`
- `created_at`
- `status`

### 12. `forecast_points`
Time-bucket forecast outputs.

Fields:
- `id`
- `forecast_run_id`
- `site_id`
- `interval_start`
- `interval_end`
- `predicted_kw`
- `predicted_kwh`
- `confidence`
- `lower_bound`, `upper_bound`

### 13. `market_sessions`
Market clearing window.

Fields:
- `id`
- `market_date`
- `market_type` (`day_ahead` initially)
- `status`
- `opened_at`
- `closed_at`
- `cleared_at`

### 14. `orders`
Buy/sell intent.

Fields:
- `id`
- `market_session_id`
- `user_id`
- `site_id`
- `side` (`buy`, `sell`)
- `energy_kwh`
- `min_price_inr_per_kwh` nullable for buy
- `max_price_inr_per_kwh` nullable for sell
- `delivery_start`
- `delivery_end`
- `node_id`
- `forecast_basis_id` nullable
- `reliability_score_snapshot`
- `status`
- `created_at`

Constraint examples:
- buy requires max price
- sell requires min price
- quantity > 0
- end > start

### 15. `trades`
Matched/committed market transaction.

Fields:
- `id`
- `buy_order_id`
- `sell_order_id`
- `quantity_kwh`
- `clearing_price_inr_per_kwh`
- `delivery_start`, `delivery_end`
- `grid_validation_id`
- `status`
- `created_at`
- `committed_at`

### 16. `grid_snapshots`
Recorded state used for validation and audit.

Fields:
- `id`
- `feeder_id`
- `captured_at`
- `system_load_kw`
- `generation_kw`
- `transformer_loading_pct`
- `max_line_loading_pct`
- `min_voltage_pu`
- `max_voltage_pu`

### 17. `grid_validation_runs`
Result of simulating a proposed trade.

Fields:
- `id`
- `trade_id` nullable before trade creation
- `grid_snapshot_id`
- `simulation_engine`
- `input_hash`
- `safe`
- `min_voltage_pu`
- `max_voltage_pu`
- `max_line_loading_pct`
- `max_transformer_loading_pct`
- `decision`
- `reason`
- `created_at`

### 18. `price_components`
Explainable price calculation.

Fields:
- `id`
- `trade_id`
- `base_market_price`
- `time_component`
- `congestion_component`
- `imbalance_component`
- `local_renewable_component`
- `final_price`
- `formula_version`

### 19. `meter_reconciliations`
Committed-vs-actual comparison.

Fields:
- `id`
- `trade_id`
- `committed_kwh`
- `actual_kwh`
- `deviation_kwh`
- `within_tolerance`
- `balancing_kwh`
- `reconciliation_status`
- `created_at`

### 20. `settlements`
Final financial allocation record.

Fields:
- `id`
- `trade_id`
- `buyer_user_id`
- `seller_user_id`
- `settled_kwh`
- `gross_amount_inr`
- `platform_fee_inr`
- `balancing_charge_inr`
- `seller_credit_inr`
- `buyer_debit_inr`
- `status`
- `settled_at`

### 21. `audit_events`
Append-oriented audit record.

Fields:
- `id`
- `event_type`
- `entity_type`
- `entity_id`
- `event_time`
- `actor_user_id`
- `payload_json`
- `event_hash`
- `previous_hash` nullable
- `ledger_anchor_id` nullable

## Key Relationships

```text
User
 ├── UtilityAccount
 ├── Sites
 │    ├── Meter
 │    ├── EnergyAsset
 │    │    └── Inverter
 │    └── GridNode
 ├── Orders
 │    └── Trades
 │         ├── GridValidationRun
 │         ├── PriceComponents
 │         ├── MeterReconciliation
 │         └── Settlement
 └── Consents / VerificationRecords

Telemetry -> ForecastRun -> ForecastPoints -> Orders
GridSnapshot -> GridValidationRun -> Trade
```

## Transaction Boundaries

### Order creation
Single transaction:
- validate actor/eligibility
- validate order
- persist order

### Trade approval
Single transaction where practical:
- store grid-validation result
- create/update trade state
- freeze price/versioned policy inputs

### Settlement
Single transaction:
- reconciliation
- settlement row
- balance/ledger entries if balances are introduced
- audit event

Never calculate a settlement only in frontend code.
