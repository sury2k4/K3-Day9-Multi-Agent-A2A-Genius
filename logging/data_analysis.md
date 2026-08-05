# Olist data analysis

Generated: `2026-08-05T05:16:34+00:00`

## Executive summary

- Orders analyzed: **99,441**
- Official input cases found: **50** (expected 50)
- Orders covered by one of the six policy paths: **97,463 / 99,441**
- Payment rows reconciled within 0.10 BRL: **98,409**
- Orders delivered after estimated date: **7,827**

The policy engine should use exact PostgreSQL/SQL-style joins and Python arithmetic. The model should not infer facts from the customer message or replace source validation.

## Source tables

| Table | Rows | Columns | Duplicate key rows |
| --- | ---: | ---: | ---: |
| `olist_customers_dataset.csv` | 99,441 | 5 | 0 |
| `olist_geolocation_dataset.csv` | 1,000,163 | 5 | 0 |
| `olist_order_items_dataset.csv` | 112,650 | 7 | 0 |
| `olist_order_payments_dataset.csv` | 103,886 | 5 | 0 |
| `olist_order_reviews_dataset.csv` | 99,224 | 7 | 814 |
| `olist_orders_dataset.csv` | 99,441 | 8 | 0 |
| `olist_products_dataset.csv` | 32,951 | 9 | 0 |
| `olist_sellers_dataset.csv` | 3,095 | 4 | 0 |
| `product_category_name_translation.csv` | 71 | 2 | 0 |

## Order status distribution

| Status | Orders | Paid orders | Payment total (BRL) |
| --- | ---: | ---: | ---: |
| `approved` | 2 | 2 | 241.08 |
| `canceled` | 625 | 622 | 143,255.60 |
| `created` | 5 | 5 | 688.10 |
| `delivered` | 96,478 | 96,477 | 15,422,461.77 |
| `invoiced` | 314 | 314 | 69,137.99 |
| `processing` | 301 | 301 | 69,394.11 |
| `shipped` | 1,107 | 1,107 | 177,213.96 |
| `unavailable` | 609 | 609 | 126,479.51 |

## Join and cardinality findings

- Orders without items: `775`.
- Orders without payment rows: `1`.
- Orders with multiple sellers: `1,278`.
- Orders with multiple payment rows: `2,961`.
- Customer unique IDs linked to multiple customer IDs: `2,997`.
- Geolocation rows are `1,000,163` across `19,015` zip prefixes; this table should be aggregated before any zip join.

### Distribution summaries

| Relationship | Mean | Median | P90 | Max |
| --- | ---: | ---: | ---: | ---: |
| Items per order | 1.13 | 1.00 | 1.00 | 21 |
| Payment rows per order | 1.04 | 1.00 | 1.00 | 29 |
| Sellers per order | 1.01 | 1.00 | 1.00 | 5 |
| Reviews per order | 1.00 | 1.00 | 1.00 | 3 |

## Payment analysis

- Aggregate item value: **13,591,643.70 BRL**.
- Aggregate freight value: **2,251,909.54 BRL**.
- Aggregate payment value: **16,008,872.12 BRL**.
- Reconciliation counts: `{"matched_within_0.10": 98409, "mismatch_over_0.10": 1031, "no_payment_rows": 1}`.

Largest mismatches are included in `data_analysis.json`; do not treat a mismatch as a refund event because the assignment only defines the listed policy cases.

## Delivery and seller handoff

- Delivery outcomes: `{"on_time": 88649, "unknown": 2965, "late": 7827}`.
- Comparable carrier-versus-shipping-limit item rows: `111,456`.
- Late handoff item comparisons: `10,423`.
- Orders with at least one late seller: `8,861`.
- Orders with multiple late sellers: `52`.
- Delivered orders missing key dates: `{"order_delivered_customer_date": 8, "order_delivered_carrier_date": 2, "order_estimated_delivery_date": 0}`.

## Candidate policy coverage

| Candidate classification | Orders | Example order IDs |
| --- | ---: | --- |
| `unsupported_late_claim` | 85,759 | `53cdb2fc8bc7dce0b6741e2150273451, 47770eb9100c2d0c44946d9cf07ec65d, 949d5b44dbf5de918fe9c16f97b45f8a, ad21c59c0840e6cb83a9ceb5573f8159, a4591c265e18cb1dcee52889e2d8acc3` |
| `late_delivery_logistics` | 5,697 | `fbf9ac61453ac646ce8ad9783d7d0af6, 8563039e855156e48fccee4d611a3196, 66e4624ae69e7dc89bd50222b59f581f, 6a0a8bfbbe700284feb0845d95e0867f, a5474c0071dd5d1074e12d417078bbd0` |
| `valid_split_payment` | 2,648 | `e481f51cbdc54678b7cc49136f2d6af7, e69bfb5eb88e0ed6a785585b27e16dbf, 83018ec114eee8641c97e08f7b4e926f, 634e8f4c0f6744a626f77f39770ac6aa, f7959f8385f34c4f645327465a1c9fc4` |
| `late_delivery_seller` | 2,128 | `203096f03d82e0dffbc41ebc2e2bcfb7, 6ea2f835b4556291ffdc53fa0b3b95e8, a685d016c8a26f71a0bb67821070e398, 9d531c565e28c3e0d756192f84d8731f, fb9b2930f4a30f96c7cc98eaaa85e5f0` |
| `unclassified_missing_delivery_data` | 1,740 | `136cce7faa42fdb2cefd53fdc79a6098, ee64d42b8cf066f35eac1cf57de1aa85, 0760a852e4e9d89eb77bf631eaaf1c84, 15bed8e2fec7fdbadb186b57c46c92f2, 6942b8da583c2f9957e990d028607019` |
| `canceled_order_paid` | 622 | `1b9ecfe83cdc259250e1a8aca174f0ad, 714fb133a6730ab81fa1d3c1b2007291, 3a129877493c8189c59c60eb71d97c29, ed3efbd3a87bea76c2812c66a0b32219, 0966b61e30c4a07edbd7523f59b3f3e4` |
| `unavailable_order_paid` | 609 | `8e24261a7e58791d10cb1bf9da94df5c, c272bcd21c287498b4883c7512019702, 37553832a3a89c9b2db59701c357ca67, d57e15fb07fd180f06ab3926b39edcd2, 2f634e2cebf8c0283e7ef0989f77d217` |
| `unclassified_no_applicable_rule` | 238 | `84d6d9710c8af32b5e88f2d1c14ab871, 239f380355f65dcb68551f07d16fc4a8, 4c57f545143e8865ca2347d8cba154a7, 6e57e23ecac1ae881286657694444267, b38b3526b8b8fdc807e8a0a42ab78573` |

## Input readiness

- Case JSON files found: `50`.
- Expected official batch present: `True`.
- Invalid input files: `0`.
- The production runner should fail fast until the official 50 case files are present; it should not invent cases from the Olist dataset.

## Implementation consequences

1. Preserve `order_id`, `order_item_id`, and `payment_sequential` exactly for evidence IDs.
2. Store timestamps without timezone conversion and compare parsed CSV values directly.
3. Aggregate geolocation by zip prefix before joining it to avoid multiplying rows.
4. Sum every `payment_value` row; do not use installment count as money.
5. Let the deterministic policy engine decide the primary issue; use the LLM only for structured explanation or non-authoritative text.
6. Make the verifier validate every evidence ID against the source rows and enforce output cardinality limits.
