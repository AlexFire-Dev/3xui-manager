from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, selectinload

from app.models import (
    DailyTrafficSnapshot,
    ItemStatus,
    RemoteConfig,
    RemoteConfigStatus,
    Subscription,
    SubscriptionItem,
    User,
    now_utc,
)


@dataclass(slots=True)
class TrafficItemUsage:
    subscription: Subscription
    item: SubscriptionItem
    remote_config: RemoteConfig
    up: int
    down: int
    total: int
    traffic_key: str


@dataclass(slots=True)
class SnapshotCreateResult:
    created: int
    updated: int
    skipped: int
    total_up: int
    total_down: int
    total: int


def make_traffic_key(
    *,
    subscription_id: str | None,
    server_id: str | None,
    inbound_id: int | None,
    client_uuid: str | None,
    client_email: str | None,
) -> str:
    return "|".join(
        [
            subscription_id or "",
            server_id or "",
            str(inbound_id or ""),
            client_uuid or "",
            client_email or "",
        ]
    )


def find_remote_config_for_item(
    db: Session,
    item: SubscriptionItem,
    *,
    include_missing: bool = False,
) -> RemoteConfig | None:
    query = db.query(RemoteConfig).filter(
        RemoteConfig.server_id == item.server_id,
        RemoteConfig.inbound_id == item.inbound_id,
    )

    if item.client_uuid:
        query = query.filter(RemoteConfig.client_uuid == item.client_uuid)
    elif item.client_email:
        query = query.filter(RemoteConfig.client_email == item.client_email)
    else:
        query = query.filter(RemoteConfig.client_uuid.is_(None), RemoteConfig.client_email.is_(None))

    if not include_missing:
        query = query.filter(RemoteConfig.status != RemoteConfigStatus.missing)

    return query.first()


def collect_subscription_traffic_items(
    db: Session,
    subscription: Subscription,
    *,
    include_missing: bool = False,
    only_enabled_synced_items: bool = True,
) -> list[TrafficItemUsage]:
    """Collect per-item traffic for one subscription without double-counting duplicate items."""
    rows: list[TrafficItemUsage] = []
    seen_keys: set[str] = set()

    for item in subscription.items or []:
        if only_enabled_synced_items and (not item.enabled or item.status != ItemStatus.synced):
            continue

        cfg = find_remote_config_for_item(db, item, include_missing=include_missing)
        if not cfg:
            continue

        key = make_traffic_key(
            subscription_id=subscription.id,
            server_id=item.server_id,
            inbound_id=item.inbound_id,
            client_uuid=item.client_uuid or cfg.client_uuid,
            client_email=item.client_email or cfg.client_email,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)

        up = int(cfg.client_up or 0)
        down = int(cfg.client_down or 0)
        rows.append(
            TrafficItemUsage(
                subscription=subscription,
                item=item,
                remote_config=cfg,
                up=up,
                down=down,
                total=up + down,
                traffic_key=key,
            )
        )

    return rows


def load_subscriptions_for_traffic(db: Session) -> list[Subscription]:
    return (
        db.query(Subscription)
        .options(
            selectinload(Subscription.user),
            selectinload(Subscription.items).selectinload(SubscriptionItem.server),
        )
        .all()
    )


def upsert_daily_traffic_snapshot(
    db: Session,
    usage: TrafficItemUsage,
    *,
    snapshot_date: date,
    snapshot_type: str = "daily_reset",
) -> tuple[DailyTrafficSnapshot, bool]:
    subscription = usage.subscription
    user: User | None = subscription.user
    item = usage.item
    cfg = usage.remote_config
    server = item.server
    now = now_utc()

    snapshot = (
        db.query(DailyTrafficSnapshot)
        .filter(
            DailyTrafficSnapshot.snapshot_date == snapshot_date,
            DailyTrafficSnapshot.snapshot_type == snapshot_type,
            DailyTrafficSnapshot.traffic_key == usage.traffic_key,
        )
        .first()
    )

    created = False
    if snapshot is None:
        snapshot = DailyTrafficSnapshot(
            snapshot_date=snapshot_date,
            snapshot_type=snapshot_type,
            traffic_key=usage.traffic_key,
            created_at=now,
        )
        db.add(snapshot)
        created = True

    snapshot.snapshot_at = now
    snapshot.user_id = user.id if user else subscription.user_id
    snapshot.user_name = user.name if user else None
    snapshot.user_telegram_id = user.telegram_id if user else None
    snapshot.subscription_id = subscription.id
    snapshot.subscription_title = subscription.title
    snapshot.subscription_token = subscription.token
    snapshot.subscription_item_id = item.id
    snapshot.server_id = item.server_id
    snapshot.server_name = server.name if server else None
    snapshot.inbound_id = item.inbound_id
    snapshot.inbound_remark = cfg.inbound_remark
    snapshot.inbound_protocol = cfg.inbound_protocol
    snapshot.client_email = item.client_email or cfg.client_email
    snapshot.client_uuid = item.client_uuid or cfg.client_uuid
    snapshot.remote_config_id = cfg.id
    snapshot.remote_config_status = cfg.status.value if hasattr(cfg.status, "value") else str(cfg.status)
    snapshot.up = usage.up
    snapshot.down = usage.down
    snapshot.total = usage.total
    snapshot.updated_at = now

    return snapshot, created


def create_daily_traffic_snapshots(
    db: Session,
    *,
    snapshot_date: date,
    snapshot_type: str = "daily_reset",
    include_missing: bool = False,
    only_enabled_synced_items: bool = True,
) -> SnapshotCreateResult:
    created = 0
    updated = 0
    skipped = 0
    total_up = 0
    total_down = 0

    for subscription in load_subscriptions_for_traffic(db):
        usages = collect_subscription_traffic_items(
            db,
            subscription,
            include_missing=include_missing,
            only_enabled_synced_items=only_enabled_synced_items,
        )
        if not usages:
            skipped += 1
            continue

        for usage in usages:
            _snapshot, was_created = upsert_daily_traffic_snapshot(
                db,
                usage,
                snapshot_date=snapshot_date,
                snapshot_type=snapshot_type,
            )
            if was_created:
                created += 1
            else:
                updated += 1
            total_up += usage.up
            total_down += usage.down

    return SnapshotCreateResult(
        created=created,
        updated=updated,
        skipped=skipped,
        total_up=total_up,
        total_down=total_down,
        total=total_up + total_down,
    )
