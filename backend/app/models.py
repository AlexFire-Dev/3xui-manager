import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ServerStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    down = "down"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    expired = "expired"


class ItemStatus(str, enum.Enum):
    pending = "pending"
    synced = "synced"
    error = "error"
    disabled = "disabled"


class RemoteConfigStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    missing = "missing"


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class AuditEventType(str, enum.Enum):
    server_created = "server_created"
    configs_refreshed = "configs_refreshed"
    subscription_created = "subscription_created"
    subscription_updated = "subscription_updated"
    item_created = "item_created"
    item_updated = "item_updated"
    item_deleted = "item_deleted"
    apply_started = "apply_started"
    apply_finished = "apply_finished"
    cache_refreshed = "cache_refreshed"
    cache_cleared = "cache_cleared"
    traffic_read = "traffic_read"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    telegram_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    panel_url: Mapped[str] = mapped_column(Text, nullable=False)
    panel_username: Mapped[str] = mapped_column(String(128), nullable=False)
    panel_password: Mapped[str] = mapped_column(Text, nullable=False)
    subscription_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ServerStatus] = mapped_column(Enum(ServerStatus), default=ServerStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_config_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_config_refresh_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["SubscriptionItem"]] = relationship(back_populates="server")
    remote_configs: Mapped[list["RemoteConfig"]] = relationship(back_populates="server", cascade="all, delete-orphan")


class RemoteConfig(Base):
    __tablename__ = "remote_configs"
    __table_args__ = (UniqueConstraint("server_id", "inbound_id", "client_uuid", name="uq_remote_config_identity"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"), nullable=False, index=True)
    inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound_remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inbound_protocol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inbound_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_uuid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_sub_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_enable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    client_expiry_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_total_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_up: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_down: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RemoteConfigStatus] = mapped_column(Enum(RemoteConfigStatus), default=RemoteConfigStatus.active)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    server: Mapped[Server] = relationship(back_populates="remote_configs")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True, default=lambda: uuid.uuid4().hex)
    shared_sub_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, default=lambda: uuid.uuid4().hex)
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.active)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    traffic_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    user: Mapped[User | None] = relationship(back_populates="subscriptions")
    items: Mapped[list["SubscriptionItem"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")
    source_caches: Mapped[list["SubscriptionSourceCache"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")


class SubscriptionItem(Base):
    __tablename__ = "subscription_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id"), nullable=False, index=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"), nullable=False, index=True)
    inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[ItemStatus] = mapped_column(Enum(ItemStatus), default=ItemStatus.pending)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)

    subscription: Mapped[Subscription] = relationship(back_populates="items")
    server: Mapped[Server] = relationship(back_populates="items")


class SubscriptionSourceCache(Base):
    __tablename__ = "subscription_source_caches"
    __table_args__ = (UniqueConstraint("subscription_id", "server_id", name="uq_subscription_source_cache"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id"), nullable=False, index=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"), nullable=False, index=True)
    normalized_links: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription: Mapped[Subscription] = relationship(back_populates="source_caches")
    server: Mapped[Server] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
