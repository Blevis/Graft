import { useEffect, useState } from 'react'
import { FileUp, Plus, ShieldX } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Empty, Field, ModeBadge, Pill, Section } from '@/components/common'
import { useDocumentCapabilities, useSubmitSource, useUploadDocument } from '@/lib/api'
import { DASH, fmtDate, fmtDateTime, humanize, JOB_LABEL, PROVIDER_LABEL, SCOPE_LABEL } from '@/lib/format'
import type { CaseDetail, Claim, DocumentInfo, Source } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Offsets are Unicode code points (Python indices). Slice by code point, not UTF-16 unit. */
function segments(body: string, claims: Claim[]) {
  const cps = Array.from(body)
  const marks = new Map<number, Claim[]>()
  for (let i = 0; i < cps.length; i++) {
    const hit = claims.filter((c) => i >= c.start && i < c.end)
    if (hit.length) marks.set(i, hit)
  }
  const out: { text: string; claims: Claim[] }[] = []
  let cur = { text: '', claims: [] as Claim[] }
  cps.forEach((ch, i) => {
    const cs = marks.get(i) ?? []
    const same = cs.length === cur.claims.length && cs.every((c, k) => c.id === cur.claims[k]?.id)
    if (!same && cur.text) {
      out.push(cur)
      cur = { text: '', claims: cs }
    } else if (!cur.text) cur.claims = cs
    cur.text += ch
  })
  if (cur.text) out.push(cur)
  return out
}

export function SourceHeader({ s }: { s: Source }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      {s.ref && <span className="font-mono font-semibold text-foreground">{s.ref}</span>}
      <span className="text-[13px] font-bold text-foreground">{s.title ?? humanize(s.kind)}</span>
      <span>·</span>
      <span>
        {s.author_role ?? 'Sender not stated'}
        {s.recipient_role ? ` → ${s.recipient_role}` : ''}
      </span>
      <span>·</span>
      <span>{fmtDate(s.date)}</span>
      <Pill className="bg-slate-50 text-slate-600 ring-slate-200">{humanize(s.kind)}</Pill>
      <span title={`sha256 ${s.body_sha256}`}>v{s.version} · {s.channel ?? s.ingested_via}</span>
      {s.sender && <span>from {s.sender}</span>}
      {s.document && <DocumentBadge doc={s.document} />}
    </div>
  )
}

const METHOD_LABEL: Record<DocumentInfo['method'], string> = {
  text: 'Text file',
  pdf_text: 'PDF text',
  docx: 'Word document',
  ocr_pdf: 'Scanned PDF · OCR',
  ocr_image: 'Image · OCR',
}

