import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorState, Loading, PageHeader, Pill, Section, StatTile } from '@/components/common'
import { useHome, useMe } from '@/lib/api'
import { ACCESS_LABEL, fmtDate, fmtDateTime, humanize, roleLabel } from '@/lib/format'
import type { HomeSection, Me, Role } from '@/lib/types'
import { cn } from '@/lib/utils'
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

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Good day, ${me.data?.user.name.split(' ')[0] ?? ''}`}
        description={
          me.data
            ? `Your work queue across ${me.data.roles.map((r) => roleLabel(me.data, r)).join(', ')}. Graft shows the evidence behind each status and who acts next.`
            : ''
        }
      />
      {home.error && <ErrorState error={home.error} />}
      {h && h.roles.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="mr-1 text-xs text-muted-foreground">Show work for</span>
          {[null, ...h.roles].map((r) => (
            <button
              key={r ?? 'all'}
              onClick={() => setFilter(r)}
              className={cn(
                'rounded-md px-2.5 py-1 text-xs ring-1 ring-inset',
                (filter ?? h.context) === r ? 'bg-primary/10 font-medium text-primary ring-primary/30' : 'ring-border hover:bg-muted',
              )}
            >
              {r ? roleLabel(me.data, r) : 'All my roles'}
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Cases I can see" value={t?.cases ?? '—'} />
        <StatTile label="Need attention" value={t?.needs_attention ?? '—'} tone="alert" />
        <StatTile label="Missing owners" value={t?.ownership_gaps ?? '—'} hint="cases with an unassigned required responsibility" />
        <StatTile label="My open tasks" value={t?.my_open_tasks ?? '—'} />
        <StatTile label="Overdue tasks" value={t?.overdue_tasks ?? '—'} hint={`as of ${fmtDate(me.data?.org.as_of_date)}`} />
      </div>
      <Section title="My open tasks" actions={<Button asChild variant="ghost" size="sm"><Link to="/app/tasks">All tasks <ArrowRight /></Link></Button>}>
        {home.isLoading ? <Loading /> : <TaskList tasks={h?.my_tasks ?? []} emptyText="Nothing assigned to you right now." />}
      </Section>
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
        <span className="flex items-center gap-2">
          {s.title}
          <Pill className="bg-muted text-muted-foreground ring-border">{roleLabel(me, s.role)}</Pill>
          <span className="text-xs font-normal text-muted-foreground">{s.items.length}</span>
        </span>
      }
    >
      <p className="-mt-1 mb-2 text-xs text-muted-foreground">{s.description}</p>
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
                  <Link className="font-mono text-xs hover:underline" to={`/app/cases/${a.case.ref}?tab=access`}>
                    {a.case.ref}
                  </Link>{' '}
                  {a.case.employee}
                </TableCell>
                <TableCell className="font-medium">{a.system}</TableCell>
                <TableCell>{ACCESS_LABEL[a.state]}</TableCell>
                <TableCell className="text-sm">{a.action}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : s.kind === 'audit' ? (
        <ul className="divide-y text-sm">
          {s.items.map((e) => (
            <li key={e.id} className="flex justify-between gap-3 py-1.5">
              <span>
                {e.actor?.name ?? 'System'} · {humanize(e.action)} {humanize(e.entity).toLowerCase()}
              </span>
              <span className="text-xs text-muted-foreground">{fmtDateTime(e.created_at)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="space-y-1 text-sm">
          {s.items.map((n, i) => (
            <li key={i}>
              <Link className="hover:underline" to={n.link}>
                {n.text}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
