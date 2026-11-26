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
    """The org's "today". Demo orgs (clock_mode "as_of"): the fixed as_of_date, never wall-clock. Private
    deployments (clock_mode "real"): the current date in the org's time zone."""
    from .sla import today

    return today(settings)
