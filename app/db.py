from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

POLICY_EVIDENCE_CODES = frozenset(
    {
        "SELLER_HANDOFF_AFTER_LIMIT",
        "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "ORDER_CANCELED_AFTER_PAYMENT",
        "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "MULTIPLE_PAYMENTS_RECONCILED",
        "DELIVERY_WITHIN_ESTIMATE",
    }
)

SOURCE_TABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "olist_customers_dataset.csv",
        "customers",
        ("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"),
    ),
    (
        "olist_geolocation_dataset.csv",
        "geolocation",
        ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"),
    ),
    (
        "olist_order_items_dataset.csv",
        "order_items",
        ("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"),
    ),
    (
        "olist_order_payments_dataset.csv",
        "order_payments",
        ("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"),
    ),
    (
        "olist_order_reviews_dataset.csv",
        "order_reviews",
        (
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ),
    ),
    (
        "olist_orders_dataset.csv",
        "orders",
        (
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
    ),
    (
        "olist_products_dataset.csv",
        "products",
        (
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ),
    ),
    (
        "olist_sellers_dataset.csv",
        "sellers",
        ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"),
    ),
    (
        "product_category_name_translation.csv",
        "product_category_name_translation",
        ("product_category_name", "product_category_name_english"),
    ),
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_unique_id TEXT NOT NULL,
    customer_zip_code_prefix TEXT,
    customer_city TEXT,
    customer_state TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_status TEXT NOT NULL,
    order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL,
    order_item_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    shipping_limit_date TIMESTAMP,
    price NUMERIC(14, 2) NOT NULL,
    freight_value NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id TEXT NOT NULL,
    payment_sequential INTEGER NOT NULL,
    payment_type TEXT NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS order_reviews (
    review_row_id BIGSERIAL PRIMARY KEY,
    review_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    review_score INTEGER,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date DATE,
    review_answer_timestamp TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    product_category_name TEXT,
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g NUMERIC,
    product_length_cm NUMERIC,
    product_height_cm NUMERIC,
    product_width_cm NUMERIC
);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT,
    seller_city TEXT,
    seller_state TEXT
);

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_row_id BIGSERIAL PRIMARY KEY,
    geolocation_zip_code_prefix TEXT NOT NULL,
    geolocation_lat NUMERIC,
    geolocation_lng NUMERIC,
    geolocation_city TEXT,
    geolocation_state TEXT
);

CREATE TABLE IF NOT EXISTS product_category_name_translation (
    translation_row_id BIGSERIAL PRIMARY KEY,
    product_category_name TEXT,
    product_category_name_english TEXT
);

