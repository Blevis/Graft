import { Link, useSearchParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { Avatar, Empty, ErrorState, Loading, PageHeader, Pill, Section } from '@/components/common'
import { useQueue, useQueues } from '@/lib/api'
import { READINESS_LABEL } from '@/lib/format'
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
  const current = (queues.data ?? []).find((x) => x.key === key)
  return (
    <div>
      <PageHeader
        eyebrow="Work"
        title="Work queues"
        description="Shared, claimable work with assignment history. Only a task's owner marks it done."
      />
      <div className="ow-filterbar">
        <div role="tablist" aria-label="Queues" className="ow-toggle">
          {(queues.data ?? []).map((x) => (
            <button key={x.key} role="tab" aria-selected={key === x.key} aria-pressed={key === x.key} onClick={() => setParams({ queue: x.key })}>
              {x.label} <em>{x.count}</em>
            </button>
          ))}
        </div>
      </div>
      <Section title={current?.label ?? 'Queue'} sub={HINT[key]}>
        {(q.isLoading || queues.isLoading) && <Loading />}
        {q.error && <ErrorState error={q.error} />}
        {q.data?.kind === 'tasks' && <TaskList tasks={q.data.items} emptyText="Nothing in this queue." />}
        {q.data?.kind === 'cases' &&
          (q.data.items.length === 0 ? (
            <Empty>No case is ready for final sign-off.</Empty>
          ) : (
            <div className="ow-rows">
              {q.data.items.map((c) => (
                <Link key={c.ref} to={`/app/cases/${c.ref}`} className="ow-row">
                  <Avatar name={c.employee} />
                  <span className="ow-row-text">
                    <b>{c.employee}</b>
                    <small>{c.ref}</small>
                  </span>
                  <Pill tone="green">{READINESS_LABEL[c.readiness]} · checks met</Pill>
                  <ChevronRight size={16} />
                </Link>
              ))}
            </div>
          ))}
      </Section>
    </div>
  )
}
