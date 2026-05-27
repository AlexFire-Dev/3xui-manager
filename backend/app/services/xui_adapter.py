from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.services.subscription_codec import normalize_links


@dataclass
class XuiServerConfig:
    panel_url: str
    panel_username: str
    panel_password: str
    subscription_base_url: str
    use_tls_verify: bool = True
    # Optional explicit 3x-ui v3 API token.
    # If it is not provided, panel_password from the existing DB field is used
    # as the Bearer token. panel_username is intentionally ignored.
    api_token: str | None = None


@dataclass
class DiscoveredClientConfig:
    inbound_id: int
    inbound_remark: str | None
    inbound_protocol: str | None
    inbound_port: int | None

    client_uuid: str | None
    client_email: str | None
    client_sub_id: str | None
    client_enable: bool | None
    client_expiry_time: int | None
    client_total_gb: int | None
    client_up: int | None
    client_down: int | None

    raw: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    """Convert dict / pydantic model / object / JSON string to a plain dict."""
    if value is None:
        return {}

    if isinstance(value, dict):
        return deepcopy(value)

    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, dict):
                return loaded
            return {"value": loaded}
        except json.JSONDecodeError:
            return {}

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    if hasattr(value, "__dict__"):
        return {
            key: val
            for key, val in vars(value).items()
            if not key.startswith("_")
        }

    return {"value": str(value)}


