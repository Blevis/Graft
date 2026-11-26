"""Inbound evidence from a trusted relay (mail gateway, ITSM webhook). Authenticated by a scoped service identity.

POST /api/integrations/inbound
  Authorization: Bearer <service token>     (python -m app.ops service-token --org <slug> --name <relay>)
  {"external_id": "...", "received_at": "...", "sender": "...", "subject": "...", "body": "...",
   "author_role": "...", "recipient_role": "...", "case_ref": "ONB-005"?}

- Tenant: the org the credential belongs to. No other tenant mapping is accepted from the payload.
- Idempotent on external_id: the same message again returns the existing current version (200, duplicate);
  a different body under the same id is rejected (409): corrections arrive under a new id or through a link.
- The body is stored verbatim as evidence; only sender, subject, received time and ids are kept as metadata.
- Strong identifiers first (case_ref, then a case reference in the text, then one employee name); ambiguity goes
  to the Inbox review queue with candidates. Matched evidence is analysed in the background."""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ServiceCredential, Source
from ..models._base import utcnow
from ..services import audit
from ..services import serialize as ser
from ..services.evidence import latest_sources
from ..services.jobs import after_commit, enqueue_analysis
from ..services.matching import match_detail
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.sla import tz

router = APIRouter(prefix="/integrations", tags=["integrations"])


class InboundMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    external_id: str = Field(min_length=3, max_length=200)
    received_at: datetime
    sender: str = Field(min_length=1, max_length=300)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    author_role: str | None = Field(default=None, max_length=100)
    recipient_role: str | None = Field(default=None, max_length=100)
    kind: str = Field(default="email", pattern="^(email|update|tracker_note)$")
    case_ref: str | None = Field(default=None, max_length=30)


def service_identity(request: Request, authorization: str | None = Header(default=None),
                     db: Session = Depends(get_db)) -> ServiceCredential:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Service token required")
    digest = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    cred = db.execute(select(ServiceCredential).where(ServiceCredential.token_sha256 == digest)).scalar_one_or_none()
    if cred is None or not cred.is_active:
        raise HTTPException(401, "Invalid service token")
    if "inbound:write" not in (cred.scopes or []):
        raise HTTPException(403, "This service identity may not deliver evidence")
    size = int(request.headers.get("content-length") or 0)
    if size > get_settings().INBOUND_MAX_BYTES:
        raise HTTPException(413, "Payload too large")
    return cred


@router.post("/inbound")
def inbound(body: InboundMessage, cred: ServiceCredential = Depends(service_identity), db: Session = Depends(get_db)):
    org_id = cred.org_id
    sha = hashlib.sha256(body.body.encode("utf-8")).hexdigest()
    first = db.execute(select(Source).where(Source.org_id == org_id, Source.external_id == body.external_id,
                                            Source.version == 1)).scalar_one_or_none()
    if first is not None:
        if first.body_sha256 != sha:
            raise HTTPException(409, "This external_id was already delivered with a different body")
        current = next((s for s in latest_sources(db, org_id) if s.external_id == body.external_id), first)
        return {"status": "duplicate", "source_id": current.id, "match_status": current.match_status}
    m = match_detail(db, org_id, body.subject, body.body, hint_ref=body.case_ref)
    received = body.received_at if body.received_at.tzinfo else body.received_at.replace(tzinfo=timezone.utc)
    settings = get_org_settings(db, org_id)
    s = Source(org_id=org_id, kind=body.kind, title=body.subject, case_id=m.case.id if m.case else None,
               project_id=m.case.project_id if m.case else None, author_role=body.author_role or "Relayed message",
               recipient_role=body.recipient_role, date=received.astimezone(tz(settings)).date(), body=body.body,
               body_sha256=sha, version=1, ingested_via="webhook", external_id=body.external_id,
               channel=f"relay:{cred.name}", sender=body.sender, received_at=received, match_status=m.status,
               match_candidates=[c.id for c in m.candidates] or None)
    db.add(s)
    db.flush()
    cred.last_used_at = utcnow()
    audit.record(db, org_id=org_id, actor_user_id=None, entity="source", entity_id=s.id, action="relayed",
                 after={**ser.source_meta(s), "service_identity": cred.name, "match": m.reason})
    job = enqueue_analysis(db, s, reason="inbound") if m.case else None
    if m.case:
        recompute_case(db, m.case)
    db.commit()
    after_commit(db, [job])
    return {"status": "created", "source_id": s.id, "match_status": m.status,
            "case_ref": m.case.ref if m.case else None, "job_id": job.id if job else None}
