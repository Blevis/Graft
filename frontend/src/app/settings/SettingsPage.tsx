import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState, Field, Loading, PageHeader, Pill, Section } from '@/components/common'
import { useAudit, useMe, usePatchSettings, useSettings } from '@/lib/api'
import { DASH, fmtDateTime, humanize, RESPONSIBILITY_ORDER, roleLabel } from '@/lib/format'
import type { OrgSettings } from '@/lib/types'
import { SettingsNav } from './PeoplePage'

export default function SettingsPage() {
  const me = useMe()
  const s = useSettings()
  const patch = usePatchSettings()
  const isAdmin = !!me.data?.roles.includes('org_admin')
  const orgAudit = isAdmin || !!me.data?.roles.some((r) => r === 'pmo_coordinator' || r === 'auditor')
  const audit = useAudit(true)
  const [form, setForm] = useState<OrgSettings | null>(null)
  useEffect(() => {
    if (s.data) setForm(s.data)
  }, [s.data])

  if (s.isLoading || !form) return <Loading />
  if (s.error) return <ErrorState error={s.error} />
  const set = <K extends keyof OrgSettings>(k: K, v: OrgSettings[K]) => setForm({ ...form, [k]: v })

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" description={isAdmin ? 'Organisation rules. Changes recompute every case’s flags.' : 'Read-only: only an admin can change these.'} />
      <SettingsNav me={me.data} />
      <Section title="Rules and SLAs">
        <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
          <Field label="Tracker is stale after (days)">
            <Input type="number" min={1} disabled={!isAdmin} value={form.stale_days} onChange={(e) => set('stale_days', Number(e.target.value))} />
          </Field>
          <Field label="Request unanswered after (working days)">
            <Input type="number" min={1} disabled={!isAdmin} value={form.unanswered_working_days} onChange={(e) => set('unanswered_working_days', Number(e.target.value))} />
          </Field>
          <Field label="Default task SLA (hours)">
            <Input type="number" min={1} disabled={!isAdmin} value={form.default_sla_hours} onChange={(e) => set('default_sla_hours', Number(e.target.value))} />
          </Field>
          <Field label="As-of date" hint="Ages, staleness and SLAs use this date in demo orgs, never the wall clock">
            <Input type="date" disabled={!isAdmin} value={form.as_of_date} onChange={(e) => set('as_of_date', e.target.value)} />
          </Field>
        </div>
      </Section>
      <Section title="Ownership and access">
        <div className="grid max-w-3xl gap-4 text-sm">
          <div>
            <div className="mb-1 font-medium">Required responsibilities on every case</div>
            <div className="flex flex-wrap gap-3">
              {RESPONSIBILITY_ORDER.map((r) => (
                <label key={r} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    disabled={!isAdmin}
                    checked={form.required_responsibilities.includes(r)}
                    onChange={(e) =>
                      set('required_responsibilities', e.target.checked ? [...form.required_responsibilities, r] : form.required_responsibilities.filter((x) => x !== r))
                    }
                  />
                  {roleLabel(me.data, r)}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Unassigned required responsibilities show as ownership gaps. Graft never fills them automatically.</p>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" disabled={!isAdmin} checked={form.project_manager_can_assign} onChange={(e) => set('project_manager_can_assign', e.target.checked)} />
            Project managers may assign responsibilities within their own projects
          </label>
          <Field label="Who confirms access is usable" hint="Starter pack: only the employee's own successful test counts.">
            <select
              className="h-8 max-w-md rounded-lg border px-2"
              disabled={!isAdmin}
              value={form.access_tester_policy}
              onChange={(e) => set('access_tester_policy', e.target.value as OrgSettings['access_tester_policy'])}
            >
              <option value="employee">The employee (default)</option>
              <option value="designated">A designated tester per system, falling back to the employee</option>
            </select>
          </Field>
        </div>
      </Section>
      <Section title="AI">
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" disabled={!isAdmin} checked={form.ai_enabled} onChange={(e) => set('ai_enabled', e.target.checked)} />
            Enable AI extraction and task drafting for this organisation
          </label>
          <div className="text-muted-foreground">
            Model <span className="font-mono">{form.llm.model}</span> ·{' '}
            {form.llm.configured ? (
              <Pill className="bg-primary/10 text-primary ring-primary/30">API key configured</Pill>
            ) : (
              <Pill className="bg-slate-100 text-slate-600 ring-slate-200">No API key: recorded examples and cache only</Pill>
            )}
          </div>
          <p className="text-xs text-muted-foreground">With AI off, originals stay visible and coordinators and technical owners keep working manually.</p>
        </div>
      </Section>
      {isAdmin && (
        <Button
          disabled={patch.isPending}
          onClick={() =>
            patch.mutate(
              {
                stale_days: form.stale_days,
                unanswered_working_days: form.unanswered_working_days,
                default_sla_hours: form.default_sla_hours,
                as_of_date: form.as_of_date,
                ai_enabled: form.ai_enabled,
                required_responsibilities: form.required_responsibilities,
                project_manager_can_assign: form.project_manager_can_assign,
                access_tester_policy: form.access_tester_policy,
              },
              { onSuccess: () => toast.success('Settings saved; flags recomputed'), onError: (e) => toast.error(e.message) },
            )
          }
        >
          Save settings
        </Button>
      )}
      {(
        <Section title={orgAudit ? 'Audit trail (latest 100)' : 'My actions (audit trail)'}>
          {audit.isLoading ? (
            <Loading />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>Entity</TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(audit.data ?? []).map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-xs">{fmtDateTime(e.created_at)}</TableCell>
                    <TableCell>{e.actor?.name ?? 'System (seed)'}</TableCell>
                    <TableCell className="text-xs">
                      {humanize(e.entity)} <span className="font-mono text-muted-foreground">{e.entity_id.slice(0, 8)}</span>
                    </TableCell>
                    <TableCell>{humanize(e.action) || DASH}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      )}
    </div>
  )
}
