import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Hand, History, ListTodo, Pause, Play, RotateCcw, UserCog } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Empty, NativeSelect, Pill } from '@/components/common'
import { useMe, useSetTaskStatus, useTaskAction, useTaskHistory, useUsers } from '@/lib/api'
import { fmtDate, fmtDateTime, humanize, roleLabel } from '@/lib/format'
import type { Role, Task } from '@/lib/types'
import { cn } from '@/lib/utils'

/** UI hint only; the server re-checks ownership (including responsibilities held on the case). */
export function canChangeTask(t: Task, userId?: string, roles: Role[] = []) {
  return t.owner_user?.id === userId || (!t.owner_user && !!t.owner_role && roles.includes(t.owner_role)) || roles.includes('org_admin')
}

type Panel = { id: string; kind: 'pause' | 'reassign' | 'history' } | null

export default function TaskList({ tasks, emptyText, showCase = true }: { tasks: Task[]; emptyText: string; showCase?: boolean }) {
  const me = useMe()
  const users = useUsers()
  const setStatus = useSetTaskStatus()
  const act = useTaskAction()
  const [panel, setPanel] = useState<Panel>(null)
  const [text, setText] = useState('')
  const [target, setTarget] = useState('')
  if (tasks.length === 0) return <Empty>{emptyText}</Empty>
  const coordinator = !!me.data?.roles.some((r) => r === 'org_admin' || r === 'pmo_coordinator')
  const err = (e: Error) => toast.error(e.message)
  const open = (id: string, kind: 'pause' | 'reassign' | 'history') => {
    setPanel(panel?.id === id && panel.kind === kind ? null : { id, kind })
    setText('')
    setTarget('')
  }

  return (
    <ul className="divide-y">
      {tasks.map((t) => {
        const mine = canChangeTask(t, me.data?.user.id, me.data?.roles)
        const unowned = !t.owner_user && t.status === 'open'
        return (
          <li key={t.id} className="py-3 first:pt-0.5 last:pb-0.5">
            <div className="flex items-start justify-between gap-4">
              <span className={cn('ow-tile-icon mt-0.5', t.status === 'done' && '!bg-emerald-100 !text-emerald-700', t.overdue && t.status === 'open' && '!bg-red-100 !text-red-700')}>
                {t.status === 'done' ? <Check size={18} /> : t.waiting ? <Pause size={18} /> : <ListTodo size={18} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className={cn('text-sm leading-snug font-bold', t.status === 'done' && 'font-semibold text-muted-foreground line-through')}>{t.title}</div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
                  {showCase && t.case && (
                    <Link to={`/app/cases/${t.case.ref}`} className="font-bold text-primary hover:underline">{t.case.employee} · {t.case.ref}</Link>
                  )}
                  <span>
                    Owner: {t.owner_user?.name ?? (t.queue === 'unowned' ? 'coordinator queue' : t.owner_role ? `any ${roleLabel(me.data, t.owner_role)}` : '—')}
                  </span>
                  <span className={cn(t.overdue && 'font-bold text-red-700')}>Due {fmtDate(t.due_date)}{t.overdue && ' · overdue'}</span>
                  {t.waiting && <Pill className="bg-sky-50 text-sky-800 ring-sky-200">Waiting: {t.waiting_reason}</Pill>}
                  {t.escalated_at && <Pill className="bg-red-50 text-red-700 ring-red-200">Escalated</Pill>}
                  {/* The working-time clock runs in real-time orgs; demo orgs keep the fixed as-of date. */}
                  {me.data?.org.clock_mode === 'real' && t.working_hours !== null && t.working_hours !== undefined && t.status === 'open' && (
                    <span title="Working time open, waiting excluded">{t.working_hours} working h</span>
                  )}
                  {t.origin === 'ai_suggested_edited' && <Pill className="bg-violet-50 text-violet-800 ring-violet-200">AI-drafted, human-edited</Pill>}
                  {t.origin === 'automation' && <Pill className="bg-muted text-muted-foreground ring-border">From template</Pill>}
                  {t.status === 'done' && <span>Done {fmtDateTime(t.completed_at)}</span>}
                  {t.created_by && <span>Assigned by {t.created_by.name}</span>}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap justify-end gap-1">
                {unowned && (mine || (coordinator && t.queue === 'unowned')) && (
                  <Button size="sm" variant="outline" disabled={act.isPending}
                    onClick={() => act.mutate({ id: t.id, action: 'claim' }, { onError: err, onSuccess: () => toast.success('Claimed') })}>
                    <Hand /> Claim
                  </Button>
                )}
                {t.status === 'open' && (mine || coordinator) && (
                  t.waiting ? (
                    <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: t.id, action: 'resume' }, { onError: err })}><Play /> Resume</Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => open(t.id, 'pause')} aria-label="Mark waiting" title="Mark waiting"><Pause /></Button>
                  )
                )}
                {t.status === 'open' && (coordinator || t.owner_user?.id === me.data?.user.id) && (
                  <Button size="sm" variant="ghost" onClick={() => open(t.id, 'reassign')} aria-label="Reassign" title="Reassign"><UserCog /></Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => open(t.id, 'history')} aria-label="Assignment history" title="Assignment history"><History /></Button>
                {mine && !unowned && (
                  <Button size="sm" variant={t.status === 'open' ? 'outline' : 'ghost'} disabled={setStatus.isPending}
                    onClick={() => setStatus.mutate({ id: t.id, status: t.status === 'open' ? 'done' : 'open' },
                      { onError: err, onSuccess: () => toast.success(t.status === 'open' ? 'Task done' : 'Task reopened') })}>
                    {t.status === 'open' ? <><Check /> Mark done</> : <><RotateCcw /> Reopen</>}
                  </Button>
                )}
              </div>
            </div>
            {panel?.id === t.id && panel.kind === 'pause' && (
              <form className="mt-2.5 ml-12 flex gap-2" onSubmit={(e) => { e.preventDefault(); act.mutate({ id: t.id, action: 'pause', body: { reason: text } }, { onError: err, onSuccess: () => setPanel(null) }) }}>
                <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Waiting for… (stops the SLA clock)" aria-label="Waiting reason" />
                <Button type="submit" disabled={text.trim().length < 3}>Mark waiting</Button>
              </form>
            )}
            {panel?.id === t.id && panel.kind === 'reassign' && (
              <form className="mt-2.5 ml-12 grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => {
                e.preventDefault()
                const [kind, val] = target.split(':')
                act.mutate({ id: t.id, action: 'reassign', body: { owner_user_id: kind === 'user' ? val : null, owner_role: kind === 'role' ? val : null, reason: text } },
                  { onError: err, onSuccess: () => { toast.success('Reassigned'); setPanel(null) } })
              }}>
                <NativeSelect value={target} onChange={(e) => setTarget(e.target.value)} aria-label="New owner">
                  <option value="">Choose…</option>
                  {coordinator && (
                    <optgroup label="People">
                      {(users.data ?? []).map((u) => <option key={u.id} value={`user:${u.id}`}>{u.name}</option>)}
                    </optgroup>
                  )}
                  <optgroup label="Back to a role queue">
                    {(['technical_owner', 'training_responsible', 'access_responsible', 'line_manager', 'pmo_coordinator'] as Role[]).map((r) => (
                      <option key={r} value={`role:${r}`}>Any {roleLabel(me.data, r)}</option>
                    ))}
                  </optgroup>
                </NativeSelect>
                <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Reason (audited)" aria-label="Reason" />
                <Button type="submit" disabled={!target || text.trim().length < 3}>Reassign</Button>
              </form>
            )}
            {panel?.id === t.id && panel.kind === 'history' && <TaskHistory id={t.id} />}
          </li>
        )
      })}
    </ul>
  )
}

