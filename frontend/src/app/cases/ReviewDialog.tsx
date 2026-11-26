import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, NativeSelect } from '@/components/common'
import { ApiError, useCreateReview } from '@/lib/api'
import { CRITERION_LABEL, DISPOSITION_LABEL, STAGE_LABEL } from '@/lib/format'
import type { CaseDetail, ReviewDisposition, Stage } from '@/lib/types'
import { cn } from '@/lib/utils'

const HELP: Record<ReviewDisposition, string> = {
  keep_open: 'Not ready for the stated scope yet; explain what is outstanding.',
  validate_scope: 'Observed execution for one named scope or milestone. Overall readiness is unchanged.',
  close: 'Final sign-off. Needs cited evidence, every required check met and no blocking access.',
  reopen: 'Reverse the current sign-off (or one milestone) because new evidence warrants it. Nothing is erased.',
}

export default function ReviewDialog({ d, open, onOpenChange, draft }: {
  d: CaseDetail; open: boolean; onOpenChange: (o: boolean) => void
  /** Prefill from a workspace draft; the reviewer still edits and signs here. */
  draft?: { scope?: string; rationale?: string }
}) {
  const create = useCreateReview(d.case.id)
  const signedOff = d.readiness?.status === 'signed_off'
  const validated = d.readiness?.validated_milestones ?? []
  const options: ReviewDisposition[] = signedOff ? ['keep_open', 'reopen'] : validated.length ? ['keep_open', 'validate_scope', 'close', 'reopen'] : ['keep_open', 'validate_scope', 'close']
  const [disposition, setDisposition] = useState<ReviewDisposition>('keep_open')
  const [milestone, setMilestone] = useState('')
  const [scope, setScope] = useState('Overall onboarding')
  const [stage, setStage] = useState<Stage | ''>('')
  const [rationale, setRationale] = useState('')
  const [cited, setCited] = useState<string[]>([])
  const [taskId, setTaskId] = useState('')
  const [exception, setException] = useState('')
  const [unmet, setUnmet] = useState<string[]>([])

  useEffect(() => {
    if (!open) return
    setDisposition('keep_open')
    setMilestone('')
    setScope(draft?.scope?.trim() || 'Overall onboarding')
    setStage('')
    setRationale(draft?.rationale ?? '')
    setCited(d.sources.map((s) => s.id))
    setTaskId(d.tasks.find((t) => t.status === 'open' && t.owner_user?.id === d.case.tech_owner?.id)?.id ?? '')
    setException('')
    setUnmet([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, d.case.id])

  const milestones = useMemo(
    () =>
      d.requirements.filter(
        (r) => r.kind === 'milestone' && r.applicability !== 'not_applicable' && (disposition === 'reopen' ? validated.includes(r.key) : !validated.includes(r.key)),
      ),
    [d.requirements, disposition, validated],
  )
  const pendingRequired = d.requirements.filter((r) => r.applicability === 'required' && r.status !== 'satisfied')
  const needsCitation = disposition === 'close' || disposition === 'validate_scope'
  const invalid =
    rationale.trim().length < 10 || scope.trim().length < 3 || (needsCitation && cited.length === 0) || (disposition === 'reopen' && !signedOff && !milestone)

  const save = () =>
    create.mutate(
      {
        disposition, scope, rationale, observed_stage: stage || null, cited_source_ids: cited, task_id: taskId || null,
        milestone_key: milestone || null, exception_reason: disposition === 'close' && exception.trim() ? exception.trim() : null,
      },
      {
        onSuccess: () => {
          toast.success(`${DISPOSITION_LABEL[disposition]} recorded`)
          onOpenChange(false)
        },
        onError: (e) => {
          if (e instanceof ApiError && e.unmet.length) setUnmet(e.unmet)
          toast.error(e.message)
        },
      },
    )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Technical review · {d.case.ref} {d.case.employee}</DialogTitle>
          <DialogDescription>
            Your signed decision. AI claims and tracker statuses are reports; only this record sets readiness. Reviews are append-only.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <fieldset className="grid gap-1.5">
            <legend className="mb-1.5 text-[13px] font-bold">Decision</legend>
            <div className={cn('grid gap-2', options.length > 3 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-3')}>
              {options.map((x) => (
                <button
                  key={x}
                  type="button"
                  aria-pressed={disposition === x}
                  onClick={() => { setDisposition(x); setMilestone(''); setUnmet([]) }}
                  className={cn('rounded-xl border bg-white p-3 text-left text-sm transition-colors', disposition === x ? 'border-primary bg-[#f6f1ff] ring-1 ring-primary' : 'hover:border-[#c9bbe8]')}
                >
                  <div className="font-bold">{DISPOSITION_LABEL[x]}</div>
                  <div className="mt-0.5 text-xs leading-snug text-muted-foreground">{HELP[x]}</div>
                </button>
              ))}
            </div>
          </fieldset>
          {(disposition === 'validate_scope' || disposition === 'reopen') && milestones.length > 0 && (
            <Field label={disposition === 'reopen' ? 'Milestone to reopen (empty = the final sign-off)' : 'Milestone validated (optional)'}>
              <NativeSelect
                value={milestone}
                onChange={(e) => {
                  setMilestone(e.target.value)
                  const m = d.requirements.find((r) => r.key === e.target.value)
                  if (m) setScope(m.title)
                }}
              >
                <option value="">{disposition === 'reopen' ? (signedOff ? 'Final sign-off' : '— choose —') : '— a free-text scope only —'}</option>
                {milestones.map((m) => <option key={m.key} value={m.key}>{m.title}</option>)}
              </NativeSelect>
            </Field>
          )}
          {disposition === 'close' && pendingRequired.length > 0 && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs leading-relaxed text-amber-900">
              Still pending: {pendingRequired.map((r) => r.title).join('; ')}. The server will refuse the sign-off unless your organisation allows a documented exception.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Scope of this decision"><Input value={scope} onChange={(e) => setScope(e.target.value)} /></Field>
            <Field label="Observed KT stage">
              <NativeSelect value={stage} onChange={(e) => setStage(e.target.value as Stage | '')}>
                <option value="">— not stated —</option>
                {(Object.keys(STAGE_LABEL) as Stage[]).map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
              </NativeSelect>
            </Field>
          </div>
          <Field label="Reason">
            <Textarea rows={4} value={rationale} onChange={(e) => setRationale(e.target.value)}
              placeholder="e.g. Handles standard requests with occasional support; two complex scenarios are still uncovered, so onboarding stays open." />
          </Field>
          <Field label="Linked follow-up">
            <NativeSelect value={taskId} onChange={(e) => setTaskId(e.target.value)}>
              <option value="">— none —</option>
              {d.tasks.map((t) => <option key={t.id} value={t.id}>{t.title} ({t.status})</option>)}
            </NativeSelect>
          </Field>
          <Field label={`Evidence reviewed${needsCitation ? ' (at least one required)' : ''}`}>
            <div className="grid gap-1">
              {d.sources.length === 0 && <span className="text-xs text-muted-foreground">No evidence on this case yet: add a source first.</span>}
              {d.sources.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-[13px] font-medium">
                  <input type="checkbox" checked={cited.includes(s.id)}
                    onChange={(e) => setCited(e.target.checked ? [...cited, s.id] : cited.filter((x) => x !== s.id))} />
                  <span className="font-mono text-xs font-semibold text-primary">{s.ref ?? `v${s.version}`}</span> {s.title}
                </label>
              ))}
            </div>
          </Field>
          {disposition === 'close' && (unmet.length > 0 || pendingRequired.length > 0) && (
            <Field label="Documented exception (only if your organisation's policy allows it)" hint="Recorded with the criteria it bypasses and audited.">
              <Textarea rows={2} value={exception} onChange={(e) => setException(e.target.value)} placeholder="Which approved policy applies, and why" />
            </Field>
          )}
          {unmet.length > 0 && (
            <div role="alert" className="flex gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-800">
              <AlertTriangle className="size-4 shrink-0" />
              <ul className="list-disc pl-4">{unmet.map((u) => <li key={u}>{CRITERION_LABEL(u)}</li>)}</ul>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={create.isPending || invalid}>Record {DISPOSITION_LABEL[disposition].toLowerCase()}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
