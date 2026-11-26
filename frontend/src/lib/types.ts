// Types mirroring the API contract in CLAUDE.md ("API contract", "Domain model").
// Dates are ISO strings: `IsoDate` = YYYY-MM-DD, `IsoDateTime` = full timestamp.
// Missing tracker fields are null (UI shows "—"), never invented.

export type Id = string
export type IsoDate = string
export type IsoDateTime = string

// ---------- Tenancy & identity ----------

export type Role = 'admin' | 'pmo_coordinator' | 'technical_owner' | 'line_manager' | 'employee' | 'viewer'

export interface Org {
  id: Id
  name: string
  is_demo: boolean
  as_of_date: IsoDate
}

export interface User {
  id: Id
  name: string
  role: Role
  title?: string | null
}

export interface Me {
  user: User
  org: Org
  role: Role
  memberships: { org: Org; role: Role }[]
}

export interface DemoAccount {
  user_id: Id
  name: string
  role: Role
  org_name: string
}

export interface DemoLoginRequest {
  user_id: Id
}

export interface SignupRequest {
  org_name: string
  your_name: string
}

// ---------- Cases ----------

export type Movement = 'new_hire' | 'reallocation'

export type Stage =
  | 'pre_onboarding'
  | 'access'
  | 'shadowing'
  | 'supported_execution'
  | 'independent_execution'
  | 'validated'

export type CaseView = 'needs_attention' | 'mine' | 'stale' | 'access_blocked' | 'all'

export type Severity = 'high' | 'medium' | 'low'

export interface ProjectRef {
  id: Id
  name: string
  code: string | null
}

export interface UserRef {
  id: Id
  name: string
  role: Role
}

export interface EmployeeCase {
  id: Id
  ref: string // e.g. "ONB-005"
  employee: string
  movement: Movement | null
  start_date: IsoDate | null
  project: ProjectRef | null
  manager: string | null
  tracker_status: string | null // verbatim tracker text, e.g. "Ready with Support"
  tracker_updated_at: IsoDate | null
  tracker_age_days: number | null // computed against the org's as_of_date
  tech_owner: UserRef | null
  /** Derived from the latest technical review only; null until a review exists. */
  stage: Stage | null
}

export interface Reason {
  rule_id: string
  severity: Severity
  message: string
}

export interface TaskSummary {
  id: Id
  title: string
  due_date: IsoDate | null
  owner_name: string | null
}

export type ReviewState = 'none' | ReviewDisposition

export interface CaseRow {
  id: Id
  ref: string
  employee: string
  project: string | null
  tracker_status: string | null
  tracker_age_days: number | null
  stage: Stage | null
  reasons: Reason[]
  next_task: TaskSummary | null
  review_state: ReviewState
}

// ---------- Evidence (immutable, versioned) ----------

export type SourceKind = 'email' | 'update' | 'tracker_note' | 'tracker_row'
export type IngestedVia = 'seed' | 'paste' | 'upload' | 'webhook'

export interface Source {
  id: Id
  ref: string | null // starter-pack id, e.g. "E3"
  kind: SourceKind
  title: string | null
  case_id: Id | null
  project_id: Id | null
  author_role: string | null // verbatim role, e.g. "Technical Lead"
  recipient_role: string | null
  date: IsoDate | null
  body: string
  body_sha256: string
  version: number
  supersedes_id: Id | null
  ingested_via: IngestedVia
  created_at: IsoDateTime
}

// ---------- Derived (recomputable) ----------

export type AnalysisMode = 'live' | 'cached' | 'replay' | 'unavailable'
export type AnalysisStatus = 'ok' | 'partial' | 'failed' | 'skipped'

export interface AnalysisRun {
  id: Id
  source_id: Id
  body_sha256: string
  prompt_version: string
  schema_version: string
  model: string
  mode: AnalysisMode
  status: AnalysisStatus
  created_at: IsoDateTime
}

export type ClaimScope =
  | 'initial_training'
  | 'knowledge_transfer'
  | 'standard_requests'
  | 'complex_scenarios'
  | 'overall_independence'
  | 'onboarding_closure'
  | 'technical_readiness_report'
  | 'access'

export interface Claim {
  id: Id
  source_id: Id
  analysis_run_id: Id
  scope: ClaimScope
  value: string
  reference: string | null // system name for access claims, else null
  quote: string
  start: number // half-open [start, end) code-point offsets into source.body
  end: number
}

