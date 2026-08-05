from sqlalchemy import text
from .db import engine


def order_exists(database_url: str, order_id: str) -> bool:
    with engine(database_url).connect() as connection:
        return connection.execute(text("SELECT 1 FROM orders WHERE order_id = :order_id"), {"order_id": order_id}).first() is not None
