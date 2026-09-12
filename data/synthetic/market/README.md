# UrjaSetu Phase 4 Market Fixtures

Deterministic synthetic market fixtures for validating order books, matching algorithms, clearing mechanics, and candidate trade creation in UrjaSetu.

---

## Overview

In accordance with [docs/04_DATA_MODEL.md](../../../docs/04_DATA_MODEL.md) (Entities 13, 14, 15) and canonical contracts in `app.domain.interfaces.market`:
- **Market Mode**: Day-ahead commitment (`MarketType.DAY_AHEAD`).
- **Units**: Energy in kWh, prices in INR/kWh (paise precision, 4 decimal places).
- **Candidate Pairing**: Clearing outputs are proposed candidate trades (`TradeStatus.PROPOSED`), which do not bypass downstream grid validation.
- **Pure Matching**: Matching algorithms take `MatchingRequest(order_book=..., cleared_at=...)` and return `MatchingResult(trades=..., unmatched_buy_order_ids=..., unmatched_sell_order_ids=...)`.
- **Price-Time Priority & Midpoint Clearing**: Baseline price-time sorting with neutral midpoint pricing $\frac{P_{\text{buy\_max}} + P_{\text{sell\_min}}}{2}$.

---

## 11 Evaluated Scenarios

| Scenario File | Scenario ID | Description | Key Matching Behavior |
|---|---|---|---|
| `01_one_seller_one_buyer.json` | `one_seller_one_buyer` | 1 buyer (10 kWh @ max 7.50), 1 seller (10 kWh @ min 5.50). | 1 trade of 10 kWh @ 6.50 INR/kWh. Both orders fully filled. |
| `02_multiple_sellers.json` | `multiple_sellers` | 1 buyer (25 kWh), 2 sellers (15 kWh @ 5.00, 15 kWh @ 6.00). | Merit-order sorting: lower ask matches first. Seller 2 partially filled (5 kWh left). |
| `03_multiple_buyers.json` | `multiple_buyers` | 1 seller (20 kWh), 2 buyers (12 kWh @ 8.00, 15 kWh @ 7.00). | Merit-order sorting: higher bid matches first. Buyer 2 partially filled (7 kWh left). |
| `04_partial_fill.json` | `partial_fill` | 1 buyer (18 kWh), 1 seller (10 kWh). | 1 trade of 10 kWh. Buyer order status is `partially_filled` (8 kWh remaining). |
| `05_insufficient_supply.json` | `insufficient_supply` | Demand (50 kWh) heavily exceeds supply (15 kWh). | 1 trade for 15 kWh. 35 kWh demand remains unmatched across buyers. |
| `06_insufficient_demand.json` | `insufficient_demand` | Supply (45 kWh) heavily exceeds demand (12 kWh). | 1 trade for 12 kWh. 33 kWh supply remains unmatched across sellers. |
| `07_buyer_max_below_seller_min.json` | `buyer_max_below_seller_min` | Buyer ceiling (5.00) < seller floor (6.20). | 0 trades. No price cross; both orders completely unmatched. |
| `08_compatible_time_windows.json` | `compatible_time_windows` | Buyer [10:00, 12:00], Seller [11:00, 13:00]. | 1 trade for 15 kWh. Matched window is the overlap [11:00, 12:00]. |
| `09_incompatible_time_windows.json` | `incompatible_time_windows` | Buyer [09:00, 10:00], Seller [11:00, 12:00]. | 0 trades. Disjoint delivery windows prevent matching despite crossing prices. |
| `10_cancelled_order.json` | `cancelled_order` | 1 cancelled sell order + 1 active sell order + 1 buy order. | Cancelled order is excluded from `OrderBook`; only active orders match. |
| `11_deterministic_tie.json` | `deterministic_tie` | 2 sellers with identical ask (5.50), submitted 5 mins apart. | Time priority breaks the tie; earlier arrival (08:00Z vs 08:05Z) matches. |

---

## Schema Adherence

### `market_sessions` (Entity 13)
```json
{
  "id": "80000000-0000-0000-0000-000000000001",
  "market_date": "2026-06-02",
  "market_type": "day_ahead",
  "status": "closed",
  "opened_at": "2026-06-01T06:00:00Z",
  "closed_at": "2026-06-01T17:00:00Z",
  "cleared_at": "2026-06-01T18:00:00Z"
}
```

### `orders` (Entity 14)
```json
{
  "id": "81000000-0001-0000-0000-000000000001",
  "user_id": "20000000-0000-0000-0000-000000000004",
  "site_id": "40000000-0000-0000-0000-000000000004",
  "node_id": "10000000-0000-0000-0000-000000000005",
  "side": "buy",
  "energy_kwh": "10.0000",
  "max_price_inr_per_kwh": "7.5000",
  "min_price_inr_per_kwh": null,
  "delivery_start": "2026-06-02T10:00:00Z",
  "delivery_end": "2026-06-02T11:00:00Z",
  "created_at": "2026-06-01T08:15:00Z",
  "status": "open",
  "matched_kwh": "0.0000"
}
```

### `trades` (Entity 15 / `ProposedTrade`)
```json
{
  "buy_order_id": "81000000-0001-0000-0000-000000000001",
  "sell_order_id": "81000000-0001-0000-0000-000000000002",
  "quantity_kwh": "10.0000",
  "clearing_price_inr_per_kwh": "6.5000",
  "delivery_start": "2026-06-02T10:00:00Z",
  "delivery_end": "2026-06-02T11:00:00Z"
}
```
