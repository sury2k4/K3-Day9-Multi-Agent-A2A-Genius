from pathlib import Path
from sqlalchemy import create_engine, text


def engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def apply_schema(database_url: str, migration_path: Path):
    sql = migration_path.read_text(encoding="utf-8")
    with engine(database_url).begin() as connection:
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                connection.execute(text(statement))
