import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Empty, ErrorState, Field, Loading, NativeSelect, PageHeader, Pill, Section } from '@/components/common'
import { useAddTemplateVersion, useAiStatus, useMe, usePatchSettings, useSettings, useTemplates } from '@/lib/api'
import { fmtDateTime, RESPONSIBILITY_ORDER, roleLabel } from '@/lib/format'
import type { Template, TemplateMilestone } from '@/lib/types'
import { SettingsNav } from './PeoplePage'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function WorkflowSettings() {
  const me = useMe()
  const isAdmin = !!me.data?.roles.includes('org_admin')
  const templates = useTemplates()
  const [selected, setSelected] = useState<string | null>(null)
  const current = (templates.data?.templates ?? []).filter((t) => t.is_current)
  const chosen = current.find((t) => t.key === selected) ?? current[0]

  return (
    <div className="ow-body">
      <PageHeader eyebrow="Administration" title="Settings" description="Onboarding templates, the working calendar behind SLAs, and the sign-off exception policy." />
      <SettingsNav me={me.data} />
      <CalendarAndPolicy isAdmin={isAdmin} />
      <Section title="Onboarding templates">
        {templates.isLoading && <Loading />}
        {templates.error && <ErrorState error={templates.error} />}
        {current.length > 0 && (
          <div className="ow-toggle mb-4" role="tablist">
            {current.map((t) => (
              <button key={t.key} role="tab" aria-selected={chosen?.key === t.key} onClick={() => setSelected(t.key)}
                aria-pressed={chosen?.key === t.key}>
                {t.name} · v{t.version}
              </button>
            ))}
          </div>
        )}
        {chosen && <TemplateEditor key={`${chosen.key}-${chosen.version}`} t={chosen} canEdit={isAdmin}
          history={(templates.data?.templates ?? []).filter((x) => x.key === chosen.key && !x.is_current)} />}
        <p className="mt-3 text-xs text-muted-foreground">
          A case keeps the template version it was created with. Saving here creates a new version for new cases only;
          change one case's checks on its page (with a reason).
        </p>
      </Section>
    </div>
  )
}

function TemplateEditor({ t, canEdit, history }: { t: Template; canEdit: boolean; history: Template[] }) {
  const me = useMe()
  const save = useAddTemplateVersion(t.key)
  const [rows, setRows] = useState<TemplateMilestone[]>(t.definition.milestones)
  const [note, setNote] = useState('')
  const set = (i: number, patch: Partial<TemplateMilestone>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)))
  const dirty = JSON.stringify(rows) !== JSON.stringify(t.definition.milestones)
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr><th className="p-1">Key</th><th className="p-1">Milestone</th><th className="p-1">Kind</th><th className="p-1">Applies</th><th className="p-1">Evidence expected</th><th className="p-1">Due (days)</th><th className="p-1">Assigned to</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t align-top">
                <td className="p-1"><Input className="h-8 w-36 font-mono text-xs" disabled={!canEdit} value={r.key} onChange={(e) => set(i, { key: e.target.value })} aria-label="Key" /></td>
                <td className="p-1"><Input className="h-8 min-w-48" disabled={!canEdit} value={r.title} onChange={(e) => set(i, { title: e.target.value })} aria-label="Title" /></td>
                <td className="p-1">
                  <NativeSelect disabled={!canEdit} value={r.kind} onChange={(e) => set(i, { kind: e.target.value as TemplateMilestone['kind'] })} aria-label="Kind">
                    <option value="milestone">Milestone</option><option value="access">Access check</option>
                  </NativeSelect>
                </td>
                <td className="p-1">
                  <NativeSelect disabled={!canEdit} value={r.applicability} onChange={(e) => set(i, { applicability: e.target.value as TemplateMilestone['applicability'] })} aria-label="Applicability">
                    <option value="required">Required</option><option value="optional">Optional</option><option value="not_applicable">Not applicable</option>
                  </NativeSelect>
                </td>
                <td className="p-1"><Input className="h-8 min-w-48" disabled={!canEdit} value={r.evidence_expectation ?? ''} onChange={(e) => set(i, { evidence_expectation: e.target.value || null })} aria-label="Evidence expectation" /></td>
                <td className="p-1"><Input className="h-8 w-20" type="number" min={0} max={365} disabled={!canEdit} value={r.due_offset_days ?? ''} onChange={(e) => set(i, { due_offset_days: e.target.value === '' ? null : Number(e.target.value) })} aria-label="Due offset days" /></td>
                <td className="p-1">
                  <NativeSelect disabled={!canEdit} value={r.assignee_role ?? ''} onChange={(e) => set(i, { assignee_role: (e.target.value || null) as TemplateMilestone['assignee_role'] })} aria-label="Assignee role">
                    <option value="">Coordinator queue</option>
                    {RESPONSIBILITY_ORDER.map((x) => <option key={x} value={x}>{roleLabel(me.data, x)}</option>)}
                  </NativeSelect>
                </td>
                <td className="p-1">{canEdit && <Button size="sm" variant="ghost" aria-label="Remove milestone" onClick={() => setRows(rows.filter((_, k) => k !== i))}><Trash2 /></Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <div className="flex flex-wrap items-end gap-2">
          <Button size="sm" variant="outline" onClick={() => setRows([...rows, { key: `milestone_${rows.length + 1}`, title: 'New milestone', kind: 'milestone', applicability: 'required', evidence_expectation: null, due_offset_days: 10, assignee_role: 'technical_owner' }])}>
            <Plus /> Add milestone
          </Button>
          <Input className="h-8 max-w-sm" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why" aria-label="Version note" />
          <Button size="sm" disabled={!dirty || save.isPending}
            onClick={() => save.mutate({ name: t.name, definition: { milestones: rows }, note: note || null }, { onSuccess: (v) => toast.success(`Saved as version ${v.version}`), onError: (e) => toast.error(e.message) })}>
            Save as version {t.version + 1}
          </Button>
        </div>
      )}
      {history.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Earlier versions ({history.length})</summary>
          <ul className="mt-1 space-y-0.5">{history.map((h) => <li key={h.id}>v{h.version} · {fmtDateTime(h.created_at)} · {h.created_by?.name ?? 'shipped with Graft'}{h.note ? ` · ${h.note}` : ''}</li>)}</ul>
        </details>
      )}
    </div>
  )
}

