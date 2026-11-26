import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, PageHeader, Section, StatStrip, StatTile } from '@/components/common'
import { Bars, ChartCard, ChartEmpty, Columns, Ring, Segments, SERIES, STATUS, Steps } from '@/components/charts'
import { useInsights } from '@/lib/api'
import { ACCESS_LABEL, DISPOSITION_LABEL, fmtDate, humanize, READINESS_LABEL, RULE_LABEL, STAGE_LABEL } from '@/lib/format'
import type { AccessState, ReviewDisposition, Stage } from '@/lib/types'
import TaskList from '../tasks/TaskList'
import OutcomeMetrics from './OutcomeMetrics'

const SEVERE = (rule: string) => !(rule.startsWith('MISSING') || rule === 'STALE_TRACKER')
const ACCESS_TONE: Partial<Record<AccessState, 'good' | 'warn' | 'bad'>> = { not_provisioned: 'bad', active: 'warn', confirmed_usable: 'good' }
const DUE_LABEL = { overdue: 'Overdue', this_week: 'Due this week', next_week: 'Due next week', later: 'Later', no_date: 'No due date' } as const
const DUE_COLOR = { overdue: STATUS.bad, this_week: STATUS.warn, next_week: STATUS.accent, later: STATUS.soft, no_date: STATUS.neutral } as const
const day = (iso: string) => fmtDate(iso).replace(/ \d{4}$/, '')

