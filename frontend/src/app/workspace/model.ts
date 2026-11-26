import seed from './snapshot.json'
import { ACCESS_LABEL, DISPOSITION_LABEL, humanize, STAGE_LABEL } from '@/lib/format'
import type { AccessState, CaseDetail, CaseRow, KnowledgeRef, Task } from '@/lib/types'

export interface Person {
  ref: string
  name: string
  project: string
  status: string
  movement: string
  stage: string
  flags: string[]
  review: string
}
export interface Requirement {
  system: string
  state: AccessState
  owner: string
  date: string
  ref: string
}
export interface Report {
  id: string
  title: string
  author: string
  date: string
  body: string
}
export interface Action {
  title: string
  owner: string
  ref: string
  date: string
  done: boolean
}
export interface Resource {
  title: string
  detail: string
  category: string
  location?: string
}
export interface Dataset {
  people: Person[]
  access: Requirement[]
  reports: Report[]
  tasks: Action[]
  resources: Resource[]
  manager: string
  start: string
  technicalOwner: string
  review: string
  training: string[]
}
export const unknown = 'Unconfirmed'
const flags: Record<string, string[]> = {
  'ONB-002': ['Confirm usable access'],
  'ONB-003': ['Confirm project assignment'],
  'ONB-004': ['Assign a line manager'],
  'ONB-005': ['Reconcile conflicting assessments', 'Evaluate two complex scenarios'],
  'ONB-007': ['Refresh the stale tracker update'],
  'ONB-008': ['Identify the blocker'],
  'ONB-009': ['Confirm project, KT owner and target date'],
  'ONB-010': ['Schedule a final review'],
}
export const samplePeople: Person[] = seed.cases.map((c) => ({
  ref: c.case,
  name: c.employee,
  project: c.project ?? unknown,
  status: c.status,
  movement: c.movement,
  stage: 'Unreviewed',
  flags: flags[c.case] ?? [],
  review: 'No signed decision',
}))
const reportCases = ['ONB-002', 'ONB-002', 'ONB-005', 'ONB-005', 'ONB-009', 'ONB-010', 'ONB-007', '']
export const sampleAccess: Requirement[] = [
  { system: 'Nova VPN', state: 'active', owner: 'Employee tester', date: '07 Oct 2026', ref: 'ONB-002' },
  {
    system: 'Orion Portal',
    state: 'awaiting_approval',
    owner: 'Application owner',
    date: '07 Oct 2026',
    ref: 'ONB-002',
  },
  {
    system: 'Helix Service Desk',
    state: 'not_provisioned',
    owner: 'IT access support',
    date: '07 Oct 2026',
    ref: 'ONB-002',
  },
]
export const sampleTasks: Action[] = [
  ['Review conflicting reports', 'Technical lead', 'ONB-005', '2026-10-19'],
  ['Follow up on access', 'Application owner', 'ONB-002', '2026-10-20'],
  ['Confirm case ownership', 'PMO coordinator', 'ONB-004', '2026-10-21'],
  ['Request a status update', 'Line manager', 'ONB-007', '2026-10-22'],
  ['Plan the final review', 'Technical lead', 'ONB-010', '2026-10-23'],
  ['Confirm project and KT owner', 'PMO coordinator', 'ONB-009', ''],
].map(([title, owner, ref, date]) => ({ title, owner, ref, date, done: false }))
const categories = [
  'Project runbooks',
  'KT guides',
  'Access guides',
  'Mentors',
  'Practical scenarios',
  'Evidence standards',
]
export const sampleResources: Resource[] = categories.map((category, i) => ({
  title: category,
  category,
  detail: [
    'Project-owned procedures',
    'Learning material by project',
    'Setup and usability checks',
    'People responsible for KT',
    'Exercises for observed work',
    'Submission and review guidance',
  ][i],
}))
export function sampleData(ref: string): Dataset {
  const c = seed.cases.find((p) => p.case === ref)
  return {
    people: samplePeople,
    access: sampleAccess,
    tasks: sampleTasks,
    resources: sampleResources,
    manager: c?.manager ?? unknown,
    start: c?.start ?? unknown,
    technicalOwner: unknown,
    review: 'No signed decision',
    training: [],
    reports: seed.evidence.flatMap((s, i) =>
      reportCases[i] === ref
        ? [
            {
              id: s.id,
              title: s.title,
              author: s.from ?? 'Employee update',
              date: s.date ?? 'Date unknown',
              body: s.body,
            },
          ]
        : [],
    ),
  }
}
export function fromCase(c: CaseRow): Person {
  return {
    ref: c.ref,
    name: c.employee,
    project: c.project ?? unknown,
    status: c.tracker_status ?? 'Not reported',
    movement: c.movement ? humanize(c.movement) : unknown,
    stage: c.stage ? STAGE_LABEL[c.stage] : 'Unreviewed',
    flags: c.reasons.map((r) => r.message),
    review: c.review_state === 'none' ? 'No signed decision' : DISPOSITION_LABEL[c.review_state],
  }
}
export function fromLive(
  people: Person[],
  d: CaseDetail | undefined,
  tasks: Task[],
  knowledge: KnowledgeRef[],
): Dataset {
  return {
    people,
    access: (d?.access_items ?? []).map((a) => ({
      system: a.system,
      state: a.state,
      owner: a.owner_role ?? unknown,
      date: a.requested_at ?? 'Date unknown',
      ref: d!.case.ref,
    })),
    reports: (d?.sources ?? []).map((s) => ({
      id: s.ref ?? s.id.slice(0, 8),
      title: s.title ?? humanize(s.kind),
      author: s.author_role ?? 'Unspecified author',
      date: s.date ?? 'Date unknown',
      body: s.body,
    })),
    tasks: tasks.map((t) => ({
      title: t.title,
      owner: t.owner_user?.name ?? (t.owner_role && humanize(t.owner_role)) ?? unknown,
      ref: t.case?.ref ?? '',
      date: t.due_date ?? '',
      done: t.status === 'done',
    })),
    resources: knowledge.map((k) => ({
      title: k.title,
      category: k.topic ?? 'Resources',
      detail: k.description ?? k.project?.name ?? 'Project resource',
      location: k.location,
    })),
    manager: d?.case.manager ?? unknown,
    start: d?.case.start_date ?? unknown,
    technicalOwner: d?.case.tech_owner?.name ?? unknown,
    review: d?.latest_review ? DISPOSITION_LABEL[d.latest_review.disposition] : 'No signed decision',
    training: d?.training.map((t) => t.title) ?? [],
  }
}
export const accessLabel = (a: Requirement) => ACCESS_LABEL[a.state]
export const initials = (value: string) =>
  value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0])
    .join('')
    .toUpperCase()
export function defaultCase(id: number) {
  if (id === 11) return 'ONB-010'
  if ([4, 15, 16, 17, 18, 21, 22].includes(id)) return 'ONB-005'
  return 'ONB-002'
}
