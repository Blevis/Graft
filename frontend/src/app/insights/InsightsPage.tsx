import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ErrorState, Loading, PageHeader, Section, SeverityBadge, StatTile } from '@/components/common'
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
  return (
    <div className="space-y-5">
      <PageHeader title="Insights" description={`Readiness risks across the portfolio, as of ${fmtDate(d.as_of_date)}.`} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Cases" value={d.totals.cases} />
        <StatTile label="Need attention" value={d.totals.cases_needing_attention} tone="alert" />
        <StatTile label="High-severity flags" value={d.by_severity.high} />
        <StatTile label="Open / overdue tasks" value={`${d.totals.open_tasks} / ${d.totals.overdue_tasks}`} />
        <StatTile label="Signed off" value={d.readiness?.signed_off ?? '—'} hint={`${d.readiness?.reopened ?? 0} reopened · ${d.readiness?.not_signed_off ?? 0} not signed off`} tone="ok" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="lg:col-span-2"><OutcomeMetrics /></div>
        <Section title="Flags by reason">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Reason</TableHead><TableHead className="text-right">Cases</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {d.by_rule.map((r) => (
                <TableRow key={r.rule_id}>
                  <TableCell><SeverityBadge severity={r.rule_id.startsWith('MISSING') || r.rule_id === 'STALE_TRACKER' ? 'medium' : 'high'} rule={r.rule_id} /></TableCell>
                  <TableCell className="text-right tabular-nums">{r.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
        <Section title="By project">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Project</TableHead><TableHead className="text-right">Cases</TableHead><TableHead className="text-right">Flagged</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {d.by_project.map((p) => (
                <TableRow key={p.project}>
                  <TableCell>{p.project}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.cases}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.flagged}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
        <Section title="Technical review state">
          <Table>
            <TableBody>
              {d.review_states.map((r) => (
                <TableRow key={r.state}>
                  <TableCell>{r.state === 'none' ? 'Not reviewed' : DISPOSITION_LABEL[r.state as ReviewDisposition]}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 text-xs font-semibold text-muted-foreground uppercase">Observed stage (from reviews)</div>
          <Table>
            <TableBody>
              {d.stage_distribution.map((s) => (
                <TableRow key={s.stage}>
                  <TableCell>{s.stage === 'none' ? 'No review yet' : (STAGE_LABEL[s.stage as Stage] ?? humanize(s.stage))}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
        <Section title={`Overdue tasks (${d.overdue.length})`}>
          <TaskList tasks={d.overdue} emptyText="No overdue tasks." />
        </Section>
      </div>
    </div>
  )
}
