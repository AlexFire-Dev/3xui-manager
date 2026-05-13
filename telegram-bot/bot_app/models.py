from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class User:
    id: str
    telegram_id: str | None
    name: str | None = None
    email: str | None = None
    status: str = "active"

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "User":
        return cls(
            id=str(data["id"]),
            telegram_id=data.get("telegram_id"),
            name=data.get("name"),
            email=data.get("email"),
            status=data.get("status") or "active",
        )


@dataclass(frozen=True)
class Subscription:
    id: str
    title: str
    token: str
    status: str
    expires_at: str | None
    traffic_limit: int | None
    created_at: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Subscription":
        return cls(
            id=str(data["id"]),
            title=data.get("title") or "Без названия",
            token=str(data["token"]),
            status=data.get("status") or "active",
            expires_at=data.get("expires_at"),
            traffic_limit=data.get("traffic_limit"),
            created_at=data.get("created_at"),
        )


@dataclass(frozen=True)
class TrafficBreakdown:
    server_name: str
    up: int
    down: int
    total: int
    items: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "TrafficBreakdown":
        return cls(
            server_name=data.get("server_name") or data.get("server_id") or "Сервер",
            up=int(data.get("up") or 0),
            down=int(data.get("down") or 0),
            total=int(data.get("total") or 0),
            items=int(data.get("items") or 0),
        )


@dataclass(frozen=True)
class Traffic:
    subscription_id: str
    up: int
    down: int
    total: int
    limit: int | None
    breakdown: list[TrafficBreakdown] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Traffic":
        return cls(
            subscription_id=str(data["subscription_id"]),
            up=int(data.get("up") or 0),
            down=int(data.get("down") or 0),
            total=int(data.get("total") or 0),
            limit=data.get("limit"),
            breakdown=[TrafficBreakdown.from_api(item) for item in data.get("breakdown") or []],
        )
