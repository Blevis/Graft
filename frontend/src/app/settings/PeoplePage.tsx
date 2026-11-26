import { useEffect, useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Plus, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorState, Field, Loading, NativeSelect, PageHeader, Pill, Section } from '@/components/common'
import {
  useAddMember, useGrantRole, useMe, useMembers, useProjects, useRevokeRole, useRoles, useSaveRoleLabels, useSetMemberStatus,
} from '@/lib/api'
import { fmtDate, roleLabel } from '@/lib/format'
import type { Me, Role } from '@/lib/types'
import { cn } from '@/lib/utils'

export function SettingsNav({ me }: { me?: Me }) {
  const roles = me?.roles ?? []
  const items = [
    { to: '/app/settings', label: 'Rules & AI', show: true },
    { to: '/app/settings/people', label: 'People & Roles', show: roles.includes('org_admin') || roles.includes('pmo_coordinator') },
    { to: '/app/settings/workflow', label: 'Workflow & calendar', show: true },
    { to: '/app/settings/ai-guidance', label: 'AI Guidance', show: true },
  ]
  return (
    <nav className="ow-toggle -mt-1.5" aria-label="Settings sections">
      {items.filter((i) => i.show).map((i) => (
        <NavLink key={i.to} to={i.to} end>
          {i.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function PeoplePage() {
  const me = useMe()
  const isAdmin = !!me.data?.roles.includes('org_admin')
  const allowed = isAdmin || !!me.data?.roles.includes('pmo_coordinator')
  const members = useMembers(allowed)
  const roles = useRoles()
  const projects = useProjects()
  const addMember = useAddMember()
  const setStatus = useSetMemberStatus()
  const grant = useGrantRole()
  const revoke = useRevokeRole()
  const saveLabels = useSaveRoleLabels()
  const [search, setSearch] = useState('')
  const [newName, setNewName] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [g, setG] = useState({ user_id: '', role_code: 'project_member' as Role, scope: 'organization', default_for_cases: false })
  const [labels, setLabels] = useState<Record<string, string>>({})
  useEffect(() => {
    if (roles.data) setLabels(Object.fromEntries(roles.data.map((r) => [r.code, r.label === r.default_label ? '' : r.label])))
  }, [roles.data])

  const list = useMemo(
    () =>
      (members.data?.members ?? []).filter((m) =>
        `${m.user.name} ${m.user.title ?? ''} ${m.grants.map((x) => x.role_label).join(' ')}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [members.data, search],
  )
  const err = (e: Error) => toast.error(e.message)

  if (!allowed)
    return (
      <div>
        <PageHeader eyebrow="Administration" title="Settings" />
        <SettingsNav me={me.data} />
        <Empty>Only an organization admin manages people and roles.</Empty>
      </div>
    )

  return (
    <div className="ow-body">
      <PageHeader
        eyebrow="Administration"
        title="Settings"
        description={
          isAdmin
            ? 'Grant and revoke roles at organization or project scope. Nobody can grant themselves a role, and the last admin cannot be removed.'
            : 'Read-only: only an organization admin grants or revokes roles.'
        }
      />
      <SettingsNav me={me.data} />
      {members.error && <ErrorState error={members.error} />}
      <Section title={`Members (${members.data?.members.length ?? 0})`} actions={<Input className="h-8 w-56" placeholder="Search people or roles…" value={search} onChange={(e) => setSearch(e.target.value)} />}>
        {members.isLoading ? (
          <Loading />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Person</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Roles and scope</TableHead>
                <TableHead>History</TableHead>
                {isAdmin && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((m) => (
                <TableRow key={m.membership_id} className={cn(m.status !== 'active' && 'opacity-60')}>
                  <TableCell>
                    <div className="font-medium">{m.user.name}</div>
                    <div className="text-xs text-muted-foreground">{m.user.title}</div>
                  </TableCell>
                  <TableCell>
                    <Pill className={m.status === 'active' ? 'bg-primary/10 text-primary ring-primary/30' : 'bg-red-50 text-red-700 ring-red-200'}>{m.status}</Pill>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      {m.grants.length === 0 && <span className="text-xs text-amber-700">No role yet</span>}
                      {m.grants.map((x) => (
                        <div key={x.id} className="flex items-center gap-1.5 text-xs">
                          <span className="font-medium">{x.role_label}</span>
                          <span className="text-muted-foreground">
                            {x.scope_type === 'organization' ? 'organization' : `${x.scope_type} ${x.scope_name ?? ''}`}
                            {x.default_for_cases ? ' · default' : ''} · by {x.assigned_by?.name ?? 'seed'} {fmtDate(x.created_at)}
                          </span>
                          {isAdmin && x.user?.id !== me.data?.user.id && (
                            <button
                              title="Revoke (kept in history)"
                              className="text-muted-foreground hover:text-red-700"
                              onClick={() => window.confirm(`Revoke ${x.role_label} from ${m.user.name}?`) && revoke.mutate(x.id, { onError: err })}
                            >
                              <X className="size-3.5" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {m.history.length === 0
                      ? '—'
                      : m.history.map((h) => (
                          <div key={h.id}>
                            {h.role_label} revoked {fmtDate(h.revoked_at)} by {h.revoked_by?.name}
                          </div>
                        ))}
                  </TableCell>
                  {isAdmin && (
                    <TableCell className="text-right">
                      {m.user.id !== me.data?.user.id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setStatus.mutate({ userId: m.user.id, status: m.status === 'active' ? 'suspended' : 'active' }, { onError: err })}
                        >
                          {m.status === 'active' ? 'Suspend' : 'Reactivate'}
                        </Button>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>

      {isAdmin && (
        <div className="ow-grid equal items-start">
          <Section title="Grant a role">
            <form
              className="grid gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                grant.mutate(
                  {
                    user_id: g.user_id,
                    role_code: g.role_code,
                    scope_type: g.scope === 'organization' ? 'organization' : 'project',
                    scope_id: g.scope === 'organization' ? null : g.scope,
                    default_for_cases: g.scope !== 'organization' && g.default_for_cases,
                  },
                  { onSuccess: () => toast.success('Role granted'), onError: err },
                )
              }}
            >
              <Field label="Person">
                <NativeSelect value={g.user_id} onChange={(e) => setG({ ...g, user_id: e.target.value })}>
                  <option value="">Choose…</option>
                  {(members.data?.members ?? [])
                    .filter((m) => m.status === 'active' && m.user.id !== me.data?.user.id)
                    .map((m) => (
                      <option key={m.user.id} value={m.user.id}>{m.user.name}</option>
                    ))}
                </NativeSelect>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Role">
                  <NativeSelect value={g.role_code} onChange={(e) => setG({ ...g, role_code: e.target.value as Role })}>
                    {(roles.data ?? []).map((r) => (
                      <option key={r.code} value={r.code}>{r.label}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Scope">
                  <NativeSelect value={g.scope} onChange={(e) => setG({ ...g, scope: e.target.value })}>
                    <option value="organization">Whole organization</option>
                    {(projects.data ?? []).map((p) => (
                      <option key={p.id} value={p.id}>Project {p.name}</option>
                    ))}
                  </NativeSelect>
                </Field>
              </div>
              {g.scope !== 'organization' && roles.data?.find((r) => r.code === g.role_code)?.is_responsibility && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={g.default_for_cases} onChange={(e) => setG({ ...g, default_for_cases: e.target.checked })} />
                  Default {roleLabel(me.data, g.role_code)} for this project's cases
                </label>
              )}
              <p className="text-xs text-muted-foreground">{roles.data?.find((r) => r.code === g.role_code)?.purpose}</p>
              <Button type="submit" disabled={!g.user_id || grant.isPending} className="justify-self-start">
                Grant role
              </Button>
            </form>
            <form
              className="mt-4 flex gap-2 border-t pt-3"
              onSubmit={(e) => {
                e.preventDefault()
                addMember.mutate(
                  { name: newName.trim(), title: newTitle.trim() || null },
                  { onSuccess: () => { toast.success('Demo member added. Grant them a role next.'); setNewName(''); setNewTitle('') }, onError: err },
                )
              }}
            >
              <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New demo member name" />
              <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title (optional)" />
              <Button type="submit" variant="outline" disabled={newName.trim().length < 2}>
                <Plus /> Add
              </Button>
            </form>
            <p className="mt-1 text-[11px] text-muted-foreground">Email invitations with SSO are planned; demo members sign in from the demo login page.</p>
          </Section>

          <Section title="Role display labels">
            <p className="mb-2 text-xs text-muted-foreground">
              Rename how a role appears (e.g. “Additional Manager”, “Tech Lead”, “KT Lead”). Labels are display only: the role code and its permissions never change.
            </p>
            <div className="grid gap-2">
              {(roles.data ?? []).map((r) => (
                <div key={r.code} className="grid grid-cols-[1fr_1fr] items-center gap-2 text-sm">
                  <div>
                    {r.default_label}
                    <div className="font-mono text-[11px] text-muted-foreground">{r.code} · {r.active_grants} active</div>
                  </div>
                  <Input
                    className="h-8"
                    placeholder="Default"
                    value={labels[r.code] ?? ''}
                    onChange={(e) => setLabels({ ...labels, [r.code]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <Button
              className="mt-3"
              variant="outline"
              disabled={saveLabels.isPending}
              onClick={() =>
                saveLabels.mutate(Object.fromEntries(Object.entries(labels).filter(([, v]) => v.trim())), {
                  onSuccess: () => toast.success('Labels saved'),
                  onError: err,
                })
              }
            >
              Save labels
            </Button>
          </Section>
        </div>
      )}
    </div>
  )
}
