import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Avatar, Empty, ErrorState, Loading, PageHeader, Pill, Section, StatStrip, StatTile } from '@/components/common'
import { Ring, Segments, STATUS } from '@/components/charts'
import { useHome, useInsights, useMe } from '@/lib/api'
import { ACCESS_LABEL, fmtDate, fmtDateTime, humanize, roleLabel } from '@/lib/format'
import type { HomeSection, Me, Role } from '@/lib/types'
import SourceDialog from '@/components/SourceDialog'
import { AskBox } from '../cases/AiPanel'
import CaseTable from '../cases/CaseTable'
import TaskList from '../tasks/TaskList'

export default function HomePage() {
  const me = useMe()
  const [filter, setFilter] = useState<Role | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const home = useHome(filter)
  const pulse = useInsights().data
  const h = home.data
  const t = h?.totals

  const first = me.data?.user.name.split(' ')[0] ?? ''
  const attention = t?.needs_attention ?? 0
  const overdue = t?.overdue_tasks ?? 0

  return (
    <div className="ow-body">
      <PageHeader
        eyebrow={me.data ? roleLabel(me.data, filter ?? h?.context ?? me.data.working_role ?? me.data.role) : 'Home'}
        title={`Good day, ${first}`}
        description="Your work queue. Graft shows the evidence behind each status and who acts next."
        actions={
          h && h.roles.length > 1 ? (
            <div className="ow-toggle" role="group" aria-label="Show work for">
              {[null, ...h.roles].map((r) => (
                <button key={r ?? 'all'} type="button" aria-pressed={(filter ?? h.context) === r} onClick={() => setFilter(r)}>
                  {r ? roleLabel(me.data, r) : 'All my roles'}
                </button>
              ))}
            </div>
          ) : undefined
        }
      />
      {home.error && <ErrorState error={home.error} />}
      <div className="ow-grid major">
        <section className="ow-spot">
          <div className="ow-orbit" aria-hidden="true" />
          <div className="ow-spot-inner">
            <span className="ow-kicker">Today · as of {fmtDate(me.data?.org.as_of_date)}</span>
            <h2>
              {!t
                ? 'Loading your queue…'
                : attention > 0
                  ? `${attention} ${attention === 1 ? 'case needs' : 'cases need'} attention${overdue > 0 ? `, ${overdue} ${overdue === 1 ? 'task is' : 'tasks are'} overdue` : ''}.`
                  : 'Nothing needs attention right now.'}
            </h2>
            <p>
              A tracker status is one report among others. Open a case to see what the evidence says and what the
              technical owner decided.
            </p>
            <Link to="/app/cases?view=needs_attention" className="ow-link">
              Review cases
              <ArrowRight size={15} />
            </Link>
          </div>
          {t && t.cases > 0 && (
            <div className="ow-spot-aside">
              <Ring value={t.cases - attention} total={t.cases} label="Cases with no open flags" caption="of cases are clear" color="#cdb4fa" size={128} />
            </div>
          )}
        </section>
        <Section
          title="My open tasks"
          sub={t ? `${t.my_open_tasks} assigned to you` : undefined}
          actions={<Link className="ow-link" to="/app/tasks">All queues <ArrowRight size={15} /></Link>}
        >
          {home.isLoading ? <Loading /> : <TaskList tasks={(h?.my_tasks ?? []).slice(0, 4)} emptyText="Nothing assigned to you right now." />}
          {(h?.my_tasks.length ?? 0) > 4 && <p className="ow-note mt-2">Showing 4 of {h!.my_tasks.length}. Open Queues for the rest.</p>}
        </Section>
      </div>
      <StatStrip>
        <StatTile label="Cases I can see" value={t?.cases ?? '—'} hint="within your roles and scope" to="/app/cases?view=all" />
        <StatTile label="Need attention" value={t?.needs_attention ?? '—'} tone={attention > 0 ? 'alert' : undefined} hint="open findings or gaps" to="/app/cases?view=needs_attention" />
        <StatTile label="Missing owners" value={t?.ownership_gaps ?? '—'} hint="a required responsibility is unassigned" to="/app/cases?view=missing_owner" />
        <StatTile label="My open tasks" value={t?.my_open_tasks ?? '—'} hint="assigned to you" to="/app/tasks?queue=mine" />
        <StatTile label="Overdue tasks" value={t?.overdue_tasks ?? '—'} tone={overdue > 0 ? 'alert' : undefined} hint={`as of ${fmtDate(me.data?.org.as_of_date)}`} to="/app/tasks?queue=overdue" />
      </StatStrip>
      {pulse && pulse.totals.cases > 0 && (
        <Section
          title="Portfolio pulse"
          sub="Readiness checks, open flags and tracker freshness across the cases you can see."
          actions={<Link className="ow-link" to="/app/insights">Open Insights <ArrowRight size={15} /></Link>}
        >
          <div className="ow-pulse">
            <div className="ow-ring-row">
              <Ring value={pulse.checks.met} total={pulse.checks.required} label="Required checks met" caption="required checks met" size={112} />
              <ul className="ow-keyfacts">
                <li>Checks met <b>{pulse.checks.met} / {pulse.checks.required}</b></li>
                <li>Signed off <b>{pulse.readiness.signed_off}</b></li>
                <li>Reviews recorded <b>{pulse.totals.reviews_recorded}</b></li>
              </ul>
            </div>
            <div>
              <h3>Open flags by severity</h3>
              <Segments
                empty="No open flags."
                unit=" flags"
                parts={[
                  { key: 'high', name: 'High', value: pulse.by_severity.high, color: STATUS.bad },
                  { key: 'medium', name: 'Medium', value: pulse.by_severity.medium, color: STATUS.warn },
                  { key: 'low', name: 'Low', value: pulse.by_severity.low, color: STATUS.neutral },
                ]}
              />
            </div>
            <div>
              <h3>Tracker freshness</h3>
              <Segments
                empty="No cases in scope."
                unit=" cases"
                parts={[
                  { key: 'fresh', name: `Within ${pulse.tracker.stale_days} days`, value: pulse.tracker.age.fresh, color: STATUS.good },
                  { key: 'aging', name: 'Ageing', value: pulse.tracker.age.aging, color: STATUS.warn },
                  { key: 'stale', name: 'Stale', value: pulse.tracker.age.stale, color: STATUS.bad },
                  { key: 'missing', name: 'No date', value: pulse.tracker.age.missing, color: STATUS.neutral },
                ]}
              />
            </div>
          </div>
        </Section>
      )}
      <AskBox onOpenSource={setSource} compact />
      <SourceDialog id={source} onClose={() => setSource(null)} />
      {home.isLoading && <Loading />}
      {h?.sections.map((s) => <HomeBlock key={s.key} s={s} me={me.data} />)}
    </div>
  )
}

