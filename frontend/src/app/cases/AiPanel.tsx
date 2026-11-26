import { useState } from 'react'
import { Bot, MessageSquareQuote, RefreshCw, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Empty, Loading, ModeBadge, Pill, Section } from '@/components/common'
import { useAgentRuns, useAiStatus, useAsk, useDismissProposal, useRunAgent } from '@/lib/api'
import { fmtDateTime, humanize } from '@/lib/format'
import type { AgentProposal, AskAnswer, CaseDetail } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Case agent: run status, cited assessment, tool steps and editable proposals. Proposals become tasks only through
 * the normal task form (a person edits and saves); stale proposals cannot be accepted. */
export function AgentPanel({ d, onAccept, onOpenSource }: { d: CaseDetail; onAccept: (p: AgentProposal) => void; onOpenSource: (id: string) => void }) {
  const runs = useAgentRuns(d.case.id, d.view.level === 'full')
  const run = useRunAgent(d.case.id)
  const dismiss = useDismissProposal()
  const status = useAiStatus()
  const [dismissing, setDismissing] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  if (d.view.level !== 'full') return null
  const latest = runs.data?.[0]
  const model = status.data
  const sourceRef = (id: string) => d.sources.find((s) => s.id === id)?.ref ?? 'source'

  return (
    <Section
      title={<span className="flex items-center gap-2"><Bot className="size-4" /> Case agent</span>}
      actions={
        d.permissions.can_run_agent ? (
          <Button size="sm" variant="outline" disabled={run.isPending || !d.analysis.ai_enabled}
            onClick={() => run.mutate(undefined, { onError: (e) => toast.error(e.message) })}>
            <RefreshCw className={cn(run.isPending && 'animate-spin')} /> {latest ? 'Run a fresh investigation' : 'Investigate'}
          </Button>
        ) : undefined
      }
    >
      <div aria-live="polite" className="space-y-2 text-sm">
        {model && model.state !== 'available' && (
          <p className="text-xs text-muted-foreground">
            Model {model.model}: {model.state}{model.detail ? ` (${model.detail})` : ''}. Manual work is unaffected.
          </p>
        )}
        {run.isPending && <Loading />}
        {!latest && !run.isPending && <Empty>No investigation yet. The agent reads this case's evidence as you and drafts follow-ups; nothing is saved without you.</Empty>}
        {latest && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Pill className={latest.status === 'completed' ? 'bg-primary/10 text-primary ring-primary/30' : 'bg-slate-100 text-slate-600 ring-slate-200'}>
                {humanize(latest.status)}
              </Pill>
              <span className="font-mono">{latest.provider}:{latest.model} · {latest.prompt_version}{latest.model_digest ? ` · ${latest.model_digest.slice(0, 19)}` : ''}</span>
              <span>{fmtDateTime(latest.created_at)}</span>
              {latest.stale && <Pill className="bg-amber-50 text-amber-800 ring-amber-200">Evidence changed since this run</Pill>}
            </div>
            <p>{latest.assessment}</p>
            {latest.steps.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">Tool steps ({latest.steps.length})</summary>
                <ol className="mt-1 list-decimal space-y-0.5 pl-5">
                  {latest.steps.map((s) => <li key={s.index}><span className="font-mono">{s.tool}</span> · {s.result_summary} · {s.duration_ms} ms</li>)}
                </ol>
              </details>
            )}
            <ul className="space-y-2">
              {latest.proposals.map((p) => (
                <li key={p.id} className="rounded-md border p-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill className="bg-violet-50 text-violet-800 ring-violet-200">{humanize(p.kind)}</Pill>
                    <span className="font-medium">{p.title}</span>
                    {p.status !== 'open' && <Pill className="bg-muted text-muted-foreground ring-border">{humanize(p.status)}</Pill>}
                  </div>
                  <p className="text-xs text-muted-foreground">{p.body}</p>
                  <div className="text-xs">
                    Cites:{' '}
                    {p.cited_source_ids.map((id) => (
                      <button key={id} className="mx-0.5 font-mono underline" onClick={() => onOpenSource(id)}>{sourceRef(id)}</button>
                    ))}
                  </div>
                  {p.status === 'open' && d.permissions.can_run_agent && (
                    <div className="mt-1.5 flex flex-wrap gap-2">
                      <Button size="sm" disabled={latest.stale} onClick={() => onAccept(p)}
                        title={latest.stale ? 'Evidence changed: run a fresh investigation' : undefined}>Edit and accept</Button>
                      {dismissing === p.id ? (
                        <form className="flex gap-1" onSubmit={(e) => {
                          e.preventDefault()
                          dismiss.mutate({ id: p.id, reason }, { onSuccess: () => { setDismissing(null); setReason('') }, onError: (er) => toast.error(er.message) })
                        }}>
                          <Input className="h-8 w-56" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why dismiss?" aria-label="Dismiss reason" />
                          <Button size="sm" type="submit" variant="outline" disabled={!reason.trim()}>Dismiss</Button>
                          <Button size="sm" type="button" variant="ghost" onClick={() => setDismissing(null)} aria-label="Cancel"><X /></Button>
                        </form>
                      ) : (
                        <Button size="sm" variant="ghost" onClick={() => setDismissing(p.id)}>Dismiss…</Button>
                      )}
                    </div>
                  )}
                  {p.dismiss_reason && <div className="text-xs text-muted-foreground">Dismissed: {p.dismiss_reason}</div>}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Section>
  )
}

/** Ask Graft, scoped to this case (or the portfolio when caseId is omitted). Citations open the exact source. */
export function AskBox({ caseId, onOpenSource, compact }: { caseId?: string; onOpenSource: (sourceId: string) => void; compact?: boolean }) {
  const ask = useAsk()
  const [q, setQ] = useState('')
  const a: AskAnswer | undefined = ask.data
  return (
    <Section title={<span className="flex items-center gap-2"><MessageSquareQuote className="size-4" /> Ask Graft{caseId ? ' about this case' : ''}</span>}>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask.mutate({ question: q.trim(), case_id: caseId ?? null }, { onError: (er) => toast.error(er.message) }) }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={caseId ? 'e.g. What is still outstanding?' : 'e.g. Which cases have conflicting closure reports?'} aria-label="Question" />
        <Button type="submit" disabled={ask.isPending || !q.trim()} aria-label="Ask"><Send /></Button>
      </form>
      <div aria-live="polite" className="mt-2 space-y-2 text-sm">
        {ask.isPending && <p className="text-xs text-muted-foreground">Reading the evidence you can see…</p>}
        {a && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <ModeBadge mode={a.mode} model={a.model} prompt={a.prompt_version} />
              {a.refused && <Pill className="bg-amber-50 text-amber-800 ring-amber-200">{a.citations.length ? 'Decision deferred to the technical owner' : 'No supported answer'}</Pill>}
            </div>
            <pre className={cn('font-sans whitespace-pre-wrap', compact && 'line-clamp-6')}>{a.answer}</pre>
            {a.citations.length > 0 && (
              <ul className="space-y-1 text-xs">
                {a.citations.map((c, i) => (
                  <li key={i}>
                    <button className="w-full rounded border bg-muted/30 px-2 py-1 text-left hover:bg-muted" onClick={() => onOpenSource(c.source_id)}>
                      “{c.quote}” <span className="text-primary underline">open source</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Section>
  )
}
