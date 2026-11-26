import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Folder, UserPlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Empty, ErrorState, Loading, NativeSelect, PageHeader, Pill, Section, StatStrip, StatTile } from '@/components/common'
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
  const list = q.data ?? []
  return (
    <div>
      <PageHeader
        eyebrow="Portfolio"
        title="Projects"
        description="Each project's team and the defaults its cases inherit. A case can override a default without changing the project."
      />
      {q.isLoading && <Loading />}
      {q.error && <ErrorState error={q.error} />}
      {q.data && list.length === 0 && <Empty boxed>You are not on any project team.</Empty>}
      {list.length > 0 && (
        <div className="ow-body">
          <StatStrip>
            <StatTile label="Projects" value={list.length} hint="visible to you" />
            <StatTile label="Cases" value={list.reduce((n, p) => n + p.case_count, 0)} hint="across these projects" />
            <StatTile label="At risk" value={list.reduce((n, p) => n + p.at_risk, 0)} tone={list.some((p) => p.at_risk) ? 'alert' : undefined} hint="cases with a high flag" />
            <StatTile label="Ownership gaps" value={list.reduce((n, p) => n + p.cases_with_gaps, 0)} hint="cases missing a required owner" />
          </StatStrip>
          <div className="ow-projects">
            {list.map((p) => (
              <Link key={p.id} to={`/app/projects/${p.id}`} className="ow-project flex flex-col">
                <Folder size={24} />
                <small>{p.case_count} {p.case_count === 1 ? 'case' : 'cases'} · {p.team_size} on team</small>
                <h2>{p.name}</h2>
                <p>
                  {p.code && <span className="font-mono text-xs">{p.code} · </span>}
                  {p.my_roles.length ? `You: ${p.my_roles.map((r) => roleLabel(me.data, r)).join(', ')}` : 'You hold no role on this team'}
                </p>
                <div className="mt-auto flex flex-wrap gap-1.5">
                  {p.at_risk > 0 && <Pill tone="red">{p.at_risk} at risk</Pill>}
                  {p.cases_with_gaps > 0 && <Pill tone="amber">{p.cases_with_gaps} with ownership gaps</Pill>}
                  {p.missing_defaults.map((r) => (
                    <Pill key={r} className="border-dashed" tone="amber" title="No project default for this responsibility">
                      No default {roleLabel(me.data, r).split(' /')[0].toLowerCase()}
                    </Pill>
                  ))}
                  {!p.at_risk && !p.cases_with_gaps && !p.missing_defaults.length && <Pill tone="green">No open gaps</Pill>}
                </div>
              </Link>
            ))}
          </div>
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
    <div>
      <Link to="/app/projects" className="ow-back">
        <ArrowLeft size={14} /> All projects
      </Link>
      <PageHeader
        compact
        eyebrow={d.project.code ? `Project · ${d.project.code}` : 'Project'}
        title={d.project.name}
        description="Project team, defaults inherited by its cases, and the cases themselves."
      />
      <div className="ow-grid major items-start">
        <div className="ow-stack">
          <Section title={<>Cases<span className="ow-count">{d.cases.length}</span></>}>
            <CaseTable rows={d.cases} compact />
          </Section>
          <Section title="Knowledge references">
            {d.knowledge.length === 0 ? (
              <Empty>No documentation location recorded for this project.</Empty>
            ) : (
              <ul className="divide-y text-sm">
                {d.knowledge.map((k) => (
                  <li key={k.id} className="py-2.5">
                    <div className="font-bold">{k.title}</div>
                    <div className="font-mono text-xs text-primary">{k.location}</div>
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
        <div className="ow-stack">
          <Section title="Team" sub="Defaults are inherited by every case on this project.">
            <ul className="divide-y text-sm">
              {ROSTER_ORDER.filter((r) => byRole.has(r) || DEFAULTABLE.has(r)).map((r) => (
                <li key={r} className="py-2.5">
                  <div className="text-[10px] font-extrabold tracking-[1.1px] text-muted-foreground uppercase">{roleLabel(me.data, r)}</div>
                  {(byRole.get(r) ?? []).length === 0 ? (
                    <div className="text-muted-foreground">{DEFAULTABLE.has(r) ? 'Nobody on this project' : DASH}</div>
                  ) : (
                    byRole.get(r)!.map((g) => (
                      <div key={g.id} className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className="font-bold">{g.user?.name}</span>
                        {g.default_for_cases && <Pill className="bg-sky-50 text-sky-800 ring-sky-200">Default for cases</Pill>}
                        {(holders.get(g.user?.id ?? '') ?? []).length > 1 && (
                          <span className="text-xs text-muted-foreground">
                            also {(holders.get(g.user!.id) ?? []).filter((x) => x !== r).map((x) => roleLabel(me.data, x)).join(', ')}
                          </span>
                        )}
                        {can && DEFAULTABLE.has(r) && (
                          <button
                            className="ow-text-button !text-xs"
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
                className="mt-3 space-y-2 rounded-xl border border-dashed border-[#cfc6e2] bg-[#fbfafd] p-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  add.mutate(
                    { user_id: user, role_code: role, default_for_cases: asDefault && DEFAULTABLE.has(role) },
                    { onSuccess: () => { toast.success('Added to team'); setUser('') }, onError: (err) => toast.error(err.message) },
                  )
                }}
              >
                <div className="text-[10px] font-extrabold tracking-[1.1px] text-muted-foreground uppercase">Add to team</div>
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
                  <label className="flex items-center gap-2 text-xs font-semibold">
                    <input type="checkbox" className="accent-primary" checked={asDefault} onChange={(e) => setAsDefault(e.target.checked)} />
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
