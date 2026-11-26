import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Empty, ErrorState, Field, Loading, ModeBadge, NativeSelect, PageHeader, Pill, Segmented } from '@/components/common'
import { useCases, useDocumentCapabilities, useInbox, useLinkSource, useMe, usePostInbox, useUploadInboxDocument } from '@/lib/api'
import { fmtDate, JOB_LABEL } from '@/lib/format'
import type { InboxItem } from '@/lib/types'
import { SourceHeader } from '../cases/EvidenceTab'

export default function InboxPage() {
  const me = useMe()
  const inbox = useInbox()
  const [filter, setFilter] = useState<'all' | 'needs_review' | 'unmatched' | 'matched'>('all')
  const [open, setOpen] = useState(false)
  const canWrite = !!me.data?.roles.some((r) => r === 'org_admin' || r === 'pmo_coordinator')
  const items = (inbox.data ?? []).filter((i) => filter === 'all' || i.status === filter)
  const unmatched = (inbox.data ?? []).filter((i) => i.status === 'unmatched').length
  const review = (inbox.data ?? []).filter((i) => i.status === 'needs_review').length

  const FILTERS = [
    { id: 'all' as const, label: 'All', count: inbox.data?.length },
    { id: 'needs_review' as const, label: 'Needs review', count: review || undefined },
    { id: 'unmatched' as const, label: 'Unmatched', count: unmatched || undefined },
    { id: 'matched' as const, label: 'Matched' },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Evidence intake"
        title="Inbox"
        description="Every email, update and tracker note, kept verbatim. Graft binds each one to a case only on an explicit match."
        actions={canWrite && <Button onClick={() => setOpen(true)}><Plus /> Add evidence</Button>}
      />
      <div className="ow-filterbar">
        <Segmented label="Inbox filter" options={FILTERS} value={filter} onChange={setFilter} />
        {inbox.data && <span className="ow-meta">{items.length} {items.length === 1 ? 'item' : 'items'}</span>}
      </div>
      {inbox.isLoading && <Loading />}
      {inbox.error && <ErrorState error={inbox.error} />}
      {inbox.data && items.length === 0 && <Empty boxed>Nothing here.</Empty>}
      <div className="ow-stack">
        {items.map((i) => (
          <InboxCard key={i.source.id} item={i} canWrite={canWrite} />
        ))}
      </div>
      <AddEvidenceDialog open={open} onOpenChange={setOpen} />
    </div>
  )
}

function InboxCard({ item, canWrite }: { item: InboxItem; canWrite: boolean }) {
  const link = useLinkSource()
  const cases = useCases('all')
  const [target, setTarget] = useState('')
  const s = item.source
  return (
    <article className="ow-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SourceHeader s={s} />
        <span className="flex items-center gap-2">
          {item.job && item.job.status !== 'done' && (
            <Pill className="bg-sky-50 text-sky-800 ring-sky-200" title={item.job.last_error ?? undefined}>{JOB_LABEL[item.job.status] ?? item.job.status}</Pill>
          )}
          {item.analysis && <ModeBadge mode={item.analysis.mode} />}
        </span>
      </div>
      {s.header && <div className="mt-2 text-xs text-muted-foreground">{s.header}</div>}
      <p className="ow-quote mt-3 whitespace-pre-wrap">{s.body}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3.5 text-[13px]">
        {item.matched_case ? (
          <>
            <Pill className="bg-primary/10 text-primary ring-primary/30">Matched</Pill>
            <Link to={`/app/cases/${item.matched_case.ref}`} className="ow-link">
              {item.matched_case.employee} · {item.matched_case.ref}
              <ArrowUpRight size={14} />
            </Link>
          </>
        ) : item.matched_project ? (
          <>
            <Pill className="bg-sky-50 text-sky-800 ring-sky-200">Project reference</Pill>
            <span>{item.matched_project.name} · not tied to one employee</span>
          </>
        ) : item.status === 'needs_review' ? (
          <>
            <Pill className="bg-amber-50 text-amber-800 ring-amber-200">Needs review</Pill>
            <span className="text-xs text-muted-foreground">
              Several cases match: {item.candidates.map((c) => `${c.ref} ${c.employee}`).join(', ')}. A person decides.
            </span>
          </>
        ) : (
          <Pill className="bg-amber-50 text-amber-800 ring-amber-200">Unmatched</Pill>
        )}
        {canWrite && !item.matched_case && (
          <span className="ml-auto flex items-center gap-2">
            <NativeSelect value={target} onChange={(e) => setTarget(e.target.value)} className="w-60">
              <option value="">Link to case…</option>
              {item.candidates.length > 0 && (
                <optgroup label="Candidates">
                  {item.candidates.map((c) => <option key={`c-${c.id}`} value={c.id}>{c.ref} · {c.employee}</option>)}
                </optgroup>
              )}
              {(cases.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.ref} · {c.employee}
                </option>
              ))}
            </NativeSelect>
            <Button
              size="sm"
              variant="outline"
              disabled={!target || link.isPending}
              onClick={() =>
                link.mutate(
                  { sourceId: s.id, caseId: target },
                  { onSuccess: () => toast.success('Linked as a new source version'), onError: (e) => toast.error(e.message) },
                )
              }
            >
              Link
            </Button>
          </span>
        )}
      </div>
    </article>
  )
}

function AddEvidenceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const post = usePostInbox()
  const upload = useUploadInboxDocument()
  const caps = useDocumentCapabilities()
  const me = useMe()
  const [source, setSource] = useState<'paste' | 'file'>('paste')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [author, setAuthor] = useState('')
  const [recipient, setRecipient] = useState('')
  const [date, setDate] = useState(me.data?.org.as_of_date ?? '')
  const [kind, setKind] = useState<'email' | 'update' | 'tracker_note'>('email')
  const [body, setBody] = useState('')
  const done = (r: InboxItem & { analysis_outcome?: { mode: string; note: string | null } | null }) => {
    toast.success(r.matched_case ? `Matched to ${r.matched_case.ref}` : r.status === 'needs_review' ? 'Several cases match: waiting in Needs review' : 'Saved as unmatched evidence', {
      description: r.analysis_outcome?.note ?? undefined,
    })
    setTitle('')
    setBody('')
    setFile(null)
    onOpenChange(false)
  }
  const save = () =>
    source === 'file' && file
      ? upload.mutate({ file, title, author_role: author, recipient_role: recipient, date }, { onSuccess: done, onError: (e) => toast.error(e.message) })
      : post.mutate(
      { title, author_role: author, recipient_role: recipient || null, date, kind, body },
      {
        onSuccess: (r) => {
          toast.success(r.matched_case ? `Matched to ${r.matched_case.ref}; analysis ${r.analysis_outcome?.mode ?? 'queued'}` : r.status === 'needs_review' ? 'Several cases match: waiting in Needs review' : 'Saved as unmatched evidence', {
            description: r.analysis_outcome?.note ?? undefined,
          })
          setTitle('')
          setBody('')
          onOpenChange(false)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add evidence</DialogTitle>
          <DialogDescription>Paste an email or update exactly as received, or upload a document. It is stored immutably; corrections become new versions.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <Segmented
            label="How to add the evidence"
            options={[{ id: 'paste', label: 'Paste text' }, { id: 'file', label: 'Upload document' }]}
            value={source}
            onChange={setSource}
          />
          <Field label={source === 'file' ? 'Title (optional)' : 'Title'} hint="Name the employee or the case ref (e.g. ONB-005) so Graft can match it">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Weekly KT update: Eva Stone" />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Sender role">
              <Input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Technical Lead" />
            </Field>
            <Field label="Recipient role">
              <Input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="optional" />
            </Field>
            <Field label="Date">
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
          </div>
          {source === 'file' ? (
            <Field label="File" hint={<>PDF, Word (.docx), text, or a scan/photo. The text is read on this server and matched to a case; the file itself is not stored.{caps.data && !caps.data.ocr && ' OCR for scans is not installed on this server.'}</>}>
              <Input type="file" accept={caps.data?.accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Field>
          ) : (<>
          <Field label="Type">
            <NativeSelect value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="email">Email</option>
              <option value="update">Update / check-in</option>
              <option value="tracker_note">Tracker note</option>
            </NativeSelect>
          </Field>
          <Field label="Original text">
            <Textarea rows={6} value={body} onChange={(e) => setBody(e.target.value)} />
          </Field>
          </>)}
          <p className="text-xs text-muted-foreground">Received {fmtDate(date)}. Fictional data only; never paste credentials.</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={source === 'file'
            ? upload.isPending || !file || author.length < 2 || !date
            : post.isPending || title.length < 3 || body.length < 3 || author.length < 2 || !date}>
            Save evidence
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
