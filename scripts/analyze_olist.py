#!/usr/bin/env python3
"""Deep, dependency-light audit of the Olist CSV dataset.

The report is intentionally based on the source CSVs rather than on assumptions
from the assignment. It measures keys, nulls, joins, payment reconciliation,
delivery lateness, seller handoff responsibility, policy coverage, and input-case
availability. The script uses only the Python standard library so it can run
before the application dependencies are installed.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

csv.field_size_limit(10_000_000)

MONEY_QUANT = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")

TABLE_SPECS: dict[str, tuple[str, ...]] = {
    "olist_customers_dataset.csv": ("customer_id",),
    "olist_geolocation_dataset.csv": (),
    "olist_order_items_dataset.csv": ("order_id", "order_item_id"),
    "olist_order_payments_dataset.csv": ("order_id", "payment_sequential"),
    "olist_order_reviews_dataset.csv": ("review_id",),
    "olist_orders_dataset.csv": ("order_id",),
    "olist_products_dataset.csv": ("product_id",),
    "olist_sellers_dataset.csv": ("seller_id",),
    "product_category_name_translation.csv": ("product_category_name",),
}

POLICY_CODES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def money(value: Any) -> Decimal:
    raw = text(value)
    if not raw:
        return Decimal(0)
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal(0)


def rounded(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def parse_timestamp(value: Any) -> datetime | None:
    raw = text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_date_field(field: str) -> bool:
    return "date" in field or "timestamp" in field


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def distribution(values: Iterable[int | float]) -> dict[str, Any]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {"count": 0}
    return {
        "count": len(numbers),
        "min": numbers[0] if len(numbers) == 1 else min(numbers),
        "max": max(numbers),
        "mean": round(statistics.fmean(numbers), 4),
        "median": round(statistics.median(numbers), 4),
        "p90": round(percentile(numbers, 0.90) or 0, 4),
        "p95": round(percentile(numbers, 0.95) or 0, 4),
        "p99": round(percentile(numbers, 0.99) or 0, 4),
    }


def frequency_buckets(values: Iterable[int]) -> dict[str, int]:
    buckets = Counter()
    for value in values:
        if value == 0:
            buckets["0"] += 1
        elif value == 1:
            buckets["1"] += 1
        elif value == 2:
            buckets["2"] += 1
        elif value <= 5:
            buckets["3-5"] += 1
        elif value <= 10:
            buckets["6-10"] += 1
        else:
            buckets[">10"] += 1
    return {key: buckets.get(key, 0) for key in ("0", "1", "2", "3-5", "6-10", ">10")}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return rounded(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, defaultdict):
        return dict(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def scan_csv(
    path: Path,
    key_fields: tuple[str, ...],
    callback: Callable[[dict[str, str]], None] | None = None,
) -> dict[str, Any]:
    """Scan a CSV once and optionally pass each row to a small in-memory loader."""

    stats: dict[str, Any] = {
        "file": path.name,
        "exists": path.exists(),
        "columns": [],
        "row_count": 0,
        "null_counts": {},
        "duplicate_key": {
            "fields": list(key_fields),
            "duplicate_row_count": 0,
            "examples": [],
        },
        "date_ranges": {},
        "sample_rows": [],
    }
    if not path.exists():
        return stats

    seen_keys: set[tuple[str, ...]] = set()
    null_counts: Counter[str] = Counter()
    date_values: dict[str, list[datetime | None | int]] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        stats["columns"] = fields
        for row_number, row in enumerate(reader, start=2):
            stats["row_count"] += 1
            if len(stats["sample_rows"]) < 2:
                stats["sample_rows"].append(dict(row))

            for field in fields:
                value = text(row.get(field))
                if not value:
                    null_counts[field] += 1
                if is_date_field(field) and value:
                    parsed = parse_timestamp(value)
                    if parsed is None:
                        date_values.setdefault(field, []).append(None)
                    else:
                        date_values.setdefault(field, []).append(parsed)

            if key_fields:
                key = tuple(text(row.get(field)) for field in key_fields)
                if all(key):
                    if key in seen_keys:
                        duplicate_info = stats["duplicate_key"]
                        duplicate_info["duplicate_row_count"] += 1
                        if len(duplicate_info["examples"]) < 5:
                            duplicate_info["examples"].append(
                                {field: value for field, value in zip(key_fields, key)}
                            )
                    else:
                        seen_keys.add(key)

            if callback is not None:
                callback(row)

    stats["null_counts"] = {
        field: {"count": count, "rate": round(count / stats["row_count"], 6)}
        for field, count in sorted(null_counts.items())
    }
    for field, values in sorted(date_values.items()):
        valid = [value for value in values if isinstance(value, datetime)]
        stats["date_ranges"][field] = {
            "min": min(valid).isoformat(sep=" ") if valid else None,
            "max": max(valid).isoformat(sep=" ") if valid else None,
            "invalid_count": sum(value is None for value in values),
        }
    return stats


def scan_inputs(input_dir: Path) -> dict[str, Any]:
    files = sorted(input_dir.glob("EC_*.json")) if input_dir.exists() else []
    result: dict[str, Any] = {
        "directory": str(input_dir),
        "file_count": len(files),
        "case_ids": [],
        "duplicate_case_ids": [],
        "invalid_files": [],
        "missing_official_batch": len(files) != 50,
    }
    seen: set[str] = set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            case_id = text(payload.get("case_id"))
            claimed_order_id = text(
                payload.get("customer_request", {}).get("claimed_order_id")
            )
            errors = []
            if not case_id:
                errors.append("missing case_id")
            if not claimed_order_id:
                errors.append("missing customer_request.claimed_order_id")
            if case_id in seen and case_id:
                result["duplicate_case_ids"].append(case_id)
            seen.add(case_id)
            result["case_ids"].append(case_id or path.stem)
            if errors:
                result["invalid_files"].append({"file": path.name, "errors": errors})
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            result["invalid_files"].append({"file": path.name, "errors": [str(exc)]})
    result["case_ids"] = sorted(result["case_ids"])
    return result


def build_report(data_dir: Path, input_dir: Path) -> dict[str, Any]:
    orders: dict[str, dict[str, str]] = {}
    items_by_order: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    payments_by_order: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    customers: dict[str, dict[str, str]] = {}
    customer_unique_to_customer_ids: defaultdict[str, set[str]] = defaultdict(set)
    products: set[str] = set()
    sellers: set[str] = set()
    reviews_by_order: Counter[str] = Counter()
    geo_zip_counts: Counter[str] = Counter()

    def load_order(row: dict[str, str]) -> None:
        order_id = text(row.get("order_id"))
        if order_id:
            orders[order_id] = row

    def load_item(row: dict[str, str]) -> None:
        order_id = text(row.get("order_id"))
        if order_id:
            items_by_order[order_id].append(row)

    def load_payment(row: dict[str, str]) -> None:
        order_id = text(row.get("order_id"))
        if order_id:
            payments_by_order[order_id].append(row)

    def load_customer(row: dict[str, str]) -> None:
        customer_id = text(row.get("customer_id"))
        unique_id = text(row.get("customer_unique_id"))
        if customer_id:
            customers[customer_id] = row
        if customer_id and unique_id:
            customer_unique_to_customer_ids[unique_id].add(customer_id)

    def load_product(row: dict[str, str]) -> None:
        product_id = text(row.get("product_id"))
        if product_id:
            products.add(product_id)

    def load_seller(row: dict[str, str]) -> None:
        seller_id = text(row.get("seller_id"))
        if seller_id:
            sellers.add(seller_id)

    def load_review(row: dict[str, str]) -> None:
        order_id = text(row.get("order_id"))
        if order_id:
            reviews_by_order[order_id] += 1

    def load_geolocation(row: dict[str, str]) -> None:
        prefix = text(row.get("geolocation_zip_code_prefix"))
        if prefix:
            geo_zip_counts[prefix] += 1

    loaders: dict[str, Callable[[dict[str, str]], None]] = {
        "olist_orders_dataset.csv": load_order,
        "olist_order_items_dataset.csv": load_item,
        "olist_order_payments_dataset.csv": load_payment,
        "olist_customers_dataset.csv": load_customer,
        "olist_products_dataset.csv": load_product,
        "olist_sellers_dataset.csv": load_seller,
        "olist_order_reviews_dataset.csv": load_review,
        "olist_geolocation_dataset.csv": load_geolocation,
    }

    table_stats: dict[str, Any] = {}
    for filename, key_fields in TABLE_SPECS.items():
        table_stats[filename] = scan_csv(
            data_dir / filename,
            key_fields,
            loaders.get(filename),
        )

    order_ids = set(orders)
    item_order_ids = set(items_by_order)
    payment_order_ids = set(payments_by_order)

    item_foreign_keys = {
        "order_missing": sorted(item_order_ids - order_ids)[:20],
        "seller_missing": sorted(
            {
                text(row.get("seller_id"))
                for rows in items_by_order.values()
                for row in rows
                if text(row.get("seller_id")) not in sellers
            }
        )[:20],
        "product_missing": sorted(
            {
                text(row.get("product_id"))
                for rows in items_by_order.values()
                for row in rows
                if text(row.get("product_id")) not in products
            }
        )[:20],
    }
    payment_foreign_keys = {
        "order_missing": sorted(payment_order_ids - order_ids)[:20],
    }
    customer_foreign_keys = {
        "customer_missing": sorted(
            {
                text(order.get("customer_id"))
                for order in orders.values()
                if text(order.get("customer_id")) not in customers
            }
        )[:20],
    }

    item_counts = [len(items_by_order.get(order_id, [])) for order_id in order_ids]
    payment_counts = [len(payments_by_order.get(order_id, [])) for order_id in order_ids]
    seller_counts = [
        len({text(row.get("seller_id")) for row in items_by_order.get(order_id, []) if text(row.get("seller_id"))})
        for order_id in order_ids
    ]
    review_counts = [reviews_by_order.get(order_id, 0) for order_id in order_ids]

    order_status = Counter(text(row.get("order_status")) for row in orders.values())
    payment_types = Counter(
        text(row.get("payment_type"))
        for rows in payments_by_order.values()
        for row in rows
    )

    item_totals: dict[str, Decimal] = {}
    freight_totals: dict[str, Decimal] = {}
    payment_totals: dict[str, Decimal] = {}
    payment_reconciliation = Counter()
    reconciliation_differences: list[float] = []
    mismatch_examples: list[dict[str, Any]] = []
    all_order_ids = order_ids | item_order_ids | payment_order_ids

    for order_id in all_order_ids:
        item_total = sum(
            (money(row.get("price")) for row in items_by_order.get(order_id, [])),
            Decimal(0),
        )
        freight_total = sum(
            (money(row.get("freight_value")) for row in items_by_order.get(order_id, [])),
            Decimal(0),
        )
        payment_total = sum(
            (money(row.get("payment_value")) for row in payments_by_order.get(order_id, [])),
            Decimal(0),
        )
        item_totals[order_id] = item_total
        freight_totals[order_id] = freight_total
        payment_totals[order_id] = payment_total

        payment_count = len(payments_by_order.get(order_id, []))
        if payment_count == 0:
            payment_reconciliation["no_payment_rows"] += 1
        else:
            difference = payment_total - item_total - freight_total
            difference_float = rounded(difference)
            reconciliation_differences.append(difference_float)
            if abs(difference) <= PAYMENT_TOLERANCE:
                payment_reconciliation["matched_within_0.10"] += 1
            else:
                payment_reconciliation["mismatch_over_0.10"] += 1
                if len(mismatch_examples) < 20:
                    mismatch_examples.append(
                        {
                            "order_id": order_id,
                            "item_total_brl": rounded(item_total),
                            "freight_total_brl": rounded(freight_total),
                            "payment_total_brl": rounded(payment_total),
                            "difference_brl": difference_float,
                            "payment_rows": payment_count,
                        }
                    )

    mismatch_examples.sort(key=lambda row: abs(row["difference_brl"]), reverse=True)

    delivery_delay_days: list[float] = []
    carrier_to_shipping_days: list[float] = []
    delivery_outcomes: Counter[str] = Counter()
    delivery_missing_fields: Counter[str] = Counter()
    seller_handoff_comparisons = 0
    seller_handoff_late_comparisons = 0
    orders_with_late_seller: set[str] = set()
    orders_with_multiple_late_sellers: dict[str, list[str]] = {}
    late_seller_by_id: Counter[str] = Counter()
    policy_candidates: Counter[str] = Counter()
    policy_examples: defaultdict[str, list[str]] = defaultdict(list)
    order_facts: dict[str, dict[str, Any]] = {}

    for order_id, order in orders.items():
        estimated = parse_timestamp(order.get("order_estimated_delivery_date"))
        delivered = parse_timestamp(order.get("order_delivered_customer_date"))
        carrier = parse_timestamp(order.get("order_delivered_carrier_date"))
        status = text(order.get("order_status"))
        if estimated is None:
            delivery_missing_fields["estimated_delivery_date"] += 1
        if delivered is None:
            delivery_missing_fields["delivered_customer_date"] += 1
        if carrier is None:
            delivery_missing_fields["delivered_carrier_date"] += 1

        delivery_outcome = "unknown"
        if delivered is not None and estimated is not None:
            delay_days = (delivered - estimated).total_seconds() / 86_400
            delivery_delay_days.append(delay_days)
            delivery_outcome = "late" if delivered > estimated else "on_time"
        delivery_outcomes[delivery_outcome] += 1

        late_seller_ids: set[str] = set()
        comparable_item_count = 0
        for item in items_by_order.get(order_id, []):
            shipping_limit = parse_timestamp(item.get("shipping_limit_date"))
            if carrier is not None and shipping_limit is not None:
                comparable_item_count += 1
                lag_days = (carrier - shipping_limit).total_seconds() / 86_400
                carrier_to_shipping_days.append(lag_days)
                seller_handoff_comparisons += 1
                if carrier > shipping_limit:
                    seller_handoff_late_comparisons += 1
                    seller_id = text(item.get("seller_id"))
                    if seller_id:
                        late_seller_ids.add(seller_id)
                        late_seller_by_id[seller_id] += 1

        if late_seller_ids:
            orders_with_late_seller.add(order_id)
            if len(late_seller_ids) > 1:
                orders_with_multiple_late_sellers[order_id] = sorted(late_seller_ids)

        payment_count = len(payments_by_order.get(order_id, []))
        payment_matches = (
            payment_count > 0
            and abs(payment_totals[order_id] - item_totals[order_id] - freight_totals[order_id])
            <= PAYMENT_TOLERANCE
        )
        if status == "canceled" and payment_totals[order_id] > 0:
            policy = "canceled_order_paid"
        elif status == "unavailable" and payment_totals[order_id] > 0:
            policy = "unavailable_order_paid"
        elif delivery_outcome == "late" and late_seller_ids:
            policy = "late_delivery_seller"
        elif delivery_outcome == "late" and carrier is not None and comparable_item_count > 0:
            policy = "late_delivery_logistics"
        elif delivery_outcome == "on_time" and payment_matches and payment_count >= 2:
            policy = "valid_split_payment"
        elif delivery_outcome == "on_time" and payment_matches:
            policy = "unsupported_late_claim"
        elif delivery_outcome == "unknown":
            policy = "unclassified_missing_delivery_data"
        else:
            policy = "unclassified_no_applicable_rule"
        policy_candidates[policy] += 1
        if len(policy_examples[policy]) < 5:
            policy_examples[policy].append(order_id)

        order_facts[order_id] = {
            "order_status": status,
            "delivery_outcome": delivery_outcome,
            "late_seller_ids": sorted(late_seller_ids),
            "seller_handoff_comparable_item_count": comparable_item_count,
            "payment_rows": payment_count,
            "payment_matches_within_0.10": payment_matches,
            "item_total_brl": rounded(item_totals[order_id]),
            "freight_total_brl": rounded(freight_totals[order_id]),
            "payment_total_brl": rounded(payment_totals[order_id]),
            "policy_candidate": policy,
        }

    status_with_payment = {
        status: sum(
            payment_totals.get(order_id, Decimal(0)) > 0
            for order_id, row in orders.items()
            if text(row.get("order_status")) == status
        )
        for status in order_status
    }
    status_with_payment_amount = {
        status: rounded(
            sum(
                (
                    payment_totals.get(order_id, Decimal(0))
                    for order_id, row in orders.items()
                    if text(row.get("order_status")) == status
                ),
                Decimal(0),
            )
        )
        for status in order_status
    }

    delivered_status_with_missing_dates = {
        field: sum(
            text(row.get("order_status")) == "delivered"
            and parse_timestamp(row.get(field)) is None
            for row in orders.values()
        )
        for field in (
            "order_delivered_customer_date",
            "order_delivered_carrier_date",
            "order_estimated_delivery_date",
        )
    }
    non_delivered_with_delivery_date = sum(
        text(row.get("order_status")) != "delivered"
        and parse_timestamp(row.get("order_delivered_customer_date")) is not None
        for row in orders.values()
    )

    relationship_report = {
        "orders": len(orders),
        "orders_with_items": len(order_ids & item_order_ids),
        "orders_without_items": len(order_ids - item_order_ids),
        "orders_with_payments": len(order_ids & payment_order_ids),
        "orders_without_payments": len(order_ids - payment_order_ids),
        "orders_with_reviews": sum(order_id in reviews_by_order for order_id in order_ids),
        "orders_with_multiple_sellers": sum(count > 1 for count in seller_counts),
        "orders_with_multiple_payment_rows": sum(count > 1 for count in payment_counts),
        "orders_with_multiple_reviews": sum(count > 1 for count in review_counts),
        "customer_unique_ids_with_multiple_customer_ids": sum(
            len(customer_ids) > 1 for customer_ids in customer_unique_to_customer_ids.values()
        ),
        "foreign_key_violation_examples": {
            "items": item_foreign_keys,
            "payments": payment_foreign_keys,
            "orders": customer_foreign_keys,
        },
    }

    total_item = sum(item_totals.values(), Decimal(0))
    total_freight = sum(freight_totals.values(), Decimal(0))
    total_payment = sum(payment_totals.values(), Decimal(0))

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_directory": str(data_dir),
        "input_audit": scan_inputs(input_dir),
        "tables": table_stats,
        "catalog_counts": {
            "customers": len(customers),
            "customer_unique_ids": len(customer_unique_to_customer_ids),
            "products": len(products),
            "sellers": len(sellers),
            "geolocation_zip_prefixes": len(geo_zip_counts),
            "geolocation_rows_with_zip": sum(geo_zip_counts.values()),
        },
        "order_status_distribution": dict(order_status),
        "status_payment_counts": status_with_payment,
        "status_payment_totals_brl": status_with_payment_amount,
        "relationship_integrity": relationship_report,
        "relationship_distributions": {
            "items_per_order": {
                "summary": distribution(item_counts),
                "buckets": frequency_buckets(item_counts),
            },
            "payment_rows_per_order": {
                "summary": distribution(payment_counts),
                "buckets": frequency_buckets(payment_counts),
            },
            "sellers_per_order": {
                "summary": distribution(seller_counts),
                "buckets": frequency_buckets(seller_counts),
            },
            "reviews_per_order": {
                "summary": distribution(review_counts),
                "buckets": frequency_buckets(review_counts),
            },
        },
        "payment_analysis": {
            "payment_type_distribution": dict(payment_types),
            "reconciliation_counts": dict(payment_reconciliation),
            "reconciliation_difference_brl": distribution(reconciliation_differences),
            "largest_mismatch_examples": mismatch_examples[:10],
            "aggregate_item_total_brl": rounded(total_item),
            "aggregate_freight_total_brl": rounded(total_freight),
            "aggregate_payment_total_brl": rounded(total_payment),
        },
        "delivery_analysis": {
            "delivery_outcomes": dict(delivery_outcomes),
            "delivery_delay_days": distribution(delivery_delay_days),
            "carrier_minus_shipping_limit_days": distribution(carrier_to_shipping_days),
            "missing_date_fields": dict(delivery_missing_fields),
            "delivered_status_missing_dates": delivered_status_with_missing_dates,
            "non_delivered_orders_with_customer_delivery_date": non_delivered_with_delivery_date,
            "seller_handoff_item_comparisons": seller_handoff_comparisons,
            "seller_handoff_late_item_comparisons": seller_handoff_late_comparisons,
            "orders_with_late_seller": len(orders_with_late_seller),
            "orders_with_multiple_late_sellers": len(orders_with_multiple_late_sellers),
            "multiple_late_seller_examples": orders_with_multiple_late_sellers,
            "top_late_seller_item_counts": late_seller_by_id.most_common(20),
        },
        "policy_candidate_analysis": {
            "counts": dict(policy_candidates),
            "examples": dict(policy_examples),
            "official_rule_coverage_orders": sum(
                count
                for key, count in policy_candidates.items()
                if key
                in {
                    "canceled_order_paid",
                    "unavailable_order_paid",
                    "late_delivery_seller",
                    "late_delivery_logistics",
                    "valid_split_payment",
                    "unsupported_late_claim",
                }
            ),
            "total_orders": len(orders),
        },
        "sample_order_facts": {
            order_id: order_facts[order_id]
            for order_id in sorted(order_facts)[:10]
        },
    }


def make_markdown(report: dict[str, Any]) -> str:
    tables = report["tables"]
    status = report["order_status_distribution"]
    policy = report["policy_candidate_analysis"]
    relationships = report["relationship_integrity"]
    payment = report["payment_analysis"]
    delivery = report["delivery_analysis"]
    inputs = report["input_audit"]

    lines = [
        "# Olist data analysis",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "## Executive summary",
        "",
        f"- Orders analyzed: **{relationships['orders']:,}**",
        f"- Official input cases found: **{inputs['file_count']}** (expected 50)",
        f"- Orders covered by one of the six policy paths: **{policy['official_rule_coverage_orders']:,} / {policy['total_orders']:,}**",
        f"- Payment rows reconciled within 0.10 BRL: **{payment['reconciliation_counts'].get('matched_within_0.10', 0):,}**",
        f"- Orders delivered after estimated date: **{delivery['delivery_outcomes'].get('late', 0):,}**",
        "",
        (
            "The policy engine should use exact PostgreSQL/SQL-style joins and Python arithmetic. "
            "The model should not infer facts from the customer message or replace source validation."
        ),
        "",
        "## Source tables",
        "",
        "| Table | Rows | Columns | Duplicate key rows |",
        "| --- | ---: | ---: | ---: |",
    ]
    for filename in sorted(tables):
        table = tables[filename]
        lines.append(
            f"| `{filename}` | {table['row_count']:,} | {len(table['columns'])} | "
            f"{table['duplicate_key']['duplicate_row_count']:,} |"
        )

    lines.extend(
        [
            "",
            "## Order status distribution",
            "",
            "| Status | Orders | Paid orders | Payment total (BRL) |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key in sorted(status):
        lines.append(
            f"| `{key}` | {status[key]:,} | {report['status_payment_counts'].get(key, 0):,} | "
            f"{report['status_payment_totals_brl'].get(key, 0.0):,.2f} |"
        )

    lines.extend(
        [
            "",
            "## Join and cardinality findings",
            "",
            f"- Orders without items: `{relationships['orders_without_items']:,}`.",
            f"- Orders without payment rows: `{relationships['orders_without_payments']:,}`.",
            f"- Orders with multiple sellers: `{relationships['orders_with_multiple_sellers']:,}`.",
            f"- Orders with multiple payment rows: `{relationships['orders_with_multiple_payment_rows']:,}`.",
            f"- Customer unique IDs linked to multiple customer IDs: `{relationships['customer_unique_ids_with_multiple_customer_ids']:,}`.",
            (
                f"- Geolocation rows are `{report['catalog_counts']['geolocation_rows_with_zip']:,}` across "
                f"`{report['catalog_counts']['geolocation_zip_prefixes']:,}` zip prefixes; this table should be aggregated before any zip join."
            ),
            "",
            "### Distribution summaries",
            "",
            "| Relationship | Mean | Median | P90 | Max |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for label, key in (
        ("Items per order", "items_per_order"),
        ("Payment rows per order", "payment_rows_per_order"),
        ("Sellers per order", "sellers_per_order"),
        ("Reviews per order", "reviews_per_order"),
    ):
        summary = report["relationship_distributions"][key]["summary"]
        lines.append(
            f"| {label} | {summary.get('mean', 0):.2f} | {summary.get('median', 0):.2f} | "
            f"{summary.get('p90', 0):.2f} | {summary.get('max', 0):.0f} |"
        )

    lines.extend(
        [
            "",
            "## Payment analysis",
            "",
            f"- Aggregate item value: **{payment['aggregate_item_total_brl']:,.2f} BRL**.",
            f"- Aggregate freight value: **{payment['aggregate_freight_total_brl']:,.2f} BRL**.",
            f"- Aggregate payment value: **{payment['aggregate_payment_total_brl']:,.2f} BRL**.",
            f"- Reconciliation counts: `{json.dumps(payment['reconciliation_counts'], ensure_ascii=False)}`.",
            "",
            "Largest mismatches are included in `data_analysis.json`; do not treat a mismatch as a refund event because the assignment only defines the listed policy cases.",
            "",
            "## Delivery and seller handoff",
            "",
            f"- Delivery outcomes: `{json.dumps(delivery['delivery_outcomes'], ensure_ascii=False)}`.",
            f"- Comparable carrier-versus-shipping-limit item rows: `{delivery['seller_handoff_item_comparisons']:,}`.",
            f"- Late handoff item comparisons: `{delivery['seller_handoff_late_item_comparisons']:,}`.",
            f"- Orders with at least one late seller: `{delivery['orders_with_late_seller']:,}`.",
            f"- Orders with multiple late sellers: `{delivery['orders_with_multiple_late_sellers']:,}`.",
            f"- Delivered orders missing key dates: `{json.dumps(delivery['delivered_status_missing_dates'], ensure_ascii=False)}`.",
            "",
            "## Candidate policy coverage",
            "",
            "| Candidate classification | Orders | Example order IDs |",
            "| --- | ---: | --- |",
        ]
    )
    for key, count in sorted(policy["counts"].items(), key=lambda item: (-item[1], item[0])):
        examples = ", ".join(policy["examples"].get(key, []))
        lines.append(f"| `{key}` | {count:,} | `{examples}` |")

    lines.extend(
        [
            "",
            "## Input readiness",
            "",
            f"- Case JSON files found: `{inputs['file_count']}`.",
            f"- Expected official batch present: `{not inputs['missing_official_batch']}`.",
            f"- Invalid input files: `{len(inputs['invalid_files'])}`.",
            "- The production runner should fail fast until the official 50 case files are present; it should not invent cases from the Olist dataset.",
            "",
            "## Implementation consequences",
            "",
            "1. Preserve `order_id`, `order_item_id`, and `payment_sequential` exactly for evidence IDs.",
            "2. Store timestamps without timezone conversion and compare parsed CSV values directly.",
            "3. Aggregate geolocation by zip prefix before joining it to avoid multiplying rows.",
            "4. Sum every `payment_value` row; do not use installment count as money.",
            "5. Let the deterministic policy engine decide the primary issue; use the LLM only for structured explanation or non-authoritative text.",
            "6. Make the verifier validate every evidence ID against the source rows and enforce output cardinality limits.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-dir", type=Path, default=Path("logging"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.data_dir, args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "data_analysis.json"
    markdown_path = args.output_dir / "data_analysis.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=json_safe) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(make_markdown(report), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Orders analyzed: {report['relationship_integrity']['orders']:,}")
    print(f"Input cases found: {report['input_audit']['file_count']}")
    print(
        "Policy coverage: "
        f"{report['policy_candidate_analysis']['official_rule_coverage_orders']:,}/"
        f"{report['policy_candidate_analysis']['total_orders']:,} orders"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