export interface RejectedCandidate {
  id: Id
  source_id: Id
  analysis_run_id: Id
  raw: { scope?: string; value?: string; quote?: string; reference?: string | null }
  reason: string
}

export interface EvidenceRef {
  source_id: Id
  claim_id: Id | null
}

export interface Finding {
  id: Id
  rule_id: string // e.g. "CLOSURE_CONFLICT", "MISSING_PROJECT"
  rule_version: string
  severity: Severity
  message: string
  evidence: EvidenceRef[]
}

export interface AnalysisSummary {
  mode: AnalysisMode
  model: string | null
  prompt_version: string | null
  last_run_at: IsoDateTime | null
  runs: AnalysisRun[]
}

// ---------- Human records ----------

export type TaskStatus = 'open' | 'done'
export type TaskOrigin = 'manual' | 'ai_suggested_edited' | 'automation'

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
  origin: TaskOrigin
  created_by: UserRef
  created_at: IsoDateTime
  completed_at: IsoDateTime | null
}

export interface CreateTaskRequest {
  title: string
  owner_user_id?: Id | null
  owner_role?: Role | null
  due_date?: IsoDate | null
  sla_hours?: number | null
  finding_id?: Id | null
  cited_source_ids: Id[]
  origin: TaskOrigin
}

export interface UpdateTaskRequest {
  status: TaskStatus
}

export type ReviewDisposition = 'keep_open' | 'validate_scope' | 'close'

export interface Review {
  id: Id
  case_id: Id
  disposition: ReviewDisposition
  scope: string
  rationale: string
  cited_source_ids: Id[]
  task_id: Id | null
  reviewer: UserRef
  created_at: IsoDateTime
}

export interface CreateReviewRequest {
  disposition: ReviewDisposition
  scope: string
  rationale: string
  cited_source_ids: Id[]
  task_id?: Id | null
}

export type AccessState =
  | 'requested'
  | 'approved'
  | 'active'
  | 'confirmed_usable'
  | 'not_provisioned'
  | 'awaiting_approval'

export interface AccessItem {
  id: Id
  case_id: Id
  system: string
  state: AccessState
  requested_at: IsoDate | null
  owner_role: string | null
  next_follow_up: IsoDate | null
  evidence_source_ids: Id[]
}

export interface KnowledgeRef {
  id: Id
  project_id: Id
  title: string
  location: string // path or URL; a reference only, never a copied document
  owner_role: string | null
  last_verified: IsoDate | null
}

// ---------- GET /cases/{id} ----------

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
  analysis: AnalysisSummary
}

// ---------- Timeline ----------

export type TimelineEventType =
  | 'source_received'
  | 'analysis_run'
  | 'finding_raised'
  | 'task_created'
  | 'task_done'
  | 'review_saved'

export interface TimelineEvent {
  id: Id
  type: TimelineEventType
  at: IsoDateTime
  title: string
  actor: string | null
  ref: { entity: string; id: Id }
}

// ---------- AI suggestions (not persisted) ----------

export interface TaskSuggestion {
  title: string
  owner_role: Role
  rationale: string
  cited_claim_ids: Id[]
  mode: AnalysisMode
  model: string | null
  prompt_version: string
}

// ---------- Inbox ----------

export type InboxStatus = 'unmatched' | 'matched'

export interface InboxItem {
  source: Source
  status: InboxStatus
  matched_case: { id: Id; ref: string; employee: string } | null
}

export interface InboxPostRequest {
  body: string
  author_role: string
  date: IsoDate
  title: string
}

export interface InboxLinkRequest {
  case_id: Id
}

// ---------- Insights ----------

export interface Insights {
  by_reason: { rule_id: string; count: number }[]
  by_severity: Record<Severity, number>
  by_project: { project: string; count: number }[]
  overdue_tasks: number
  stage_distribution: { stage: Stage | 'none'; count: number }[]
}

// ---------- Settings & audit ----------

export interface OrgSettings {
  stale_days: number
  unanswered_working_days: number
  as_of_date: IsoDate
  ai_enabled: boolean
  default_sla_hours: number
}

export interface AuditEvent {
  id: Id
  org_id: Id
  actor: UserRef | null
  entity: string
  entity_id: Id
  action: string
  before: unknown
  after: unknown
  created_at: IsoDateTime
}

export interface Notification {
  id: Id
  text: string
  link: string | null
  read: boolean
  created_at: IsoDateTime
}

export interface Health {
  status: 'ok'
  auth_mode: 'demo' | 'oidc'
  demo_mode: boolean
}
