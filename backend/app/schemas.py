from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.models import (
    AuditEventType,
    ItemStatus,
    RemoteConfigStatus,
    ServerStatus,
    SubscriptionStatus,
    UserStatus,
)


class DeleteResult(BaseModel):
    deleted: bool
    entity_type: str
    entity_id: str
    deleted_children: dict[str, int] = {}


class UserCreate(BaseModel):
    external_id: str | None = None
    name: str | None = None
    email: str | None = None
    telegram_id: str | None = None


class UserUpdate(BaseModel):
    external_id: str | None = None
    name: str | None = None
    email: str | None = None
    telegram_id: str | None = None
    status: UserStatus | None = None

    external_id_set: bool = False
    name_set: bool = False
    email_set: bool = False
    telegram_id_set: bool = False

    @model_validator(mode="after")
    def mark_explicit_fields(self):
        self.external_id_set = "external_id" in self.model_fields_set
        self.name_set = "name" in self.model_fields_set
        self.email_set = "email" in self.model_fields_set
        self.telegram_id_set = "telegram_id" in self.model_fields_set
        return self


class UserRead(BaseModel):
    id: str
    external_id: str | None
    name: str | None
    email: str | None
    telegram_id: str | None
    status: UserStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ServerCreate(BaseModel):
    name: str
    panel_url: HttpUrl
    panel_username: str
    panel_password: str
    subscription_base_url: HttpUrl = Field(description="Base URL for 3x-ui subscription endpoint, e.g. https://xui.example.com/sub")


class ServerRead(BaseModel):
    id: str
    name: str
    panel_url: str
    subscription_base_url: str
    status: ServerStatus
    created_at: datetime
    last_config_refresh_at: datetime | None = None
    last_config_refresh_error: str | None = None
    last_health_at: datetime | None = None
    last_health_error: str | None = None

    model_config = {"from_attributes": True}


class ServerHealthRead(BaseModel):
    server_id: str
    status: ServerStatus
    ok: bool
    checked_at: datetime
    error: str | None = None


class RemoteConfigRead(BaseModel):
    id: str
    server_id: str
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
    client_up: int | None = None
    client_down: int | None = None
    status: RemoteConfigStatus
    discovered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RefreshConfigsResult(BaseModel):
    server_id: str
    discovered: int
    upserted: int
    marked_missing: int
    configs: list[RemoteConfigRead]


class SubscriptionCreate(BaseModel):
    title: str
    user_id: str | None = None
    expires_at: datetime | None = None
    traffic_limit: int | None = None


class SubscriptionUpdate(BaseModel):
    title: str | None = None
    user_id: str | None = None
    status: SubscriptionStatus | None = None
    expires_at: datetime | None = None
    traffic_limit: int | None = None

    user_id_set: bool = False
    expires_at_set: bool = False
    traffic_limit_set: bool = False

    @model_validator(mode="after")
    def mark_explicit_fields(self):
        self.user_id_set = "user_id" in self.model_fields_set
        self.expires_at_set = "expires_at" in self.model_fields_set
        self.traffic_limit_set = "traffic_limit" in self.model_fields_set
        return self


class SubscriptionRead(BaseModel):
    id: str
    user_id: str | None
    title: str
    token: str
    shared_sub_id: str
    status: SubscriptionStatus
    expires_at: datetime | None
    traffic_limit: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionItemCreate(BaseModel):
    server_id: str
    inbound_id: int
    client_email: str | None = None
    client_uuid: str | None = None
    sort_order: int = 100


class SubscriptionItemFromRemoteConfigCreate(BaseModel):
    remote_config_id: str
    sort_order: int = 100


class SubscriptionItemUpdate(BaseModel):
    server_id: str | None = None
    inbound_id: int | None = None
    client_email: str | None = None
    client_uuid: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None

    client_email_set: bool = False
    client_uuid_set: bool = False

    @model_validator(mode="after")
    def mark_explicit_fields(self):
        self.client_email_set = "client_email" in self.model_fields_set
        self.client_uuid_set = "client_uuid" in self.model_fields_set
        return self


class BulkSubscriptionItemsUpdate(BaseModel):
    remote_config_ids: list[str]
    replace_existing: bool = False


class SubscriptionItemRead(BaseModel):
    id: str
    subscription_id: str
    server_id: str
    inbound_id: int
    client_email: str | None
    client_uuid: str | None
    enabled: bool
    status: ItemStatus
    last_error: str | None
    last_sync_at: datetime | None
    sort_order: int

    model_config = {"from_attributes": True}


class SubscriptionDetail(SubscriptionRead):
    items: list[SubscriptionItemRead]


class ApplyItemResult(BaseModel):
    item_id: str
    server_id: str
    inbound_id: int
    client_email: str | None
    client_uuid: str | None
    status: ItemStatus
    ok: bool
    action: str
    error: str | None = None


class ApplyResult(BaseModel):
    subscription_id: str
    shared_sub_id: str
    synced: int
    failed: int
    skipped: int = 0
    errors: list[str]
    results: list[ApplyItemResult] = []


class PreviewResult(BaseModel):
    subscription_id: str
    token: str
    link_count: int
    links: list[str]
    errors: list[str]
    used_cache: bool


class TrafficServerBreakdown(BaseModel):
    server_id: str
    server_name: str
    up: int
    down: int
    total: int
    items: int


class TrafficResult(BaseModel):
    subscription_id: str
    up: int
    down: int
    total: int
    limit: int | None
    breakdown: list[TrafficServerBreakdown]


class SourceCacheRead(BaseModel):
    id: str
    subscription_id: str
    server_id: str
    normalized_links: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class AuditLogRead(BaseModel):
    id: str
    event_type: AuditEventType
    entity_type: str | None
    entity_id: str | None
    message: str
    payload_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
