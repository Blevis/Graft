import type { AccessState, AnalysisMode, ReviewDisposition, Role, Severity, Stage } from './types'

export const DASH = '—'

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  pmo_coordinator: 'PMO Coordinator',
  technical_owner: 'Technical Owner',
  line_manager: 'Line Manager',
  employee: 'Employee',
  viewer: 'Management',
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
