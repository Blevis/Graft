import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ClipboardCheck, EyeOff, FileSearch, Plus, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Avatar, Empty, ErrorState, Loading, ModeBadge, Pill, Section } from '@/components/common'
import { ApiError, useAnalyze, useCase } from '@/lib/api'
import { ageLabel, DASH, DISPOSITION_LABEL, fmtDate, fmtDateTime, humanize, RULE_LABEL, STAGE_LABEL, VIEW_LEVEL_LABEL } from '@/lib/format'
import type { AgentProposal, CaseDetail } from '@/lib/types'
import SourceDialog from '@/components/SourceDialog'
import { AgentPanel, AskBox } from './AiPanel'
import { CaseFields, DecisionHistory, ReassessmentBanner, readinessLabel, readinessTone, RequirementsPanel } from './Readiness'
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
  const [proposal, setProposal] = useState<AgentProposal | null>(null)
  const [sourceDialog, setSourceDialog] = useState<string | null>(null)

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
    setProposal(null)
    setTaskFinding(findingId)
    setTaskOpen(true)
  }
  // Current sources open in the Evidence tab (with highlighted claims); older versions and others open by id.
  const openSource = (id: string) => (d.sources.some((s) => s.id === id) ? openEvidence(id) : setSourceDialog(id))

  const evidenceTone = d.findings.some((f) => f.severity === 'high') ? 'alert' : d.findings.length ? 'warn' : 'ok'

  return (
    <div className="ow-body">
      <Link to="/app/cases" className="ow-back !mb-0 self-start">
        <ArrowLeft size={14} /> All cases
      </Link>

      <header className="ow-casehead">
        <div className="ow-casehead-top">
          <Avatar name={c.employee} large />
          <div className="min-w-0">
            <small>{c.ref}</small>
            <h1>{c.employee}</h1>
            <p>
              {c.movement ? humanize(c.movement) : DASH} · started {fmtDate(c.start_date)}
              {c.stage && <> · {STAGE_LABEL[c.stage]}</>}
            </p>
          </div>
          <div className="ow-heading-actions">
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
                <ClipboardCheck /> Record decision
              </Button>
            )}
          </div>
        </div>
        <dl className="ow-deflist ow-casehead-meta">
          <div>
            <dt>Project</dt>
            <dd>
              {c.project?.name ?? DASH}
              {c.project?.code ? <span className="font-medium text-muted-foreground"> · {c.project.code}</span> : ''}
            </dd>
          </div>
          <div>
            <dt>Line manager</dt>
            <dd>
              {c.line_manager?.name ?? DASH}
              {!c.line_manager && c.manager && <span className="font-medium text-muted-foreground"> (tracker: {c.manager})</span>}
            </dd>
          </div>
          <div>
            <dt>Technical owner</dt>
            <dd>{c.tech_owner?.name ?? DASH}</dd>
          </div>
          <CaseFields d={d} />
        </dl>
        <div className="ow-status3">
          <StatusBox label="Tracker report" note={`One report among others · updated ${ageLabel(c.tracker_age_days)}`}>
            {c.tracker_status ?? DASH}
          </StatusBox>
          <StatusBox
            label="Evidence"
            note={<ModeBadge mode={d.analysis.mode} model={d.analysis.model} prompt={d.analysis.prompt_version} />}
            tone={evidenceTone}
          >
            {d.findings.length === 0
              ? 'No open flags'
              : d.findings.some((f) => f.rule_id === 'CLOSURE_CONFLICT')
                ? 'Conflicting reports'
                : `${d.findings.length} open flag${d.findings.length > 1 ? 's' : ''}`}
          </StatusBox>
          <StatusBox
            label="Technical review"
            note={d.latest_review ? `Last: ${DISPOSITION_LABEL[d.latest_review.disposition]} · ${d.latest_review.reviewer?.name} · ${fmtDateTime(d.latest_review.created_at)}` : 'Only the technical owner can decide readiness'}
            tone={readinessTone(d) ?? (d.latest_review?.disposition === 'keep_open' ? 'warn' : undefined)}
            extra={
              d.readiness && d.readiness.validated_milestones.length > 0 && d.readiness.status !== 'signed_off'
                ? `${d.readiness.validated_milestones.length} milestone(s) validated`
                : undefined
            }
          >
            {readinessLabel(d)}
          </StatusBox>
        </div>
      </header>

      <ReassessmentBanner d={d} />

      {d.view.level !== 'full' && (
        <div className="flex items-start gap-2.5 rounded-xl border border-dashed border-[#cfc6e2] bg-white px-4 py-3 text-xs text-muted-foreground">
          <EyeOff className="mt-0.5 size-3.5 shrink-0 text-primary" />
          <span>
            <b className="font-bold text-foreground">{VIEW_LEVEL_LABEL[d.view.level]}.</b> Your roles on this case do not include{' '}
            {d.view.restricted.join(', ')}. The server withholds them; nothing is hidden only in the browser.
          </span>
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="evidence">Evidence <em className="font-extrabold not-italic opacity-70">{d.sources.length}</em></TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="access">Access <em className="font-extrabold not-italic opacity-70">{d.access_items.length}</em></TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge <em className="font-extrabold not-italic opacity-70">{d.knowledge.length}</em></TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-2.5">
          <Overview d={d} openEvidence={openEvidence} assign={assign} openSource={openSource}
            acceptProposal={(p) => { setProposal(p); setTaskFinding(null); setTaskOpen(true) }} />
        </TabsContent>
        <TabsContent value="evidence" className="mt-2.5">
          <EvidenceTab d={d} focus={focus} />
        </TabsContent>
        <TabsContent value="timeline" className="mt-2.5">
          <TimelineTab caseId={c.id} />
        </TabsContent>
        <TabsContent value="access" className="mt-2.5">
          <AccessTab d={d} />
        </TabsContent>
        <TabsContent value="knowledge" className="mt-2.5">
          <Section title="Knowledge references" sub="References only. Documents stay project-owned.">
            {d.knowledge.length === 0 ? (
              <Empty>No KT documentation location is recorded for {c.project?.name ?? 'this case (no project)'}.</Empty>
            ) : (
              <ul className="divide-y">
                {d.knowledge.map((k) => (
                  <li key={k.id} className="py-3 text-sm">
                    <div className="font-bold">{k.title}</div>
                    <div className="mt-0.5 font-mono text-xs text-primary">{k.location}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      Owner: {k.owner_role ?? DASH} · last verified {fmtDate(k.last_verified)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>
      </Tabs>

      <TaskDialog d={d} open={taskOpen} onOpenChange={setTaskOpen} findingId={taskFinding} proposal={proposal} />
      <SourceDialog id={sourceDialog} onClose={() => setSourceDialog(null)} />
      <ReviewDialog d={d} open={reviewOpen} onOpenChange={setReviewOpen} />
    </div>
  )
}

function StatusBox({ label, note, children, tone, extra }: {
  label: string; note: React.ReactNode; children: React.ReactNode; tone?: 'alert' | 'warn' | 'ok'; extra?: React.ReactNode
}) {
  return (
    <div className={cn('ow-status', tone)}>
      <span>{label}</span>
      <strong>{children}</strong>
      {extra && <small className="font-semibold">{extra}</small>}
      <small>{note}</small>
    </div>
  )
}

function Overview({ d, openEvidence, assign, openSource, acceptProposal }: {
  d: CaseDetail; openEvidence: (s: string, c?: string | null) => void; assign: (f: string | null) => void
  openSource: (id: string) => void; acceptProposal: (p: AgentProposal) => void
}) {
  const srcRef = (id: string) => d.sources.find((s) => s.id === id)
  const claim = (id: string | null) => d.claims.find((c) => c.id === id)
  const open = d.tasks.filter((t) => t.status === 'open')
  const done = d.tasks.filter((t) => t.status === 'done')
  return (
    <div className="ow-grid major items-start">
      <div className="ow-stack">
        <Section
          title={<>Flags{d.findings.length > 0 && <span className="ow-count">{d.findings.length}</span>}</>}
          sub="Computed from the evidence by rules. A flag holds no decision."
        >
          {d.findings.length === 0 ? (
            <Empty>No open flags. The rules found no conflict, gap or stale report in the current evidence.</Empty>
          ) : (
            <ul className="space-y-3">
              {d.findings.map((f) => {
                const owned = d.tasks.find((t) => t.finding_id === f.id && t.status === 'open')
                return (
                  <li key={f.id} className={cn('ow-flag', f.severity === 'high' ? 'red' : 'amber')}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Pill className={f.severity === 'high' ? 'bg-red-50 text-red-700 ring-red-200' : 'bg-amber-50 text-amber-800 ring-amber-200'}>
                            {humanize(f.severity)}
                          </Pill>
                          <span className="text-[15px] font-bold tracking-[-0.01em]">{f.message}</span>
                        </div>
                        {f.detail && <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{f.detail}</p>}
                      </div>
                      {d.permissions.can_create_task && !owned && (
                        <Button size="sm" variant="outline" onClick={() => assign(f.id)}>
                          <Plus /> Assign
                        </Button>
                      )}
                      {owned && <span className="text-xs text-muted-foreground">Assigned to {owned.owner_user?.name ?? owned.owner_role}</span>}
                    </div>
                    {f.evidence.length > 0 && (
                      <ul className="mt-3 space-y-0.5 border-t border-dashed pt-2.5">
                        {f.evidence.map((e, i) => {
                          const s = srcRef(e.source_id)
                          const c = claim(e.claim_id)
                          return (
                            <li key={i}>
                              <button
                                onClick={() => openEvidence(e.source_id, e.claim_id)}
                                className="flex w-full items-baseline gap-2 rounded-md px-1.5 py-1 text-left text-[13px] hover:bg-accent"
                              >
                                <FileSearch className="size-3.5 shrink-0 translate-y-0.5 text-primary" />
                                <span className="shrink-0 font-mono text-xs font-semibold text-primary">{s?.ref ?? 'source'}</span>
                                <span className="shrink-0 text-xs text-muted-foreground">{s?.author_role}</span>
                                <span className="text-muted-foreground">{c ? `“${c.quote}”` : s?.title}</span>
                              </button>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                    <div className="mt-2.5 text-[11px] font-medium text-muted-foreground">
                      Rule {RULE_LABEL[f.rule_id] ?? f.rule_id} {f.rule_version}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>
        <Section title={<>Tasks<span className="ow-count">{open.length} open</span></>}>
          <TaskList tasks={[...open, ...done]} emptyText="No follow-ups yet." showCase={false} />
        </Section>
        {d.view.level !== 'access_only' && d.view.level !== 'task_only' && <TrainingSection d={d} />}
        <AgentPanel d={d} onAccept={acceptProposal} onOpenSource={openSource} />
        {(d.view.level === 'full' || d.view.level === 'employee') && <AskBox caseId={d.case.id} onOpenSource={openSource} />}
      </div>
      <div className="ow-stack">
        <StakeholdersPanel d={d} />
        <RequirementsPanel d={d} onOpenSource={openSource} />
        <DecisionHistory d={d} onOpenSource={openSource} />
      </div>
    </div>
  )
}
