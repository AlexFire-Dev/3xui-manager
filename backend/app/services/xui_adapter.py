from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.subscription_codec import normalize_links


@dataclass
class XuiServerConfig:
    panel_url: str
    panel_username: str
    panel_password: str
    subscription_base_url: str
    use_tls_verify: bool = True


@dataclass
class DiscoveredClientConfig:
    inbound_id: int
    inbound_remark: str | None
    inbound_protocol: str | None
    inbound_port: int | None
    client_uuid: str
    client_email: str | None
    client_sub_id: str | None
    client_enable: bool | None
    client_expiry_time: int | None
    client_total_gb: int | None
    client_up: int | None
    client_down: int | None
    raw: dict[str, Any]


def _get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if obj is None:
            continue
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _set_attr(obj: Any, names: tuple[str, ...], value: Any) -> None:
    for name in names:
        if hasattr(obj, name):
            setattr(obj, name, value)
            return
    setattr(obj, names[0], value)


def _to_jsonable(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {"value": str(obj)}


class XuiAdapter:
    """Boundary around 3x-ui.

    Panel mutations are done via py3xui; generated subscription responses are
    fetched from 3x-ui's native `/sub/{subId}` endpoint.
    """

    def __init__(self, config: XuiServerConfig):
        self.config = config

    def _api(self):
        try:
            from py3xui import Api
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("py3xui is not installed. Run: pip install py3xui") from exc

        try:
            api = Api(
                self.config.panel_url,
                self.config.panel_username,
                self.config.panel_password,
                use_tls_verify=self.config.use_tls_verify,
            )
        except TypeError:
            api = Api(self.config.panel_url, self.config.panel_username, self.config.panel_password)
        api.login()
        return api

    def list_client_configs(self) -> list[DiscoveredClientConfig]:
        api = self._api()
        inbounds = api.inbound.get_list()
        discovered: list[DiscoveredClientConfig] = []

        for inbound in inbounds:
            inbound_id = _get_attr(inbound, "id")
            inbound_remark = _get_attr(inbound, "remark")
            inbound_protocol = _get_attr(inbound, "protocol")
            inbound_port = _get_attr(inbound, "port")
            settings = _get_attr(inbound, "settings", default={})
            clients = _get_attr(settings, "clients", default=[])
            if not clients:
                continue

            for client in clients:
                client_uuid = _get_attr(client, "id", "uuid")
                if not client_uuid:
                    continue
                discovered.append(
                    DiscoveredClientConfig(
                        inbound_id=int(inbound_id),
                        inbound_remark=inbound_remark,
                        inbound_protocol=inbound_protocol,
                        inbound_port=int(inbound_port) if inbound_port is not None else None,
                        client_uuid=str(client_uuid),
                        client_email=_get_attr(client, "email"),
                        client_sub_id=_get_attr(client, "sub_id", "subId"),
                        client_enable=_get_attr(client, "enable", "enabled"),
                        client_expiry_time=_get_attr(client, "expiry_time", "expiryTime"),
                        client_total_gb=_get_attr(client, "total_gb", "totalGB"),
                        client_up=_get_attr(client, "up", default=0),
                        client_down=_get_attr(client, "down", default=0),
                        raw=_to_jsonable(client),
                    )
                )
        return discovered

    def health_check(self) -> None:
        api = self._api()
        api.inbound.get_list()

    def set_client_subscription_fields(
        self,
        *,
        inbound_id: int,
        client_email: str | None,
        client_uuid: str | None,
        sub_id: str,
        expiry_time: int | None = None,
        total_gb: int | None = None,
        enable: bool | None = True,
    ) -> str:
        """Set subId plus optional expiry/traffic/enabled fields.

        Returns the effective client UUID found on the server.
        """
        if not client_email and not client_uuid:
            raise ValueError("client_email or client_uuid is required")

        api = self._api()
        inbound = api.inbound.get_by_id(inbound_id)
        clients = _get_attr(_get_attr(inbound, "settings", default={}), "clients", default=[])

        inbound_client = None
        for candidate in clients:
            candidate_uuid = str(_get_attr(candidate, "id", "uuid", default=""))
            candidate_email = _get_attr(candidate, "email")
            if client_uuid and candidate_uuid == client_uuid:
                inbound_client = candidate
                break
            if client_email and candidate_email == client_email:
                inbound_client = candidate
                break

        if inbound_client is None:
            raise ValueError(
                f"Client not found in inbound {inbound_id}: "
                f"email={client_email!r}, uuid={client_uuid!r}"
            )

        effective_uuid = str(_get_attr(inbound_client, "id", "uuid"))

        update_client = inbound_client
        if client_email:
            try:
                update_client = api.client.get_by_email(client_email)
            except Exception:
                update_client = inbound_client

        _set_attr(update_client, ("id", "uuid"), effective_uuid)
        _set_attr(update_client, ("sub_id", "subId"), sub_id)
        if expiry_time is not None:
            _set_attr(update_client, ("expiry_time", "expiryTime"), expiry_time)
        if total_gb is not None:
            _set_attr(update_client, ("total_gb", "totalGB"), total_gb)
        if enable is not None:
            _set_attr(update_client, ("enable", "enabled"), enable)

        api.client.update(effective_uuid, update_client)
        return effective_uuid

    def set_client_sub_id(
        self,
        *,
        inbound_id: int,
        client_email: str | None,
        client_uuid: str | None,
        sub_id: str,
    ) -> str:
        return self.set_client_subscription_fields(
            inbound_id=inbound_id,
            client_email=client_email,
            client_uuid=client_uuid,
            sub_id=sub_id,
        )

    async def fetch_subscription_links_with_raw(self, sub_id: str, *, prefix: str | None = None) -> tuple[list[str], str]:
        url = self.config.subscription_base_url.rstrip("/") + f"/{sub_id}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=self.config.use_tls_verify) as client:
            response = await client.get(url)
            response.raise_for_status()
        raw = response.text
        return normalize_links(raw, prefix=prefix), raw

    async def fetch_subscription_links(self, sub_id: str, *, prefix: str | None = None) -> list[str]:
        links, _raw = await self.fetch_subscription_links_with_raw(sub_id, prefix=prefix)
        return links
