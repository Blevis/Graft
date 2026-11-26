import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ClipboardCheck, EyeOff, FileSearch, Plus, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Empty, ErrorState, Loading, ModeBadge, Pill, Section } from '@/components/common'
import { ApiError, useAnalyze, useCase } from '@/lib/api'
import { ageLabel, DASH, DISPOSITION_LABEL, fmtDate, fmtDateTime, humanize, RULE_LABEL, STAGE_LABEL, VIEW_LEVEL_LABEL } from '@/lib/format'
import type { CaseDetail } from '@/lib/types'
import { cn } from '@/lib/utils'
import TaskList from '../tasks/TaskList'
import AccessTab from './AccessTab'
import EvidenceTab from './EvidenceTab'
import ReviewDialog from './ReviewDialog'
import StakeholdersPanel, { TrainingSection } from './StakeholdersPanel'
import TaskDialog from './TaskDialog'
import TimelineTab from './TimelineTab'

export default function CasePage() {
  const { caseId = '' } = useParams()
  const q = useCase(caseId)
  const analyze = useAnalyze(caseId)
  const [params] = useSearchParams()
  const [tab, setTab] = useState(params.get('tab') ?? 'overview')
  const [focus, setFocus] = useState<{ sourceId?: string; claimId?: string }>({})
  const [taskOpen, setTaskOpen] = useState(false)
  const [taskFinding, setTaskFinding] = useState<string | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)

  if (q.isLoading) return <Loading />
  if (q.error instanceof ApiError && q.error.status === 404)
    return <ErrorState error={new Error(`No case "${caseId}" that you have access to.`)} />
  if (q.error) return <ErrorState error={q.error} />
  const d = q.data!
  const c = d.case
  const openEvidence = (sourceId: string, claimId?: string | null) => {
    setFocus({ sourceId, claimId: claimId ?? undefined })
    setTab('evidence')
  }
  const assign = (findingId: string | null) => {
    setTaskFinding(findingId)
    setTaskOpen(true)
  }

  return (
    <div className="space-y-4">
      <Link to="/app/cases" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronLeft className="size-4" /> Cases
      </Link>

      <header className="rounded-lg border bg-background p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-mono text-xs text-muted-foreground">{c.ref}</div>
            <h1 className="text-xl font-semibold tracking-tight">{c.employee}</h1>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>Project: <b className="font-medium text-foreground">{c.project?.name ?? DASH}</b>{c.project?.code ? ` (${c.project.code})` : ''}</span>
              <span>{c.movement ? humanize(c.movement) : DASH} · started {fmtDate(c.start_date)}</span>
              <span>
                Line manager: <b className="font-medium text-foreground">{c.line_manager?.name ?? DASH}</b>
                {!c.line_manager && c.manager && <span> (tracker: {c.manager})</span>}
              </span>
              <span>Technical owner: <b className="font-medium text-foreground">{c.tech_owner?.name ?? DASH}</b></span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {d.permissions.can_analyze && (
              <Button
                variant="outline"
                disabled={analyze.isPending}
                onClick={() =>
                  analyze.mutate(undefined, {
                    onSuccess: (r) => {
                      const modes = [...new Set(r.outcomes.map((o) => o.mode))].join(', ')
                      const note = r.outcomes.find((o) => o.note)?.note
                      toast.success(`Analysis complete (${modes})`, { description: note ?? undefined })
                    },
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                <RefreshCw className={cn(analyze.isPending && 'animate-spin')} /> Analyze evidence
              </Button>
            )}
            {d.permissions.can_create_task && (
              <Button variant="outline" onClick={() => assign(d.findings[0]?.id ?? null)}>
                <Plus /> Assign follow-up
              </Button>
            )}
            {d.permissions.can_review && (
              <Button onClick={() => setReviewOpen(true)}>
                <ClipboardCheck /> Record technical review
              </Button>
            )}
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <StatusBox label="Tracker report" note={`one report among others · updated ${ageLabel(c.tracker_age_days)}`}>
            {c.tracker_status ?? DASH}
          </StatusBox>
          <StatusBox
            label="Evidence"
            note={<ModeBadge mode={d.analysis.mode} model={d.analysis.model} prompt={d.analysis.prompt_version} />}
            tone={d.findings.some((f) => f.severity === 'high') ? 'alert' : d.findings.length ? 'warn' : 'ok'}
          >
            {d.findings.length === 0
              ? 'No open flags'
              : d.findings.some((f) => f.rule_id === 'CLOSURE_CONFLICT')
                ? 'Conflicting reports'
                : `${d.findings.length} open flag${d.findings.length > 1 ? 's' : ''}`}
          </StatusBox>
          <StatusBox
            label="Technical review"
            note={d.latest_review ? `${d.latest_review.reviewer?.name} · ${fmtDateTime(d.latest_review.created_at)}` : 'Only the technical owner can decide readiness'}
            tone={!d.latest_review ? undefined : d.latest_review.disposition === 'keep_open' ? 'warn' : 'ok'}
          >
            {d.latest_review ? `${DISPOSITION_LABEL[d.latest_review.disposition]} · ${d.latest_review.scope}` : 'Not reviewed'}
            {c.stage && <div className="text-xs font-normal text-muted-foreground">Stage: {STAGE_LABEL[c.stage]}</div>}
          </StatusBox>
        </div>
      </header>

      {d.view.level !== 'full' && (
        <div className="flex items-start gap-2 rounded-md border border-dashed bg-background px-3 py-2 text-xs text-muted-foreground">
          <EyeOff className="mt-0.5 size-3.5 shrink-0" />
          <span>
            <b className="font-medium text-foreground">{VIEW_LEVEL_LABEL[d.view.level]}.</b> Your roles on this case do not include{' '}
            {d.view.restricted.join(', ')}. The server withholds them; nothing is hidden only in the browser.
          </span>
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="evidence">Evidence ({d.sources.length})</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="access">Access ({d.access_items.length})</TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge ({d.knowledge.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-3">
          <Overview d={d} openEvidence={openEvidence} assign={assign} />
        </TabsContent>
        <TabsContent value="evidence" className="mt-3">
          <EvidenceTab d={d} focus={focus} />
        </TabsContent>
        <TabsContent value="timeline" className="mt-3">
          <TimelineTab caseId={c.id} />
        </TabsContent>
        <TabsContent value="access" className="mt-3">
          <AccessTab d={d} />
        </TabsContent>
        <TabsContent value="knowledge" className="mt-3">
          <Section title="Knowledge references">
            {d.knowledge.length === 0 ? (
              <Empty>No KT documentation location is recorded for {c.project?.name ?? 'this case (no project)'}.</Empty>
            ) : (
              <ul className="divide-y">
                {d.knowledge.map((k) => (
                  <li key={k.id} className="py-2 text-sm">
                    <div className="font-medium">{k.title}</div>
                    <div className="font-mono text-xs">{k.location}</div>
                    <div className="text-xs text-muted-foreground">
                      Owner: {k.owner_role ?? DASH} · last verified {fmtDate(k.last_verified)} · reference only, documents stay project-owned
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>
      </Tabs>

      <TaskDialog d={d} open={taskOpen} onOpenChange={setTaskOpen} findingId={taskFinding} />
      <ReviewDialog d={d} open={reviewOpen} onOpenChange={setReviewOpen} />
    </div>
  )
}

function StatusBox({ label, note, children, tone }: { label: string; note: React.ReactNode; children: React.ReactNode; tone?: 'alert' | 'warn' | 'ok' }) {
  return (
    <div
      className={cn(
        'rounded-md border p-3',
        tone === 'alert' && 'border-red-200 bg-red-50/60',
        tone === 'warn' && 'border-amber-200 bg-amber-50/60',
        tone === 'ok' && 'border-primary/30 bg-primary/5',
      )}
    >
      <div className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className="mt-0.5 font-semibold">{children}</div>
      <div className="mt-1 text-xs text-muted-foreground">{note}</div>
    </div>
  )
}

function checklist(d: CaseDetail) {
  const c = d.case
  const highFlags = d.findings.filter((f) => f.severity === 'high')
  const kt = d.claims.some((x) => ['knowledge_transfer', 'standard_requests', 'complex_scenarios'].includes(x.scope))
  const r = d.latest_review
  return [
    { label: 'Start date and movement type recorded', ok: !!(c.start_date && c.movement) },
    { label: 'Project recorded', ok: !!c.project },
    { label: 'Line manager and technical owner identified', ok: !!(c.line_manager && c.tech_owner) },
    { label: 'Training responsible assigned', ok: !d.ownership_gaps.includes('training_responsible') },
    { label: 'Required systems tracked', ok: d.access_items.length > 0, na: d.access_items.length === 0 },
    { label: 'Access confirmed usable by the employee', ok: d.access_items.length > 0 && d.access_items.every((a) => a.state === 'confirmed_usable'), na: d.access_items.length === 0 },
    { label: 'KT execution evidence captured', ok: kt },
    { label: 'Final readiness validated by the technical owner', ok: !!r && r.disposition !== 'keep_open' },
    { label: 'KT documents location recorded', ok: d.knowledge.length > 0 },
    { label: 'High-severity flags have an owner', ok: highFlags.every((f) => d.tasks.some((t) => t.finding_id === f.id && t.status === 'open')) },
  ]
}

function Overview({ d, openEvidence, assign }: { d: CaseDetail; openEvidence: (s: string, c?: string | null) => void; assign: (f: string | null) => void }) {
  const srcRef = (id: string) => d.sources.find((s) => s.id === id)
  const claim = (id: string | null) => d.claims.find((c) => c.id === id)
  const open = d.tasks.filter((t) => t.status === 'open')
  const done = d.tasks.filter((t) => t.status === 'done')
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Section title="Flags">
          {d.findings.length === 0 ? (
            <Empty>No open flags. The rules found no conflict, gap or stale report in the current evidence.</Empty>
          ) : (
            <ul className="space-y-3">
              {d.findings.map((f) => {
                const owned = d.tasks.find((t) => t.finding_id === f.id && t.status === 'open')
                return (
                  <li key={f.id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <Pill className={f.severity === 'high' ? 'bg-red-50 text-red-700 ring-red-200' : 'bg-amber-50 text-amber-800 ring-amber-200'}>
                            {f.severity}
                          </Pill>
                          <span className="font-medium">{f.message}</span>
                        </div>
                        {f.detail && <p className="mt-1 text-sm text-muted-foreground">{f.detail}</p>}
                      </div>
                      {d.permissions.can_create_task && !owned && (
                        <Button size="sm" variant="outline" onClick={() => assign(f.id)}>
                          <Plus /> Assign
                        </Button>
                      )}
                      {owned && <span className="text-xs text-muted-foreground">Assigned to {owned.owner_user?.name ?? owned.owner_role}</span>}
                    </div>
                    {f.evidence.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {f.evidence.map((e, i) => {
                          const s = srcRef(e.source_id)
                          const c = claim(e.claim_id)
                          return (
                            <li key={i}>
                              <button
                                onClick={() => openEvidence(e.source_id, e.claim_id)}
                                className="flex w-full items-baseline gap-2 rounded px-1 text-left text-sm hover:bg-muted"
                              >
                                <FileSearch className="size-3.5 shrink-0 translate-y-0.5 text-muted-foreground" />
                                <span className="shrink-0 font-mono text-xs">{s?.ref ?? 'source'}</span>
                                <span className="shrink-0 text-xs text-muted-foreground">{s?.author_role}</span>
                                <span className="text-muted-foreground">{c ? `“${c.quote}”` : s?.title}</span>
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                    <div className="mt-2 text-[11px] text-muted-foreground">
                      Rule {RULE_LABEL[f.rule_id] ?? f.rule_id} {f.rule_version} · computed from evidence, holds no decision
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>
        <Section title={`Tasks (${open.length} open)`}>
          <TaskList tasks={[...open, ...done]} emptyText="No follow-ups yet." showCase={false} />
        </Section>
        {d.view.level !== 'access_only' && <TrainingSection d={d} />}
      </div>
      <div className="space-y-4">
        <StakeholdersPanel d={d} />
        <Section title="Latest technical review">
          {d.latest_review ? (
            <div className="space-y-1 text-sm">
              <div className="font-semibold">
                {DISPOSITION_LABEL[d.latest_review.disposition]} <span className="font-normal text-muted-foreground">· {d.latest_review.scope}</span>
              </div>
              {d.latest_review.rationale !== null ? (
                <p>{d.latest_review.rationale}</p>
              ) : (
                <p className="text-xs text-muted-foreground">Rationale visible to the case team only.</p>
              )}
              <div className="text-xs text-muted-foreground">
                {d.latest_review.reviewer?.name} · {fmtDateTime(d.latest_review.created_at)}
                {d.latest_review.observed_stage && ` · stage ${STAGE_LABEL[d.latest_review.observed_stage]}`}
              </div>
              {d.latest_review.task_id && (
                <div className="text-xs text-muted-foreground">
                  Linked task: {d.tasks.find((t) => t.id === d.latest_review!.task_id)?.title ?? DASH}
                </div>
              )}
              <div className="text-xs text-muted-foreground">
                Evidence reviewed: {d.latest_review.cited_source_ids.map((id) => srcRef(id)?.ref ?? 'source').join(', ') || DASH}
              </div>
              {d.reviews.length > 1 && <div className="pt-1 text-xs text-muted-foreground">{d.reviews.length - 1} earlier review(s) kept in the timeline.</div>}
            </div>
          ) : (
            <Empty>
              No decision yet. {d.case.tech_owner ? `${d.case.tech_owner.name} (technical owner)` : 'The technical owner'} records it; AI and trackers cannot.
            </Empty>
          )}
        </Section>
        <Section title="Onboarding checklist">
          <ul className="space-y-1.5 text-sm">
            {checklist(d).map((x) => (
              <li key={x.label} className="flex items-start gap-2">
                <span className={cn('mt-0.5 inline-block size-3.5 shrink-0 rounded-full border', x.ok ? 'border-primary bg-primary' : x.na ? 'border-dashed' : 'border-amber-500')} />
                <span className={cn(x.na && !x.ok && 'text-muted-foreground')}>
                  {x.label}
                  {x.na && !x.ok && ' (none recorded)'}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  )
}
