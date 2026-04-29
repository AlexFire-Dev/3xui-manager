from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc_aware(value: datetime | None) -> datetime | None:
    """Normalize datetimes coming from SQLite/SQLAlchemy/Pydantic.

    SQLite often returns offset-naive datetimes even when SQLAlchemy columns are
    declared as DateTime(timezone=True). We store and compare everything as UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
