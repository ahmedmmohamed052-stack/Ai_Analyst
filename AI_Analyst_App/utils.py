import datetime


def utcnow() -> datetime.datetime:
    """Naive UTC datetime — consistent with what SQLite/Postgres columns store
    here, without using the deprecated datetime.datetime.utcnow()."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def to_iso(dt: datetime.datetime) -> str:
    """Stores as a plain ISO string in Firestore documents — simple, sortable,
    and JSON-friendly without needing Firestore's native Timestamp type."""
    return dt.isoformat()


def parse_iso(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)