function TaskHistory({ id }: { id: string }) {
  const h = useTaskHistory(id, true)
  if (h.isLoading) return <div className="mt-2 ml-12 text-xs text-muted-foreground">Loading history…</div>
  if (!h.data) return null
  return (
    <ol className="mt-2.5 ml-12 space-y-1 rounded-xl border border-dashed border-[#d9d2e8] bg-[#fbfafd] px-3.5 py-2.5 text-xs font-medium text-[#4c4266]">
      {h.data.assignments.map((a, i) => (
        <li key={i}>
          {fmtDateTime(a.at)} · {humanize(a.action)}
          {a.to ? ` → ${a.to.name}` : a.queue ? ` → ${a.queue === 'unowned' ? 'coordinator queue' : `${a.queue} queue`}` : ''}
          {a.by ? ` by ${a.by.name}` : ''}
          {a.reason ? ` — ${a.reason}` : ''}
        </li>
      ))}
      {h.data.pauses.map((p, i) => (
        <li key={`p${i}`}>Waiting {fmtDateTime(p.paused_at)}{p.resumed_at ? ` → ${fmtDateTime(p.resumed_at)}` : ' (ongoing)'} — {p.reason}</li>
      ))}
      {h.data.assignments.length === 0 && h.data.pauses.length === 0 && <li>No assignment changes recorded.</li>}
    </ol>
  )
}