CREATE TABLE IF NOT EXISTS geolocation_zip_summary (
    geolocation_zip_code_prefix TEXT PRIMARY KEY,
    average_lat NUMERIC,
    average_lng NUMERIC,
    representative_city TEXT,
    representative_state TEXT,
    source_row_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    opened_at TEXT NOT NULL,
    order_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    run_id UUID PRIMARY KEY,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    trace_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS agent_handoffs (
    handoff_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    agent_name TEXT NOT NULL,
    input_summary JSONB,
    output_summary JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_results (
    case_id TEXT PRIMARY KEY,
    run_id UUID NOT NULL,
    output_payload JSONB NOT NULL,
    verification_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_references (
    run_id UUID PRIMARY KEY,
    case_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    langfuse_host TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_seller_id ON order_items(seller_id);
CREATE INDEX IF NOT EXISTS idx_order_payments_order_id ON order_payments(order_id);
CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id ON order_reviews(order_id);
CREATE INDEX IF NOT EXISTS idx_geolocation_zip_prefix ON geolocation(geolocation_zip_code_prefix);
CREATE INDEX IF NOT EXISTS idx_cases_order_id ON cases(order_id);
CREATE INDEX IF NOT EXISTS idx_runs_case_id ON runs(case_id);
"""

TRUNCATE_TABLES = (
    "trace_references",
    "case_results",
    "agent_handoffs",
    "runs",
    "cases",
    "geolocation_zip_summary",
    "product_category_name_translation",
    "geolocation",
    "order_reviews",
    "order_payments",
    "order_items",
    "orders",
    "products",
    "sellers",
    "customers",
)


def connect(dsn: str) -> psycopg.Connection[Any]:
    return psycopg.connect(dsn, row_factory=dict_row)


def initialize_schema(dsn: str) -> None:
    with connect(dsn) as connection:
        connection.execute(SCHEMA_SQL)
        connection.commit()


def _copy_csv(
    connection: psycopg.Connection[Any],
    csv_path: Path,
    table_name: str,
    columns: tuple[str, ...],
) -> None:
    column_sql = ", ".join(columns)
    copy_sql = (
        f"COPY {table_name} ({column_sql}) FROM STDIN "
        "WITH (FORMAT CSV, HEADER TRUE, NULL '')"
    )
    with (
        connection.cursor() as cursor,
        cursor.copy(copy_sql) as copy,
        csv_path.open("rb") as source,
    ):
        while chunk := source.read(1024 * 1024):
            copy.write(chunk)


def ingest_csv_data(dsn: str, data_dir: Path) -> dict[str, int]:
    """Replace source tables with the current CSV snapshot and return row counts."""

    initialize_schema(dsn)
    with connect(dsn) as connection:
        connection.execute(
            "TRUNCATE "
            + ", ".join(TRUNCATE_TABLES)
            + " RESTART IDENTITY"
        )
        for filename, table_name, columns in SOURCE_TABLES:
            csv_path = data_dir / filename
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing source CSV: {csv_path}")
            _copy_csv(connection, csv_path, table_name, columns)

        connection.execute(
            """
            INSERT INTO geolocation_zip_summary (
                geolocation_zip_code_prefix,
                average_lat,
                average_lng,
                representative_city,
                representative_state,
                source_row_count
            )
            SELECT
                geolocation_zip_code_prefix,
                AVG(geolocation_lat),
                AVG(geolocation_lng),
                MIN(geolocation_city),
                MIN(geolocation_state),
                COUNT(*)::INTEGER
            FROM geolocation
            GROUP BY geolocation_zip_code_prefix
            """
        )
        counts: dict[str, int] = {}
        for _, table_name, _ in SOURCE_TABLES:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
            counts[table_name] = int(row["count"] if row else 0)
        row = connection.execute("SELECT COUNT(*) AS count FROM geolocation_zip_summary").fetchone()
        counts["geolocation_zip_summary"] = int(row["count"] if row else 0)
        connection.commit()
        return counts


class PostgresRepository:
    """Read-only source repository used by the graph agents and verifier."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        # The 50-case batch repeatedly reads the same order in three graph
        # branches and then in the verifier. Source tables are immutable during
        # a run, so a small per-process cache removes hundreds of short-lived
        # PostgreSQL connections without changing the source-of-truth contract.
        self._order_cache: dict[str, dict[str, Any] | None] = {}
        self._items_cache: dict[str, list[dict[str, Any]]] = {}
        self._payments_cache: dict[str, list[dict[str, Any]]] = {}
        self._seller_exists_cache: dict[str, bool] = {}
        self._evidence_cache: dict[str, bool] = {}

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        if order_id in self._order_cache:
            return self._order_cache[order_id]
        with connect(self.dsn) as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE order_id = %s",
                (order_id,),
            ).fetchone()
        self._order_cache[order_id] = row
        return row

    def get_items(self, order_id: str) -> list[dict[str, Any]]:
        if order_id in self._items_cache:
            return list(self._items_cache[order_id])
        with connect(self.dsn) as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM order_items WHERE order_id = %s ORDER BY order_item_id",
                    (order_id,),
                ).fetchall()
            )
        self._items_cache[order_id] = rows
        return list(rows)

    def get_payments(self, order_id: str) -> list[dict[str, Any]]:
        if order_id in self._payments_cache:
            return list(self._payments_cache[order_id])
        with connect(self.dsn) as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM order_payments WHERE order_id = %s ORDER BY payment_sequential",
                    (order_id,),
                ).fetchall()
            )
        self._payments_cache[order_id] = rows
        return list(rows)

    def evidence_exists(self, evidence_id: str) -> bool:
        if evidence_id in self._evidence_cache:
            return self._evidence_cache[evidence_id]
        parts = evidence_id.split(":")
        if not parts:
            return False
        if parts[0] == "policy":
            result = len(parts) == 2 and parts[1] in POLICY_EVIDENCE_CODES
            self._evidence_cache[evidence_id] = result
            return result
        try:
            if parts[0] == "order" and len(parts) == 2:
                result = self.get_order(parts[1]) is not None
            elif parts[0] == "item" and len(parts) == 3:
                item_id = int(parts[2])
                result = any(
                    int(row.get("order_item_id")) == item_id
                    for row in self.get_items(parts[1])
                )
            elif parts[0] == "payment" and len(parts) == 3:
                payment_id = int(parts[2])
                result = any(
                    int(row.get("payment_sequential")) == payment_id
                    for row in self.get_payments(parts[1])
                )
            elif parts[0] == "seller" and len(parts) == 2:
                if parts[1] not in self._seller_exists_cache:
                    with connect(self.dsn) as connection:
                        row = connection.execute(
                            "SELECT 1 FROM sellers WHERE seller_id = %s",
                            (parts[1],),
                        ).fetchone()
                    self._seller_exists_cache[parts[1]] = row is not None
                result = self._seller_exists_cache[parts[1]]
            else:
                result = False
        except (TypeError, ValueError, psycopg.Error):
            result = False
        self._evidence_cache[evidence_id] = result
        return result


