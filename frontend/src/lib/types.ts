// Types mirroring the API (backend/app/services/serialize.py and app/api/*).
// Dates: IsoDate = YYYY-MM-DD, IsoDateTime = full timestamp. Missing tracker fields are null (UI shows "—").

export type Id = string
export type IsoDate = string
export type IsoDateTime = string

/** Stable canonical role codes. Orgs may rename display labels (me.role_labels) but never the codes. */
export type Role =
  | 'org_admin'
  | 'pmo_coordinator'
  | 'project_manager'
  | 'line_manager'
  | 'technical_owner'
  | 'training_responsible'
  | 'hr_business_partner'
  | 'access_responsible'
  | 'project_member'
  | 'employee'
  | 'management_viewer'
  | 'auditor'
export type ResponsibilityType =
  | 'line_manager'
  | 'project_manager'
  | 'technical_owner'
  | 'training_responsible'
  | 'hr_business_partner'
  | 'access_responsible'
export type ViewLevel = 'full' | 'employee' | 'summary' | 'access_only' | 'task_only'
export type Stage =
  | 'pre_onboarding'
  | 'access'
  | 'shadowing'
  | 'supported_execution'
  | 'independent_execution'
  | 'validated'
export type CaseView = 'needs_attention' | 'mine' | 'stale' | 'access_blocked' | 'missing_owner' | 'all'
export type Severity = 'high' | 'medium' | 'low'
export type AnalysisMode = 'live' | 'cached' | 'replay' | 'unavailable'
export type ReviewDisposition = 'keep_open' | 'validate_scope' | 'close' | 'reopen'
export type ReadinessStatus = 'not_signed_off' | 'signed_off' | 'reopened'
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
  clock_mode: 'as_of' | 'real'
  timezone: string | null
}

export interface UserRef {
  id: Id
  name: string
  role: Role
}

export interface OrgUser extends UserRef {
  title: string | null
  roles: Role[]
  status: 'active' | 'suspended' | 'invited'
}

export interface MeGrant {
  role: Role
  label: string
  scope_type: 'organization' | 'project' | 'case'
  scope_id: Id | null
  scope_name: string | null
  default_for_cases: boolean
}

export interface Me {
  user: { id: Id; name: string; title: string | null; role: Role }
  org: Org
  /** Highest-priority role, for display only. */
  role: Role
  roles: Role[]
  grants: MeGrant[]
  /** Presentation context chosen by the user among roles they hold. Never grants anything. */
  working_role: Role | null
  role_labels: Record<Role, string>
  auth_mode: 'demo' | 'oidc'
  demo_mode: boolean
}

export interface DemoAccount {
  user_id: Id
  name: string
  email: string | null
  title: string | null
  role: Role
  roles: Role[]
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
  movement?: string | null
  tracker_status: string | null
  tracker_age_days: number | null
  stage: Stage | null
  reasons: Reason[]
  next_task: { id: Id; title: string; due_date: IsoDate | null; owner_name: string | null; overdue: boolean } | null
  open_task_count: number
  review_state: ReviewDisposition | 'none'
  ownership_gaps: ResponsibilityType[]
  my_responsibilities: ResponsibilityType[]
  view_level: ViewLevel
  readiness: ReadinessStatus | null
  validated_milestones: string[]
  note?: string
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
  line_manager: UserRef | null
  employee_user_id: Id | null
  expected_readiness_date: IsoDate | null
  exact_role: string | null
  external_id: string | null
  readiness: Readiness | null
  /** From the latest technical review only; null until one exists. */
  stage: Stage | null
}

export interface DocumentInfo {
  filename: string
  content_type: string
  size: number
  sha256: string
  method: 'text' | 'pdf_text' | 'docx' | 'ocr_pdf' | 'ocr_image'
  pages: number | null
  warnings: string[]
}

export interface DocumentCapabilities {
  accept: string
  max_bytes: number
  max_pages: number
  max_chars: number
  ocr: boolean
}

export interface Source {
  id: Id
  ref: string | null
  kind: 'email' | 'update' | 'tracker_note' | 'tracker_row' | 'document'
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
  external_id: string | null
  channel: string | null
  sender: string | null
  received_at: IsoDateTime | null
  /** Set when the text was extracted from an uploaded file (the file itself is not kept). */
  document?: DocumentInfo | null
  match_status: 'matched' | 'needs_review' | 'unmatched' | null
  superseded?: boolean
}

