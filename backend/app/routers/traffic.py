from __future__ import annotations

from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DailyTrafficSnapshot
from app.schemas import DailyTrafficSnapshotRead, DailyTrafficSummary, DailyTrafficSummaryBucket

router = APIRouter(prefix="/traffic", tags=["traffic"])


def _daily_query(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    user_id: str | None,
    telegram_id: str | None,
    subscription_id: str | None,
    snapshot_type: str | None,
):
    query = db.query(DailyTrafficSnapshot)
    if date_from is not None:
        query = query.filter(DailyTrafficSnapshot.snapshot_date >= date_from)
    if date_to is not None:
        query = query.filter(DailyTrafficSnapshot.snapshot_date <= date_to)
    if user_id:
        query = query.filter(DailyTrafficSnapshot.user_id == user_id)
    if telegram_id:
        query = query.filter(DailyTrafficSnapshot.user_telegram_id == telegram_id)
    if subscription_id:
        query = query.filter(DailyTrafficSnapshot.subscription_id == subscription_id)
    if snapshot_type:
        query = query.filter(DailyTrafficSnapshot.snapshot_type == snapshot_type)
    return query


@router.get("/daily", response_model=list[DailyTrafficSnapshotRead])
def list_daily_traffic_snapshots(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: str | None = Query(default=None),
    telegram_id: str | None = Query(default=None),
    subscription_id: str | None = Query(default=None),
    snapshot_type: str | None = Query(default="daily_reset"),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    return (
        _daily_query(
            db,
            date_from=date_from,
            date_to=date_to,
            user_id=user_id,
            telegram_id=telegram_id,
            subscription_id=subscription_id,
            snapshot_type=snapshot_type,
        )
        .order_by(DailyTrafficSnapshot.snapshot_date.desc(), DailyTrafficSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/daily/summary", response_model=DailyTrafficSummary)
def get_daily_traffic_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: str | None = Query(default=None),
    telegram_id: str | None = Query(default=None),
    subscription_id: str | None = Query(default=None),
    snapshot_type: str | None = Query(default="daily_reset"),
    db: Session = Depends(get_db),
):
    rows = _daily_query(
        db,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        telegram_id=telegram_id,
        subscription_id=subscription_id,
        snapshot_type=snapshot_type,
    ).all()

    total_up = sum(int(row.up or 0) for row in rows)
    total_down = sum(int(row.down or 0) for row in rows)

    by_subscription: dict[str, dict] = defaultdict(lambda: {"title": None, "up": 0, "down": 0, "items": 0})
    by_server: dict[str, dict] = defaultdict(lambda: {"title": None, "up": 0, "down": 0, "items": 0})

    for row in rows:
        subscription_key = row.subscription_id or "unknown"
        by_subscription[subscription_key]["title"] = row.subscription_title
        by_subscription[subscription_key]["up"] += int(row.up or 0)
        by_subscription[subscription_key]["down"] += int(row.down or 0)
        by_subscription[subscription_key]["items"] += 1

        server_key = row.server_id or "unknown"
        by_server[server_key]["title"] = row.server_name
        by_server[server_key]["up"] += int(row.up or 0)
        by_server[server_key]["down"] += int(row.down or 0)
        by_server[server_key]["items"] += 1

    return DailyTrafficSummary(
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        telegram_id=telegram_id,
        up=total_up,
        down=total_down,
        total=total_up + total_down,
        items=len(rows),
        by_subscription=[
            DailyTrafficSummaryBucket(
                key=key,
                title=value["title"],
                up=value["up"],
                down=value["down"],
                total=value["up"] + value["down"],
                items=value["items"],
            )
            for key, value in sorted(by_subscription.items(), key=lambda pair: pair[1]["title"] or pair[0])
        ],
        by_server=[
            DailyTrafficSummaryBucket(
                key=key,
                title=value["title"],
                up=value["up"],
                down=value["down"],
                total=value["up"] + value["down"],
                items=value["items"],
            )
            for key, value in sorted(by_server.items(), key=lambda pair: pair[1]["title"] or pair[0])
        ],
    )