function CalendarAndPolicy({ isAdmin }: { isAdmin: boolean }) {
  const s = useSettings()
  const patch = usePatchSettings()
  const ai = useAiStatus()
  const [tz, setTz] = useState('')
  const [hours, setHours] = useState({ start: '09:00', end: '17:00', days: [0, 1, 2, 3, 4] })
  const [holidays, setHolidays] = useState('')
  const [esc, setEsc] = useState(2)
  const [exceptions, setExceptions] = useState(false)
  useEffect(() => {
    if (!s.data) return
    setTz(s.data.timezone)
    setHours(s.data.working_hours)
    setHolidays(s.data.holidays.join(', '))
    setEsc(s.data.escalation_working_days)
    setExceptions(s.data.allow_closure_exceptions)
  }, [s.data])
  if (!s.data) return <Loading />
  return (
    <Section title="Clock, calendar and sign-off policy">
      <div className="grid max-w-3xl gap-4 text-sm sm:grid-cols-2">
        <div className="sm:col-span-2 text-xs text-muted-foreground">
          Clock: <Pill className="bg-muted text-muted-foreground ring-border">{s.data.clock_mode === 'as_of' ? `Fixed demo date ${s.data.as_of_date}` : 'Real time'}</Pill>{' '}
          Model: <Pill className="bg-muted text-muted-foreground ring-border">{ai.data ? `${ai.data.model} · ${ai.data.state}` : '…'}</Pill>
        </div>
        <Field label="Time zone"><Input disabled={!isAdmin} value={tz} onChange={(e) => setTz(e.target.value)} /></Field>
        <Field label="Escalate after (working days overdue)"><Input type="number" min={1} disabled={!isAdmin} value={esc} onChange={(e) => setEsc(Number(e.target.value))} /></Field>
        <Field label="Working hours">
          <div className="flex items-center gap-2">
            <Input type="time" disabled={!isAdmin} value={hours.start} onChange={(e) => setHours({ ...hours, start: e.target.value })} className="h-8 w-28" />
            <span>to</span>
            <Input type="time" disabled={!isAdmin} value={hours.end} onChange={(e) => setHours({ ...hours, end: e.target.value })} className="h-8 w-28" />
          </div>
        </Field>
        <Field label="Working days">
          <div className="flex flex-wrap gap-2">
            {DAYS.map((d, i) => (
              <label key={d} className="flex items-center gap-1">
                <input type="checkbox" disabled={!isAdmin} checked={hours.days.includes(i)}
                  onChange={(e) => setHours({ ...hours, days: e.target.checked ? [...hours.days, i].sort() : hours.days.filter((x) => x !== i) })} />
                {d}
              </label>
            ))}
          </div>
        </Field>
        <Field label="Holidays" hint="YYYY-MM-DD, comma separated"><Input disabled={!isAdmin} value={holidays} onChange={(e) => setHolidays(e.target.value)} /></Field>
        <label className="flex items-start gap-2 sm:col-span-2">
          <input type="checkbox" className="mt-1" disabled={!isAdmin} checked={exceptions} onChange={(e) => setExceptions(e.target.checked)} />
          <span>
            Allow documented exceptions at final sign-off
            <span className="block text-xs text-muted-foreground">
              Off by default. When on, the technical owner may sign off with unmet milestones or blocking access only by giving an exception reason; the bypassed criteria are stored and audited. Citations and a rationale are always required.
            </span>
          </span>
        </label>
      </div>
      {isAdmin ? (
        <Button className="mt-3" disabled={patch.isPending}
          onClick={() => patch.mutate({
            timezone: tz, working_hours: hours, escalation_working_days: esc, allow_closure_exceptions: exceptions,
            holidays: holidays.split(',').map((x) => x.trim()).filter(Boolean),
          }, { onSuccess: () => toast.success('Saved'), onError: (e) => toast.error(e.message) })}>
          Save
        </Button>
      ) : (
        <Empty>Only an organization admin can change these.</Empty>
      )}
    </Section>
  )
}
