// Typed fetch client + TanStack Query hooks. Every mutation refetches from the API (no optimistic state).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  AccessItem, AccessState, AgentRunOut, AiStatus, AnalyzeResult, AskAnswer, CaseForm, ImportRow, Job, Metrics,
  QueueInfo, QueuePayload, Source, Template, AskDetail, AskFocus, AskFormat, AskInclude, AuditEvent, CaseDetail,
  CaseRow, CaseView, DemoAccount, Grant, GuidancePayload, HomePayload, InboxItem, InboxPost, Insights, KnowledgeRef, Me,
  Member, Notification, OrgSettings, OrgUser, Preferences, ProjectDetail, ProjectSummary, ResponsibilitiesPayload,
  ResponsibilityType, Review, ReviewDisposition, Role, RoleInfo, Stage, Task, TaskSuggestion, TimelineEvent,
  TrainingEntry, DocumentCapabilities, DocumentInfo,
} from './types'

export class ApiError extends Error {
  status: number
  /** Structured details when the server explains a refusal (e.g. unmet sign-off criteria). */
  unmet: string[]
  constructor(status: number, message: string, unmet: string[] = []) {
    super(message)
    this.status = status
    this.unmet = unmet
  }
}

function csrfToken(): string | null {
  const m = document.cookie.match(/(?:^|; )graft_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const form = body instanceof FormData
  if (body !== undefined && !form) headers['Content-Type'] = 'application/json' // the browser sets the multipart boundary
  const token = csrfToken()
  if (method !== 'GET' && token) headers['X-CSRF-Token'] = token
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : form ? (body as FormData) : JSON.stringify(body),
  })
  if (!res.ok) {
    let msg = res.statusText
    let unmet: string[] = []
    try {
      const j = await res.json()
      const d = j.detail
      if (typeof d === 'string') msg = d
      else if (Array.isArray(d)) msg = d.map((x: { msg: string }) => x.msg).join('; ')
      else if (d && typeof d === 'object') {
        msg = d.message ?? msg
        unmet = Array.isArray(d.unmet) ? d.unmet : []
        if (unmet.length) msg = `${msg}: ${unmet.join(', ')}`
      }
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg, unmet)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T,>(p: string) => request<T>('GET', p),
  post: <T,>(p: string, b?: unknown) => request<T>('POST', p, b ?? {}),
  patch: <T,>(p: string, b: unknown) => request<T>('PATCH', p, b),
  del: <T,>(p: string) => request<T>('DELETE', p),
}

// ---------- Queries ----------

