from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import (
    ItemStatus,
    ServerStatus,
    Subscription,
    SubscriptionItem,
    SubscriptionSourceCache,
    SubscriptionStatus,
    now_utc,
)
from app.services.subscription_codec import encode_response
from app.services.xui_adapter import XuiAdapter, XuiServerConfig
from app.time_utils import as_utc_aware, utc_now

router = APIRouter(tags=["public subscription"])


def _links_from_cache(cache: SubscriptionSourceCache | None) -> list[str]:
    if not cache or not cache.normalized_links:
        return []
    return [line.strip() for line in cache.normalized_links.splitlines() if line.strip()]


@router.get("/sub/{token}")
async def get_public_subscription(
    token: str,
    format: str = "plain",
    use_cache_on_error: bool = True,
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(Subscription)
        .options(selectinload(Subscription.items).selectinload(SubscriptionItem.server))
        .filter(Subscription.token == token)
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.status != SubscriptionStatus.active:
        return Response(content="", media_type="text/plain")

    expires_at = as_utc_aware(subscription.expires_at)
    if expires_at and expires_at < utc_now():
        return Response(content="", media_type="text/plain")

    links: list[str] = []
    active_items = [
        item
        for item in sorted(subscription.items, key=lambda item: item.sort_order)
        if item.enabled and item.status == ItemStatus.synced and item.server and item.server.status == ServerStatus.active
    ]

    # 3x-ui native subscription endpoint is per subId on a server, not per item.
    # Query each selected server only once, then cache its normalized response.
    server_ids_in_order: list[str] = []
    servers_by_id = {}
    for item in active_items:
        if item.server_id not in servers_by_id:
            server_ids_in_order.append(item.server_id)
            servers_by_id[item.server_id] = item.server

    for server_id in server_ids_in_order:
        server = servers_by_id[server_id]
        cache = (
            db.query(SubscriptionSourceCache)
            .filter(
                SubscriptionSourceCache.subscription_id == subscription.id,
                SubscriptionSourceCache.server_id == server_id,
            )
            .first()
        )
        if cache is None:
            cache = SubscriptionSourceCache(subscription_id=subscription.id, server_id=server_id)
            db.add(cache)
            db.flush()

        cache.last_attempt_at = now_utc()
        adapter = XuiAdapter(
            XuiServerConfig(
                panel_url=server.panel_url,
                panel_username=server.panel_username,
                panel_password=server.panel_password,
                subscription_base_url=server.subscription_base_url,
            )
        )
        try:
            server_links, raw = await adapter.fetch_subscription_links_with_raw(
                subscription.shared_sub_id,
                prefix=server.name,
            )
            cache.raw_response = raw
            cache.normalized_links = "\n".join(server_links)
            cache.last_success_at = now_utc()
            cache.last_error = None
            links.extend(server_links)
        except Exception as exc:  # noqa: BLE001
            cache.last_error = str(exc)
            if use_cache_on_error:
                links.extend(_links_from_cache(cache))
            continue

    db.commit()
    body = encode_response(links, fmt=format)
    return Response(content=body, media_type="text/plain; charset=utf-8")