export default function InsightsPage() {
  const q = useInsights()
  if (q.isLoading) return <Loading />
  if (q.error) return <ErrorState error={q.error} />
  const d = q.data!
  const attention = d.totals.cases_needing_attention
  const flags = d.by_severity.high + d.by_severity.medium + d.by_severity.low
  const judged = d.evidence.claims + d.evidence.rejected
  const stages = d.stage_distribution.map((s) => ({
    key: s.stage,
    name: s.stage === 'none' ? 'No review yet' : (STAGE_LABEL[s.stage as Stage] ?? humanize(s.stage)),
    value: s.count,
    tone: s.stage === 'validated' ? ('good' as const) : undefined,
  }))
  // Every stage keeps its place in the sequence, including the ones nobody has reached.
  const pipeline = [
    stages.find((s) => s.key === 'none') ?? { key: 'none', name: 'No review yet', value: 0, tone: undefined },
    ...(Object.keys(STAGE_LABEL) as Stage[]).map((k) => stages.find((s) => s.key === k) ?? { key: k, name: STAGE_LABEL[k], value: 0, tone: undefined }),
  ]

  return (
    <div className="ow-body">
      <PageHeader
        eyebrow="Reporting"
        title="Insights"
        description={`Readiness, evidence and follow-up across the cases you can see, as of ${fmtDate(d.as_of_date)}. Hover any mark for its number, or switch a card to its table.`}
        actions={<Button asChild variant="outline"><a href="/api/export/cases.csv?view=all" download><Download /> Export CSV</a></Button>}
      />
      <StatStrip>
        <StatTile label="Cases" value={d.totals.cases} hint="in your scope" to="/app/cases?view=all" />
        <StatTile label="Need attention" value={attention} tone={attention ? 'alert' : undefined} hint="open flags or gaps" to="/app/cases?view=needs_attention" />
        <StatTile label="Open flags" value={flags} hint={`${d.by_severity.high} high · ${d.by_severity.medium} medium · ${d.by_severity.low} low`} />
        <StatTile label="Open follow-ups" value={d.totals.open_tasks} tone={d.totals.overdue_tasks ? 'alert' : undefined} hint={`${d.totals.overdue_tasks} overdue`} to="/app/tasks?queue=overdue" />
        <StatTile label="Signed off" value={d.readiness.signed_off} tone="ok" hint={`${d.readiness.reopened} reopened · ${d.readiness.not_signed_off} not signed off`} />
      </StatStrip>

      <div className="ow-grid equal">
        <ChartCard
          title="Portfolio readiness"
          sub="Required checks met across all cases, and where each case stands with its technical owner."
          table={{
            head: ['Measure', 'Count'],
            rows: [
              ['Required checks met', `${d.checks.met} of ${d.checks.required}`],
              ...(['signed_off', 'reopened', 'not_signed_off'] as const).map((k) => [READINESS_LABEL[k], d.readiness[k]]),
            ],
          }}
          footer="Readiness is recorded by the technical owner. Nothing here is decided by the tracker or by AI."
        >
          <div className="ow-ring-row">
            <Ring value={d.checks.met} total={d.checks.required} label="Required checks met" caption={`${d.checks.met} of ${d.checks.required} checks`} />
            <div>
              <Segments
                empty="No cases in scope."
                unit=" cases"
                parts={[
                  { key: 'signed_off', name: 'Signed off', value: d.readiness.signed_off, color: STATUS.good },
                  { key: 'reopened', name: 'Reopened', value: d.readiness.reopened, color: STATUS.warn },
                  { key: 'not_signed_off', name: 'Not signed off', value: d.readiness.not_signed_off, color: STATUS.neutral },
                ]}
              />
            </div>
          </div>
          <ul className="ow-keyfacts mt-5">
            <li>Cases with every required check met <b>{d.progress.filter((p) => p.required > 0 && p.met === p.required).length}</b></li>
            <li>Cases with a recorded technical review <b>{d.totals.reviews_recorded}</b></li>
            <li>Cases without a checklist template <b>{d.progress.filter((p) => p.required === 0).length}</b></li>
          </ul>
        </ChartCard>

        <ChartCard
          title="Open flags"
          sub="What the rules found in the evidence, by severity and by reason."
          table={{ head: ['Reason', 'Cases'], rows: d.by_rule.map((r) => [RULE_LABEL[r.rule_id] ?? r.rule_id, r.count]) }}
        >
          <Segments
            empty="No open flags."
            unit=" flags"
            parts={[
              { key: 'high', name: 'High', value: d.by_severity.high, color: STATUS.bad },
              { key: 'medium', name: 'Medium', value: d.by_severity.medium, color: STATUS.warn },
              { key: 'low', name: 'Low', value: d.by_severity.low, color: STATUS.neutral },
            ]}
          />
          {d.by_rule.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <Bars
                rows={d.by_rule.map((r) => ({
                  key: r.rule_id,
                  name: RULE_LABEL[r.rule_id] ?? r.rule_id,
                  value: r.count,
                  note: SEVERE(r.rule_id) ? 'High severity' : 'Medium severity',
                  color: SEVERE(r.rule_id) ? STATUS.bad : STATUS.warn,
                }))}
              />
            </div>
          )}
        </ChartCard>
      </div>

      <div className="ow-grid equal">
        <ChartCard
          title="Readiness progress by case"
          sub="Required checks met on each case. Select a row to open the case."
          table={{ head: ['Case', 'Employee', 'Met', 'Required', 'Status'], rows: d.progress.map((p) => [p.ref, p.employee, p.met, p.required, READINESS_LABEL[p.readiness]]) }}
        >
          <Bars
            empty="No cases in scope."
            rows={d.progress.filter((p) => p.required > 0).slice(0, 12).map((p) => ({
              key: p.ref,
              name: `${p.employee} (${p.ref})`,
              label: p.employee,
              value: p.met,
              of: p.required,
              note: READINESS_LABEL[p.readiness],
              to: `/app/cases/${p.ref}`,
              color: p.readiness === 'signed_off' ? STATUS.good : STATUS.accent,
            }))}
          />
          {d.progress.filter((p) => p.required > 0).length > 12 && <p className="ow-note mt-2">Showing the first 12 cases. The table view lists all of them.</p>}
        </ChartCard>

        <ChartCard
          title="Observed knowledge-transfer stage"
          sub="Where technical owners last observed each employee, in stage order."
          table={{ head: ['Stage', 'Cases'], rows: pipeline.map((s) => [s.name, s.value]) }}
          footer="Stages come from recorded reviews. Shadowing, supported execution and independent execution are different things."
        >
          <Steps steps={pipeline} empty="No cases in scope." />
          <div className="mt-4 border-t pt-3">
            <Bars
              empty="No reviews recorded yet."
              rows={d.review_states.map((r) => ({
                key: r.state,
                name: r.state === 'none' ? 'Not reviewed' : DISPOSITION_LABEL[r.state as ReviewDisposition],
                value: r.count,
                color: r.state === 'close' ? STATUS.good : r.state === 'none' ? STATUS.neutral : STATUS.accent,
              }))}
            />
          </div>
        </ChartCard>
      </div>

      <div className="ow-grid equal">
        <ChartCard
          title="What the tracker reports"
          sub="Reported status per case, and how old each report is. A tracker status is one report among others."
          table={{ head: ['Tracker status', 'Cases'], rows: d.tracker.by_status.map((t) => [t.status, t.count]) }}
        >
          <Bars empty="No cases in scope." rows={d.tracker.by_status.map((t) => ({ key: t.status, name: t.status, value: t.count }))} />
          <div className="mt-4 border-t pt-3.5">
            <Segments
              unit=" cases"
              parts={[
                { key: 'fresh', name: `Updated within ${d.tracker.stale_days} days`, value: d.tracker.age.fresh, color: STATUS.good },
                { key: 'aging', name: `${d.tracker.stale_days + 1}–${d.tracker.stale_days * 2} days old`, value: d.tracker.age.aging, color: STATUS.warn },
                { key: 'stale', name: `Older than ${d.tracker.stale_days * 2} days`, value: d.tracker.age.stale, color: STATUS.bad },
                { key: 'missing', name: 'No update date', value: d.tracker.age.missing, color: STATUS.neutral },
              ]}
            />
          </div>
        </ChartCard>

        <ChartCard
          title="System access"
          sub={`${d.access.systems} tracked ${d.access.systems === 1 ? 'system' : 'systems'}, ${d.access.cases_blocked} ${d.access.cases_blocked === 1 ? 'case' : 'cases'} waiting on access.`}
          table={{ head: ['State', 'Systems'], rows: d.access.by_state.map((a) => [ACCESS_LABEL[a.state], a.count]) }}
          footer="Requested, approved and active are not usable. Only a successful test by the designated tester counts."
        >
          <Steps
            empty="No system access is tracked on these cases."
            steps={d.access.by_state.map((a) => ({ key: a.state, name: ACCESS_LABEL[a.state], value: a.count, tone: ACCESS_TONE[a.state] }))}
          />
        </ChartCard>
      </div>

      <div className="ow-grid major">
        <ChartCard
          title="Evidence received"
          sub={`Sources dated in the last ${d.evidence.by_day.length} days, by the date on the source.`}
          table={{ head: ['Date', 'Sources'], rows: d.evidence.by_day.filter((x) => x.count > 0).map((x) => [fmtDate(x.date), x.count]) }}
        >
          <Columns
            unit={['source', 'sources']}
            data={d.evidence.by_day.map((x, i) => ({ key: x.date, label: fmtDate(x.date), value: x.count, tick: i % 7 === 0 ? day(x.date) : undefined }))}
          />
          {d.evidence.by_kind.length > 0 && (
            <div className="mt-4 border-t pt-3.5">
              <Segments
                unit=" sources"
                parts={d.evidence.by_kind.slice(0, 4).map((k, i) => ({ key: k.kind, name: humanize(k.kind), value: k.count, color: SERIES[i] }))}
              />
            </div>
          )}
        </ChartCard>

        <ChartCard
          title="AI trust layer"
          sub="Every extracted claim must quote its source exactly once. The verifier rejects the rest."
          table={{ head: ['Measure', 'Count'], rows: [['Sources', d.evidence.sources], ['Verified claims', d.evidence.claims], ['Rejected by the verifier', d.evidence.rejected]] }}
          footer="Rejected candidates never reach a rule, a flag or this page's other figures."
        >
          {d.evidence.claim_sources === 0 ? (
            <ChartEmpty>Claims are visible to the case team. Your role sees summaries, so there is nothing to chart here.</ChartEmpty>
          ) : (
            <div className="ow-ring-row">
              <Ring value={d.evidence.claims} total={judged} label="Claims that passed verification" caption="passed the verifier" color={STATUS.good} />
              <ul className="ow-keyfacts">
                <li>Sources analysed <b>{d.evidence.claim_sources}</b></li>
                <li>Verified claims <b>{d.evidence.claims}</b></li>
                <li>Rejected by the verifier <b>{d.evidence.rejected}</b></li>
              </ul>
            </div>
          )}
        </ChartCard>
      </div>

      <div className="ow-grid equal">
        <ChartCard
          title="Flagged cases by project"
          sub="Cases with a high or medium flag, out of all cases on the project."
          table={{ head: ['Project', 'Flagged', 'Cases'], rows: d.by_project.map((p) => [p.project, p.flagged, p.cases]) }}
        >
          <Bars
            empty="No projects in scope."
            rows={d.by_project.map((p) => ({ key: p.project, name: p.project, value: p.flagged, of: p.cases, color: STATUS.bad, note: 'flagged of all cases' }))}
          />
        </ChartCard>

        <ChartCard
          title="Follow-ups in flight"
          sub="Open tasks by due date, and who is carrying them."
          table={{ head: ['Owner', 'Open', 'Overdue'], rows: d.workload.map((w) => [w.owner, w.open, w.overdue]) }}
        >
          <Segments
            empty="No open follow-ups."
            unit=" tasks"
            parts={(Object.keys(DUE_LABEL) as (keyof typeof DUE_LABEL)[]).map((k) => ({ key: k, name: DUE_LABEL[k], value: d.due[k], color: DUE_COLOR[k] }))}
          />
          {d.workload.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <Bars
                rows={d.workload.slice(0, 8).map((w) => ({
                  key: w.owner, name: w.owner, value: w.open, note: w.overdue ? `${w.overdue} overdue` : 'none overdue',
                  color: w.overdue ? STATUS.bad : STATUS.accent,
                }))}
              />
            </div>
          )}
        </ChartCard>
      </div>

      <OutcomeMetrics />

      <Section title={<>Overdue tasks<span className="ow-count">{d.overdue.length}</span></>} sub="Past due and not waiting.">
        <TaskList tasks={d.overdue} emptyText="No overdue tasks." />
      </Section>
    </div>
  )
}
