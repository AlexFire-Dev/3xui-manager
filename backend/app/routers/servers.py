import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEventType, RemoteConfig, RemoteConfigStatus, Server, ServerStatus, SubscriptionItem, SubscriptionSourceCache, now_utc
from app.schemas import DeleteResult, RefreshConfigsResult, RemoteConfigRead, ServerCreate, ServerHealthRead, ServerRead
from app.services.audit import audit
from app.services.xui_adapter import XuiAdapter, XuiServerConfig

router = APIRouter(prefix="/servers", tags=["servers"])


def get_server_or_404(db: Session, server_id: str) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


def make_adapter(server: Server) -> XuiAdapter:
    return XuiAdapter(
        XuiServerConfig(
            panel_url=server.panel_url,
            panel_username=server.panel_username,
            panel_password=server.panel_password,
            subscription_base_url=server.subscription_base_url,
        )
    )


@router.post("", response_model=ServerRead)
def create_server(payload: ServerCreate, db: Session = Depends(get_db)):
    server = Server(
        name=payload.name,
        panel_url=str(payload.panel_url).rstrip("/"),
        panel_username=payload.panel_username,
        panel_password=payload.panel_password,
        subscription_base_url=str(payload.subscription_base_url).rstrip("/"),
    )
    db.add(server)
    db.flush()
    audit(db, AuditEventType.server_created, f"Server {server.name} created", entity_type="server", entity_id=server.id)
    db.commit()
    db.refresh(server)
    return server


@router.get("", response_model=list[ServerRead])
def list_servers(db: Session = Depends(get_db)):
    return db.query(Server).order_by(Server.created_at.desc()).all()



@router.delete("/{server_id}", response_model=DeleteResult)
def delete_server(server_id: str, force: bool = Query(default=False), db: Session = Depends(get_db)):
    server = get_server_or_404(db, server_id)
    item_count = db.query(SubscriptionItem).filter(SubscriptionItem.server_id == server_id).count()
    cache_count = db.query(SubscriptionSourceCache).filter(SubscriptionSourceCache.server_id == server_id).count()
    remote_config_count = db.query(RemoteConfig).filter(RemoteConfig.server_id == server_id).count()

    if (item_count or cache_count) and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Server is used by subscriptions/cache. Pass force=true to delete local references too.",
                "subscription_items": item_count,
                "source_caches": cache_count,
                "remote_configs": remote_config_count,
            },
        )

    if force:
        db.query(SubscriptionItem).filter(SubscriptionItem.server_id == server_id).delete(synchronize_session=False)
        db.query(SubscriptionSourceCache).filter(SubscriptionSourceCache.server_id == server_id).delete(synchronize_session=False)
        db.query(RemoteConfig).filter(RemoteConfig.server_id == server_id).delete(synchronize_session=False)

    audit(
        db,
        AuditEventType.subscription_updated,
        f"Server {server.name} deleted",
        entity_type="server",
        entity_id=server.id,
        payload={
            "force": force,
            "deleted_subscription_items": item_count if force else 0,
            "deleted_source_caches": cache_count if force else 0,
            "deleted_remote_configs": remote_config_count,
        },
    )
    db.delete(server)
    db.commit()
    return DeleteResult(
        deleted=True,
        entity_type="server",
        entity_id=server_id,
        deleted_children={
            "subscription_items": item_count if force else 0,
            "source_caches": cache_count if force else 0,
            "remote_configs": remote_config_count,
        },
    )

@router.get("/{server_id}/health", response_model=ServerHealthRead)
def server_health(server_id: str, db: Session = Depends(get_db)):
    server = get_server_or_404(db, server_id)
    checked_at = now_utc()
    try:
        make_adapter(server).health_check()
        server.status = ServerStatus.active
        server.last_health_at = checked_at
        server.last_health_error = None
        db.commit()
        return ServerHealthRead(server_id=server.id, status=server.status, ok=True, checked_at=checked_at)
    except Exception as exc:  # noqa: BLE001
        server.status = ServerStatus.down
        server.last_health_at = checked_at
        server.last_health_error = str(exc)
        db.commit()
        return ServerHealthRead(server_id=server.id, status=server.status, ok=False, checked_at=checked_at, error=str(exc))


