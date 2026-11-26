// Types mirroring the API (backend/app/services/serialize.py and app/api/*).
// Dates: IsoDate = YYYY-MM-DD, IsoDateTime = full timestamp. Missing tracker fields are null (UI shows "—").

export type Id = string
export type IsoDate = string
export type IsoDateTime = string

export type Role = 'admin' | 'pmo_coordinator' | 'technical_owner' | 'line_manager' | 'employee' | 'viewer'
export type Stage =
  | 'pre_onboarding'
  | 'access'
  | 'shadowing'
  | 'supported_execution'
  | 'independent_execution'
  | 'validated'
export type CaseView = 'needs_attention' | 'mine' | 'stale' | 'access_blocked' | 'all'
export type Severity = 'high' | 'medium' | 'low'
export type AnalysisMode = 'live' | 'cached' | 'replay' | 'unavailable'
export type ReviewDisposition = 'keep_open' | 'validate_scope' | 'close'
export type TaskStatus = 'open' | 'done'
export type AccessState =
  | 'requested'
  | 'awaiting_approval'
  | 'approved'
  | 'not_provisioned'
  | 'active'
  | 'confirmed_usable'

// ---------- Identity ----------

export interface Org {
  id: Id
  name: string
  is_demo: boolean
  as_of_date: IsoDate
}

export interface UserRef {
  id: Id
  name: string
  role: Role
}

export interface OrgUser extends UserRef {
  title: string | null
}

export interface Me {
  user: { id: Id; name: string; title: string | null; role: Role }
  org: Org
  role: Role
  auth_mode: 'demo' | 'oidc'
  demo_mode: boolean
}

export interface DemoAccount {
  user_id: Id
  name: string
  title: string | null
  role: Role
  org_id: Id
  org_name: string
}

export interface Notification {
  id: Id
  text: string
  link: string | null
  read: boolean
  created_at: IsoDateTime
}

// ---------- Cases ----------

export interface Reason {
  rule_id: string
  severity: Severity
  message: string
}

export interface CaseRow {
  id: Id
  ref: string
  employee: string
  project: string | null
  tracker_status: string | null
  tracker_age_days: number | null
  stage: Stage | null
  reasons: Reason[]
  next_task: { id: Id; title: string; due_date: IsoDate | null; owner_name: string | null; overdue: boolean } | null
  open_task_count: number
  review_state: ReviewDisposition | 'none'
}

export interface EmployeeCase {
  id: Id
  ref: string
  employee: string
  movement: 'new_hire' | 'reallocation' | null
  start_date: IsoDate | null
  project: { id: Id; name: string; code: string | null } | null
  manager: string | null
  tracker_status: string | null
  tracker_updated_at: IsoDate | null
  tracker_age_days: number | null
  tech_owner: UserRef | null
  employee_user_id: Id | null
  /** From the latest technical review only; null until one exists. */
  stage: Stage | null
}

export interface Source {
  id: Id
  ref: string | null
  kind: 'email' | 'update' | 'tracker_note' | 'tracker_row'
  title: string | null
  case_id: Id | null
  project_id: Id | null
  author_role: string | null
  recipient_role: string | null
  date: IsoDate | null
  header: string | null
  body: string
  body_sha256: string
  version: number
  supersedes_id: Id | null
  ingested_via: 'seed' | 'paste' | 'upload' | 'webhook'
  created_at: IsoDateTime
}

export interface AnalysisRun {
  id: Id
  source_id: Id
  body_sha256: string
  prompt_version: string
  schema_version: string
  model: string
  mode: AnalysisMode
  status: 'ok' | 'partial' | 'failed'
  error: string | null
  created_at: IsoDateTime
}

export interface Claim {
  id: Id
  source_id: Id
  analysis_run_id: Id
  scope: string
  value: string
  reference: string | null
  quote: string
  start: number
  end: number
}

export interface RejectedCandidate {
  id: Id
  source_id: Id
  analysis_run_id: Id
  raw: { scope?: string; value?: string; quote?: string; reference?: string | null }
  reason: string
}

export interface Finding {
  id: Id
  rule_id: string
  rule_version: string
  severity: Severity
  message: string
  detail: string | null
  evidence: { source_id: Id; claim_id: Id | null }[]
  created_at: IsoDateTime
}

