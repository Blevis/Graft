import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Empty, ErrorState, Field, Loading, NativeSelect, PageHeader, Section } from '@/components/common'
import { useGuidance, useMe, usePatchPreferences, usePreferences, useSaveGuidance } from '@/lib/api'
import { fmtDateTime, roleLabel } from '@/lib/format'
import type { AskDetail, AskFocus, AskFormat } from '@/lib/types'
import { SettingsNav } from './PeoplePage'

const FIELDS = [
  { key: 'terminology', label: 'Preferred terminology', hint: 'e.g. “Say KT, not training. Say Additional Manager for the project lead.”' },
  { key: 'report_structure', label: 'Standard report structure', hint: 'e.g. “Risks first, then owners, then dates.”' },
  { key: 'escalation_summary', label: 'What a useful escalation summary contains', hint: 'e.g. “Who is blocked, since when, and who acts next.”' },
  { key: 'formatting', label: 'Date and status formatting', hint: 'e.g. “Dates as 14 Oct; always show the tracker age.”' },
  { key: 'context', label: 'Organization context already approved in Graft', hint: 'Context only. External sources are never used.' },
] as const
type Key = (typeof FIELDS)[number]['key']

export const FOCUS_LABEL: Record<AskFocus, string> = {
  auto: 'Auto (from my role)',
  my_tasks: 'My tasks',
  one_employee: 'One employee',
  one_project: 'One project',
  cross_project: 'Cross-project',
  access: 'Access',
  training: 'Training / KT',
  technical_readiness: 'Technical readiness',
}
export const DETAIL_LABEL: Record<AskDetail, string> = { brief: 'Brief', standard: 'Standard', detailed: 'Detailed' }
export const FORMAT_LABEL: Record<AskFormat, string> = {
  action_list: 'Action list',
  status_brief: 'Status brief',
  chronological: 'Chronological',
  stakeholder_report: 'Stakeholder report',
}

export default function GuidancePage() {
  const me = useMe()
  const q = useGuidance()
  const save = useSaveGuidance()
  const prefs = usePreferences()
  const patchPrefs = usePatchPreferences()
  const [form, setForm] = useState<Record<Key, string>>({ terminology: '', report_structure: '', escalation_summary: '', formatting: '', context: '' })
  useEffect(() => {
    const c = q.data?.current
    if (c) setForm({ terminology: c.terminology, report_structure: c.report_structure, escalation_summary: c.escalation_summary, formatting: c.formatting, context: c.context })
  }, [q.data])
  const p = prefs.data
  const err = (e: Error) => toast.error(e.message)

  return (
    <div className="ow-body">
      <PageHeader eyebrow="Administration" title="Settings" description="Guide how the assistant presents information. Guidance shapes presentation only; it never changes who can see what." />
      <SettingsNav me={me.data} />
      <div className="ow-grid major items-start">
        <div className="ow-stack">
          <Section title={`PMO AI guidance${q.data?.current ? ` · version ${q.data.current.version}` : ''}`}>
            {q.isLoading && <Loading />}
            {q.error && <ErrorState error={q.error} />}
            {q.data && (
              <form
                className="grid gap-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  save.mutate(form, { onSuccess: (r) => toast.success(`Saved as version ${r.current?.version}`), onError: err })
                }}
              >
                {FIELDS.map((f) => (
                  <Field key={f.key} label={f.label} hint={f.hint}>
                    <Textarea rows={2} disabled={!q.data.can_edit} value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                  </Field>
                ))}
                {q.data.can_edit ? (
                  <Button type="submit" className="justify-self-start" disabled={save.isPending}>
                    Save new version
                  </Button>
                ) : (
                  <p className="text-xs text-muted-foreground">Only an admin or the PMO can change the organization's guidance.</p>
                )}
              </form>
            )}
          </Section>
          <Section title="Version history">
            {(q.data?.history ?? []).length === 0 ? (
              <Empty>No guidance saved yet. The assistant uses each role's default profile.</Empty>
            ) : (
              <ul className="divide-y text-sm">
                {q.data!.history.map((h) => (
                  <li key={h.version} className="py-1.5">
                    <b>v{h.version}</b> · {h.created_by?.name} · {fmtDateTime(h.created_at)}
                    <div className="truncate text-xs text-muted-foreground">{[h.terminology, h.report_structure].filter(Boolean).join(' · ') || '—'}</div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
        <div className="ow-stack">
          <Section title="Guardrails">
            <ul className="space-y-2 text-sm">
              {(q.data?.guardrails ?? []).map((g) => (
                <li key={g} className="flex gap-2">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
                  {g}
                </li>
              ))}
            </ul>
          </Section>
          <Section title="My presentation preferences">
            {p ? (
              <div className="grid gap-3">
                <p className="text-xs text-muted-foreground">
                  Profile: <b>{p.effective.profile_label}</b>. {p.effective.emphasis}
                </p>
                <Field label="Default focus">
                  <NativeSelect value={p.preferences.focus} onChange={(e) => patchPrefs.mutate({ focus: e.target.value as AskFocus }, { onError: err })}>
                    {Object.entries(FOCUS_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Detail">
                  <NativeSelect value={p.preferences.detail} onChange={(e) => patchPrefs.mutate({ detail: e.target.value as AskDetail }, { onError: err })}>
                    {Object.entries(DETAIL_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Format">
                  <NativeSelect
                    value={p.preferences.format ?? ''}
                    onChange={(e) => patchPrefs.mutate({ format: (e.target.value || null) as AskFormat | null }, { onError: err })}
                  >
                    <option value="">Role default ({FORMAT_LABEL[p.effective.format]})</option>
                    {Object.entries(FORMAT_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
                {p.available_roles.length > 1 && (
                  <Field label="Working context" hint="Presentation only: it never adds or removes a permission.">
                    <NativeSelect
                      value={p.preferences.working_role ?? ''}
                      onChange={(e) => patchPrefs.mutate({ working_role: (e.target.value || null) as never }, { onError: err })}
                    >
                      <option value="">All my roles</option>
                      {p.available_roles.map((r) => (
                        <option key={r} value={r}>{roleLabel(me.data, r)}</option>
                      ))}
                    </NativeSelect>
                  </Field>
                )}
              </div>
            ) : (
              <Loading />
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}
