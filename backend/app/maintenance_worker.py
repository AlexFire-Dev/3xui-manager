from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.services.maintenance import run_daily_maintenance
from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("maintenance_worker")


def _next_scheduled_at(now: datetime) -> datetime:
    scheduled = now.replace(
        hour=settings.maintenance_run_hour_utc,
        minute=settings.maintenance_run_minute_utc,
        second=0,
        microsecond=0,
    )
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return scheduled


def _run_once_for_today() -> None:
    with SessionLocal() as db:
        result = run_daily_maintenance(db)
        logger.info("daily maintenance result: %s", result)


def main() -> None:
    logger.info(
        "maintenance worker started; daily run at %02d:%02d UTC",
        settings.maintenance_run_hour_utc,
        settings.maintenance_run_minute_utc,
    )

    if settings.maintenance_run_on_start:
        try:
            _run_once_for_today()
        except Exception:  # noqa: BLE001
            logger.exception("maintenance run on start failed")

    next_run_at = _next_scheduled_at(datetime.now(timezone.utc))
    while True:
        now = datetime.now(timezone.utc)
        if now >= next_run_at:
            try:
                _run_once_for_today()
            except Exception:  # noqa: BLE001
                logger.exception("scheduled maintenance run failed")
            next_run_at = _next_scheduled_at(datetime.now(timezone.utc))

        sleep_seconds = max(5, min(settings.maintenance_loop_sleep_seconds, int((next_run_at - now).total_seconds())))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
