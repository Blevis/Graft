// Typed fetch client + TanStack Query hooks. Every mutation refetches from the API (no optimistic state).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  AccessItem, AccessState, AnalyzeResult, AskAnswer, AskDetail, AskFocus, AskFormat, AskInclude, AuditEvent, CaseDetail,
  CaseRow, CaseView, DemoAccount, Grant, GuidancePayload, HomePayload, InboxItem, InboxPost, Insights, KnowledgeRef, Me,
  Member, Notification, OrgSettings, OrgUser, Preferences, ProjectDetail, ProjectSummary, ResponsibilitiesPayload,
  ResponsibilityType, Review, ReviewDisposition, Role, RoleInfo, Stage, Task, TaskSuggestion, TimelineEvent,
  TrainingEntry,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join('; ') : msg
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg)
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

export function useDemoLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (user_id: string) => api.post('/auth/demo-login', { user_id }),
    onSuccess: () => qc.clear(),
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
