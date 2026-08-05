import csv
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from .money import decimal
from .schemas import ItemFact, PaymentFact, OrderFacts

DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"unsupported timestamp: {value}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class DatasetFacts:
    orders: dict[str, dict[str, str]]
    items: dict[str, tuple[dict[str, str], ...]]
    payments: dict[str, tuple[dict[str, str], ...]]


@lru_cache(maxsize=8)
def load_dataset(data_dir: str) -> DatasetFacts:
    root = Path(data_dir)
    orders = {row["order_id"]: row for row in read_csv(root / "olist_orders_dataset.csv")}
    item_index: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(root / "olist_order_items_dataset.csv"):
        item_index.setdefault(row["order_id"], []).append(row)
    payment_index: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(root / "olist_order_payments_dataset.csv"):
        payment_index.setdefault(row["order_id"], []).append(row)
    for rows in item_index.values():
        rows.sort(key=lambda row: int(row["order_item_id"]))
    for rows in payment_index.values():
        rows.sort(key=lambda row: int(row["payment_sequential"]))
    return DatasetFacts(orders, {key: tuple(value) for key, value in item_index.items()}, {key: tuple(value) for key, value in payment_index.items()})


def load_order_facts(data_dir: Path, order_id: str) -> OrderFacts:
    dataset = load_dataset(str(data_dir.resolve()))
    order = dataset.orders.get(order_id)
    if order is None:
        raise KeyError(f"order not found: {order_id}")
    item_rows = dataset.items.get(order_id, ())
    payment_rows = dataset.payments.get(order_id, ())
    return OrderFacts(
        order_id=order_id,
        order_status=order["order_status"],
        delivered_carrier_date=parse_timestamp(order.get("order_delivered_carrier_date")),
        delivered_customer_date=parse_timestamp(order.get("order_delivered_customer_date")),
        estimated_delivery_date=parse_timestamp(order.get("order_estimated_delivery_date")),
        items=[ItemFact(order_id=order_id, order_item_id=int(row["order_item_id"]), product_id=row["product_id"], seller_id=row["seller_id"], shipping_limit_date=parse_timestamp(row.get("shipping_limit_date")), price=decimal(row.get("price")), freight_value=decimal(row.get("freight_value"))) for row in item_rows],
        payments=[PaymentFact(order_id=order_id, payment_sequential=int(row["payment_sequential"]), payment_value=decimal(row.get("payment_value"))) for row in payment_rows],
    )