function HomeBlock({ s, me }: { s: HomeSection; me?: Me }) {
  return (
    <Section
      title={
        <>
          {s.title}
          <span className="ow-count">{s.items.length}</span>
        </>
      }
      sub={s.description}
      actions={<Pill tone="violet">{roleLabel(me, s.role)}</Pill>}
    >
      {s.items.length === 0 ? (
        <Empty>Nothing here right now.</Empty>
      ) : s.kind === 'cases' ? (
        <CaseTable rows={s.items} compact />
      ) : s.kind === 'access' ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case</TableHead>
              <TableHead>System</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Next step</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {s.items.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  <Link className="ow-identity hover:text-primary" to={`/app/cases/${a.case.ref}?tab=access`}>
                    <Avatar name={a.case.employee} />
                    <span>
                      <b>{a.case.employee}</b>
                      <small>{a.case.ref}</small>
                    </span>
                  </Link>
                </TableCell>
                <TableCell className="font-semibold">{a.system}</TableCell>
                <TableCell><Pill tone={a.state === 'confirmed_usable' ? 'green' : a.state === 'not_provisioned' ? 'red' : 'amber'}>{ACCESS_LABEL[a.state]}</Pill></TableCell>
                <TableCell className="text-sm">{a.action}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : s.kind === 'audit' ? (
        <ul className="divide-y text-[13px]">
          {s.items.map((e) => (
            <li key={e.id} className="flex justify-between gap-3 py-2 font-medium">
              <span>
                {e.actor?.name ?? 'System'} · {humanize(e.action)} {humanize(e.entity).toLowerCase()}
              </span>
              <span className="text-xs text-muted-foreground">{fmtDateTime(e.created_at)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="divide-y text-[13px]">
          {s.items.map((n, i) => (
            <li key={i} className="py-2">
              <Link className="font-semibold hover:text-primary" to={n.link}>
                {n.text}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
