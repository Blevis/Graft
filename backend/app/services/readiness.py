"""Readiness derived from the technical owner's append-only reviews. Read-only: the AI layer may import this.

Dispositions:
  keep_open       the case stays open for a stated scope and reason
  validate_scope  a named scope (optionally a case milestone) is validated; overall readiness is unchanged
  close           final sign-off, gated (see closure_gate)
  reopen          reverses the current sign-off, or one milestone validation, when evidence warrants it

Nothing here is stored: milestone satisfaction and final readiness are recomputed from the review history, so
every earlier decision stays visible and a reopen never edits the record it supersedes."""
from dataclasses import dataclass, field

from ..models import AccessItem, CaseRequirement, Review, Source

FINAL, REOPEN = "close", "reopen"


@dataclass
class ReadinessState:
    status: str = "not_signed_off"  # not_signed_off | signed_off | reopened
    final_review: Review | None = None
    reopen_review: Review | None = None
    validated: dict[str, Review] = field(default_factory=dict)


def derive(reviews: list[Review]) -> ReadinessState:
    """reviews in any order; processed oldest first."""
    st = ReadinessState()
    for r in sorted(reviews, key=lambda r: r.created_at):
        if r.disposition == "validate_scope" and r.milestone_key:
            st.validated[r.milestone_key] = r
        elif r.disposition == FINAL:
            st.status, st.final_review = "signed_off", r
        elif r.disposition == REOPEN:
            if r.milestone_key:
                st.validated.pop(r.milestone_key, None)
            else:
                st.status, st.final_review, st.reopen_review = "reopened", None, r
    return st


def access_blockers(items: list[AccessItem]) -> list[AccessItem]:
    return [a for a in items if a.state != "confirmed_usable"]


def requirement_status(req: CaseRequirement, st: ReadinessState, access: list[AccessItem]) -> dict:
    """status: satisfied | pending | not_applicable. Optional items report status but never block closure."""
    if req.applicability == "not_applicable":
        return {"status": "not_applicable", "detail": req.change_reason}
    if req.kind == "access":
        blockers = access_blockers(access)
        if blockers:
            return {"status": "pending",
                    "detail": "Not yet confirmed usable: " + ", ".join(a.system for a in blockers)}
        return {"status": "satisfied",
                "detail": "No systems are tracked for this case" if not access else
                "Every tracked system was confirmed usable by its tester"}
    review = st.validated.get(req.key)
    if review is not None:
        return {"status": "satisfied", "review_id": review.id, "detail": review.scope}
    return {"status": "pending", "detail": req.evidence_expectation}


def closure_gate(*, cited_ids: list[str], current_sources: list[Source], reqs: list[CaseRequirement],
                 st: ReadinessState, access: list[AccessItem]) -> tuple[list[str], list[str]]:
    """(hard failures, waivable criteria). Hard failures can never be bypassed; waivable ones only under a
    documented exception policy with a reason."""
    hard: list[str] = []
    if not cited_ids:
        hard.append("citations: final sign-off must cite at least one current source on this case")
    current = {s.id for s in current_sources}
    if any(i not in current for i in cited_ids):
        hard.append("citations: every citation must be a current source version on this case")
    waivable: list[str] = []
    has_access_req = False
    for r in reqs:
        if r.applicability != "required":
            if r.kind == "access" and r.applicability == "not_applicable":
                has_access_req = True
            continue
        if r.kind == "access":
            has_access_req = True
        if requirement_status(r, st, access)["status"] != "satisfied":
            waivable.append(f"milestone:{r.key}" if r.kind == "milestone" else "access:blocking")
    # Cases without an access requirement (legacy / no template) still may not close over blocking access.
    if not has_access_req and access_blockers(access):
        waivable.append("access:blocking")
    return hard, list(dict.fromkeys(waivable))


def snapshot(sources: list[Source]) -> list[dict]:
    return [{"source_id": s.id, "ref": s.ref, "body_sha256": s.body_sha256, "version": s.version} for s in sources]


def reassessment(latest: Review | None, current_sources: list[Source]) -> dict:
    """Why the last decision may need reconsidering: evidence that arrived or changed after it was recorded."""
    if latest is None:
        return {"needed": False, "reasons": []}
    reasons = []
    if latest.evidence_snapshot is not None:
        seen = {e["source_id"] for e in latest.evidence_snapshot}
        for s in current_sources:
            if s.id not in seen:
                label = s.ref or s.title or "A source"
                what = "re-linked or corrected (new version)" if s.version > 1 else "received"
                reasons.append(f"{label} {what} after the {latest.disposition.replace('_', ' ')} decision")
    else:
        for s in current_sources:
            if s.created_at and latest.created_at and _utc(s.created_at) > _utc(latest.created_at):
                reasons.append(f"{s.ref or s.title or 'A source'} received after the decision")
    return {"needed": bool(reasons), "reasons": reasons, "decision_id": latest.id}


def legacy_gaps(r: Review) -> list[str]:
    """Disclose what a decision recorded before the closure gate lacks, without rewriting it."""
    gaps = []
    if r.policy_version == "legacy" and r.disposition == FINAL:
        if not r.cited_source_ids:
            gaps.append("Recorded before the closure gate: no evidence citation")
        gaps.append("Recorded before the closure gate: required checks were not verified")
    return gaps


def _utc(v):
    from datetime import timezone
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
