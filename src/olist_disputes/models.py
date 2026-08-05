"""Database model contract is represented by migrations for reproducible deployment."""

SOURCE_TABLES = ("customers", "orders", "order_items", "order_payments", "order_reviews", "products", "sellers", "geolocation")
OPERATION_TABLES = ("cases", "runs", "agent_handoffs", "case_results", "trace_references")
