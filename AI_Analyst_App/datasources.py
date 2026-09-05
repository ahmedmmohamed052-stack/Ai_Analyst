"""
Per-user data sources for the analysis pipeline.

Each user's dataset (see firestore_db.py's dataset methods and the
/datasets/* endpoints in main.py) is one of:

  - "external_db": the user's own Postgres or MySQL database. We connect
    live, read-only, using SQLAlchemy — same query-generation/validation
    pipeline as before, just pointed at the user's credentials instead of
    one shared app-wide database.

  - "file": a CSV/Excel file the user uploaded. Its rows are stored in
    Firestore (chunked across subcollection docs to stay under the 1MB
    per-document limit). At analysis time we reconstruct the DataFrame and
    load it into a throwaway in-memory SQLite database, so the rest of the
    pipeline (SQL generation via the LLM, security.validate_sql, etc.) can
    stay exactly as it was — it always just sees "a database with a schema
    it can run SELECT against."

Both kinds implement the same three methods pipeline.py needs:
get_schema(), get_latest_date(table, column), execute_sql(query).
"""
from typing import Optional

import pandas as pd
import sqlalchemy as sa

from security import decrypt_secret

SUPPORTED_DB_TYPES = ("postgres", "mysql")


class DataSourceError(Exception):
    pass


class SqlAlchemyDataSource:
    """Backs both the external-DB case and the uploaded-file case (the file
    case just points at an in-memory SQLite engine instead of a real
    network database)."""

    def __init__(self, engine: sa.Engine, dialect_note: Optional[str] = None):
        self._engine = engine
        # A short human-readable hint appended to the business_context the
        # SQL-generation prompt sees, e.g. "sql_dialect: sqlite" — lets the
        # LLM avoid Postgres-only syntax when the data actually lives in an
        # in-memory SQLite table built from an uploaded file.
        self.dialect_note = dialect_note

    def get_schema(self) -> dict:
        inspector = sa.inspect(self._engine)
        schema = {}
        for table in inspector.get_table_names():
            columns = inspector.get_columns(table)
            schema[table] = [
                {
                    "column": c["name"],
                    "type": str(c["type"]),
                    "nullable": bool(c.get("nullable", True)),
                }
                for c in columns
            ]
        if not schema:
            raise DataSourceError("This data source has no tables to analyze.")
        return schema

    def get_latest_date(self, table_name: str, date_column: str):
        quoted_table = self._engine.dialect.identifier_preparer.quote(table_name)
        quoted_col = self._engine.dialect.identifier_preparer.quote(date_column)
        with self._engine.connect() as conn:
            result = conn.execute(sa.text(f"SELECT MAX({quoted_col}) FROM {quoted_table}"))
            row = result.fetchone()
            return row[0] if row else None

    def execute_sql(self, query: str) -> pd.DataFrame:
        try:
            with self._engine.connect() as conn:
                return pd.read_sql_query(sa.text(query), conn)
        except Exception as e:
            raise DataSourceError(f"SQL execution failed: {e}")


def build_external_datasource(dataset: dict) -> SqlAlchemyDataSource:
    """dataset is the Firestore dataset doc dict for a source_type='external_db' dataset."""
    db_type = dataset["db_type"]
    password = decrypt_secret(dataset["encrypted_password"]) if dataset.get("encrypted_password") else ""
    host, port, database, user = dataset["host"], dataset["port"], dataset["database"], dataset["user"]

    if db_type == "postgres":
        sslmode = dataset.get("sslmode", "prefer")
        url = sa.URL.create(
            "postgresql+psycopg2",
            username=user, password=password, host=host, port=port, database=database,
            query={"sslmode": sslmode},
        )
    elif db_type == "mysql":
        url = sa.URL.create(
            "mysql+pymysql",
            username=user, password=password, host=host, port=port, database=database,
        )
    else:
        raise DataSourceError(f"Unsupported database type: {db_type}")

    engine = sa.create_engine(url, pool_pre_ping=True)
    return SqlAlchemyDataSource(engine)


def test_external_connection(db_type: str, host: str, port: int, database: str, user: str, password: str, sslmode: str = "prefer") -> None:
    """Raises DataSourceError with a readable message if the credentials don't work.
    Called once at /datasets/connect time so bad credentials fail fast instead
    of only surfacing the first time the user runs an analysis."""
    fake_dataset = {
        "db_type": db_type, "host": host, "port": port, "database": database,
        "user": user, "sslmode": sslmode,
    }
    password_enc = None
    try:
        from security import encrypt_secret
        password_enc = encrypt_secret(password)
        fake_dataset["encrypted_password"] = password_enc
        ds = build_external_datasource(fake_dataset)
        with ds._engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except DataSourceError:
        raise
    except Exception as e:
        raise DataSourceError(f"Could not connect: {e}")


def build_file_datasource(rows: list[dict]) -> SqlAlchemyDataSource:
    """rows is the full reconstructed list of row-dicts for an uploaded file
    dataset (see firestore_db.py::get_dataset_rows). Loaded into a
    throwaway in-memory SQLite database as a single table named `data`."""
    if not rows:
        raise DataSourceError("This dataset has no rows.")
    df = pd.DataFrame(rows)
    engine = sa.create_engine("sqlite://")
    df.to_sql("data", engine, index=False, if_exists="replace")
    return SqlAlchemyDataSource(engine, dialect_note="sqlite")
