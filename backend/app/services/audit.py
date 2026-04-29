import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEventType, AuditLog


def audit(
    db: Session,
    event_type: AuditEventType,
    message: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None,
        )
    )
