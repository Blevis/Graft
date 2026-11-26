import { Link, useSearchParams } from 'react-router-dom'
import { Empty, ErrorState, Loading, PageHeader, Pill } from '@/components/common'
import { useQueue, useQueues } from '@/lib/api'
import { READINESS_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import TaskList from './TaskList'

const HINT: Record<string, string> = {
  mine: 'Work assigned to you by name.',
  claimable: 'Shared queues for roles you hold on these cases. Claim a task to own it.',
  unowned: 'Work Graft could not route: nobody holds the needed responsibility. Assign or claim it.',
  overdue: 'Past due and not waiting. Owners are reminded; coordinators see escalations.',
  waiting: 'Paused with a stated reason; the SLA clock is stopped.',
  review_ready: 'Every required check is met; the technical owner can record the final sign-off.',
}

/** Work queues: server-owned saved filters over the tasks and cases you may see. */
export default function TasksPage() {
  const queues = useQueues()
  const [params, setParams] = useSearchParams()
  const key = params.get('queue') ?? 'mine'
  const q = useQueue(key)
  return (
    <div>
      <PageHeader title="Work queues" description="Shared, claimable work with assignment history. Only a task's owner marks it done." />
      <div role="tablist" aria-label="Queues" className="mb-3 flex flex-wrap gap-1">
        {(queues.data ?? []).map((x) => (
          <button
            key={x.key}
            role="tab"
            aria-selected={key === x.key}
            onClick={() => setParams({ queue: x.key })}
            className={cn('rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted', key === x.key && 'bg-background font-medium text-foreground shadow-sm ring-1 ring-border')}
          >
            {x.label} <span className="ml-1 text-xs tabular-nums">{x.count}</span>
          </button>
        ))}
      </div>
      <p className="mb-2 text-xs text-muted-foreground">{HINT[key]}</p>
      <div className="rounded-lg border bg-background px-4">
        {(q.isLoading || queues.isLoading) && <Loading />}
        {q.error && <div className="py-3"><ErrorState error={q.error} /></div>}
        {q.data?.kind === 'tasks' && <TaskList tasks={q.data.items} emptyText="Nothing in this queue." />}
        {q.data?.kind === 'cases' &&
          (q.data.items.length === 0 ? (
            <Empty>No case is ready for final sign-off.</Empty>
          ) : (
            <ul className="divide-y">
              {q.data.items.map((c) => (
                <li key={c.ref} className="flex items-center justify-between py-2.5 text-sm">
                  <Link to={`/app/cases/${c.ref}`} className="hover:underline"><span className="font-mono text-xs">{c.ref}</span> {c.employee}</Link>
                  <Pill className="bg-primary/10 text-primary ring-primary/30">{READINESS_LABEL[c.readiness]} · checks met</Pill>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </div>
  )
}
