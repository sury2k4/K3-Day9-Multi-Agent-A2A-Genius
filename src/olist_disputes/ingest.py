import csv
from pathlib import Path
from sqlalchemy import text
from .db import engine
from .facts import parse_timestamp

TABLES = {
    "olist_customers_dataset.csv": ("customers", ("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state")),
    "olist_orders_dataset.csv": ("orders", ("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date")),
    "olist_order_items_dataset.csv": ("order_items", ("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value")),
    "olist_order_payments_dataset.csv": ("order_payments", ("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value")),
    "olist_order_reviews_dataset.csv": ("order_reviews", ("review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp")),
    "olist_products_dataset.csv": ("products", ("product_id", "product_category_name")),
    "olist_sellers_dataset.csv": ("sellers", ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state")),
    "olist_geolocation_dataset.csv": ("geolocation", ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state")),
}

REQUIRED = {filename: set(columns) for filename, (_, columns) in TABLES.items()}


def _coerce(column: str, value: str | None):
    if value is None or value == "":
        return None
    if column in {"customer_zip_code_prefix", "seller_zip_code_prefix", "geolocation_zip_code_prefix", "order_item_id", "payment_sequential", "payment_installments", "review_score"}:
        return int(float(value))
    if column in {"price", "freight_value", "payment_value", "geolocation_lat", "geolocation_lng"}:
        return value
    return value


def validate_csvs(data_dir: Path):
    for filename, required in REQUIRED.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{filename} missing headers: {sorted(missing)}")
            if filename == "olist_orders_dataset.csv":
                row = next(reader, None)
                if row:
                    for field in ("order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"):
                        parse_timestamp(row.get(field))
    return True


def ingest_csvs(database_url: str, data_dir: Path):
    validate_csvs(data_dir)
    with engine(database_url).begin() as connection:
        connection.execute(text("TRUNCATE order_items, order_payments, order_reviews, orders, customers, products, sellers, geolocation CASCADE"))
        for filename, (table, columns) in TABLES.items():
            placeholders = ", ".join(f":{column}" for column in columns)
            statement = text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})")
            with (data_dir / filename).open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    connection.execute(statement, {column: _coerce(column, row.get(column)) for column in columns})
