from __future__ import annotations

import json
from copy import deepcopy
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

    # Для обычных client-based протоколов: VLESS / VMess / Trojan и т.д.
    # Для inbound-only протоколов вроде Hysteria может быть None.
    client_uuid: str | None
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


def _set_existing_or_first_attr(obj: Any, names: tuple[str, ...], value: Any) -> None:
    """
    Аккуратно выставляет поле на объекте py3xui.

    Если у объекта уже есть одно из имён — меняем его.
    Если нет — ставим первое имя.

    Это нужно из-за различий:
      sub_id vs subId
      expiry_time vs expiryTime
      total_gb vs totalGB
      enable vs enabled
    """
    for name in names:
        if hasattr(obj, name):
            setattr(obj, name, value)
            return

    setattr(obj, names[0], value)


def _as_dict(value: Any) -> dict[str, Any]:
    """
    Универсально превращает объект py3xui / pydantic / dict / json-string в dict.

    Важно:
    - возвращаем deepcopy, чтобы не мутировать исходный объект случайно;
    - поддерживаем settings как строку JSON;
    - поддерживаем pydantic v1/v2.
    """
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


def _maybe_json(value: Any) -> Any:
    """
    Для raw-полей inbound'а.

    В 3x-ui часть полей часто приходит JSON-строкой:
      settings
      streamSettings
      sniffing
      allocate

    Чтобы в БД raw был полезным, пытаемся их распарсить.
    """
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _inbound_to_raw(inbound: Any) -> dict[str, Any]:
    raw = _as_dict(inbound)

    for key in ("settings", "streamSettings", "sniffing", "allocate"):
        if key in raw:
            raw[key] = _maybe_json(raw[key])

    return raw


def _get_inbound_settings(inbound: Any) -> dict[str, Any]:
    settings = _get_attr(inbound, "settings", default={})
    return _as_dict(settings)


def _get_clients_from_inbound(inbound: Any) -> list[Any]:
    settings = _get_inbound_settings(inbound)
    clients = settings.get("clients", [])

    if clients is None:
        return []

    if isinstance(clients, list):
        return clients

    return []


def _find_client(
    clients: list[Any],
    *,
    client_email: str | None,
    client_uuid: str | None,
) -> Any | None:
    for candidate in clients:
        candidate_uuid = str(_get_attr(candidate, "id", "uuid", default="") or "")
        candidate_email = _get_attr(candidate, "email")

        if client_uuid and candidate_uuid == client_uuid:
            return candidate

        if client_email and candidate_email == client_email:
            return candidate

    return None


