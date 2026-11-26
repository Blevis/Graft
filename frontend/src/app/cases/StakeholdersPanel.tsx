import { useState } from 'react'
import { History, UserPlus, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Empty, Loading, NativeSelect, Pill, Section } from '@/components/common'
import { useAssignResponsibility, useEndResponsibility, useMe, useRecordTraining, useResponsibilities } from '@/lib/api'
import { DASH, fmtDate, fmtDateTime, humanize, roleLabel, SOURCE_LABEL } from '@/lib/format'
import type { CaseDetail, ResponsibilityType, Stakeholder } from '@/lib/types'
import { cn } from '@/lib/utils'

const SOURCE_CLASS: Record<string, string> = {
  project_default: 'bg-sky-50 text-sky-800 ring-sky-200',
  case_override: 'bg-violet-50 text-violet-800 ring-violet-200',
  manual: 'bg-slate-50 text-slate-700 ring-slate-200',
  migrated: 'bg-slate-50 text-slate-700 ring-slate-200',
}

/** Stakeholders & Responsibilities: who is accountable for what on this case, inherited or assigned, with gaps. */
export default function StakeholdersPanel({ d }: { d: CaseDetail }) {
  const me = useMe()
  const q = useResponsibilities(d.case.id)
  const assign = useAssignResponsibility(d.case.id)
  const end = useEndResponsibility(d.case.id)
  const [editing, setEditing] = useState<ResponsibilityType | null>(null)
  const [pick, setPick] = useState('')
  const [system, setSystem] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const data = q.data
  const rows: Stakeholder[] = data?.stakeholders ?? d.stakeholders

  const save = (rtype: ResponsibilityType) => {
    if (!pick) return
    assign.mutate(
      { user_id: pick, responsibility_type: rtype, access_item_id: rtype === 'access_responsible' && system ? system : null },
      {
        onSuccess: () => {
          toast.success(`${roleLabel(me.data, rtype)} assigned`)
          setEditing(null)
          setPick('')
          setSystem('')
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  return (
    <Section
      title="Stakeholders & responsibilities"
      actions={
        data && data.history.length > 0 ? (
          <Button size="sm" variant="ghost" onClick={() => setShowHistory((v) => !v)}>
            <History /> History ({data.history.length})
          </Button>
        ) : undefined
      }
    >
      {q.isLoading && !rows.length ? (
        <Loading />
      ) : (
        <ul className="divide-y text-sm">
          {rows.map((s) => (
            <li key={s.responsibility_type} className="py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-medium text-muted-foreground">
                    {roleLabel(me.data, s.responsibility_type)}
                    {s.required && ' · required'}
                  </div>
                  {s.assignments.length === 0 ? (
                    <div className={cn('mt-0.5', s.required ? 'font-medium text-amber-700' : 'text-muted-foreground')}>
                      {s.required ? 'Unassigned: ownership gap' : 'Not assigned'}
                      {s.responsibility_type === 'line_manager' && d.case.manager && (
                        <span className="font-normal text-muted-foreground"> · tracker names “{d.case.manager}”</span>
                      )}
                    </div>
                  ) : (
                    s.assignments.map((a) => (
                      <div key={a.id} className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        <span className="font-medium">{a.user?.name ?? DASH}</span>
                        {a.system && <span className="text-xs text-muted-foreground">for {a.system}</span>}
                        <Pill className={SOURCE_CLASS[a.source]} title={a.assigned_by ? `by ${a.assigned_by.name} · ${fmtDateTime(a.assigned_at)}` : undefined}>
                          {SOURCE_LABEL[a.source] ?? a.source}
                        </Pill>
                        {a.also_holds.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            also {a.also_holds.map((r) => roleLabel(me.data, r)).join(', ')}
                          </span>
                        )}
                        {data?.can_assign && a.kind === 'case_responsibility' && (
                          <button
                            className="text-muted-foreground hover:text-red-700"
                            title="End this assignment (kept in history)"
                            onClick={() =>
                              window.confirm(`End ${a.user?.name}'s assignment? It stays in the history.`) &&
                              end.mutate(a.id, { onError: (e) => toast.error(e.message), onSuccess: () => toast.success('Assignment ended') })
                            }
                          >
                            <X className="size-3.5" />
                          </button>
                        )}
                        {a.notes && <div className="w-full text-xs text-muted-foreground">{a.notes}</div>}
                      </div>
                    ))
                  )}
                </div>
                {data?.can_assign && editing !== s.responsibility_type && (
                  <Button size="sm" variant="ghost" onClick={() => setEditing(s.responsibility_type)} title="Assign or override">
                    <UserPlus />
                  </Button>
                )}
              </div>
              {editing === s.responsibility_type && data && (
                <div className="mt-2 space-y-2 rounded-md border bg-muted/30 p-2">
                  <NativeSelect value={pick} onChange={(e) => setPick(e.target.value)}>
                    <option value="">Choose a person who holds this role…</option>
                    {(data.eligible[s.responsibility_type] ?? []).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </NativeSelect>
                  {s.responsibility_type === 'access_responsible' && data.access_items.length > 0 && (
                    <NativeSelect value={system} onChange={(e) => setSystem(e.target.value)}>
                      <option value="">All systems on this case</option>
                      {data.access_items.map((a) => (
                        <option key={a.id} value={a.id}>
                          Only {a.system}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                  {(data.eligible[s.responsibility_type] ?? []).length === 0 && (
                    <p className="text-xs text-muted-foreground">Nobody holds this role yet. An admin grants it in Settings → People &amp; Roles.</p>
                  )}
                  <div className="flex gap-2">
                    <Button size="sm" disabled={!pick || assign.isPending} onClick={() => save(s.responsibility_type)}>
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                      Cancel
                    </Button>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    A case-level assignment overrides the project default for this case only; the project and other cases are unchanged.
                  </p>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data && !data.can_assign && data.reason && <p className="mt-2 text-xs text-muted-foreground">{data.reason}</p>}
      {showHistory && data && (
        <div className="mt-3 border-t pt-2">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Ended or replaced assignments</div>
          <ul className="space-y-1 text-xs">
            {data.history.map((h) => (
              <li key={h.id}>
                {roleLabel(me.data, h.responsibility_type)}: <b>{h.user?.name}</b>
                {h.system ? ` (${h.system})` : ''} · {fmtDate(h.assigned_at)} → {fmtDate(h.ended_at)}
                {h.ended_by ? ` by ${h.ended_by.name}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  )
}

/** Training & KT log: append-only; never changes the stage (training completed ≠ can execute). */
export function TrainingSection({ d }: { d: CaseDetail }) {
  const record = useRecordTraining(d.case.id)
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<'plan' | 'session' | 'observation'>('session')
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  return (
    <Section
      title={`Training & KT log (${d.training.length})`}
      actions={
        d.permissions.can_record_training && !open ? (
          <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
            Record
          </Button>
        ) : undefined
      }
    >
      {open && (
        <form
          className="mb-3 space-y-2 rounded-md border bg-muted/30 p-2"
          onSubmit={(e) => {
            e.preventDefault()
            record.mutate(
              { kind, title: title.trim(), notes: notes.trim(), activity_date: null },
              {
                onSuccess: () => {
                  toast.success('Recorded. The stage changes only with a technical review.')
                  setOpen(false)
                  setTitle('')
                  setNotes('')
                },
                onError: (err) => toast.error(err.message),
              },
            )
          }}
        >
          <NativeSelect value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            <option value="plan">Plan item</option>
            <option value="session">Session delivered</option>
            <option value="observation">Observation</option>
          </NativeSelect>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Walked through the release runbook" />
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional, no HR commentary)" />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={title.trim().length < 3 || record.isPending}>
              Save
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {d.training.length === 0 ? (
        <Empty>No training or KT activity recorded yet.</Empty>
      ) : (
        <ul className="space-y-2 text-sm">
          {d.training.map((t) => (
            <li key={t.id}>
              <div>
                <Pill className="mr-1.5 bg-muted text-muted-foreground ring-border">{humanize(t.kind)}</Pill>
                {t.title}
              </div>
              {t.notes && <div className="text-xs text-muted-foreground">{t.notes}</div>}
              <div className="text-[11px] text-muted-foreground">
                {t.recorded_by?.name} as {humanize(t.capacity).toLowerCase()} · {fmtDate(t.activity_date)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
