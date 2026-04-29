from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload, selectinload

from app.services.xui_factory import make_adapter


from app.db import get_db
from app.models import (
    AuditEventType,
    ItemStatus,
    RemoteConfig,
    Server,
    ServerStatus,
    Subscription,
    SubscriptionItem,
    SubscriptionSourceCache,
    User,
    now_utc,
)
from app.schemas import (
    ApplyItemResult,
    ApplyResult,
    BulkSubscriptionItemsUpdate,
    PreviewResult,
    SourceCacheRead,
    SubscriptionCreate,
    SubscriptionDetail,
    SubscriptionItemCreate,
    SubscriptionItemFromRemoteConfigCreate,
    SubscriptionItemRead,
    SubscriptionItemUpdate,
    SubscriptionRead,
    SubscriptionUpdate,
    TrafficResult,
    TrafficServerBreakdown,
)
from app.services.audit import audit
from app.services.subscription_codec import encode_response
from app.services.xui_adapter import XuiAdapter, XuiServerConfig

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def get_subscription_or_404(db: Session, subscription_id: str) -> Subscription:
    subscription = (
        db.query(Subscription)
        .options(joinedload(Subscription.items))
        .filter(Subscription.id == subscription_id)
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


def make_adapter(server: Server) -> XuiAdapter:
    return XuiAdapter(
        XuiServerConfig(
            panel_url=server.panel_url,
            panel_username=server.panel_username,
            panel_password=server.panel_password,
            subscription_base_url=server.subscription_base_url,
        )
    )


def _active_servers_for_subscription(subscription: Subscription) -> list[Server]:
    active_items = [
        item
        for item in sorted(subscription.items, key=lambda item: item.sort_order)
        if item.enabled and item.status == ItemStatus.synced and item.server and item.server.status == ServerStatus.active
    ]
    result: list[Server] = []
    seen: set[str] = set()
    for item in active_items:
        if item.server_id not in seen:
            result.append(item.server)
            seen.add(item.server_id)
    return result


def _links_from_cache(cache: SubscriptionSourceCache | None) -> list[str]:
    if not cache or not cache.normalized_links:
        return []
    return [line.strip() for line in cache.normalized_links.splitlines() if line.strip()]


async def _collect_subscription_links(
    db: Session,
    subscription: Subscription,
    *,
    use_cache_on_error: bool = True,
    refresh_cache: bool = True,
) -> tuple[list[str], list[str], bool]:
    links: list[str] = []
    errors: list[str] = []
    used_cache = False

    for server in _active_servers_for_subscription(subscription):
        cache = (
            db.query(SubscriptionSourceCache)
            .filter(SubscriptionSourceCache.subscription_id == subscription.id, SubscriptionSourceCache.server_id == server.id)
            .first()
        )
        if cache is None:
            cache = SubscriptionSourceCache(subscription_id=subscription.id, server_id=server.id)
            db.add(cache)
            db.flush()

        cache.last_attempt_at = now_utc()
        try:
            server_links, raw = await make_adapter(server).fetch_subscription_links_with_raw(subscription.shared_sub_id, prefix=server.name)
            if refresh_cache:
                cache.raw_response = raw
                cache.normalized_links = "\n".join(server_links)
                cache.last_success_at = now_utc()
                cache.last_error = None
            links.extend(server_links)
        except Exception as exc:  # noqa: BLE001
            cache.last_error = str(exc)
            errors.append(f"{server.name}: {exc}")
            if use_cache_on_error:
                cached = _links_from_cache(cache)
                if cached:
                    used_cache = True
                    links.extend(cached)
    return links, errors, used_cache


@router.post("", response_model=SubscriptionRead)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    if payload.user_id and not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    subscription = Subscription(
        title=payload.title,
        user_id=payload.user_id,
        expires_at=payload.expires_at,
        traffic_limit=payload.traffic_limit,
    )
    db.add(subscription)
    db.flush()
    audit(db, AuditEventType.subscription_created, f"Subscription {subscription.title} created", entity_type="subscription", entity_id=subscription.id)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(user_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Subscription)
    if user_id:
        query = query.filter(Subscription.user_id == user_id)
    return query.order_by(Subscription.created_at.desc()).all()


@router.get("/{subscription_id}", response_model=SubscriptionDetail)
def read_subscription(subscription_id: str, db: Session = Depends(get_db)):
    return get_subscription_or_404(db, subscription_id)


@router.put("/{subscription_id}", response_model=SubscriptionRead)
def update_subscription(subscription_id: str, payload: SubscriptionUpdate, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    if payload.user_id_set and payload.user_id and not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if payload.title is not None:
        subscription.title = payload.title
    if payload.user_id_set:
        subscription.user_id = payload.user_id
    if payload.status is not None:
        subscription.status = payload.status
    if payload.expires_at_set:
        subscription.expires_at = payload.expires_at
    if payload.traffic_limit_set:
        subscription.traffic_limit = payload.traffic_limit
    audit(db, AuditEventType.subscription_updated, f"Subscription {subscription.id} updated", entity_type="subscription", entity_id=subscription.id)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.patch("/{subscription_id}", response_model=SubscriptionRead)
def patch_subscription(subscription_id: str, payload: SubscriptionUpdate, db: Session = Depends(get_db)):
    return update_subscription(subscription_id, payload, db)



@router.delete("/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: str, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    item_count = len(subscription.items or [])
    cache_count = db.query(SubscriptionSourceCache).filter(SubscriptionSourceCache.subscription_id == subscription_id).count()
    audit(
        db,
        AuditEventType.subscription_updated,
        f"Subscription {subscription.id} deleted",
        entity_type="subscription",
        entity_id=subscription.id,
        payload={"deleted_items": item_count, "deleted_caches": cache_count},
    )
    db.delete(subscription)
    db.commit()
    return None

@router.post("/{subscription_id}/items", response_model=SubscriptionItemRead)
def add_subscription_item(subscription_id: str, payload: SubscriptionItemCreate, db: Session = Depends(get_db)):
    get_subscription_or_404(db, subscription_id)
    if not db.get(Server, payload.server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    if not payload.client_email and not payload.client_uuid:
        raise HTTPException(status_code=400, detail="client_email or client_uuid is required")
    item = SubscriptionItem(**payload.model_dump(), subscription_id=subscription_id)
    db.add(item)
    db.flush()
    audit(db, AuditEventType.item_created, f"Subscription item {item.id} created", entity_type="subscription", entity_id=subscription_id)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{subscription_id}/items/from-config", response_model=SubscriptionItemRead)
def add_subscription_item_from_remote_config(subscription_id: str, payload: SubscriptionItemFromRemoteConfigCreate, db: Session = Depends(get_db)):
    get_subscription_or_404(db, subscription_id)
    remote_config = db.get(RemoteConfig, payload.remote_config_id)
    if not remote_config:
        raise HTTPException(status_code=404, detail="Remote config not found")
    item = SubscriptionItem(
        subscription_id=subscription_id,
        server_id=remote_config.server_id,
        inbound_id=remote_config.inbound_id,
        client_email=remote_config.client_email,
        client_uuid=remote_config.client_uuid,
        sort_order=payload.sort_order,
    )
    db.add(item)
    db.flush()
    audit(db, AuditEventType.item_created, f"Subscription item {item.id} created from remote config", entity_type="subscription", entity_id=subscription_id)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{subscription_id}/items/bulk", response_model=list[SubscriptionItemRead])
def replace_or_add_items_bulk(subscription_id: str, payload: BulkSubscriptionItemsUpdate, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    if payload.replace_existing:
        for item in list(subscription.items):
            db.delete(item)
        db.flush()
    created: list[SubscriptionItem] = []
    for remote_config_id in payload.remote_config_ids:
        remote_config = db.get(RemoteConfig, remote_config_id)
        if not remote_config:
            raise HTTPException(status_code=404, detail=f"Remote config not found: {remote_config_id}")
        item = SubscriptionItem(
            subscription_id=subscription_id,
            server_id=remote_config.server_id,
            inbound_id=remote_config.inbound_id,
            client_email=remote_config.client_email,
            client_uuid=remote_config.client_uuid,
            sort_order=100 + len(created),
        )
        db.add(item)
        created.append(item)
    audit(db, AuditEventType.item_created, f"Bulk updated {len(created)} subscription items", entity_type="subscription", entity_id=subscription_id)
    db.commit()
    return created


@router.put("/{subscription_id}/items/{item_id}", response_model=SubscriptionItemRead)
def update_subscription_item(subscription_id: str, item_id: str, payload: SubscriptionItemUpdate, db: Session = Depends(get_db)):
    get_subscription_or_404(db, subscription_id)
    item = db.query(SubscriptionItem).filter(SubscriptionItem.id == item_id, SubscriptionItem.subscription_id == subscription_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Subscription item not found")
    if payload.server_id is not None:
        if not db.get(Server, payload.server_id):
            raise HTTPException(status_code=404, detail="Server not found")
        item.server_id = payload.server_id
    if payload.inbound_id is not None:
        item.inbound_id = payload.inbound_id
    if payload.client_email_set:
        item.client_email = payload.client_email
    if payload.client_uuid_set:
        item.client_uuid = payload.client_uuid
    if payload.enabled is not None:
        item.enabled = payload.enabled
        if not item.enabled:
            item.status = ItemStatus.disabled
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    if not item.client_email and not item.client_uuid:
        raise HTTPException(status_code=400, detail="client_email or client_uuid is required")
    if item.enabled:
        item.status = ItemStatus.pending
    item.last_error = None
    audit(db, AuditEventType.item_updated, f"Subscription item {item.id} updated", entity_type="subscription", entity_id=subscription_id)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{subscription_id}/items/{item_id}", response_model=SubscriptionItemRead)
def patch_subscription_item(subscription_id: str, item_id: str, payload: SubscriptionItemUpdate, db: Session = Depends(get_db)):
    return update_subscription_item(subscription_id, item_id, payload, db)


@router.delete("/{subscription_id}/items/{item_id}", status_code=204)
def delete_subscription_item(
    subscription_id: str,
    item_id: str,
    db: Session = Depends(get_db),
):
    subscription = get_subscription_or_404(db, subscription_id)

    item = (
        db.query(SubscriptionItem)
        .filter(
            SubscriptionItem.id == item_id,
            SubscriptionItem.subscription_id == subscription_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Subscription item not found")

    remote_config = (
        db.query(RemoteConfig)
        .filter(RemoteConfig.id == item.remote_config_id)
        .first()
    )

    if remote_config:
        server = (
            db.query(Server)
            .filter(Server.id == remote_config.server_id)
            .first()
        )

        if server:
            try:
                make_adapter(server).clear_client_sub_id(
                    inbound_id=remote_config.inbound_id,
                    client_email=remote_config.client_email,
                    client_uuid=remote_config.client_uuid,
                )
            except Exception as exc:  # noqa: BLE001
                audit(
                    db,
                    AuditEventType.item_deleted,
                    f"Failed to clear remote subId for item {item_id}: {exc}",
                    entity_type="subscription",
                    entity_id=subscription_id,
                    payload={
                        "item_id": item_id,
                        "remote_config_id": remote_config.id,
                        "server_id": server.id,
                        "error": str(exc),
                    },
                )

                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to remove config from remote 3x-ui subscription: {exc}",
                ) from exc

    db.delete(item)

    audit(
        db,
        AuditEventType.item_deleted,
        f"Subscription item {item_id} deleted and remote subId cleared",
        entity_type="subscription",
        entity_id=subscription_id,
        payload={
            "item_id": item_id,
            "remote_config_id": item.remote_config_id,
            "subscription_id": subscription.id,
        },
    )

    db.commit()
    return None


@router.post("/{subscription_id}/apply", response_model=ApplyResult)
def apply_subscription(subscription_id: str, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    synced = 0
    failed = 0
    skipped = 0
    errors: list[str] = []
    results: list[ApplyItemResult] = []
    audit(db, AuditEventType.apply_started, f"Apply started for subscription {subscription.id}", entity_type="subscription", entity_id=subscription.id)

    expiry_time = int(subscription.expires_at.timestamp() * 1000) if subscription.expires_at else None

    for item in sorted(subscription.items, key=lambda x: x.sort_order):
        if not item.enabled:
            skipped += 1
            results.append(
                ApplyItemResult(
                    item_id=item.id,
                    server_id=item.server_id,
                    inbound_id=item.inbound_id,
                    client_email=item.client_email,
                    client_uuid=item.client_uuid,
                    status=ItemStatus.disabled,
                    ok=True,
                    action="skipped_disabled",
                )
            )
            continue

        server = db.get(Server, item.server_id)
        if not server or server.status != ServerStatus.active:
            item.status = ItemStatus.error
            item.last_error = "Server is missing or not active"
            failed += 1
            errors.append(f"item {item.id}: {item.last_error}")
            results.append(
                ApplyItemResult(
                    item_id=item.id,
                    server_id=item.server_id,
                    inbound_id=item.inbound_id,
                    client_email=item.client_email,
                    client_uuid=item.client_uuid,
                    status=item.status,
                    ok=False,
                    action="failed",
                    error=item.last_error,
                )
            )
            continue

        try:
            effective_uuid = make_adapter(server).set_client_subscription_fields(
                inbound_id=item.inbound_id,
                client_email=item.client_email,
                client_uuid=item.client_uuid,
                sub_id=subscription.shared_sub_id,
                expiry_time=expiry_time,
                total_gb=subscription.traffic_limit,
                enable=subscription.status.value == "active",
            )
            item.client_uuid = effective_uuid
            item.status = ItemStatus.synced
            item.last_error = None
            item.last_sync_at = now_utc()
            synced += 1
            results.append(
                ApplyItemResult(
                    item_id=item.id,
                    server_id=item.server_id,
                    inbound_id=item.inbound_id,
                    client_email=item.client_email,
                    client_uuid=item.client_uuid,
                    status=item.status,
                    ok=True,
                    action="synced",
                )
            )
        except Exception as exc:  # noqa: BLE001
            item.status = ItemStatus.error
            item.last_error = str(exc)
            failed += 1
            errors.append(f"item {item.id}: {exc}")
            results.append(
                ApplyItemResult(
                    item_id=item.id,
                    server_id=item.server_id,
                    inbound_id=item.inbound_id,
                    client_email=item.client_email,
                    client_uuid=item.client_uuid,
                    status=item.status,
                    ok=False,
                    action="failed",
                    error=str(exc),
                )
            )

    audit(
        db,
        AuditEventType.apply_finished,
        f"Apply finished: {synced} synced, {failed} failed, {skipped} skipped",
        entity_type="subscription",
        entity_id=subscription.id,
        payload={"errors": errors, "results": [result.model_dump(mode="json") for result in results]},
    )
    db.commit()
    return ApplyResult(
        subscription_id=subscription.id,
        shared_sub_id=subscription.shared_sub_id,
        synced=synced,
        failed=failed,
        skipped=skipped,
        errors=errors,
        results=results,
    )


@router.post("/{subscription_id}/reconcile", response_model=ApplyResult)
def reconcile_subscription(subscription_id: str, db: Session = Depends(get_db)):
    # For MVP, reconcile uses the same idempotent operation as apply.
    return apply_subscription(subscription_id, db)


@router.get("/{subscription_id}/preview", response_model=PreviewResult)
async def preview_subscription(
    subscription_id: str,
    use_cache_on_error: bool = True,
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(Subscription)
        .options(selectinload(Subscription.items).selectinload(SubscriptionItem.server))
        .filter(Subscription.id == subscription_id)
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    links, errors, used_cache = await _collect_subscription_links(db, subscription, use_cache_on_error=use_cache_on_error)
    db.commit()
    return PreviewResult(subscription_id=subscription.id, token=subscription.token, link_count=len(links), links=links, errors=errors, used_cache=used_cache)


@router.get("/{subscription_id}/preview.txt")
async def preview_subscription_text(
    subscription_id: str,
    format: str = Query(default="plain", pattern="^(plain|base64)$"),
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(Subscription)
        .options(selectinload(Subscription.items).selectinload(SubscriptionItem.server))
        .filter(Subscription.id == subscription_id)
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    links, _errors, _used_cache = await _collect_subscription_links(db, subscription)
    db.commit()
    return Response(content=encode_response(links, fmt=format), media_type="text/plain; charset=utf-8")


@router.get("/{subscription_id}/traffic", response_model=TrafficResult)
def subscription_traffic(subscription_id: str, refresh: bool = True, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    if refresh:
        servers = {item.server_id: item.server for item in subscription.items if item.server}
        for server in servers.values():
            if server.status != ServerStatus.active:
                continue
            try:
                from app.routers.servers import refresh_configs
                refresh_configs(server.id, db)
            except Exception:
                pass

    by_server: dict[str, dict] = defaultdict(lambda: {"up": 0, "down": 0, "items": 0, "server_name": ""})
    total_up = 0
    total_down = 0
    for item in subscription.items:
        query = db.query(RemoteConfig).filter(RemoteConfig.server_id == item.server_id, RemoteConfig.inbound_id == item.inbound_id)
        if item.client_uuid:
            query = query.filter(RemoteConfig.client_uuid == item.client_uuid)
        elif item.client_email:
            query = query.filter(RemoteConfig.client_email == item.client_email)
        cfg = query.first()
        if not cfg:
            continue
        up = cfg.client_up or 0
        down = cfg.client_down or 0
        server_name = item.server.name if item.server else item.server_id
        by_server[item.server_id]["server_name"] = server_name
        by_server[item.server_id]["up"] += up
        by_server[item.server_id]["down"] += down
        by_server[item.server_id]["items"] += 1
        total_up += up
        total_down += down

    breakdown = [
        TrafficServerBreakdown(server_id=sid, server_name=data["server_name"], up=data["up"], down=data["down"], total=data["up"] + data["down"], items=data["items"])
        for sid, data in by_server.items()
    ]
    audit(db, AuditEventType.traffic_read, f"Traffic read for subscription {subscription.id}", entity_type="subscription", entity_id=subscription.id)
    db.commit()
    return TrafficResult(subscription_id=subscription.id, up=total_up, down=total_down, total=total_up + total_down, limit=subscription.traffic_limit, breakdown=breakdown)


@router.get("/{subscription_id}/cache", response_model=list[SourceCacheRead])
def get_subscription_cache(subscription_id: str, db: Session = Depends(get_db)):
    get_subscription_or_404(db, subscription_id)
    return db.query(SubscriptionSourceCache).filter(SubscriptionSourceCache.subscription_id == subscription_id).all()


@router.post("/{subscription_id}/cache/refresh", response_model=PreviewResult)
async def refresh_subscription_cache(subscription_id: str, db: Session = Depends(get_db)):
    subscription = (
        db.query(Subscription)
        .options(selectinload(Subscription.items).selectinload(SubscriptionItem.server))
        .filter(Subscription.id == subscription_id)
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    links, errors, used_cache = await _collect_subscription_links(db, subscription, use_cache_on_error=False, refresh_cache=True)
    audit(db, AuditEventType.cache_refreshed, f"Cache refreshed for subscription {subscription.id}", entity_type="subscription", entity_id=subscription.id, payload={"errors": errors})
    db.commit()
    return PreviewResult(subscription_id=subscription.id, token=subscription.token, link_count=len(links), links=links, errors=errors, used_cache=used_cache)


@router.delete("/{subscription_id}/cache", status_code=204)
def clear_subscription_cache(subscription_id: str, db: Session = Depends(get_db)):
    get_subscription_or_404(db, subscription_id)
    db.query(SubscriptionSourceCache).filter(SubscriptionSourceCache.subscription_id == subscription_id).delete()
    audit(db, AuditEventType.cache_cleared, f"Cache cleared for subscription {subscription_id}", entity_type="subscription", entity_id=subscription_id)
    db.commit()
    return None


@router.get("/{subscription_id}/events")
def subscription_events(subscription_id: str, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    from app.models import AuditLog
    return db.query(AuditLog).filter(AuditLog.entity_type == "subscription", AuditLog.entity_id == subscription_id).order_by(AuditLog.created_at.desc()).limit(limit).all()