def _parse_3xui_json_field(value: Any) -> Any:
    """3x-ui v3 returns JSON objects, older panels may return JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _inbound_to_raw(inbound: Any) -> dict[str, Any]:
    raw = _as_dict(inbound)

    for key in ("settings", "streamSettings", "sniffing", "allocate"):
        if key in raw:
            raw[key] = _parse_3xui_json_field(raw[key])

    return raw


def _get_inbound_settings(inbound: Any) -> dict[str, Any]:
    inbound_dict = _as_dict(inbound)
    settings = _parse_3xui_json_field(inbound_dict.get("settings") or {})
    return settings if isinstance(settings, dict) else {}


def _get_clients_from_inbound(inbound: Any) -> list[dict[str, Any]]:
    settings = _get_inbound_settings(inbound)
    clients = settings.get("clients") or []

    if not isinstance(clients, list):
        return []

    result: list[dict[str, Any]] = []
    for client in clients:
        client_dict = _as_dict(client)
        if client_dict:
            result.append(client_dict)

    return result


def _get_client_stats_from_inbound(inbound: Any) -> dict[str, dict[str, int]]:
    raw = _inbound_to_raw(inbound)
    stats = raw.get("clientStats") or raw.get("client_stats") or []

    result: dict[str, dict[str, int]] = {}
    if not isinstance(stats, list):
        return result

    for stat in stats:
        stat_dict = _as_dict(stat)
        email = stat_dict.get("email")
        if email:
            result[str(email)] = {
                "up": int(stat_dict.get("up") or 0),
                "down": int(stat_dict.get("down") or 0),
            }

    return result


def _client_identity(client: dict[str, Any]) -> str | None:
    """Return the proxy credential/identity, not the 3x-ui DB row id.

    Important for 3x-ui v3:
    - /panel/api/clients/get/:email returns client.id as the numeric DB row id.
    - In inbound settings for VLESS/VMess, client.id may still be the proxy UUID.
    - Password-based protocols use password/auth instead of UUID.

    So we prefer explicit credential fields and only use id when it looks like
    a protocol identity, not when it is an int-like DB id such as 16.
    """
    for key in ("uuid", "password", "auth"):
        value = client.get(key)
        if value:
            return str(value)

    value = client.get("id")
    if value is None:
        return None

    # In 3x-ui v3 client API, id=16 means DB row id, not proxy identity.
    if isinstance(value, int):
        return None

    text = str(value).strip()
    if not text or text.isdigit():
        return None

    return text


def _client_sub_id(client: dict[str, Any]) -> str | None:
    value = client.get("subId") or client.get("sub_id")
    return str(value) if value else None


def _client_enable(client: dict[str, Any]) -> bool | None:
    value = client.get("enable", client.get("enabled"))
    return value if isinstance(value, bool) else None


def _client_expiry_time(client: dict[str, Any]) -> int | None:
    value = client.get("expiryTime", client.get("expiry_time"))
    return int(value) if value is not None else None


def _client_total_gb(client: dict[str, Any]) -> int | None:
    value = client.get("totalGB", client.get("total_gb"))
    return int(value) if value is not None else None


def _sanitize_client_update_payload(client_data: dict[str, Any]) -> dict[str, Any]:
    """Build a safe payload for /panel/api/clients/update/:email.

    3x-ui v3 has two different meanings around `id`:
    - /clients/get/:email may return `id` as the numeric DB row id.
    - /clients/update/:email expects `client.id` to be a string when present
      (historically the VLESS/VMess UUID field in settings.clients[]).

    Round-tripping the GET object directly therefore breaks with:
      json: cannot unmarshal number into Go struct field Client.id of type string

    This function removes API/read-only fields and ensures `id`, when sent, is
    never numeric. Existing secrets are preserved through `uuid`, `password`, or
    `auth` when the panel returned them.
    """
    payload = deepcopy(client_data)

    # These fields are response metadata / computed fields, not client payload.
    for key in (
        "traffic",
        "inboundIds",
        "inbound_ids",
        "createdAt",
        "updatedAt",
        "created_at",
        "updated_at",
        "lastOnline",
        "online",
    ):
        payload.pop(key, None)

    raw_id = payload.get("id")
    uuid_value = payload.get("uuid")

    # If id is a numeric row id, never send it back to update.
    if isinstance(raw_id, int) or (isinstance(raw_id, str) and raw_id.strip().isdigit()):
        payload.pop("id", None)

        # Some 3x-ui builds still expect the protocol UUID under `id`.
        # If `uuid` is available, use it as string `id` as well.
        if uuid_value:
            payload["id"] = str(uuid_value)

    elif raw_id is not None:
        payload["id"] = str(raw_id)

    # Normalize common scalar fields to the types expected by the API.
    for key in ("uuid", "password", "auth", "email", "subId", "comment", "flow"):
        if key in payload and payload[key] is not None:
            payload[key] = str(payload[key])

    for key in ("totalGB", "expiryTime", "limitIp", "tgId", "reset"):
        if key in payload and payload[key] is not None:
            try:
                payload[key] = int(payload[key])
            except (TypeError, ValueError):
                payload.pop(key, None)

    if "enable" in payload and payload["enable"] is not None:
        payload["enable"] = bool(payload["enable"])

    return payload


def _quote_path(value: str) -> str:
    return quote(value, safe="")


class XuiAdapter:
    """3x-ui v3 REST API adapter.

    This class intentionally keeps the old public methods used by the rest of
    the backend, but internally talks to 3x-ui directly through HTTP instead of
    py3xui.

    Auth mode:
      Bearer token only. By default, the adapter uses panel_password from the
      existing Server model as the 3x-ui v3 API token. panel_username is kept
      only for compatibility with the current backend model and is not used.
    """

    def __init__(self, config: XuiServerConfig):
        self.config = config

    def _panel_url(self, path: str) -> str:
        return self.config.panel_url.rstrip("/") + "/" + path.lstrip("/")

    def _public_subscription_url(self, sub_id: str) -> str:
        return self.config.subscription_base_url.rstrip("/") + f"/{sub_id}"

    @staticmethod
    def _extract_3xui_obj(response: httpx.Response) -> Any:
        response.raise_for_status()

        payload = response.json()

        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise RuntimeError(payload.get("msg") or "3x-ui API request failed")

            if "obj" in payload:
                return payload["obj"]

        return payload

    def _api_token(self) -> str:
        token = self.config.api_token or self.config.panel_password
        token = (token or "").strip()
        if not token:
            raise ValueError(
                "3x-ui API token is empty. Put the 3x-ui v3 API token into "
                "the server panel_password field."
            )
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_token()}",
        }

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            verify=self.config.use_tls_verify,
            headers=self._auth_headers(),
        )

    def _login_http_client(self) -> httpx.Client:
        # Backward-compatible alias used by older maintenance/utility code.
        # Despite the name, this no longer performs /login.
        return self._http_client()

    async def _async_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            verify=self.config.use_tls_verify,
            headers=self._auth_headers(),
        )

    def health_check(self) -> None:
        client = self._http_client()
        try:
            self._extract_3xui_obj(
                client.get(self._panel_url("/panel/api/server/status"))
            )
        finally:
            client.close()

    def list_client_configs(self) -> list[DiscoveredClientConfig]:
        """Return all inbounds/clients from the panel.

        v3 endpoint used:
            GET /panel/api/inbounds/list

        The backend still stores one RemoteConfig per inbound/client pair, so we
        keep the old DiscoveredClientConfig shape.
        """
        client = self._http_client()
        try:
            inbounds = self._extract_3xui_obj(
                client.get(self._panel_url("/panel/api/inbounds/list"))
            )
        finally:
            client.close()

        if not isinstance(inbounds, list):
            raise RuntimeError("Unexpected 3x-ui /inbounds/list response")

        discovered: list[DiscoveredClientConfig] = []

        for inbound_raw_value in inbounds:
            inbound = _inbound_to_raw(inbound_raw_value)
            inbound_id = inbound.get("id")
            if inbound_id is None:
                continue

            inbound_remark = inbound.get("remark")
            inbound_protocol = inbound.get("protocol")
            inbound_port = inbound.get("port")

            clients = _get_clients_from_inbound(inbound)
            client_stats = _get_client_stats_from_inbound(inbound)

            if clients:
                for client_data in clients:
                    client_email = client_data.get("email")
                    client_uuid = _client_identity(client_data)
                    stats = client_stats.get(str(client_email)) if client_email else None

                    discovered.append(
                        DiscoveredClientConfig(
                            inbound_id=int(inbound_id),
                            inbound_remark=str(inbound_remark) if inbound_remark is not None else None,
                            inbound_protocol=str(inbound_protocol) if inbound_protocol is not None else None,
                            inbound_port=int(inbound_port) if inbound_port is not None else None,
                            client_uuid=client_uuid,
                            client_email=str(client_email) if client_email else None,
                            client_sub_id=_client_sub_id(client_data),
                            client_enable=_client_enable(client_data),
                            client_expiry_time=_client_expiry_time(client_data),
                            client_total_gb=_client_total_gb(client_data),
                            client_up=(stats or {}).get("up", int(client_data.get("up") or 0)),
                            client_down=(stats or {}).get("down", int(client_data.get("down") or 0)),
                            raw={
                                "inbound": inbound,
                                "client": client_data,
                                "client_stats": stats,
                            },
                        )
                    )

                continue

            discovered.append(
                DiscoveredClientConfig(
                    inbound_id=int(inbound_id),
                    inbound_remark=str(inbound_remark) if inbound_remark is not None else None,
                    inbound_protocol=str(inbound_protocol) if inbound_protocol is not None else None,
                    inbound_port=int(inbound_port) if inbound_port is not None else None,
                    client_uuid=None,
                    client_email=None,
                    client_sub_id=None,
                    client_enable=inbound.get("enable") if isinstance(inbound.get("enable"), bool) else None,
                    client_expiry_time=None,
                    client_total_gb=None,
                    client_up=int(inbound.get("up") or 0),
                    client_down=int(inbound.get("down") or 0),
                    raw={
                        "inbound": inbound,
                        "client": None,
                    },
                )
            )

        return discovered

    def _get_client_by_email(self, client: httpx.Client, client_email: str) -> tuple[dict[str, Any], list[int]]:
        obj = self._extract_3xui_obj(
            client.get(self._panel_url(f"/panel/api/clients/get/{_quote_path(client_email)}"))
        )

        if not isinstance(obj, dict):
            raise RuntimeError(f"Unexpected 3x-ui client payload for {client_email}")

        client_data = obj.get("client") or obj
        inbound_ids = obj.get("inboundIds") or obj.get("inbound_ids") or []

        if not isinstance(client_data, dict):
            raise RuntimeError(f"Unexpected 3x-ui client data for {client_email}")

        if not isinstance(inbound_ids, list):
            inbound_ids = []

        return deepcopy(client_data), [int(item) for item in inbound_ids]

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

        v3 endpoint used:
            GET  /panel/api/clients/get/:email
            POST /panel/api/clients/update/:email

        3x-ui v3 treats clients as first-class entities, identified by email.
        The update endpoint replaces the client row, so this method first reads
        the full client payload and then changes only the fields managed by this
        central backend.
        """
        if not client_email:
            raise ValueError("3x-ui v3 client update requires client_email")

        client = self._http_client()
        try:
            client_data, inbound_ids = self._get_client_by_email(client, client_email)

            # Do not compare client_uuid with client_data["id"] here.
            # In 3x-ui v3 /clients/get/:email, client.id is the numeric DB row id
            # (for example 16), while our RemoteConfig.client_uuid stores the
            # proxy credential: UUID/password/auth. The email is the stable v3
            # identifier, and /clients/update/:email is intentionally keyed by it.
            #
            # A stale/missing client is still handled correctly by /clients/get/:email
            # returning "record not found" before this point.

            payload = _sanitize_client_update_payload(client_data)
            payload["email"] = client_email
            payload["subId"] = sub_id

            if expiry_time is not None:
                payload["expiryTime"] = expiry_time

            if total_gb is not None:
                payload["totalGB"] = total_gb

            if enable is not None:
                payload["enable"] = enable

            # Do not send inboundIds or numeric DB id to /clients/update.
            # Attach/detach is managed by dedicated endpoints in 3x-ui v3.

            self._extract_3xui_obj(
                client.post(
                    self._panel_url(f"/panel/api/clients/update/{_quote_path(client_email)}"),
                    json=payload,
                )
            )

            return str(_client_identity(payload) or client_uuid or client_email)

        finally:
            client.close()

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

    def clear_client_sub_id(
        self,
        *,
        inbound_id: int,
        client_email: str | None,
        client_uuid: str | None,
    ) -> str:
        return self.set_client_subscription_fields(
            inbound_id=inbound_id,
            client_email=client_email,
            client_uuid=client_uuid,
            sub_id="",
            expiry_time=None,
            total_gb=None,
            enable=None,
        )

    async def fetch_subscription_links_with_raw(
        self,
        sub_id: str,
        *,
        prefix: str | None = None,
    ) -> tuple[list[str], str]:
        """Fetch subscription links for a subId.

        Primary v3 endpoint:
            GET /panel/api/clients/subLinks/:subId

        Fallback:
            public subscription_base_url/<subId>
        """
        api_error: Exception | None = None

        try:
            client = await self._async_http_client()
            try:
                response = await client.get(
                    self._panel_url(f"/panel/api/clients/subLinks/{_quote_path(sub_id)}")
                )
                obj = self._extract_3xui_obj(response)

                if not isinstance(obj, list):
                    raise RuntimeError("Unexpected 3x-ui subLinks response")

                links = [str(item).strip() for item in obj if str(item).strip()]
                raw = json.dumps(obj, ensure_ascii=False)

                if prefix:
                    links = normalize_links("\n".join(links), prefix=prefix)

                return links, raw
            finally:
                await client.aclose()
        except Exception as exc:  # noqa: BLE001
            api_error = exc

        # Keep the old public-subscription fallback so this file can be deployed
        # before every remote panel/token is fully migrated.
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=self.config.use_tls_verify,
        ) as public_client:
            try:
                response = await public_client.get(self._public_subscription_url(sub_id))
                response.raise_for_status()
            except Exception as fallback_exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Failed to fetch subscription links via v3 API ({api_error}) "
                    f"and public subscription fallback ({fallback_exc})"
                ) from fallback_exc

        raw = response.text
        return normalize_links(raw, prefix=prefix), raw

    async def fetch_subscription_links(
        self,
        sub_id: str,
        *,
        prefix: str | None = None,
    ) -> list[str]:
        links, _raw = await self.fetch_subscription_links_with_raw(
            sub_id,
            prefix=prefix,
        )
        return links

    def reset_all_client_traffics(self) -> None:
        """Reset all per-client traffic counters on the panel."""
        client = self._http_client()
        try:
            self._extract_3xui_obj(
                client.post(self._panel_url("/panel/api/clients/resetAllTraffics"))
            )
        finally:
            client.close()

    def reset_all_panel_traffics(self) -> None:
        """Reset inbound-level traffic counters on the panel."""
        client = self._http_client()
        try:
            self._extract_3xui_obj(
                client.post(self._panel_url("/panel/api/inbounds/resetAllTraffics"))
            )
        finally:
            client.close()

    def reset_client_traffic(self, *, client_email: str) -> None:
        """Reset one client's traffic counters by email."""
        client = self._http_client()
        try:
            self._extract_3xui_obj(
                client.post(self._panel_url(f"/panel/api/clients/resetTraffic/{_quote_path(client_email)}"))
            )
        finally:
            client.close()

    def get_client_links(self, *, client_email: str) -> list[str]:
        """Return all protocol URLs for one client across attached inbounds."""
        client = self._http_client()
        try:
            obj = self._extract_3xui_obj(
                client.get(self._panel_url(f"/panel/api/clients/links/{_quote_path(client_email)}"))
            )
        finally:
            client.close()

        if not isinstance(obj, list):
            raise RuntimeError("Unexpected 3x-ui client links response")

        return [str(item).strip() for item in obj if str(item).strip()]
