"""Request bodies (the write side of the API contract). Role never appears in a body."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "pmo_coordinator", "technical_owner", "line_manager", "employee", "viewer"]
Stage = Literal["pre_onboarding", "access", "shadowing", "supported_execution", "independent_execution", "validated"]
AccessState = Literal["requested", "awaiting_approval", "approved", "not_provisioned", "active", "confirmed_usable"]


class DemoLogin(BaseModel):
    user_id: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    owner_user_id: str | None = None
    owner_role: Role | None = None
    due_date: date | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=24 * 60)
    finding_id: str | None = None
    cited_source_ids: list[str] = []
    origin: Literal["manual", "ai_suggested_edited"] = "manual"


class TaskUpdate(BaseModel):
    status: Literal["open", "done"]


class ReviewCreate(BaseModel):
    disposition: Literal["keep_open", "validate_scope", "close"]
    scope: str = Field(min_length=3, max_length=300)
    rationale: str = Field(min_length=10, max_length=4000)
    observed_stage: Stage | None = None
    cited_source_ids: list[str] = []
    task_id: str | None = None


class InboxPost(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=3, max_length=20000)
    author_role: str = Field(min_length=2, max_length=100)
    recipient_role: str | None = Field(default=None, max_length=100)
    date: date
    kind: Literal["email", "update", "tracker_note"] = "email"


class InboxLink(BaseModel):
    case_id: str


class AccessCreate(BaseModel):
    system: str = Field(min_length=2, max_length=200)
    state: AccessState = "requested"
    requested_at: date | None = None
    owner_role: str | None = None
    next_follow_up: date | None = None
    evidence_source_ids: list[str] = []


class AccessUpdate(BaseModel):
    state: AccessState
    next_follow_up: date | None = None


class SettingsPatch(BaseModel):
    stale_days: int | None = Field(default=None, ge=1, le=90)
    unanswered_working_days: int | None = Field(default=None, ge=1, le=30)
    as_of_date: date | None = None
    ai_enabled: bool | None = None
    default_sla_hours: int | None = Field(default=None, ge=1, le=24 * 30)