export interface Readiness {
  status: ReadinessStatus
  final_review_id: Id | null
  signed_off_at: IsoDateTime | null
  signed_off_by: UserRef | null
  reopened_at: IsoDateTime | null
  validated_milestones: string[]
}

export interface Requirement {
  id: Id
  key: string
  title: string
  kind: 'milestone' | 'access'
  applicability: 'required' | 'optional' | 'not_applicable'
  evidence_expectation: string | null
  due_date: IsoDate | null
  assignee_role: ResponsibilityType | null
  status: 'satisfied' | 'pending' | 'not_applicable'
  detail: string | null
  validated_by: UserRef | null
  validated_at: IsoDateTime | null
  review_id: Id | null
  change_reason: string | null
}

export interface Job {
  id: Id
  source_id: Id
  case_id: Id | null
  status: 'queued' | 'running' | 'done' | 'waiting' | 'failed' | 'superseded'
  reason: string
  attempts: number
  max_attempts: number
  outcome_mode: string | null
  last_error: string | null
  run_after: IsoDateTime
  created_at: IsoDateTime
  finished_at: IsoDateTime | null
}

export interface AnalysisRun {
  id: Id
  source_id: Id
  body_sha256: string
  prompt_version: string
  schema_version: string
  model: string
  provider: 'ollama' | 'recorded' | 'groq'
  model_digest: string | null
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
  queue: string | null
  requirement_id: Id | null
  reminded_at: IsoDateTime | null
  escalated_at: IsoDateTime | null
  waiting: boolean
  waiting_reason: string | null
  working_hours: number | null
  waiting_hours: number | null
}

export interface Review {
  id: Id
  case_id: Id
  disposition: ReviewDisposition
  scope: string
  /** null when your view level hides technical assessment notes. */
  rationale: string | null
  observed_stage: Stage | null
  cited_source_ids: Id[]
  task_id: Id | null
  reviewer: UserRef | null
  created_at: IsoDateTime
  milestone_key: string | null
  supersedes_review_id: Id | null
  exception_reason: string | null
  bypassed_criteria: string[]
  policy_version: 'v1' | 'legacy'
  gaps: string[]
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
  tester: UserRef | null
  tested_by: UserRef | null
  tested_at: IsoDateTime | null
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
  topic: string | null
  description: string | null
  applies_to_roles: Role[]
  tags: string[]
  needs_review: boolean
}

export interface TrainingEntry {
  id: Id
  case_id: Id
  kind: 'plan' | 'session' | 'observation'
  title: string
  notes: string | null
  activity_date: IsoDate | null
  cited_source_ids: Id[]
  recorded_by: UserRef | null
  capacity: string
  created_at: IsoDateTime
}

export interface StakeholderAssignment {
  id: Id
  kind: 'case_responsibility' | 'role_assignment'
  user: UserRef | null
  source: 'project_default' | 'case_override' | 'manual' | 'migrated'
  is_primary: boolean
  access_item_id: Id | null
  system: string | null
  assigned_by: UserRef | null
  assigned_at: IsoDateTime | null
  notes: string | null
  also_holds: ResponsibilityType[]
}

export interface Stakeholder {
  responsibility_type: ResponsibilityType
  label: string
  required: boolean
  assignments: StakeholderAssignment[]
}

export interface ResponsibilitiesPayload {
  stakeholders: Stakeholder[]
  ownership_gaps: ResponsibilityType[]
  history: {
    id: Id
    responsibility_type: ResponsibilityType
    user: UserRef | null
    source: string
    assigned_at: IsoDateTime
    assigned_by: UserRef | null
    ended_at: IsoDateTime | null
    ended_by: UserRef | null
    system: string | null
  }[]
  can_assign: boolean
  reason: string | null
  eligible: Partial<Record<ResponsibilityType, UserRef[]>>
  access_items: { id: Id; system: string }[]
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
  training: TrainingEntry[]
  stakeholders: Stakeholder[]
  ownership_gaps: ResponsibilityType[]
  my_responsibilities: ResponsibilityType[]
  view: { level: ViewLevel; restricted: string[] }
  requirements: Requirement[]
  readiness: Readiness | null
  reassessment: { needed: boolean; reasons: string[]; decision_id?: Id }
  historic_sources: Source[]
  jobs?: Record<Id, { status: Job['status']; attempts: number; outcome_mode: string | null; last_error: string | null; updated_at: string }>
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
    can_upload_document: boolean
    can_create_task: boolean
    can_analyze: boolean
    can_review: boolean
    can_edit_access: boolean
    can_confirm_access: boolean
    can_confirm_access_ids: Id[]
    can_assign: boolean
    can_record_training: boolean
    can_patch_case: boolean
    can_run_agent: boolean
    /** Which kinds of first-hand observation the caller may submit on this case. */
    observation_kinds?: ('employee_evidence' | 'manager_check_in')[]
  }
}