def _patch_client_for_subscription(
    existing_client: Any,
    *,
    effective_uuid: str,
    sub_id: str,
    expiry_time: int | None,
    total_gb: int | None,
    enable: bool | None,
) -> Any:
    """
    Патчит существующего клиента, НЕ создавая его заново.

    Это критично.

    Старый баг:
      apply собирал client object с нуля и отправлял его в 3x-ui.
      Из-за этого терялись поля вроде:
        flow
        limitIp
        tgId
        reset
        comment
        security-related custom fields

    Новая логика:
      берём существующего клиента;
      меняем только:
        subId
        expiryTime
        totalGB
        enable;
      всё остальное оставляем как было.
    """
    patched = deepcopy(existing_client)

    if effective_uuid:
        _set_existing_or_first_attr(patched, ("id", "uuid"), effective_uuid)
    _set_existing_or_first_attr(patched, ("sub_id", "subId"), sub_id)

    if expiry_time is not None:
        _set_existing_or_first_attr(patched, ("expiry_time", "expiryTime"), expiry_time)

    if total_gb is not None:
        _set_existing_or_first_attr(patched, ("total_gb", "totalGB"), total_gb)

    if enable is not None:
        _set_existing_or_first_attr(patched, ("enable", "enabled"), enable)

    return patched


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
            api = Api(
                self.config.panel_url,
                self.config.panel_username,
                self.config.panel_password,
            )

        api.login()
        return api

    def list_client_configs(self) -> list[DiscoveredClientConfig]:
        """
        Возвращает список конфигов с сервера.

        Важное изменение:
        - больше НЕ фильтруем протоколы;
        - больше НЕ пропускаем inbound без settings.clients;
        - inbound-only протоколы вроде hysteria/hysteria2 тоже попадают в список.

        Для VLESS/VMess/Trojan:
          один client = один DiscoveredClientConfig.

        Для Hysteria/Hysteria2 и других inbound-only:
          один inbound = один DiscoveredClientConfig с client_uuid=None.
        """
        api = self._api()
        inbounds = api.inbound.get_list()
        discovered: list[DiscoveredClientConfig] = []

        for inbound in inbounds:
            inbound_id = _get_attr(inbound, "id")
            if inbound_id is None:
                continue

            inbound_remark = _get_attr(inbound, "remark")
            inbound_protocol = _get_attr(inbound, "protocol")
            inbound_port = _get_attr(inbound, "port")
            inbound_raw = _inbound_to_raw(inbound)

            clients = _get_clients_from_inbound(inbound)

            # Case 1: обычные inbound'ы с clients.
            if clients:
                for client in clients:
                    client_uuid = _get_attr(client, "id", "uuid")
                    client_email = _get_attr(client, "email")

                    # Если у client почему-то нет uuid/email, всё равно не валим импорт.
                    # Но такой config нельзя будет apply'нуть как client-based.
                    discovered.append(
                        DiscoveredClientConfig(
                            inbound_id=int(inbound_id),
                            inbound_remark=inbound_remark,
                            inbound_protocol=inbound_protocol,
                            inbound_port=int(inbound_port) if inbound_port is not None else None,
                            client_uuid=str(client_uuid) if client_uuid else None,
                            client_email=str(client_email) if client_email else None,
                            client_sub_id=_get_attr(client, "sub_id", "subId"),
                            client_enable=_get_attr(client, "enable", "enabled"),
                            client_expiry_time=_get_attr(client, "expiry_time", "expiryTime"),
                            client_total_gb=_get_attr(client, "total_gb", "totalGB"),
                            client_up=_get_attr(client, "up", default=0),
                            client_down=_get_attr(client, "down", default=0),
                            raw={
                                "inbound": inbound_raw,
                                "client": _as_dict(client),
                            },
                        )
                    )

                continue

            # Case 2: inbound-only протоколы, например hysteria/hysteria2.
            discovered.append(
                DiscoveredClientConfig(
                    inbound_id=int(inbound_id),
                    inbound_remark=inbound_remark,
                    inbound_protocol=inbound_protocol,
                    inbound_port=int(inbound_port) if inbound_port is not None else None,
                    client_uuid=None,
                    client_email=None,
                    client_sub_id=None,
                    client_enable=_get_attr(inbound, "enable", "enabled"),
                    client_expiry_time=None,
                    client_total_gb=None,
                    client_up=_get_attr(inbound, "up", default=0),
                    client_down=_get_attr(inbound, "down", default=0),
                    raw={
                        "inbound": inbound_raw,
                        "client": None,
                    },
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

        Важное изменение:
        - update теперь делается как PATCH поверх существующего client;
        - flow и остальные поля не должны перетираться.
        """
        if not client_email and not client_uuid:
            raise ValueError("client_email or client_uuid is required")

        api = self._api()
        inbound = api.inbound.get_by_id(inbound_id)
        clients = _get_clients_from_inbound(inbound)

        inbound_client = _find_client(
            clients,
            client_email=client_email,
            client_uuid=client_uuid,
        )

        if inbound_client is None:
            raise ValueError(
                f"Client not found in inbound {inbound_id}: "
                f"email={client_email!r}, uuid={client_uuid!r}"
            )

        raw_uuid = _get_attr(inbound_client, "id", "uuid")
        effective_uuid = str(raw_uuid) if raw_uuid else ""

        # Не используем api.client.get_by_email как источник правды для update,
        # потому что он может вернуть урезанную модель без flow.
        #
        # Используем client ровно из inbound.settings.clients,
        # где обычно лежит полный объект клиента.
        patched_client = _patch_client_for_subscription(
            inbound_client,
            effective_uuid=effective_uuid,
            sub_id=sub_id,
            expiry_time=expiry_time,
            total_gb=total_gb,
            enable=enable,
        )

        update_key = effective_uuid or client_email

        if not update_key:
            raise ValueError(
                f"Cannot update client in inbound {inbound_id}: no uuid and no email"
            )

        api.client.update(update_key, patched_client)
        return effective_uuid or str(client_email)

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

    async def fetch_subscription_links_with_raw(
        self,
        sub_id: str,
        *,
        prefix: str | None = None,
    ) -> tuple[list[str], str]:
        url = self.config.subscription_base_url.rstrip("/") + f"/{sub_id}"

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=self.config.use_tls_verify,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

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