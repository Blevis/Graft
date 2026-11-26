"""Audit trail. Every write adds an AuditEvent to the same session, so it commits in the same transaction."""
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..models import AuditEvent


def snapshot(obj: Any) -> dict | None:
    if obj is None:
        return None
    out = {}
    for attr in inspect(obj).mapper.column_attrs:
        v = getattr(obj, attr.key)
        out[attr.key] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def record(
    db: Session,
    *,
    org_id: str,
    actor_user_id: str | None,
    entity: str,
    entity_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        org_id=org_id,
        actor_user_id=actor_user_id,
        entity=entity,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
    )
    db.add(ev)
    return ev
