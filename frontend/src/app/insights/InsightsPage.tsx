import type { ReactNode } from 'react'
import { Empty, ErrorState, Loading, PageHeader, Section, SeverityBadge, StatStrip, StatTile } from '@/components/common'
import { useInsights } from '@/lib/api'
import OutcomeMetrics from './OutcomeMetrics'
import { DISPOSITION_LABEL, fmtDate, humanize, STAGE_LABEL } from '@/lib/format'
import type { ReviewDisposition, Stage } from '@/lib/types'
import TaskList from '../tasks/TaskList'

export default function InsightsPage() {
  const q = useInsights()
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} />
  const d = q.data!
  const attention = d.totals.cases_needing_attention
  return (
    <div className="ow-body">
      <PageHeader eyebrow="Reporting" title="Insights" description={`Readiness risks across the portfolio, as of ${fmtDate(d.as_of_date)}.`} />
      <StatStrip>
        <StatTile label="Cases" value={d.totals.cases} hint="in your scope" />
        <StatTile label="Need attention" value={attention} tone={attention ? 'alert' : undefined} hint="open flags or gaps" />
        <StatTile label="High-severity flags" value={d.by_severity.high} hint={`${d.by_severity.medium} medium · ${d.by_severity.low} low`} />
        <StatTile label="Open / overdue tasks" value={`${d.totals.open_tasks} / ${d.totals.overdue_tasks}`} hint="follow-ups in flight" />
        <StatTile label="Signed off" value={d.readiness?.signed_off ?? '—'} hint={`${d.readiness?.reopened ?? 0} reopened · ${d.readiness?.not_signed_off ?? 0} not signed off`} tone="ok" />
      </StatStrip>
      <OutcomeMetrics />
      <div className="ow-grid equal">
        <Section title="Flags by reason" sub="Cases carrying each open flag.">
          <Bars
            empty="No open flags."
            rows={d.by_rule.map((r) => ({
              key: r.rule_id,
              label: <SeverityBadge severity={r.rule_id.startsWith('MISSING') || r.rule_id === 'STALE_TRACKER' ? 'medium' : 'high'} rule={r.rule_id} />,
              value: r.count,
            }))}
          />
        </Section>
        <Section title="By project" sub="Flagged cases out of all cases on the project.">
          <Bars empty="No projects in scope." rows={d.by_project.map((p) => ({ key: p.project, label: p.project, value: p.flagged, of: p.cases }))} />
        </Section>
        <Section title="Technical review state" sub="Latest recorded decision per case.">
          <Bars
            empty="No cases."
            rows={d.review_states.map((r) => ({
              key: r.state, label: r.state === 'none' ? 'Not reviewed' : DISPOSITION_LABEL[r.state as ReviewDisposition], value: r.count,
            }))}
          />
          <div className="mt-5 mb-1 text-[10px] font-extrabold tracking-[1.1px] text-muted-foreground uppercase">Observed stage (from reviews)</div>
          <Bars
            empty="No cases."
            rows={d.stage_distribution.map((s) => ({
              key: s.stage, label: s.stage === 'none' ? 'No review yet' : (STAGE_LABEL[s.stage as Stage] ?? humanize(s.stage)), value: s.count,
            }))}
          />
        </Section>
        <Section title={<>Overdue tasks<span className="ow-count">{d.overdue.length}</span></>} sub="Past due and not waiting.">
          <TaskList tasks={d.overdue} emptyText="No overdue tasks." />
        </Section>
      </div>
    </div>
  )
}

/** Proportional bars drawn in CSS. Every bar carries its number, so nothing depends on reading the length. */
function Bars({ rows, empty }: { rows: { key: string; label: ReactNode; value: number; of?: number }[]; empty: string }) {
  if (rows.length === 0) return <Empty>{empty}</Empty>
  const max = Math.max(1, ...rows.map((r) => r.of ?? r.value))
  return (
    <div className="ow-bars wide">
      {rows.map((r) => (
        <div key={r.key}>
          <b>{r.label}</b>
          <span>{r.value > 0 && <i style={{ width: `${Math.max(4, (r.value / (r.of ?? max)) * 100)}%` }} />}</span>
          <em>{r.of !== undefined ? `${r.value} / ${r.of}` : r.value}</em>
        </div>
      ))}
    </div>
  )
}
