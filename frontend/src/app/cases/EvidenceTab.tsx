import { useEffect } from 'react'
import { ShieldX } from 'lucide-react'
import { Empty, ModeBadge, Pill } from '@/components/common'
import { DASH, fmtDate, fmtDateTime, humanize, SCOPE_LABEL } from '@/lib/format'
import type { CaseDetail, Claim, Source } from '@/lib/types'
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
      <span className="font-medium text-foreground">{s.title ?? humanize(s.kind)}</span>
      <span>·</span>
      <span>
        {s.author_role ?? 'Sender not stated'}
        {s.recipient_role ? ` → ${s.recipient_role}` : ''}
      </span>
      <span>·</span>
      <span>{fmtDate(s.date)}</span>
      <Pill className="bg-slate-50 text-slate-600 ring-slate-200">{humanize(s.kind)}</Pill>
      <span title={`sha256 ${s.body_sha256}`}>v{s.version} · {s.ingested_via}</span>
    </div>
  )
}

export default function EvidenceTab({ d, focus }: { d: CaseDetail; focus: { sourceId?: string; claimId?: string } }) {
  useEffect(() => {
    const id = focus.claimId ? `claim-${focus.claimId}` : focus.sourceId ? `source-${focus.sourceId}` : null
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focus.claimId, focus.sourceId])

  if (d.sources.length === 0) return <Empty>No evidence is linked to this case yet. Add it from the Inbox.</Empty>

  return (
    <div className="space-y-4">
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
            className={cn('rounded-lg border bg-background', focus.sourceId === s.id && 'ring-2 ring-primary/40')}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
              <SourceHeader s={s} />
              {run ? (
                <ModeBadge mode={run.mode} model={run.model} prompt={run.prompt_version} />
              ) : (
                <ModeBadge mode="unavailable" />
              )}
            </div>
            <div className="space-y-3 p-4">
              {s.header && <div className="text-xs text-muted-foreground">{s.header}</div>}
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {segments(s.body, claims).map((seg, i) =>
                  seg.claims.length ? (
                    <mark
                      key={i}
                      title={seg.claims.map((c) => `${SCOPE_LABEL[c.scope] ?? c.scope}: ${humanize(c.value)}`).join('\n')}
                      className={cn(
                        'rounded-sm bg-primary/15 px-0.5 text-foreground',
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
                <div className="mb-1 text-xs font-semibold text-muted-foreground uppercase">Verified claims</div>
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
                        className={cn('flex flex-wrap items-baseline gap-2 rounded px-1 text-sm', focus.claimId === c.id && 'bg-amber-50')}
                      >
                        <span className="w-40 shrink-0 text-xs text-muted-foreground">{SCOPE_LABEL[c.scope] ?? c.scope}</span>
                        <span className="font-medium">
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
                <div className="rounded-md border border-dashed p-2.5">
                  <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase">
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
