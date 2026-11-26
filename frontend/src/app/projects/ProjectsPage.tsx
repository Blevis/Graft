import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, UserPlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorState, Loading, NativeSelect, PageHeader, Pill, Section } from '@/components/common'
import { ApiError, useAddProjectMember, useMe, usePatchProjectMember, useProject, useProjects, useRemoveProjectMember } from '@/lib/api'
import { DASH, fmtDate, roleLabel } from '@/lib/format'
import type { Grant, Role } from '@/lib/types'
import CaseTable from '../cases/CaseTable'

const ROSTER_ORDER: Role[] = [
  'project_manager', 'technical_owner', 'training_responsible', 'access_responsible', 'hr_business_partner',
  'project_member', 'management_viewer', 'auditor',
]
const DEFAULTABLE = new Set<Role>(['project_manager', 'technical_owner', 'training_responsible', 'access_responsible', 'hr_business_partner'])

export default function ProjectsPage() {
  const me = useMe()
  const q = useProjects()
  const navigate = useNavigate()
  return (
    <div>
      <PageHeader
        title="Projects"
        description="Each project's team and the defaults its cases inherit. A case can override a default without changing the project."
      />
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} />}
      {q.data && (
        <div className="rounded-lg border bg-background">
          {q.data.length === 0 ? (
            <div className="px-4">
              <Empty>You are not on any project team.</Empty>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Cases</TableHead>
                  <TableHead>At risk</TableHead>
                  <TableHead>Cases with ownership gaps</TableHead>
                  <TableHead>Team</TableHead>
                  <TableHead>Missing project defaults</TableHead>
                  <TableHead>My roles here</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.map((p) => (
                  <TableRow key={p.id} className="cursor-pointer" onClick={() => navigate(`/app/projects/${p.id}`)}>
                    <TableCell className="font-medium">
                      {p.name} {p.code && <span className="font-mono text-xs text-muted-foreground">{p.code}</span>}
                    </TableCell>
                    <TableCell>{p.case_count}</TableCell>
                    <TableCell className={p.at_risk ? 'text-red-700' : ''}>{p.at_risk}</TableCell>
                    <TableCell className={p.cases_with_gaps ? 'text-amber-700' : ''}>{p.cases_with_gaps}</TableCell>
                    <TableCell>{p.team_size}</TableCell>
                    <TableCell className="text-xs">
                      {p.missing_defaults.length ? p.missing_defaults.map((r) => roleLabel(me.data, r)).join(', ') : DASH}
                    </TableCell>
                    <TableCell className="text-xs">{p.my_roles.map((r) => roleLabel(me.data, r)).join(', ') || DASH}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </div>
  )
}

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const me = useMe()
  const q = useProject(projectId)
  const add = useAddProjectMember(projectId)
  const patch = usePatchProjectMember(projectId)
  const remove = useRemoveProjectMember(projectId)
  const [role, setRole] = useState<Role>('technical_owner')
  const [user, setUser] = useState('')
  const [asDefault, setAsDefault] = useState(false)

  if (q.isLoading) return <Loading />
  if (q.error instanceof ApiError && q.error.status === 404) return <ErrorState error={new Error('No project that you have access to.')} />
  if (q.error) return <ErrorState error={q.error} />
  const d = q.data!
  const can = d.permissions.can_manage_team
  const byRole = new Map<Role, Grant[]>()
  for (const g of d.team) byRole.set(g.role_code, [...(byRole.get(g.role_code) ?? []), g])
  const holders = new Map<string, Role[]>()
  for (const g of d.team) if (g.user) holders.set(g.user.id, [...(holders.get(g.user.id) ?? []), g.role_code])

  return (
    <div className="space-y-4">
      <Link to="/app/projects" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-4" /> Projects
      </Link>
      <PageHeader title={`${d.project.name}${d.project.code ? ` · ${d.project.code}` : ''}`} description="Project team, defaults inherited by its cases, and the cases themselves." />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title={`Cases (${d.cases.length})`}>
            <CaseTable rows={d.cases} compact />
          </Section>
          <Section title="Knowledge references">
            {d.knowledge.length === 0 ? (
              <Empty>No documentation location recorded for this project.</Empty>
            ) : (
              <ul className="divide-y text-sm">
                {d.knowledge.map((k) => (
                  <li key={k.id} className="py-1.5">
                    <div className="font-medium">{k.title}</div>
                    <div className="font-mono text-xs">{k.location}</div>
                    <div className="text-xs text-muted-foreground">
                      Verified {fmtDate(k.last_verified)}
                      {k.needs_review && ' · needs re-verification'}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
        <div className="space-y-4">
          <Section title="Team">
            <ul className="divide-y text-sm">
              {ROSTER_ORDER.filter((r) => byRole.has(r) || DEFAULTABLE.has(r)).map((r) => (
                <li key={r} className="py-2">
                  <div className="text-xs font-medium text-muted-foreground">{roleLabel(me.data, r)}</div>
                  {(byRole.get(r) ?? []).length === 0 ? (
                    <div className="text-muted-foreground">{DEFAULTABLE.has(r) ? 'Nobody on this project' : DASH}</div>
                  ) : (
                    byRole.get(r)!.map((g) => (
                      <div key={g.id} className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        <span className="font-medium">{g.user?.name}</span>
                        {g.default_for_cases && <Pill className="bg-sky-50 text-sky-800 ring-sky-200">Default for cases</Pill>}
                        {(holders.get(g.user?.id ?? '') ?? []).length > 1 && (
                          <span className="text-xs text-muted-foreground">
                            also {(holders.get(g.user!.id) ?? []).filter((x) => x !== r).map((x) => roleLabel(me.data, x)).join(', ')}
                          </span>
                        )}
                        {can && DEFAULTABLE.has(r) && (
                          <button
                            className="text-xs text-primary hover:underline"
                            onClick={() =>
                              patch.mutate({ id: g.id, default_for_cases: !g.default_for_cases }, { onError: (e) => toast.error(e.message) })
                            }
                          >
                            {g.default_for_cases ? 'Unset default' : 'Make default'}
                          </button>
                        )}
                        {can && (
                          <button
                            title="Remove from team (kept in history)"
                            className="text-muted-foreground hover:text-red-700"
                            onClick={() =>
                              window.confirm(`Remove ${g.user?.name} as ${roleLabel(me.data, r)}?`) &&
                              remove.mutate(g.id, { onError: (e) => toast.error(e.message) })
                            }
                          >
                            <X className="size-3.5" />
                          </button>
                        )}
                        <div className="w-full text-[11px] text-muted-foreground">
                          granted by {g.assigned_by?.name ?? 'seed'} · {fmtDate(g.created_at)}
                        </div>
                      </div>
                    ))
                  )}
                </li>
              ))}
            </ul>
            {can ? (
              <form
                className="mt-3 space-y-2 border-t pt-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  add.mutate(
                    { user_id: user, role_code: role, default_for_cases: asDefault && DEFAULTABLE.has(role) },
                    { onSuccess: () => { toast.success('Added to team'); setUser('') }, onError: (err) => toast.error(err.message) },
                  )
                }}
              >
                <div className="text-xs font-medium">Add to team</div>
                <NativeSelect value={role} onChange={(e) => { setRole(e.target.value as Role); setUser('') }}>
                  {ROSTER_ORDER.map((r) => (
                    <option key={r} value={r}>{roleLabel(me.data, r)}</option>
                  ))}
                </NativeSelect>
                <NativeSelect value={user} onChange={(e) => setUser(e.target.value)}>
                  <option value="">Choose a person…</option>
                  {(d.eligible[role] ?? []).map((u) => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </NativeSelect>
                {!d.permissions.is_admin && (
                  <p className="text-[11px] text-muted-foreground">Only people who already hold this role in the organization are listed.</p>
                )}
                {DEFAULTABLE.has(role) && (
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} />
                    Default for this project's cases
                  </label>
                )}
                <Button size="sm" type="submit" disabled={!user || add.isPending}>
                  <UserPlus /> Add
                </Button>
              </form>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">{d.permissions.reason}</p>
            )}
          </Section>
          {d.history.length > 0 && (
            <Section title="Team history">
              <ul className="space-y-1 text-xs">
                {d.history.map((g) => (
                  <li key={g.id}>
                    {g.user?.name} · {roleLabel(me.data, g.role_code)} · removed {fmtDate(g.revoked_at)}
                    {g.revoked_by ? ` by ${g.revoked_by.name}` : ''}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