export interface Task {
  id: Id
  case_id: Id
  finding_id: Id | null
  title: string
  owner_user: UserRef | null
  owner_role: Role | null
  due_date: IsoDate | null
  sla_hours: number | null
  status: TaskStatus
  cited_source_ids: Id[]
  origin: 'manual' | 'ai_suggested_edited' | 'automation'
  created_by: UserRef | null
  created_at: IsoDateTime
  completed_at: IsoDateTime | null
  overdue: boolean
  case?: { id: Id; ref: string; employee: string }
}

export interface Review {
  id: Id
  case_id: Id
  disposition: ReviewDisposition
  scope: string
  rationale: string
  observed_stage: Stage | null
  cited_source_ids: Id[]
  task_id: Id | null
  reviewer: UserRef | null
  created_at: IsoDateTime
}

export interface AccessItem {
  id: Id
  case_id: Id
  system: string
  state: AccessState
  requested_at: IsoDate | null
  owner_role: string | null
  next_follow_up: IsoDate | null
  evidence_source_ids: Id[]
  updated_at: IsoDateTime
}

export interface KnowledgeRef {
  id: Id
  project_id: Id
  project: { id: Id; name: string; code: string | null } | null
  title: string
  location: string
  owner_role: string | null
  last_verified: IsoDate | null
  source_id: Id | null
}

export interface CaseDetail {
  case: EmployeeCase
  sources: Source[]
  claims: Claim[]
  rejected: RejectedCandidate[]
  findings: Finding[]
  tasks: Task[]
  access_items: AccessItem[]
  latest_review: Review | null
  reviews: Review[]
  knowledge: KnowledgeRef[]
  analysis: {
    mode: AnalysisMode
    model: string | null
    prompt_version: string | null
    last_run_at: IsoDateTime | null
    runs: AnalysisRun[]
    per_source: { source_id: Id; run: AnalysisRun | null; last_attempt: AnalysisRun | null }[]
    ai_enabled: boolean
    ai_configured: boolean
  }
  permissions: {
    can_create_task: boolean
    can_analyze: boolean
    can_review: boolean
    can_edit_access: boolean
    can_confirm_access: boolean
  }
}

export interface AnalyzeResult {
  outcomes: { source_id: Id; ref: string | null; mode: string; note: string | null; status: string | null }[]
  detail: CaseDetail
}

export interface TaskSuggestion {
  title: string
  owner_role: Role
  rationale: string
  cited_claim_ids: Id[]
  cited_source_ids: Id[]
  mode: AnalysisMode
  model: string
  prompt_version: string
}

export interface TimelineEvent {
  id: string
  type: 'source_received' | 'analysis_run' | 'finding_raised' | 'task_created' | 'task_done' | 'review_saved'
  at: string
  title: string
  actor: string | null
  ref: { entity: string; id: Id }
}

// ---------- Inbox ----------

export interface InboxItem {
  source: Source
  status: 'matched' | 'unmatched'
  matched_case: { id: Id; ref: string; employee: string } | null
  matched_project: { id: Id; name: string; code: string | null } | null
  analysis: AnalysisRun | null
}

export interface InboxPost {
  title: string
  body: string
  author_role: string
  recipient_role?: string | null
  date: IsoDate
  kind: 'email' | 'update' | 'tracker_note'
}

// ---------- Insights, settings, audit ----------

export interface Insights {
  as_of_date: IsoDate
  totals: { cases: number; cases_needing_attention: number; open_tasks: number; overdue_tasks: number; reviews_recorded: number }
  by_rule: { rule_id: string; count: number }[]
  by_reason: { rule_id: string; message: string; count: number }[]
  by_severity: Record<Severity, number>
  by_project: { project: string; cases: number; flagged: number }[]
  stage_distribution: { stage: string; count: number }[]
  review_states: { state: string; count: number }[]
  overdue: Task[]
}

export interface OrgSettings {
  stale_days: number
  unanswered_working_days: number
  as_of_date: IsoDate
  ai_enabled: boolean
  default_sla_hours: number
  llm: { model: string; configured: boolean }
}

export interface AuditEvent {
  id: Id
  actor: UserRef | null
  entity: string
  entity_id: Id
  action: string
  before: unknown
  after: unknown
  created_at: IsoDateTime
}

export interface Health {
  status: 'ok'
  auth_mode: 'demo' | 'oidc'
  demo_mode: boolean
}
