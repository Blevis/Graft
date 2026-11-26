import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, MinusCircle, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Empty, Field, NativeSelect, Pill, Section } from '@/components/common'
import { useApplyTemplate, useMe, usePatchCase, usePatchRequirement, useTemplates } from '@/lib/api'
import { CRITERION_LABEL, DASH, DISPOSITION_LABEL, fmtDate, fmtDateTime, READINESS_LABEL, roleLabel } from '@/lib/format'
import type { CaseDetail, Requirement } from '@/lib/types'
import { cn } from '@/lib/utils'

const APPLICABILITY_LABEL = { required: 'Required', optional: 'Optional', not_applicable: 'Not applicable' } as const

export function readinessTone(d: CaseDetail): 'ok' | 'warn' | undefined {
  const s = d.readiness?.status
  return s === 'signed_off' ? 'ok' : s === 'reopened' ? 'warn' : undefined
}

/** Required / optional / not-applicable milestones and checks, with who validated what and when. */
export function RequirementsPanel({ d, onOpenSource }: { d: CaseDetail; onOpenSource: (id: string) => void }) {
  const me = useMe()
  const patch = usePatchRequirement(d.case.id)
  const apply = useApplyTemplate(d.case.id)
  const templates = useTemplates()
  const [editing, setEditing] = useState<string | null>(null)
  const [applicability, setApplicability] = useState<Requirement['applicability']>('required')
  const [reason, setReason] = useState('')
  const [tpl, setTpl] = useState('new_hire')
  const canEdit = d.permissions.can_patch_case
  const required = d.requirements.filter((r) => r.applicability === 'required')
  const done = required.filter((r) => r.status === 'satisfied').length

  return (
    <Section
      title={
        <span>
          Readiness checks{' '}
          {required.length > 0 && (
            <span className="text-xs font-normal text-muted-foreground">
              {done}/{required.length} required met
            </span>
          )}
        </span>
      }
    >
      {d.requirements.length === 0 ? (
        <div className="space-y-2">
          <Empty>No template was applied to this case, so only citations and blocking access gate the final sign-off.</Empty>
          {canEdit && (
            <div className="flex gap-2">
              <NativeSelect value={tpl} onChange={(e) => setTpl(e.target.value)} className="max-w-xs" aria-label="Template">
                {(templates.data?.templates ?? []).filter((t) => t.is_current).map((t) => (
                  <option key={t.key} value={t.key}>{t.name} (v{t.version})</option>
                ))}
              </NativeSelect>
              <Button size="sm" variant="outline" disabled={apply.isPending} onClick={() => apply.mutate(tpl, { onError: (e) => toast.error(e.message) })}>
                Apply template
              </Button>
            </div>
          )}
        </div>
      ) : (
        <ul className="space-y-2 text-sm">
          {d.requirements.map((r) => (
            <li key={r.id} className={cn('rounded-md border p-2', r.applicability === 'not_applicable' && 'opacity-60')}>
              <div className="flex items-start gap-2">
                {r.status === 'satisfied' ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-label="Satisfied" />
                ) : r.status === 'not_applicable' ? (
                  <MinusCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Not applicable" />
                ) : (
                  <Circle className={cn('mt-0.5 size-4 shrink-0', r.applicability === 'required' ? 'text-amber-600' : 'text-muted-foreground')} aria-label="Pending" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium">{r.title}</span>
                    <Pill className={r.applicability === 'required' ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-muted text-muted-foreground ring-border'}>
                      {APPLICABILITY_LABEL[r.applicability]}
                    </Pill>
                    {r.kind === 'access' && <Pill className="bg-sky-50 text-sky-800 ring-sky-200">Access check</Pill>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {r.status === 'satisfied' && r.validated_by
                      ? `Validated by ${r.validated_by.name} · ${fmtDateTime(r.validated_at)}${r.detail ? ` · ${r.detail}` : ''}`
                      : r.detail ?? r.evidence_expectation ?? DASH}
                    {r.due_date && r.status === 'pending' && ` · due ${fmtDate(r.due_date)}`}
                    {r.assignee_role && ` · ${roleLabel(me.data, r.assignee_role)}`}
                  </div>
                  {r.change_reason && r.applicability !== 'required' && (
                    <div className="text-[11px] text-muted-foreground">Changed: {r.change_reason}</div>
                  )}
                </div>
                {canEdit && editing !== r.id && (
                  <button
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label={`Change applicability of ${r.title}`}
                    onClick={() => {
                      setEditing(r.id)
                      setApplicability(r.applicability)
                      setReason('')
                    }}
                  >
                    <Pencil className="size-3.5" />
                  </button>
                )}
              </div>
              {editing === r.id && (
                <form
                  className="mt-2 grid gap-2 sm:grid-cols-[10rem_1fr_auto]"
                  onSubmit={(e) => {
                    e.preventDefault()
                    patch.mutate(
                      { id: r.id, applicability, reason },
                      { onSuccess: () => { toast.success('Requirement updated for this case only'); setEditing(null) }, onError: (er) => toast.error(er.message) },
                    )
                  }}
                >
                  <NativeSelect value={applicability} onChange={(e) => setApplicability(e.target.value as Requirement['applicability'])} aria-label="Applicability">
                    <option value="required">Required</option>
                    <option value="optional">Optional</option>
                    <option value="not_applicable">Not applicable</option>
                  </NativeSelect>
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (kept in the audit trail)" aria-label="Reason" />
                  <div className="flex gap-1">
                    <Button size="sm" type="submit" disabled={reason.trim().length < 5 || patch.isPending}>Save</Button>
                    <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                  </div>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}
      {d.readiness?.status === 'signed_off' && d.readiness.final_review_id && (
        <p className="mt-3 text-xs text-muted-foreground">
          Final sign-off by {d.readiness.signed_off_by?.name} · {fmtDateTime(d.readiness.signed_off_at)}.{' '}
          {(() => {
            const r = d.reviews.find((x) => x.id === d.readiness?.final_review_id)
            return r?.cited_source_ids.length ? (
              <>Evidence: {r.cited_source_ids.map((id) => (
                <button key={id} className="mx-0.5 font-mono underline" onClick={() => onOpenSource(id)}>
                  {[...d.sources, ...d.historic_sources].find((s) => s.id === id)?.ref ?? 'source'}
                </button>
              ))}</>
            ) : null
          })()}
        </p>
      )}
    </Section>
  )
}

/** Every decision ever recorded, newest first: scope, reviewer, time, rationale, citations, exceptions, gaps. */
export function DecisionHistory({ d, onOpenSource }: { d: CaseDetail; onOpenSource: (id: string) => void }) {
  const allSources = [...d.sources, ...d.historic_sources]
  return (
    <Section title={`Technical decisions (${d.reviews.length})`}>
      {d.reviews.length === 0 ? (
        <Empty>
          No decision yet. {d.case.tech_owner ? `${d.case.tech_owner.name} (technical owner)` : 'The technical owner'} records it; AI and trackers cannot.
        </Empty>
      ) : (
        <ol className="space-y-3">
          {d.reviews.map((r) => {
            const superseded = d.reviews.some((x) => x.supersedes_review_id === r.id)
            return (
              <li key={r.id} className={cn('border-l-2 pl-3 text-sm', r.disposition === 'close' ? 'border-primary' : r.disposition === 'reopen' ? 'border-amber-500' : 'border-border', superseded && 'opacity-70')}>
                <div className="font-semibold">
                  {DISPOSITION_LABEL[r.disposition]}
                  <span className="font-normal text-muted-foreground"> · {r.milestone_key ? `milestone: ${r.milestone_key.replace(/_/g, ' ')}` : r.scope}</span>
                  {superseded && <Pill className="ml-1.5 bg-muted text-muted-foreground ring-border">Superseded</Pill>}
                </div>
                {r.rationale !== null ? <p>{r.rationale}</p> : <p className="text-xs text-muted-foreground">Rationale visible to the case team only.</p>}
                {r.exception_reason && (
                  <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
                    Documented exception: {r.exception_reason}. Bypassed: {r.bypassed_criteria.map(CRITERION_LABEL).join('; ')}
                  </div>
                )}
                {r.gaps.map((g) => (
                  <div key={g} className="mt-1 flex items-center gap-1 text-xs text-amber-800">
                    <AlertTriangle className="size-3" /> {g}
                  </div>
                ))}
                <div className="text-xs text-muted-foreground">
                  {r.reviewer?.name} · {fmtDateTime(r.created_at)}
                  {r.cited_source_ids.length > 0 && (
                    <>
                      {' · cites '}
                      {r.cited_source_ids.map((id) => {
                        const s = allSources.find((x) => x.id === id)
                        return (
                          <button key={id} className="mx-0.5 font-mono underline hover:text-foreground" onClick={() => onOpenSource(id)}>
                            {s?.ref ?? 'source'}
                            {s?.superseded ? ` v${s.version}` : ''}
                          </button>
                        )
                      })}
                    </>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Section>
  )
}

export function ReassessmentBanner({ d }: { d: CaseDetail }) {
  if (!d.reassessment.needed) return null
  return (
    <div role="status" className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div>
        <b>Evidence changed since the last decision.</b> The earlier record is kept; the technical owner may reconsider.
        <ul className="list-disc pl-5 text-xs">
          {d.reassessment.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </div>
    </div>
  )
}

/** Coordinator-maintained case fields: readiness date and exact role (tracker fields stay as reported). */
export function CaseFields({ d }: { d: CaseDetail }) {
  const patch = usePatchCase(d.case.id)
  const [editing, setEditing] = useState(false)
  const [date, setDate] = useState(d.case.expected_readiness_date ?? '')
  const [role, setRole] = useState(d.case.exact_role ?? '')
  if (!editing)
    return (
      <span className="inline-flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>Exact role: <b className="font-medium text-foreground">{d.case.exact_role ?? DASH}</b></span>
        <span>Expected readiness: <b className="font-medium text-foreground">{fmtDate(d.case.expected_readiness_date)}</b></span>
        {d.case.external_id && <span>External id: <span className="font-mono">{d.case.external_id}</span></span>}
        {d.permissions.can_patch_case && (
          <button className="text-xs text-primary hover:underline" onClick={() => setEditing(true)}>Edit</button>
        )}
      </span>
    )
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        patch.mutate(
          { exact_role: role.trim() || null, expected_readiness_date: date || null },
          { onSuccess: () => { toast.success('Case updated'); setEditing(false) }, onError: (er) => toast.error(er.message) },
        )
      }}
    >
      <Field label="Exact role"><Input value={role} onChange={(e) => setRole(e.target.value)} className="h-8 w-48" /></Field>
      <Field label="Expected readiness"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="h-8" /></Field>
      <Button size="sm" type="submit" disabled={patch.isPending}>Save</Button>
      <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
    </form>
  )
}

export const readinessLabel = (d: CaseDetail) => READINESS_LABEL[d.readiness?.status ?? 'not_signed_off']
