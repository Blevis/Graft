from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DEFAULT_SETTINGS, Setting


def get_org_settings(db: Session, org_id: str) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for s in db.execute(select(Setting).where(Setting.org_id == org_id)).scalars():
        out[s.key] = s.value
    return out


def as_of(settings: dict) -> date:
    """Ages, staleness and SLAs are computed against the org's as_of_date, never wall-clock."""
    return date.fromisoformat(settings["as_of_date"])
