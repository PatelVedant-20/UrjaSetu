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
