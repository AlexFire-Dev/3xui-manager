from __future__ import annotations

import time
from typing import Any

import httpx

from bot_app.config import settings
from bot_app.models import Subscription, Traffic, User


class BackendApiError(RuntimeError):
    pass


class BackendApiClient:
    """Small async client for the existing backend HTTP API.

    The bot intentionally does not import backend modules and does not connect to the DB.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=settings.request_timeout_seconds,
        )
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _login(self) -> str:
        response = await self._client.post(
            "/auth/login",
            json={
                "username": settings.admin_username,
                "password": settings.admin_password.get_secret_value(),
            },
        )
        if response.status_code >= 400:
            raise BackendApiError(f"Не удалось авторизоваться в backend: {response.status_code} {response.text}")

        data = response.json()
        self._token = str(data["access_token"])
        ttl = int(data.get("expires_in") or 3600)
        self._token_expires_at = time.time() + max(ttl - 60, 60)
        return self._token

    async def _get_token(self) -> str:
        if not self._token or time.time() >= self._token_expires_at:
            return await self._login()
        return self._token

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = await self._get_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"

        response = await self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401:
            token = await self._login()
            headers["Authorization"] = f"Bearer {token}"
            response = await self._client.request(method, path, headers=headers, **kwargs)

        if response.status_code >= 400:
            raise BackendApiError(f"Backend вернул ошибку {response.status_code}: {response.text}")

        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    @staticmethod
    def normalize_telegram_username(username: str | None) -> str | None:
        username = (username or "").strip()
        if not username:
            return None
        if username.startswith("@"):
            return username
        return f"@{username}"

    async def find_user_by_telegram_username(self, username: str) -> User | None:
        normalized = self.normalize_telegram_username(username)
        if not normalized:
            return None

        users_data = await self._request("GET", "/users", params={"q": normalized})
        users = [User.from_api(item) for item in users_data]
        normalized_lower = normalized.casefold()

        for user in users:
            if (user.telegram_id or "").strip().casefold() == normalized_lower:
                return user
        return None

    async def get_user_subscriptions(self, user_id: str) -> list[Subscription]:
        data = await self._request("GET", f"/users/{user_id}/subscriptions")
        return [Subscription.from_api(item) for item in data]

    async def get_subscription_traffic(self, subscription_id: str, *, refresh: bool | None = None) -> Traffic:
        should_refresh = settings.traffic_refresh if refresh is None else refresh
        data = await self._request(
            "GET",
            f"/subscriptions/{subscription_id}/traffic",
            params={"refresh": str(should_refresh).lower()},
        )
        return Traffic.from_api(data)

    def subscription_public_url(self, subscription: Subscription) -> str:
        return f"{settings.public_sub_base_url}/sub/{subscription.token}"
