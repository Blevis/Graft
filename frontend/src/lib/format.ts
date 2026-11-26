import type { AccessState, AnalysisMode, ResponsibilityType, ReviewDisposition, Role, Severity, Stage } from './types'

export const DASH = '—'

/** Default display labels. An org may override them (me.role_labels); prefer roleLabel(me, code). */
export const ROLE_LABEL: Record<Role, string> = {
  org_admin: 'Organization Admin',
  pmo_coordinator: 'PMO Coordinator',
  project_manager: 'Project Manager / Additional Manager',
  line_manager: 'Line Manager',
  technical_owner: 'Technical Lead / Technical Owner',
  training_responsible: 'Training Responsible',
  hr_business_partner: 'HR Business Partner',
  access_responsible: 'Access Responsible',
  project_member: 'Project Member',
  employee: 'Employee / New Hire',
  management_viewer: 'Management Viewer',
  auditor: 'Auditor',
}

export const ROLE_ORDER: Role[] = Object.keys(ROLE_LABEL) as Role[]

export const RESPONSIBILITY_ORDER: ResponsibilityType[] = [
  'line_manager',
  'project_manager',
  'technical_owner',
  'training_responsible',
  'hr_business_partner',
  'access_responsible',
]

export function roleLabel(me: { role_labels?: Partial<Record<Role, string>> } | undefined, code: Role | string | null | undefined): string {
  if (!code) return DASH
  return me?.role_labels?.[code as Role] ?? ROLE_LABEL[code as Role] ?? humanize(code)
}

export const SOURCE_LABEL: Record<string, string> = {
  project_default: 'Inherited from project',
  case_override: 'Case override',
  manual: 'Assigned on case',
  migrated: 'Migrated',
}

export const VIEW_LEVEL_LABEL: Record<string, string> = {
  full: 'Case team view',
  employee: 'Your own case',
  summary: 'Summary view (read-only)',
  access_only: 'Access view',
}

export const STAGE_LABEL: Record<Stage, string> = {
  pre_onboarding: 'Pre-onboarding',
  access: 'Access',
  shadowing: 'Shadowing',
  supported_execution: 'Supported execution',
  independent_execution: 'Independent execution',
  validated: 'Validated',
}

export const DISPOSITION_LABEL: Record<ReviewDisposition, string> = {
  keep_open: 'Keep open',
  validate_scope: 'Validated for scope',
  close: 'Closed',
}

export const ACCESS_LABEL: Record<AccessState, string> = {
  requested: 'Requested',
  awaiting_approval: 'Awaiting approval',
  approved: 'Approved',
  not_provisioned: 'Not provisioned',
  active: 'Active (not tested)',
  confirmed_usable: 'Confirmed usable',
}

export const MODE_LABEL: Record<AnalysisMode, string> = {
  live: 'Live AI',
  cached: 'Verified cache',
  replay: 'Recorded example',
  unavailable: 'Analysis unavailable',
}

export const RULE_LABEL: Record<string, string> = {
  CLOSURE_CONFLICT: 'Closure conflict',
  ACCESS_NOT_CONFIRMED: 'Access not confirmed',
  UNANSWERED_REQUEST: 'Unanswered request',
  STALE_TRACKER: 'Stale tracker',
  MISSING_PROJECT: 'Missing project',
  MISSING_MANAGER: 'Missing manager',
  MISSING_TECH_OWNER: 'Missing technical owner',
  MISSING_READINESS_DATE: 'Missing readiness date',
}

export const SCOPE_LABEL: Record<string, string> = {
  initial_training: 'Initial training',
  knowledge_transfer: 'KT stage',
  standard_requests: 'Standard requests',
  complex_scenarios: 'Complex scenarios',
  overall_independence: 'Overall independence',
  onboarding_closure: 'Onboarding closure',
  technical_readiness_report: 'Readiness (reported)',
  access: 'Access',
}

export const humanize = (s: string) => s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const SEVERITY_CLASS: Record<Severity, string> = {
  high: 'bg-red-50 text-red-700 ring-red-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  low: 'bg-slate-50 text-slate-700 ring-slate-200',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function fmtDate(d: string | null | undefined): string {
  if (!d) return DASH
  const [y, m, day] = d.slice(0, 10).split('-')
  return `${Number(day)} ${MONTHS[Number(m) - 1]} ${y}`
}

export function fmtDateTime(d: string | null | undefined): string {
  if (!d) return DASH
  if (d.length <= 10) return fmtDate(d)
  const dt = new Date(d)
  return `${dt.getDate()} ${MONTHS[dt.getMonth()]} ${dt.getFullYear()} ${dt.toTimeString().slice(0, 5)}`
}

export const ageLabel = (days: number | null) => (days === null ? DASH : days === 0 ? 'today' : `${days}d ago`)
