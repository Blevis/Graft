// Typed fetch client + TanStack Query hooks. Every mutation refetches from the API (no optimistic state).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  AccessItem, AccessState, AnalyzeResult, AuditEvent, CaseDetail, CaseRow, CaseView, DemoAccount, InboxItem,
  InboxPost, Insights, KnowledgeRef, Me, Notification, OrgSettings, OrgUser, Review, ReviewDisposition, Stage, Task,
  TaskSuggestion, TimelineEvent, Role,
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
export const useAudit = (enabled: boolean) =>
  useQuery({ queryKey: ['audit'], queryFn: () => api.get<AuditEvent[]>('/audit?limit=100'), enabled })
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
