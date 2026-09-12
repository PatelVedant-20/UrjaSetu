# UrjaSetu Phase 3 Forecast Evaluation Datasets

Representative synthetic evaluation datasets for validating forecast models, baseline predictors, and quality scoring pipelines under realistic Indian solar and residential demand conditions.

---

## Overview

In accordance with [docs/04_DATA_MODEL.md](../../../docs/04_DATA_MODEL.md) (Entities 11 & 12) and [docs/11_REGULATORY_AND_INDIA_CONTEXT.md](../../../docs/11_REGULATORY_AND_INDIA_CONTEXT.md), these datasets represent:
- **15-Minute Block Telemetry**: Indian standard metering blocks (96 blocks/day) aligned with CERC/CEA AMI guidelines.
- **Ahmedabad / Gujarat Community**: Realistic solar irradiance curves (23.03°N latitude) and residential load profiles for demo sites (`40000000-0000-0000-0000-000000000001` - Arjun, 5.0 kW PV and `40000000-0000-0000-0000-000000000004` - Priya, Consumer).
- **Paired Ground Truth & Forecast Points**: Direct alignment between `forecast_points` predictions (`predicted_kw`, `predicted_kwh`, `confidence`, `lower_bound`, `upper_bound`) and `actual_readings` (`generation_kw`, `load_kw`, `grid_import_kw`, `grid_export_kw`, `energy_kwh`, `quality_status`).

---

## Dataset Scenarios

| File | Scenario ID | Description | Type | Key Challenge / Metric Focus |
|---|---|---|---|---|
| `normal_solar_day.json` | `normal_solar_day` | Clear-sky sunny day in Ahmedabad (peak 4.1 kW). | Solar | Baseline benchmark; small residuals ($\text{nMAE} \le 5\%$). |
| `cloudy_day.json` | `cloudy_day` | Intermittent cloud cover with sharp midday drops (to 0.9 kW). | Solar | Fast ramps; baseline persistence lag ($\text{nMAE} \approx 15-25\%$). |
| `low_generation_day.json` | `low_generation_day` | Overcast monsoon day with diffuse solar only (peak 0.85 kW). | Solar | Clear-sky overforecasting; tests negative bias detection. |
| `high_generation_day.json` | `high_generation_day` | Optimal clear summer day near inverter ceiling (peak 4.8 kW). | Solar | Tests upper bound clipping and high generation capture. |
| `normal_household_demand.json` | `normal_household_demand` | Standard dual-peak Indian residential load (morning & evening peaks). | Load | Evaluates baseline diurnal cycle accuracy ($\text{MAE} \le 0.25\text{ kW}$). |
| `unusual_demand.json` | `unusual_demand` | Afternoon EV charging surge (+3.3 kW) + evening AC heatwave spike (+2.2 kW). | Load | Evaluates model handling of unannounced demand shocks. |
| `missing_historical_telemetry.json` | `missing_historical_telemetry` | 2-hour blackout gap (8 consecutive 15-min intervals missing). | Solar | Evaluates fallback imputation and confidence degradation ($0.88 \rightarrow 0.50$). |

---

## Schema Adherence

### `forecast_run` (Entity 11)
```json
{
  "id": "70000000-0001-0000-0000-000000000001",
  "forecast_type": "solar",
  "provider": "baseline_profile",
  "model_version": "v1.0.0",
  "horizon_start": "2026-03-15T00:00:00Z",
  "horizon_end": "2026-03-16T00:00:00Z",
  "created_at": "2026-03-14T18:00:00Z",
  "status": "completed"
}
```

### `forecast_points` (Entity 12)
```json
{
  "id": "71000000-0001-0000-0000-000000000001",
  "forecast_run_id": "70000000-0001-0000-0000-000000000001",
  "site_id": "40000000-0000-0000-0000-000000000001",
  "interval_start": "2026-03-15T00:00:00Z",
  "interval_end": "2026-03-15T00:15:00Z",
  "predicted_kw": 0.0,
  "predicted_kwh": 0.0,
  "confidence": 0.98,
  "lower_bound": 0.0,
  "upper_bound": 0.0
}
```

---

## Metric Definitions & Zero-Denominator Safety

In solar generation forecasting, actual generation at night is exactly $0.0\text{ kW}$. Standard Mean Absolute Percentage Error ($\text{MAPE} = \frac{100\%}{n} \sum \frac{|y_i - \hat{y}_i|}{y_i}$) suffers from division-by-zero errors.

The evaluation tooling implements three safe alternatives:
1. **Safe Masked MAPE (`safe_mape`)**: Evaluates percentage error exclusively on intervals where $y_i \ge \text{threshold}$ (default $0.1\text{ kW}$ / daylight hours).
2. **Symmetric MAPE (`symmetric_mape`)**: $\text{sMAPE} = \frac{100\%}{n} \sum \frac{2 |y_i - \hat{y}_i|}{|y_i| + |\hat{y}_i| + \epsilon}$.
3. **Normalized MAE (`normalized_mae`)**: $\text{nMAE} = \frac{\text{MAE}}{\text{Asset Capacity (kW)}} \times 100\%$, the standard metric mandated by the Central Electricity Regulatory Commission (CERC) for renewable energy forecasting and deviation settlement.