export interface AgentProposal {
  id: Id
  kind: 'task' | 'message' | 'access_followup'
  title: string
  body: string
  owner_role: Role | null
  owner_user_id: Id | null
  due_date: IsoDate | null
  cited_source_ids: Id[]
  cited_claim_ids: Id[]
  status: 'open' | 'accepted' | 'dismissed'
  dismiss_reason: string | null
}

export interface AgentRunOut {
  id: Id
  case_id: Id
  status: 'running' | 'completed' | 'failed' | 'unavailable'
  assessment: string
  proposals: AgentProposal[]
  steps: { index: number; tool: string; arguments: Record<string, unknown>; result_summary: string; duration_ms: number }[]
  model: string
  prompt_version: string
  provider: string
  model_digest: string | null
  stale: boolean
  created_at: IsoDateTime
}

export interface QueueInfo {
  key: string
  label: string
  count: number
}

export interface QueuePayload {
  key: string
  label: string
  kind: 'tasks' | 'cases'
  items: (Task & { ref: string; employee: string; readiness: ReadinessStatus })[]
}

export interface TemplateMilestone {
  key: string
  title: string
  kind: 'milestone' | 'access'
  applicability: 'required' | 'optional' | 'not_applicable'
  evidence_expectation: string | null
  due_offset_days: number | null
  assignee_role: ResponsibilityType | null
}

export interface Template {
  id: Id
  key: string
  version: number
  name: string
  movement: 'new_hire' | 'reallocation' | null
  definition: { milestones: TemplateMilestone[] }
  is_current: boolean
  note: string | null
  created_at: IsoDateTime
  created_by: UserRef | null
}

export interface CaseForm {
  projects: { id: Id; name: string; code: string | null }[]
  people: Record<'line_manager' | 'technical_owner' | 'employee', UserRef[]>
  members: UserRef[]
  templates: { key: string; name: string; version: number; movement: string | null }[]
  next_ref: string
}

export interface ImportRow {
  line: number
  employee: string
  external_id: string | null
  ref: string | null
  action: 'create' | 'skip_existing' | 'error' | 'created'
  errors: string[]
  duplicate: string | null
}

export interface MetricBlock {
  n: number
  median: number | null
  p90: number | null
  open: number
  cases: { ref: string; values: number[] }[]
}

export interface Metrics {
  filters: { from: IsoDate | null; to: IsoDate | null; project_id: Id | null; cases_in_scope: number }
  blocker_to_owner_hours: MetricBlock & { open_cases: string[] }
  start_to_signoff_days: MetricBlock & { missing_start: string[] }
  closes_with_unmet_checks: { closes: number; flagged: number; exceptions: number; legacy_unverified: number; share: number | null; cases: string[] }
}

export interface AiStatus {
  state: 'available' | 'busy' | 'unavailable' | 'misconfigured'
  provider: string
  model: string
  digest: string | null
  detail: string | null
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
  type:
    | 'source_received'
    | 'analysis_run'
    | 'finding_raised'
    | 'task_created'
    | 'task_done'
    | 'review_saved'
    | 'training_recorded'
    | 'responsibility_assigned'
    | 'responsibility_ended'
  at: string
  title: string
  actor: string | null
  ref: { entity: string; id: Id }
}

// ---------- Inbox ----------

