import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, FileUp } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState, Field, Loading, NativeSelect, PageHeader, Pill, Section } from '@/components/common'
import { type CaseInput, useCaseForm, useCreateCase, useImportCommit, useImportPreview } from '@/lib/api'
import type { ImportRow } from '@/lib/types'

/** Coordinator/admin: create one case. People and projects are resolved inside the org; the template is snapshotted. */
export function NewCaseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const form = useCaseForm(open)
  const create = useCreateCase()
  const navigate = useNavigate()
  const blank: CaseInput = { employee: '', movement: 'new_hire', start_date: null }
  const [v, setV] = useState<CaseInput>(blank)
  useEffect(() => { if (open) setV(blank) }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof CaseInput, val: string | null) => setV({ ...v, [k]: val || null })
  const f = form.data
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New onboarding case</DialogTitle>
          <DialogDescription>The template's milestones are copied onto the case and routed as tasks to the people responsible.</DialogDescription>
        </DialogHeader>
        {form.isLoading && <Loading />}
        {form.error && <ErrorState error={form.error} />}
        {f && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Employee name"><Input value={v.employee} onChange={(e) => setV({ ...v, employee: e.target.value })} autoFocus /></Field>
            <Field label="Movement">
              <NativeSelect value={v.movement} onChange={(e) => setV({ ...v, movement: e.target.value as CaseInput['movement'], template_key: null })}>
                <option value="new_hire">New hire</option>
                <option value="reallocation">Project transfer</option>
              </NativeSelect>
            </Field>
            <Field label="Start date"><Input type="date" value={v.start_date ?? ''} onChange={(e) => set('start_date', e.target.value)} /></Field>
            <Field label="Project">
              <NativeSelect value={v.project_id ?? ''} onChange={(e) => set('project_id', e.target.value)}>
                <option value="">— not decided —</option>
                {f.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Line manager">
              <NativeSelect value={v.line_manager_user_id ?? ''} onChange={(e) => set('line_manager_user_id', e.target.value)}>
                <option value="">— assign later —</option>
                {f.people.line_manager.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Technical owner" hint="Empty = the project's default technical owner">
              <NativeSelect value={v.technical_owner_user_id ?? ''} onChange={(e) => set('technical_owner_user_id', e.target.value)}>
                <option value="">— project default —</option>
                {f.people.technical_owner.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Employee account (optional)">
              <NativeSelect value={v.employee_user_id ?? ''} onChange={(e) => set('employee_user_id', e.target.value)}>
                <option value="">— none yet —</option>
                {f.members.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Template">
              <NativeSelect value={v.template_key ?? ''} onChange={(e) => set('template_key', e.target.value)}>
                <option value="">Default for the movement</option>
                {f.templates.map((t) => <option key={t.key} value={t.key}>{t.name} · v{t.version}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Exact role"><Input value={v.exact_role ?? ''} onChange={(e) => set('exact_role', e.target.value)} /></Field>
            <Field label="Expected readiness date"><Input type="date" value={v.expected_readiness_date ?? ''} onChange={(e) => set('expected_readiness_date', e.target.value)} /></Field>
            <Field label="Case reference" hint={`Empty = next free (${f.next_ref})`}><Input value={v.ref ?? ''} onChange={(e) => set('ref', e.target.value.toUpperCase())} placeholder={f.next_ref} /></Field>
            <Field label="External id (HR system)" hint="Unique; used to avoid duplicates on import"><Input value={v.external_id ?? ''} onChange={(e) => set('external_id', e.target.value)} /></Field>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={create.isPending || v.employee.trim().length < 2}
            onClick={() => create.mutate(v, {
              onSuccess: (d) => { toast.success(`${d.case.ref} created with ${d.requirements.length} checks and ${d.tasks.length} tasks`); onOpenChange(false); navigate(`/app/cases/${d.case.ref}`) },
              onError: (e) => toast.error(e.message),
            })}>
            Create case
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const SAMPLE = `external_id,employee,movement,start_date,project,line_manager,technical_owner,template,exact_role,expected_readiness_date
HR-2001,Arta Lika,new_hire,2026-10-20,Orion,Luca Gray,,new_hire,Support Engineer,2026-11-20`

const ACTION: Record<ImportRow['action'], { label: string; cls: string }> = {
  create: { label: 'Will create', cls: 'bg-primary/10 text-primary ring-primary/30' },
  created: { label: 'Created', cls: 'bg-primary/10 text-primary ring-primary/30' },
  skip_existing: { label: 'Already imported', cls: 'bg-muted text-muted-foreground ring-border' },
  error: { label: 'Error', cls: 'bg-red-50 text-red-700 ring-red-200' },
}

/** Controlled CSV import: preview with row-level errors first; committing skips rows already imported. */
export function ImportPage() {
  const preview = useImportPreview()
  const commit = useImportCommit()
  const [csv, setCsv] = useState('')
  const rows = commit.data?.rows ?? preview.data?.rows
  const creatable = preview.data?.rows.filter((r) => r.action === 'create').length ?? 0
  return (
    <div className="space-y-4">
      <Link to="/app/cases" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="size-4" /> Cases</Link>
      <PageHeader title="Import cases from CSV" description="Preview first. Valid rows are created together; invalid rows are listed and skipped. Re-submitting the same file never creates duplicates (external id, then case reference)." />
      <Section title="CSV">
        <div className="grid gap-2">
          <label className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
            <FileUp className="size-4" /> Choose a file
            <input type="file" accept=".csv,text/csv" className="sr-only" onChange={async (e) => {
              const file = e.target.files?.[0]
              if (file) { setCsv(await file.text()); preview.reset(); commit.reset() }
            }} />
          </label>
          <Textarea rows={8} value={csv} onChange={(e) => { setCsv(e.target.value); preview.reset(); commit.reset() }} className="font-mono text-xs" placeholder={SAMPLE} aria-label="CSV content" />
          <p className="text-xs text-muted-foreground">
            Columns: external_id, ref, employee (required), movement, start_date (YYYY-MM-DD), project (name or code), line_manager and technical_owner (member email or exact name), employee_email, template, exact_role, expected_readiness_date. Up to 500 rows.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" disabled={!csv.trim() || preview.isPending} onClick={() => preview.mutate(csv, { onError: (e) => toast.error(e.message) })}>Preview</Button>
            <Button disabled={!preview.data || creatable === 0 || commit.isPending || !!commit.data}
              onClick={() => commit.mutate(csv, { onSuccess: (r) => toast.success(`${r.created.length} case(s) created`), onError: (e) => toast.error(e.message) })}>
              Import {creatable} case(s)
            </Button>
          </div>
        </div>
      </Section>
      {rows && (
        <Section title={commit.data ? 'Result' : 'Preview'}>
          <Table>
            <TableHeader><TableRow><TableHead>Line</TableHead><TableHead>Employee</TableHead><TableHead>External id</TableHead><TableHead>Outcome</TableHead><TableHead>Details</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.line}>
                  <TableCell>{r.line}</TableCell>
                  <TableCell>{r.employee || '—'}{r.ref && r.action === 'created' && <Link className="ml-1 font-mono text-xs hover:underline" to={`/app/cases/${r.ref}`}>{r.ref}</Link>}</TableCell>
                  <TableCell className="font-mono text-xs">{r.external_id ?? '—'}</TableCell>
                  <TableCell><Pill className={ACTION[r.action].cls}>{ACTION[r.action].label}</Pill></TableCell>
                  <TableCell className="text-xs text-red-700">{r.errors.join('; ')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
    </div>
  )
}