@router.get("/{server_id}/configs", response_model=list[RemoteConfigRead])
def list_cached_configs(
    server_id: str,
    status: RemoteConfigStatus | None = Query(default=None),
    q: str | None = Query(default=None, description="Search in client_email, uuid, subId, inbound remark"),
    db: Session = Depends(get_db),
):
    get_server_or_404(db, server_id)
    query = db.query(RemoteConfig).filter(RemoteConfig.server_id == server_id)
    if status is not None:
        query = query.filter(RemoteConfig.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (RemoteConfig.client_email.ilike(like))
            | (RemoteConfig.client_uuid.ilike(like))
            | (RemoteConfig.client_sub_id.ilike(like))
            | (RemoteConfig.inbound_remark.ilike(like))
        )
    return query.order_by(RemoteConfig.inbound_id.asc(), RemoteConfig.client_email.asc()).all()


@router.post("/{server_id}/configs/refresh", response_model=RefreshConfigsResult)
def refresh_configs(server_id: str, db: Session = Depends(get_db)):
    server = get_server_or_404(db, server_id)
    now = now_utc()

    try:
        discovered = make_adapter(server).list_client_configs()
        server.status = ServerStatus.active
        server.last_health_at = now
        server.last_health_error = None
    except Exception as exc:  # noqa: BLE001
        server.status = ServerStatus.down
        server.last_config_refresh_at = now
        server.last_config_refresh_error = str(exc)
        server.last_health_at = now
        server.last_health_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to refresh configs from 3x-ui: {exc}") from exc

    seen_keys: set[tuple[int, str]] = set()
    upserted = 0

    for cfg in discovered:
        key = (cfg.inbound_id, cfg.client_uuid)
        seen_keys.add(key)
        existing = (
            db.query(RemoteConfig)
            .filter(
                RemoteConfig.server_id == server.id,
                RemoteConfig.inbound_id == cfg.inbound_id,
                RemoteConfig.client_uuid == cfg.client_uuid,
            )
            .first()
        )
        if existing is None:
            existing = RemoteConfig(server_id=server.id, inbound_id=cfg.inbound_id, client_uuid=cfg.client_uuid, discovered_at=now)
            db.add(existing)

        existing.inbound_remark = cfg.inbound_remark
        existing.inbound_protocol = cfg.inbound_protocol
        existing.inbound_port = cfg.inbound_port
        existing.client_email = cfg.client_email
        existing.client_sub_id = cfg.client_sub_id
        existing.client_enable = cfg.client_enable
        existing.client_expiry_time = cfg.client_expiry_time
        existing.client_total_gb = cfg.client_total_gb
        existing.client_up = cfg.client_up
        existing.client_down = cfg.client_down
        existing.raw_json = json.dumps(cfg.raw, ensure_ascii=False, default=str)
        existing.status = RemoteConfigStatus.active
        existing.updated_at = now
        upserted += 1

    marked_missing = 0
    existing_configs = db.query(RemoteConfig).filter(RemoteConfig.server_id == server.id).all()
    for existing in existing_configs:
        if (existing.inbound_id, existing.client_uuid) not in seen_keys and existing.status != RemoteConfigStatus.missing:
            existing.status = RemoteConfigStatus.missing
            existing.updated_at = now
            marked_missing += 1

    server.last_config_refresh_at = now
    server.last_config_refresh_error = None
    audit(
        db,
        AuditEventType.configs_refreshed,
        f"Refreshed {len(discovered)} configs from {server.name}",
        entity_type="server",
        entity_id=server.id,
        payload={"discovered": len(discovered), "upserted": upserted, "marked_missing": marked_missing},
    )
    db.commit()

    configs = db.query(RemoteConfig).filter(RemoteConfig.server_id == server.id).all()
    return RefreshConfigsResult(server_id=server.id, discovered=len(discovered), upserted=upserted, marked_missing=marked_missing, configs=configs)