export interface InboxItem {
  source: Source
  status: 'matched' | 'unmatched' | 'needs_review'
  candidates: { id: Id; ref: string; employee: string }[]
  job: Job | null
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
  readiness: Record<ReadinessStatus, number>
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
  flag_missing_readiness_date: boolean
  allow_closure_exceptions: boolean
  clock_mode: 'as_of' | 'real'
  timezone: string
  working_hours: { start: string; end: string; days: number[] }
  holidays: string[]
  escalation_working_days: number
  required_responsibilities: ResponsibilityType[]
  project_manager_can_assign: boolean
  access_tester_policy: 'employee' | 'designated'
  role_labels: Partial<Record<Role, string>>
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

// ---------- People, roles, projects ----------

export interface RoleInfo {
  code: Role
  default_label: string
  label: string
  scope: string
  purpose: string
  is_responsibility: boolean
  project_assignable: boolean
  active_grants: number
}

export interface Grant {
  id: Id
  user: UserRef | null
  role_code: Role
  role_label: string
  scope_type: 'organization' | 'project' | 'case'
  scope_id: Id | null
  scope_name: string | null
  default_for_cases: boolean
  is_active: boolean
  assigned_by: UserRef | null
  created_at: IsoDateTime
  valid_from: IsoDate | null
  valid_until: IsoDate | null
  revoked_at: IsoDateTime | null
  revoked_by: UserRef | null
}

export interface Member {
  membership_id: Id
  user: { id: Id; name: string; title: string | null; email: string | null }
  status: 'active' | 'suspended' | 'invited'
  joined_at: IsoDateTime | null
  grants: Grant[]
  history: Grant[]
}

export interface ProjectSummary {
  id: Id
  name: string
  code: string | null
  case_count: number
  at_risk: number
  cases_with_gaps: number
  team_size: number
  missing_defaults: ResponsibilityType[]
  my_roles: Role[]
}

export interface ProjectDetail {
  project: { id: Id; name: string; code: string | null }
  team: Grant[]
  history: Grant[]
  cases: CaseRow[]
  knowledge: KnowledgeRef[]
  permissions: { can_manage_team: boolean; is_admin: boolean; reason: string | null }
  eligible: Partial<Record<Role, UserRef[]>>
}

// ---------- Home ----------

export interface HomeSection {
  key: string
  title: string
  description: string
  kind: 'cases' | 'access' | 'notes' | 'audit'
  role: Role
  items: (CaseRow & AccessItem & { text: string; link: string; action: string; case: { id: Id; ref: string; employee: string } } & AuditEvent)[]
}

export interface HomePayload {
  roles: Role[]
  context: Role | null
  totals: { cases: number; needs_attention: number; ownership_gaps: number; my_open_tasks: number; overdue_tasks: number }
  my_tasks: Task[]
  sections: HomeSection[]
}

// ---------- AI presentation ----------

export type AskFocus = 'auto' | 'my_tasks' | 'one_employee' | 'one_project' | 'cross_project' | 'access' | 'training' | 'technical_readiness'
export type AskDetail = 'brief' | 'standard' | 'detailed'
export type AskFormat = 'action_list' | 'status_brief' | 'chronological' | 'stakeholder_report'
export type AskInclude = 'risks' | 'ownership' | 'citations' | 'deadlines' | 'open_questions'

export interface Presentation {
  profile: Role
  profile_label: string
  focus: AskFocus
  detail: AskDetail
  format: AskFormat
  guidance_version: number | null
}

export interface Preferences {
  preferences: { working_role: Role | null; focus: AskFocus; detail: AskDetail; format: AskFormat | null; include: AskInclude[] }
  effective: Presentation & { emphasis: string; include: AskInclude[]; max_citations: number }
  available_roles: Role[]
  profiles: Record<string, { label: string; emphasis: string }>
}

export interface AskAnswer {
  answer: string
  citations: { source_id: Id; claim_id: Id | null; quote: string }[]
  refused: boolean
  mode: AnalysisMode
  model: string | null
  prompt_version: string
  presentation: Presentation | null
}

export interface AskCitation {
  source_id: Id
  claim_id: Id | null
  quote: string
}

export interface GuidanceVersion {
  version: number
  terminology: string
  report_structure: string
  escalation_summary: string
  formatting: string
  context: string
  created_at: IsoDateTime
  created_by: UserRef | null
}

export interface GuidancePayload {
  current: GuidanceVersion | null
  history: GuidanceVersion[]
  can_edit: boolean
  guardrails: string[]
}
