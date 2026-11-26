import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Avatar, Empty, ErrorState, Loading, PageHeader, Pill, Section, StatStrip, StatTile } from '@/components/common'
import { useHome, useMe } from '@/lib/api'
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
        <StatTile label="Cases I can see" value={t?.cases ?? '—'} hint="within your roles and scope" />
        <StatTile label="Need attention" value={t?.needs_attention ?? '—'} tone={attention > 0 ? 'alert' : undefined} hint="open findings or gaps" />
        <StatTile label="Missing owners" value={t?.ownership_gaps ?? '—'} hint="a required responsibility is unassigned" />
        <StatTile label="My open tasks" value={t?.my_open_tasks ?? '—'} hint="assigned to you" />
        <StatTile label="Overdue tasks" value={t?.overdue_tasks ?? '—'} tone={overdue > 0 ? 'alert' : undefined} hint={`as of ${fmtDate(me.data?.org.as_of_date)}`} />
      </StatStrip>
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
