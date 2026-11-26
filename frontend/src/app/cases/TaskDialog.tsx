import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Field, ModeBadge, NativeSelect, Pill } from '@/components/common'
import { useCreateTask, useMe, useSuggestTask, useUsers } from '@/lib/api'
import { roleLabel, RULE_LABEL } from '@/lib/format'
import type { CaseDetail, Role, TaskSuggestion } from '@/lib/types'

export default function TaskDialog({
  d, open, onOpenChange, findingId,
}: { d: CaseDetail; open: boolean; onOpenChange: (o: boolean) => void; findingId?: string | null }) {
  const users = useUsers()
  const me = useMe()
  const create = useCreateTask(d.case.id)
  const suggest = useSuggestTask(d.case.id)
  const finding = d.findings.find((f) => f.id === findingId)

  const [title, setTitle] = useState('')
  const [owner, setOwner] = useState('')
  const [due, setDue] = useState('')
  const [fid, setFid] = useState('')
  const [cited, setCited] = useState<string[]>([])
  const [draft, setDraft] = useState<TaskSuggestion | null>(null)

  useEffect(() => {
    if (!open) return
    setTitle('')
    setDraft(null)
    setDue('')
    setFid(finding?.id ?? '')
    setCited(finding ? [...new Set(finding.evidence.map((e) => e.source_id))] : [])
    setOwner(d.case.tech_owner ? `user:${d.case.tech_owner.id}` : 'role:pmo_coordinator')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, findingId])

  const runSuggest = () =>
    suggest.mutate(undefined, {
      onSuccess: (s) => {
        setDraft(s)
        setTitle(s.title)
        const u = s.owner_role === 'technical_owner' && d.case.tech_owner ? `user:${d.case.tech_owner.id}` : `role:${s.owner_role}`
        setOwner(u)
        if (s.cited_source_ids.length) setCited(s.cited_source_ids)
      },
      onError: (e) => toast.error(e.message),
    })

  const save = () => {
    const [kind, val] = owner.split(':')
    create.mutate(
      {
        title,
        owner_user_id: kind === 'user' ? val : null,
        owner_role: kind === 'role' ? (val as Role) : null,
        due_date: due || null,
        finding_id: fid || null,
        cited_source_ids: cited,
        origin: draft ? 'ai_suggested_edited' : 'manual',
      },
      {
        onSuccess: () => {
          toast.success('Follow-up assigned')
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Assign a follow-up · {d.case.ref}</DialogTitle>
          <DialogDescription>A named owner, a due date and the evidence it relies on. Saved tasks survive re-analysis.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          {d.analysis.ai_enabled && d.analysis.ai_configured && (
            <div className="flex items-center justify-between rounded-md border border-dashed p-2.5">
              <span className="text-xs text-muted-foreground">Let the AI draft it from the flags and verified claims. You edit before saving.</span>
              <Button size="sm" variant="outline" onClick={runSuggest} disabled={suggest.isPending}>
                <Sparkles /> {suggest.isPending ? 'Drafting…' : 'Draft with AI'}
              </Button>
            </div>
          )}
          {draft && (
            <div className="rounded-md bg-violet-50 p-2.5 text-xs text-violet-900">
              <div className="mb-1 flex items-center gap-2">
                <Pill className="bg-white text-violet-800 ring-violet-200">AI suggestion · not saved</Pill>
                <ModeBadge mode={draft.mode} model={draft.model} prompt={draft.prompt_version} />
              </div>
              {draft.rationale}
            </div>
          )}
          <Field label="Task">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Plan coverage of the two outstanding complex scenarios" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Owner">
              <NativeSelect value={owner} onChange={(e) => setOwner(e.target.value)}>
                <optgroup label="People">
                  {(users.data ?? []).map((u) => (
                    <option key={u.id} value={`user:${u.id}`}>
                      {u.name} — {roleLabel(me.data, u.role)}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Any holder of a role">
                  {(['pmo_coordinator', 'project_manager', 'technical_owner', 'training_responsible', 'line_manager',
                    'hr_business_partner', 'access_responsible'] as Role[]).map((r) => (
                    <option key={r} value={`role:${r}`}>Any {roleLabel(me.data, r)}</option>
                  ))}
                </optgroup>
              </NativeSelect>
            </Field>
            <Field label="Due date" hint="Empty = org default SLA from the as-of date">
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </Field>
          </div>
          <Field label="Resolves flag">
            <NativeSelect value={fid} onChange={(e) => setFid(e.target.value)}>
              <option value="">— none —</option>
              {d.findings.map((f) => (
                <option key={f.id} value={f.id}>
                  {RULE_LABEL[f.rule_id] ?? f.rule_id}: {f.message}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Cited evidence">
            <div className="grid gap-1">
              {d.sources.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={cited.includes(s.id)}
                    onChange={(e) => setCited(e.target.checked ? [...cited, s.id] : cited.filter((x) => x !== s.id))}
                  />
                  <span className="font-mono text-xs">{s.ref}</span> {s.title} <span className="text-xs text-muted-foreground">({s.author_role ?? '—'})</span>
                </label>
              ))}
            </div>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={create.isPending || title.trim().length < 3}>Save task</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