const fmtSize = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`)

function DocumentBadge({ doc }: { doc: DocumentInfo }) {
  const ocr = doc.method.startsWith('ocr')
  return (
    <Pill
      className={ocr ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-slate-50 text-slate-600 ring-slate-200'}
      title={[`File sha256 ${doc.sha256}`, ...doc.warnings].join(' · ')}
    >
      <FileUp className="size-3" /> {doc.filename} · {METHOD_LABEL[doc.method]}
      {doc.pages ? ` · ${doc.pages} p.` : ''} · {fmtSize(doc.size)}
    </Pill>
  )
}

/** Upload a report, record or scan. The text is extracted on the server; the file itself is not kept. */
function UploadDocument({ d }: { d: CaseDetail }) {
  const upload = useUploadDocument(d.case.id)
  const caps = useDocumentCapabilities()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const [result, setResult] = useState<{ text: string; doc: DocumentInfo } | null>(null)
  if (!d.permissions.can_upload_document) return null
  const close = () => { setOpen(false); setFile(null); setTitle(''); setDate(''); setResult(null) }
  if (!open)
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FileUp /> Upload document
      </Button>
    )
  if (result)
    return (
      <Section title="Document added as evidence">
        <p className="mb-2 text-xs text-muted-foreground">
          This text was extracted from {result.doc.filename} ({METHOD_LABEL[result.doc.method]}) and stored verbatim.
          The original file was not kept. Analysis runs in the background.
        </p>
        {result.doc.warnings.map((w) => <p key={w} className="mb-2 text-xs text-amber-800">{w}</p>)}
        <pre className="max-h-64 overflow-auto rounded-xl border bg-[#fbfafd] p-3 text-xs whitespace-pre-wrap">{result.text}</pre>
        <Button size="sm" className="mt-2" variant="outline" onClick={close}>Done</Button>
      </Section>
    )
  const maxMb = caps.data ? Math.round(caps.data.max_bytes / 1024 / 1024) : 10
  return (
    <Section title="Upload a document to this case">
      <form className="grid gap-2" onSubmit={(e) => {
        e.preventDefault()
        if (!file) return
        upload.mutate({ file, title, date: date || undefined }, {
          onSuccess: (r) => {
            const analysis = r.job?.outcome_mode === 'unavailable' ? 'AI analysis unavailable; the text is saved' : JOB_LABEL[r.job?.status ?? 'queued'] ?? 'queued'
            toast.success(`Extracted ${r.text.length.toLocaleString()} characters · ${analysis}`)
            setResult({ text: r.text, doc: r.document })
          },
          onError: (er) => toast.error(er.message),
        })
      }}>
        <Field label="File" hint={
          <>PDF, Word (.docx), text, or a scan/photo (PNG, JPEG, TIFF). Up to {maxMb} MB
            {caps.data ? `, ${caps.data.max_pages} pages, ${caps.data.max_chars.toLocaleString()} characters of text` : ''}.
            {caps.data && !caps.data.ocr && ' Scans and photos need OCR, which is not installed on this server.'}
            {' '}The text is read on this server; the file itself is not stored.</>
        }>
          <Input type="file" accept={caps.data?.accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Title" hint="Defaults to the file name."><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. HR check-in report" /></Field>
          <Field label="Document date" hint="Defaults to today."><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        </div>
        <div className="flex gap-2">
          <Button size="sm" type="submit" disabled={upload.isPending || !file}>{upload.isPending ? 'Reading the file…' : 'Upload and extract'}</Button>
          <Button size="sm" type="button" variant="ghost" onClick={close}>Cancel</Button>
        </div>
      </form>
    </Section>
  )
}

/** The employee (own case) or case team adds evidence; it is stored verbatim and analysed in the background. */
function SubmitEvidence({ d }: { d: CaseDetail }) {
  const submit = useSubmitSource(d.case.id)
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  if (d.view.level !== 'full' && d.view.level !== 'employee') return null
  if (!open)
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus /> Add evidence
      </Button>
    )
  return (
    <Section title={d.view.level === 'employee' ? 'Add an update about your onboarding' : 'Add evidence to this case'}>
      <form className="grid gap-2" onSubmit={(e) => {
        e.preventDefault()
        submit.mutate({ title, body, kind: 'update' }, {
          onSuccess: (r) => { toast.success(`Saved verbatim · ${JOB_LABEL[r.job?.status ?? 'queued'] ?? 'queued'}`); setOpen(false); setTitle(''); setBody('') },
          onError: (er) => toast.error(er.message),
        })
      }}>
        <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Covered the second complex scenario" /></Field>
        <Field label="What happened" hint="Stored exactly as written. It is one report among others, never a decision.">
          <Textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        <div className="flex gap-2">
          <Button size="sm" type="submit" disabled={submit.isPending || title.trim().length < 3 || body.trim().length < 3}>Save</Button>
          <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </form>
    </Section>
  )
}

export default function EvidenceTab({ d, focus }: { d: CaseDetail; focus: { sourceId?: string; claimId?: string } }) {
  useEffect(() => {
    const id = focus.claimId ? `claim-${focus.claimId}` : focus.sourceId ? `source-${focus.sourceId}` : null
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focus.claimId, focus.sourceId])

  if (d.sources.length === 0)
    return (
      <div className="space-y-3">
        <Empty>
          {d.view.level === 'task_only' || d.view.level === 'access_only' || d.view.level === 'summary'
            ? 'No evidence is shared with you on this case.'
            : 'No evidence is linked to this case yet. Add it here or from the Inbox.'}
        </Empty>
        <div className="flex flex-wrap items-start gap-2 [&>section]:w-full"><SubmitEvidence d={d} /><UploadDocument d={d} /></div>
      </div>
    )

  return (
    <div className="ow-stack">
      <div className="flex flex-wrap items-start gap-2 [&>section]:w-full"><SubmitEvidence d={d} /><UploadDocument d={d} /></div>
      {d.sources.map((s) => {
        const claims = d.claims.filter((c) => c.source_id === s.id)
        const rejected = d.rejected.filter((r) => r.source_id === s.id)
        const ps = d.analysis.per_source.find((p) => p.source_id === s.id)
        const run = ps?.run
        const attempt = ps?.last_attempt
        return (
          <article
            key={s.id}
            id={`source-${s.id}`}
            className={cn('ow-panel !p-0 overflow-hidden', focus.sourceId === s.id && 'ring-2 ring-primary/45')}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-[#fbfafd] px-5 py-3">
              <SourceHeader s={s} />
              <span className="flex flex-wrap items-center gap-2">
                {d.jobs?.[s.id] && d.jobs[s.id].status !== 'done' && (
                  <Pill className="bg-sky-50 text-sky-800 ring-sky-200" title={d.jobs[s.id].last_error ?? undefined}>
                    {JOB_LABEL[d.jobs[s.id].status] ?? d.jobs[s.id].status}
                  </Pill>
                )}
                {run ? (
                  <ModeBadge mode={run.mode} model={`${PROVIDER_LABEL[run.provider] ?? run.provider} · ${run.model}`} prompt={run.prompt_version} />
                ) : (
                  <ModeBadge mode="unavailable" />
                )}
              </span>
            </div>
            <div className="space-y-4 p-5">
              {s.header && <div className="text-xs text-muted-foreground">{s.header}</div>}
              <p className="ow-quote whitespace-pre-wrap">
                {segments(s.body, claims).map((seg, i) =>
                  seg.claims.length ? (
                    <mark
                      key={i}
                      title={seg.claims.map((c) => `${SCOPE_LABEL[c.scope] ?? c.scope}: ${humanize(c.value)}`).join('\n')}
                      className={cn(
                        'rounded-[4px] bg-[#e2d6fa] px-0.5 text-foreground',
                        seg.claims.some((c) => c.id === focus.claimId) && 'bg-amber-200',
                      )}
                    >
                      {seg.text}
                    </mark>
                  ) : (
                    <span key={i}>{seg.text}</span>
                  ),
                )}
              </p>
              <div>
                <div className="mb-1.5 text-[10px] font-extrabold tracking-[1.1px] text-muted-foreground uppercase">Verified claims</div>
                {claims.length === 0 ? (
                  <div className="text-sm text-muted-foreground">
                    {run ? 'No verified claim for this question.' : attempt?.error ? `Analysis unavailable: ${attempt.error}. The original above is the evidence.` : 'Not analysed yet. The original above is the evidence.'}
                  </div>
                ) : (
                  <ul className="space-y-1">
                    {claims.map((c) => (
                      <li
                        key={c.id}
                        id={`claim-${c.id}`}
                        className={cn('flex flex-wrap items-baseline gap-2 rounded-md px-1.5 py-0.5 text-[13px]', focus.claimId === c.id && 'bg-amber-100')}
                      >
                        <span className="w-40 shrink-0 text-xs text-muted-foreground">{SCOPE_LABEL[c.scope] ?? c.scope}</span>
                        <span className="font-bold">
                          {humanize(c.value)}
                          {c.reference ? ` · ${c.reference}` : ''}
                        </span>
                        <span className="text-muted-foreground">“{c.quote}”</span>
                        <span className="font-mono text-[10px] text-muted-foreground">[{c.start},{c.end})</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {rejected.length > 0 && (
                <div className="rounded-xl border border-dashed border-[#d9d2e8] bg-[#fbfafd] p-3">
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-extrabold tracking-[1.1px] text-muted-foreground uppercase">
                    <ShieldX className="size-3.5" /> Rejected by the verifier · never used as evidence
                  </div>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {rejected.map((r) => (
                      <li key={r.id}>
                        <span className="line-through">“{r.raw.quote ?? DASH}”</span>{' '}
                        <span className="text-xs">
                          ({r.raw.scope}/{r.raw.value}) — {r.reason}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {run && (
                <div className="text-[11px] text-muted-foreground">
                  Extracted {fmtDateTime(run.created_at)} · status {run.status}
                  {run.model_digest && ` · digest ${run.model_digest.slice(0, 19)}`}
                  {run.mode === 'replay' && ' · committed example replayed through the same verifier, not a live model call'}
                </div>
              )}
            </div>
          </article>
        )
      })}
    </div>
  )
}
