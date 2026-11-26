import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Field, NativeSelect } from '@/components/common'
import { useCreateReview } from '@/lib/api'
import { DISPOSITION_LABEL, STAGE_LABEL } from '@/lib/format'
import type { CaseDetail, ReviewDisposition, Stage } from '@/lib/types'
import { cn } from '@/lib/utils'

const DISPOSITIONS: { id: ReviewDisposition; help: string }[] = [
  { id: 'keep_open', help: 'Not ready for the stated scope yet; explain what is outstanding.' },
  { id: 'validate_scope', help: 'Observed independent execution for a named scope only.' },
  { id: 'close', help: 'Final readiness validated from observed execution.' },
]

export default function ReviewDialog({ d, open, onOpenChange }: { d: CaseDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateReview(d.case.id)
  const [disposition, setDisposition] = useState<ReviewDisposition>('keep_open')
  const [scope, setScope] = useState('Overall onboarding')
  const [stage, setStage] = useState<Stage | ''>('')
  const [rationale, setRationale] = useState('')
  const [cited, setCited] = useState<string[]>([])
  const [taskId, setTaskId] = useState('')

  useEffect(() => {
    if (!open) return
    setDisposition('keep_open')
    setScope('Overall onboarding')
    setStage('')
    setRationale('')
    setCited(d.sources.map((s) => s.id))
    setTaskId(d.tasks.find((t) => t.status === 'open' && t.owner_user?.id === d.case.tech_owner?.id)?.id ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, d.case.id])

  const save = () =>
    create.mutate(
      { disposition, scope, rationale, observed_stage: stage || null, cited_source_ids: cited, task_id: taskId || null },
      {
        onSuccess: () => {
          toast.success('Technical review saved')
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Technical review · {d.case.ref} {d.case.employee}</DialogTitle>
          <DialogDescription>
            Your signed decision. AI claims and tracker statuses are reports; this record is what sets the case's stage. Reviews are append-only.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <span className="text-sm font-medium">Decision</span>
            <div className="grid grid-cols-3 gap-2">
              {DISPOSITIONS.map((x) => (
                <button
                  key={x.id}
                  type="button"
                  onClick={() => setDisposition(x.id)}
                  className={cn(
                    'rounded-md border p-2 text-left text-sm',
                    disposition === x.id ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'hover:bg-muted',
                  )}
                >
                  <div className="font-medium">{DISPOSITION_LABEL[x.id]}</div>
                  <div className="text-xs text-muted-foreground">{x.help}</div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Scope of this decision">
              <Input value={scope} onChange={(e) => setScope(e.target.value)} />
            </Field>
            <Field label="Observed KT stage">
              <NativeSelect value={stage} onChange={(e) => setStage(e.target.value as Stage | '')}>
                <option value="">— not stated —</option>
                {(Object.keys(STAGE_LABEL) as Stage[]).map((s) => (
                  <option key={s} value={s}>{STAGE_LABEL[s]}</option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <Field label="Reason">
            <Textarea
              rows={4}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="e.g. Handles standard requests with occasional support; two complex scenarios are still uncovered, so onboarding stays open."
            />
          </Field>
          <Field label="Linked follow-up">
            <NativeSelect value={taskId} onChange={(e) => setTaskId(e.target.value)}>
              <option value="">— none —</option>
              {d.tasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title} ({t.status})
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Evidence reviewed">
            <div className="grid gap-1">
              {d.sources.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={cited.includes(s.id)}
                    onChange={(e) => setCited(e.target.checked ? [...cited, s.id] : cited.filter((x) => x !== s.id))}
                  />
                  <span className="font-mono text-xs">{s.ref}</span> {s.title}
                </label>
              ))}
            </div>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={create.isPending || rationale.trim().length < 10 || scope.trim().length < 3}>
            Save review
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