export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/auth/me'), retry: false, staleTime: 60_000 })
export const useDemoAccounts = () => useQuery({ queryKey: ['demo-accounts'], queryFn: () => api.get<DemoAccount[]>('/auth/demo-accounts') })
export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => api.get<OrgUser[]>('/users') })
export const useCases = (view: CaseView, q?: string) =>
  useQuery({
    queryKey: ['cases', view, q ?? ''],
    queryFn: () => api.get<CaseRow[]>(`/cases?view=${view}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
  })
export const useCase = (id: string) => useQuery({ queryKey: ['case', id], queryFn: () => api.get<CaseDetail>(`/cases/${id}`) })
export const useTimeline = (id: string) =>
  useQuery({ queryKey: ['timeline', id], queryFn: () => api.get<TimelineEvent[]>(`/cases/${id}/timeline`) })
export const useTasks = (mine: boolean, status: 'open' | 'done' | 'all') =>
  useQuery({
    queryKey: ['tasks', mine, status],
    queryFn: () => api.get<Task[]>(`/tasks?mine=${mine ? 1 : 0}&status=${status}`),
  })
export const useInbox = () => useQuery({ queryKey: ['inbox'], queryFn: () => api.get<InboxItem[]>('/inbox') })
export const useKnowledge = () => useQuery({ queryKey: ['knowledge'], queryFn: () => api.get<KnowledgeRef[]>('/knowledge') })
export const useInsights = () => useQuery({ queryKey: ['insights'], queryFn: () => api.get<Insights>('/insights') })
export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: () => api.get<OrgSettings>('/settings') })
export const useAudit = (enabled: boolean, entity?: string) =>
  useQuery({
    queryKey: ['audit', entity ?? ''],
    queryFn: () => api.get<AuditEvent[]>(`/audit?limit=100${entity ? `&entity=${entity}` : ''}`),
    enabled,
  })
export const useHome = (context: string | null) =>
  useQuery({ queryKey: ['home', context ?? ''], queryFn: () => api.get<HomePayload>(`/home${context ? `?context=${context}` : ''}`) })
export const useProjects = () => useQuery({ queryKey: ['projects'], queryFn: () => api.get<ProjectSummary[]>('/projects') })
export const useProject = (id: string) => useQuery({ queryKey: ['project', id], queryFn: () => api.get<ProjectDetail>(`/projects/${id}`) })
export const useMembers = (enabled: boolean) =>
  useQuery({ queryKey: ['members'], queryFn: () => api.get<{ members: Member[]; can_manage: boolean }>('/org/members'), enabled })
export const useRoles = () => useQuery({ queryKey: ['roles'], queryFn: () => api.get<RoleInfo[]>('/org/roles') })
export const useResponsibilities = (caseId: string) =>
  useQuery({ queryKey: ['responsibilities', caseId], queryFn: () => api.get<ResponsibilitiesPayload>(`/cases/${caseId}/responsibilities`) })
export const usePreferences = () => useQuery({ queryKey: ['preferences'], queryFn: () => api.get<Preferences>('/me/preferences') })
export const useGuidance = () => useQuery({ queryKey: ['ai-guidance'], queryFn: () => api.get<GuidancePayload>('/settings/ai-guidance') })
export const useNotifications = () =>
  useQuery({ queryKey: ['notifications'], queryFn: () => api.get<Notification[]>('/notifications'), refetchInterval: 30_000 })

// ---------- Mutations ----------

function useInvalidateAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries()
}

export function usePasswordLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: { email: string; password: string }) => api.post('/auth/login', b),
    onSuccess: () => qc.clear(),
  })
}

export const useDemoPassword = (enabled: boolean) =>
  useQuery({ queryKey: ['demo-password'], queryFn: () => api.get<{ password: string }>('/auth/demo-password'), enabled })

export const useDocumentCapabilities = () =>
  useQuery({ queryKey: ['document-capabilities'], queryFn: () => api.get<DocumentCapabilities>('/documents/capabilities'), staleTime: Infinity })

export interface DocumentUploadResult {
  source: Pick<Source, 'id' | 'title' | 'kind' | 'date'>
  document: DocumentInfo
  job: Job | null
  text: string
}

export function useUploadDocument(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { file: File; title?: string; date?: string }) => {
      const f = new FormData()
      f.append('file', b.file)
      if (b.title?.trim()) f.append('title', b.title.trim())
      if (b.date) f.append('date', b.date)
      return api.post<DocumentUploadResult>(`/cases/${caseId}/documents`, f)
    },
    onSuccess: inv,
  })
}

export function useUploadInboxDocument() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { file: File; title?: string; author_role: string; recipient_role?: string; date: string }) => {
      const f = new FormData()
      f.append('file', b.file)
      f.append('author_role', b.author_role)
      f.append('date', b.date)
      if (b.title?.trim()) f.append('title', b.title.trim())
      if (b.recipient_role?.trim()) f.append('recipient_role', b.recipient_role.trim())
      return api.post<InboxItem & { document: DocumentInfo }>('/inbox/documents', f)
    },
    onSuccess: inv,
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => api.post('/auth/logout'), onSuccess: () => qc.clear() })
}

export function useAnalyze(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => api.post<AnalyzeResult>(`/cases/${caseId}/analyze`), onSuccess: inv })
}

export function useSuggestTask(caseId: string) {
  return useMutation({ mutationFn: () => api.post<TaskSuggestion>(`/cases/${caseId}/suggest-task`) })
}

export interface TaskInput {
  proposal_id?: string | null
  route?: boolean
  requirement_id?: string | null
  title: string
  owner_user_id?: string | null
  owner_role?: Role | null
  due_date?: string | null
  finding_id?: string | null
  cited_source_ids: string[]
  origin: 'manual' | 'ai_suggested_edited'
}

export function useCreateTask(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: TaskInput) => api.post<Task>(`/cases/${caseId}/tasks`, b), onSuccess: inv })
}

export function useSetTaskStatus() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'open' | 'done' }) => api.patch<Task>(`/tasks/${id}`, { status }),
    onSuccess: inv,
  })
}

export interface ReviewInput {
  disposition: ReviewDisposition
  scope: string
  rationale: string
  observed_stage: Stage | null
  cited_source_ids: string[]
  task_id: string | null
  milestone_key?: string | null
  exception_reason?: string | null
}

export function useCreateReview(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: ReviewInput) => api.post<Review>(`/cases/${caseId}/reviews`, b), onSuccess: inv })
}

export function usePostInbox() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: InboxPost) => api.post<InboxItem & { analysis_outcome: { mode: string; note: string | null } | null }>('/inbox', b),
    onSuccess: inv,
  })
}

export function useLinkSource() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ sourceId, caseId }: { sourceId: string; caseId: string }) =>
      api.post<InboxItem>(`/inbox/${sourceId}/link`, { case_id: caseId }),
    onSuccess: inv,
  })
}

export function useUpdateAccess() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, state }: { id: string; state: AccessState }) => api.patch<AccessItem>(`/access-items/${id}`, { state }),
    onSuccess: inv,
  })
}

export function useCreateAccess(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { system: string; state: AccessState; requested_at: string | null; owner_role: string | null }) =>
      api.post<AccessItem>(`/cases/${caseId}/access-items`, b),
    onSuccess: inv,
  })
}

export function usePatchSettings() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: Partial<OrgSettings>) => api.patch<OrgSettings>('/settings', b), onSuccess: inv })
}

export function useReadAllNotifications() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => api.post('/notifications/read-all'), onSuccess: inv })
}

export function useResetDemo() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => api.post<{ message: string }>('/admin/reset'), onSuccess: () => qc.clear() })
}

// ---------- People, roles, responsibilities ----------

export function useAddMember() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: { name: string; title: string | null }) => api.post('/org/members', b), onSuccess: inv })
}

export function useSetMemberStatus() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: 'active' | 'suspended' }) => api.patch(`/org/members/${userId}`, { status }),
    onSuccess: inv,
  })
}

export interface GrantInput {
  user_id: string
  role_code: Role
  scope_type: 'organization' | 'project'
  scope_id: string | null
  default_for_cases: boolean
}

export function useGrantRole() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: GrantInput) => api.post<Grant>('/org/role-assignments', b), onSuccess: inv })
}

export function useRevokeRole() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (id: string) => api.del<Grant>(`/org/role-assignments/${id}`), onSuccess: inv })
}

export function useSaveRoleLabels() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (labels: Record<string, string>) => api.patch<RoleInfo[]>('/org/roles/labels', { labels }), onSuccess: inv })
}

export function useAddProjectMember(projectId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { user_id: string; role_code: Role; default_for_cases: boolean }) => api.post<Grant>(`/projects/${projectId}/assignments`, b),
    onSuccess: inv,
  })
}

export function usePatchProjectMember(projectId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, default_for_cases }: { id: string; default_for_cases: boolean }) =>
      api.patch<Grant>(`/projects/${projectId}/assignments/${id}`, { default_for_cases }),
    onSuccess: inv,
  })
}

export function useRemoveProjectMember(projectId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (id: string) => api.del<Grant>(`/projects/${projectId}/assignments/${id}`), onSuccess: inv })
}

export function useAssignResponsibility(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { user_id: string; responsibility_type: ResponsibilityType; access_item_id?: string | null; notes?: string | null }) =>
      api.post<ResponsibilitiesPayload>(`/cases/${caseId}/responsibilities`, b),
    onSuccess: inv,
  })
}

export function useEndResponsibility(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (id: string) => api.del<ResponsibilitiesPayload>(`/cases/${caseId}/responsibilities/${id}`), onSuccess: inv })
}

export function useRecordTraining(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { kind: TrainingEntry['kind']; title: string; notes: string; activity_date: string | null }) =>
      api.post<TrainingEntry>(`/cases/${caseId}/training`, b),
    onSuccess: inv,
  })
}

// ---------- AI presentation ----------

export function usePatchPreferences() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: Partial<{ working_role: Role | null; focus: AskFocus; detail: AskDetail; format: AskFormat | null; include: AskInclude[] }>) =>
      api.patch<Preferences>('/me/preferences', b),
    onSuccess: inv,
  })
}

export function useSaveGuidance() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { terminology: string; report_structure: string; escalation_summary: string; formatting: string; context: string }) =>
      api.patch<GuidancePayload>('/settings/ai-guidance', b),
    onSuccess: inv,
  })
}

export function useAsk() {
  return useMutation({
    mutationFn: (b: { question: string; case_id?: string | null; focus?: AskFocus; detail?: AskDetail; format?: AskFormat }) =>
      api.post<AskAnswer>('/ask', b),
  })
}

// ---------- Workflow (cases, templates, queues) ----------

export const useCaseForm = (enabled = true) =>
  useQuery({ queryKey: ['case-form'], queryFn: () => api.get<CaseForm>('/cases-meta/form'), enabled })
export const useTemplates = () =>
  useQuery({ queryKey: ['templates'], queryFn: () => api.get<{ templates: Template[]; can_edit: boolean }>('/templates') })
export const useQueues = () => useQuery({ queryKey: ['queues'], queryFn: () => api.get<QueueInfo[]>('/queues') })
export const useQueue = (key: string) =>
  useQuery({ queryKey: ['queue', key], queryFn: () => api.get<QueuePayload>(`/queues/${key}`) })
export const useTaskHistory = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: ['task-history', id],
    enabled,
    queryFn: () =>
      api.get<{
        assignments: { action: string; from: { name: string } | null; to: { name: string } | null; to_role: string | null; queue: string | null; reason: string | null; by: { name: string } | null; at: string }[]
        pauses: { reason: string; paused_at: string; resumed_at: string | null; by: { name: string } | null }[]
      }>(`/tasks/${id}/history`),
  })
export const useMetrics = (params: { start?: string; end?: string; project_id?: string }) =>
  useQuery({
    queryKey: ['metrics', params],
    queryFn: () => api.get<Metrics>(`/metrics?${new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])}`),
  })
export const useAgentRuns = (caseId: string, enabled: boolean) =>
  useQuery({ queryKey: ['agent-runs', caseId], enabled, queryFn: () => api.get<AgentRunOut[]>(`/cases/${caseId}/agent-runs`) })
export const useAiStatus = () => useQuery({ queryKey: ['ai-status'], queryFn: () => api.get<AiStatus>('/ai/status'), staleTime: 30_000 })
export const useSource = (id: string | null) =>
  useQuery({ queryKey: ['source', id], enabled: !!id, queryFn: () => api.get<Source & { case: { id: string; ref: string; employee: string } | null }>(`/sources/${id}`) })
export const useAuthConfig = () =>
  useQuery({ queryKey: ['auth-config'], queryFn: () => api.get<{ auth_mode: 'demo' | 'oidc'; demo_mode: boolean; password_login: boolean; oidc_login_url: string | null }>('/auth/config') })

export interface CaseInput {
  employee: string
  movement: 'new_hire' | 'reallocation'
  start_date: string | null
  ref?: string | null
  external_id?: string | null
  project_id?: string | null
  employee_user_id?: string | null
  line_manager_user_id?: string | null
  technical_owner_user_id?: string | null
  template_key?: string | null
  exact_role?: string | null
  expected_readiness_date?: string | null
}

export function useCreateCase() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: CaseInput) => api.post<CaseDetail>('/cases', b), onSuccess: inv })
}

export function usePatchCase(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: Partial<CaseInput>) => api.patch<CaseDetail>(`/cases/${caseId}`, b), onSuccess: inv })
}

export function useImportPreview() {
  return useMutation({
    mutationFn: (csv: string) => api.post<{ rows: ImportRow[]; summary: Record<string, number> }>('/cases/import/preview', { csv }),
  })
}

export function useImportCommit() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (csv: string) => api.post<{ rows: ImportRow[]; created: string[] }>('/cases/import', { csv }), onSuccess: inv })
}

export function useAddTemplateVersion(key: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { name: string; definition: Template['definition']; note: string | null }) => api.post<Template>(`/templates/${key}/versions`, b),
    onSuccess: inv,
  })
}

export function usePatchRequirement(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, ...b }: { id: string; applicability?: string; due_date?: string | null; reason: string }) =>
      api.patch<CaseDetail>(`/cases/${caseId}/requirements/${id}`, b),
    onSuccess: inv,
  })
}

export function useApplyTemplate(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (template_key: string) => api.post<CaseDetail>(`/cases/${caseId}/apply-template`, { template_key, create_tasks: true }), onSuccess: inv })
}

export function useTaskAction() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, action, body }: { id: string; action: 'claim' | 'pause' | 'resume' | 'reassign'; body?: unknown }) =>
      api.post<Task>(`/tasks/${id}/${action}`, body ?? {}),
    onSuccess: inv,
  })
}

export function useSubmitSource(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: { title: string; body: string; kind: 'update' | 'email' | 'tracker_note' }) =>
      api.post<{ source: Source; job: Job | null }>(`/cases/${caseId}/sources`, b),
    onSuccess: inv,
  })
}

export function useRunAgent(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => api.post<AgentRunOut>(`/cases/${caseId}/agent-runs`), onSuccess: inv })
}

export function useDismissProposal() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: ({ id, reason }: { id: string; reason: string }) => api.post(`/agent-proposals/${id}/dismiss`, { reason }), onSuccess: inv })
}

// ---------- Role workspace ----------

/** Employee evidence and manager check-ins from the role workspace. Both are stored verbatim through the same
 * evidence-submission route as the case page; the server decides who may submit (permissions.observation_kinds). */
export function usePostObservation(caseId: string) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (body: { kind: 'employee_evidence' | 'manager_check_in'; title: string; body: string }) =>
      api.post<{ source: Source; job: Job | null }>(`/cases/${caseId}/sources`, { title: body.title, body: body.body, kind: 'update' }),
    onSuccess: inv,
  })
}