class InMemoryRepository:
    """Small repository for unit tests and policy verification without PostgreSQL."""

    def __init__(
        self,
        orders: dict[str, dict[str, Any]],
        items_by_order: dict[str, list[dict[str, Any]]],
        payments_by_order: dict[str, list[dict[str, Any]]],
        sellers: Iterable[str],
    ):
        self.orders = orders
        self.items_by_order = defaultdict(list, items_by_order)
        self.payments_by_order = defaultdict(list, payments_by_order)
        self.sellers = set(sellers)

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        return self.orders.get(order_id)

    def get_items(self, order_id: str) -> list[dict[str, Any]]:
        return list(self.items_by_order.get(order_id, []))

    def get_payments(self, order_id: str) -> list[dict[str, Any]]:
        return list(self.payments_by_order.get(order_id, []))

    def evidence_exists(self, evidence_id: str) -> bool:
        parts = evidence_id.split(":")
        if parts[0] == "policy":
            return len(parts) == 2 and parts[1] in POLICY_EVIDENCE_CODES
        if parts[0] == "order" and len(parts) == 2:
            return parts[1] in self.orders
        if parts[0] == "seller" and len(parts) == 2:
            return parts[1] in self.sellers
        if parts[0] == "item" and len(parts) == 3:
            try:
                item_id = int(parts[2])
            except ValueError:
                return False
            return any(
                str(row.get("order_item_id")) == str(item_id)
                for row in self.items_by_order.get(parts[1], [])
            )
        if parts[0] == "payment" and len(parts) == 3:
            try:
                payment_id = int(parts[2])
            except ValueError:
                return False
            return any(
                str(row.get("payment_sequential")) == str(payment_id)
                for row in self.payments_by_order.get(parts[1], [])
            )
        return False


class RunStore:
    """Write-only operational store; source tables remain read-only to agents."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def start_case(self, run_id: str, case_payload: dict[str, Any], trace_id: str) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                """
                INSERT INTO cases (case_id, opened_at, order_id, policy_version, input_payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (case_id) DO UPDATE SET
                    opened_at = EXCLUDED.opened_at,
                    order_id = EXCLUDED.order_id,
                    policy_version = EXCLUDED.policy_version,
                    input_payload = EXCLUDED.input_payload
                """,
                (
                    case_payload["case_id"],
                    case_payload["opened_at"],
                    case_payload["customer_request"]["claimed_order_id"],
                    case_payload["policy_version"],
                    Jsonb(case_payload),
                ),
            )
            connection.execute(
                """
                INSERT INTO runs (run_id, case_id, status, trace_id)
                VALUES (%s, %s, 'running', %s)
                """,
                (run_id, case_payload["case_id"], trace_id),
            )
            connection.execute(
                """
                INSERT INTO trace_references (run_id, case_id, trace_id, langfuse_host)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET trace_id = EXCLUDED.trace_id
                """,
                (run_id, case_payload["case_id"], trace_id, None),
            )
            connection.commit()

    def record_handoff(
        self,
        run_id: str,
        agent_name: str,
        input_summary: dict[str, Any],
        output_summary: dict[str, Any],
    ) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                """
                INSERT INTO agent_handoffs (run_id, agent_name, input_summary, output_summary)
                VALUES (%s, %s, %s, %s)
                """,
                (run_id, agent_name, Jsonb(input_summary), Jsonb(output_summary)),
            )
            connection.commit()

    def finish_case(
        self,
        run_id: str,
        case_id: str,
        status: str,
        output_payload: dict[str, Any] | None = None,
        verification_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = %s, finished_at = NOW(), error_message = %s
                WHERE run_id = %s
                """,
                (status, error_message, run_id),
            )
            if output_payload is not None and verification_payload is not None:
                connection.execute(
                    """
                    INSERT INTO case_results (case_id, run_id, output_payload, verification_payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (case_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        output_payload = EXCLUDED.output_payload,
                        verification_payload = EXCLUDED.verification_payload
                    """,
                    (
                        case_id,
                        run_id,
                        Jsonb(output_payload),
                        Jsonb(verification_payload),
                    ),
                )
            connection.commit()
