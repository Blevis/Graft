"""Uploaded documents become evidence: the file's text is extracted on this server (services/documents.py), stored as
an immutable source (ingested_via "upload") and analysed like any other source. The file itself is not kept."""
import hashlib
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AnalysisJob, Source
from ..services import audit
from ..services import documents as docs
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.jobs import after_commit, enqueue_analysis
from ..services.matching import match_detail
from ..services.permissions import EMPLOYEE, FULL, Policy
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, require_roles
from ..services.visibility import visible_cases
from .inbox import COORD, _item

router = APIRouter(tags=["documents"])


async def _extract(file: UploadFile) -> tuple[bytes, docs.ExtractedDocument]:
    data = await file.read(docs.MAX_BYTES + 1)
    try:
        return data, docs.extract(data)
    except docs.DocumentError as e:
        raise HTTPException(e.status, str(e)) from e


def _upload_out(s: Source, job: AnalysisJob | None, preview: bool) -> dict:
    out = {"source": ser.source_meta(s), "document": s.document, "job": ser.job_out(job) if job else None}
    if preview:  # the uploader always sees what was extracted from their own file
        out["text"] = s.body
    return out


@router.get("/documents/capabilities")
def capabilities(ctx: Ctx = Depends(get_ctx)):
    return docs.capabilities()


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload_to_case(case_id: str, file: UploadFile = File(...), title: str | None = Form(None),
                         source_date: date | None = Form(None, alias="date"),
                         ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """The employee, the case team, or the HR business partner adds a document (a report, a training record, a scan)
    to one case. It is one report among others, never a decision."""
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    level = policy.level(case)
    case_roles = policy.roles_for_case(case)
    if not policy.can_upload_document(case):
        raise HTTPException(403, "Only the employee, the case team or HR can add documents to this case")
    data, doc = await _extract(file)
    labels = ser.Lookup(db, ctx.org_id).labels
    if level == EMPLOYEE:
        role = "employee"
    elif level == FULL:
        role = (sorted(case_roles) or [ctx.role])[0]
    else:
        role = "hr_business_partner"
    s = Source(org_id=ctx.org_id, kind="document", title=(title or "").strip()[:300] or docs.default_title(file.filename),
               case_id=case.id, project_id=case.project_id, author_role=labels.get(role, role), recipient_role=None,
               date=source_date or policy.today, body=doc.text,
               body_sha256=hashlib.sha256(doc.text.encode("utf-8")).hexdigest(), version=1, ingested_via="upload",
               created_by_user_id=ctx.user_id, channel="case_page", sender=ctx.user.name,
               document=docs.provenance(file.filename, data, doc))
    db.add(s)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=s.id,
                 action="uploaded", after=ser.source_meta(s))
    job = enqueue_analysis(db, s, reason="uploaded", user_id=ctx.user_id)
    recompute_case(db, case)
    db.commit()
    after_commit(db, [job])
    db.expire_all()
    job = db.get(AnalysisJob, job.id) if job else None
    return _upload_out(db.get(Source, s.id), job, preview=True)


@router.post("/inbox/documents", status_code=201)
async def upload_to_inbox(file: UploadFile = File(...), author_role: str = Form(..., min_length=2, max_length=100),
                          source_date: date = Form(..., alias="date"), title: str | None = Form(None),
                          recipient_role: str | None = Form(None),
                          ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    """PMO intake of a document: the text is extracted, matched to a case like any inbox item, then analysed."""
    data, doc = await _extract(file)
    title = (title or "").strip()[:300] or docs.default_title(file.filename)
    m = match_detail(db, ctx.org_id, title, doc.text)
    case = m.case
    s = Source(org_id=ctx.org_id, kind="document", title=title, case_id=case.id if case else None,
               project_id=case.project_id if case else None, author_role=author_role.strip(),
               recipient_role=(recipient_role or "").strip()[:100] or None, date=source_date, body=doc.text,
               body_sha256=hashlib.sha256(doc.text.encode("utf-8")).hexdigest(), version=1, ingested_via="upload",
               created_by_user_id=ctx.user_id, channel="upload", sender=ctx.user.name, match_status=m.status,
               match_candidates=[c.id for c in m.candidates] or None,
               document=docs.provenance(file.filename, data, doc))
    db.add(s)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=s.id,
                 action="uploaded", after={**ser.source_meta(s), "match": m.reason})
    job = enqueue_analysis(db, s, reason="uploaded", user_id=ctx.user_id) if case else None
    if case:
        recompute_case(db, case)
    db.commit()
    after_commit(db, [job])
    db.expire_all()
    lk = ser.Lookup(db, ctx.org_id)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    return {**_item(db, db.get(Source, s.id), cases, lk), "document": s.document}
