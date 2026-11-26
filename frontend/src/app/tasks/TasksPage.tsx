import { useState } from 'react'
import { ErrorState, Loading, PageHeader } from '@/components/common'
import { useTasks } from '@/lib/api'
import { cn } from '@/lib/utils'
import TaskList from './TaskList'

const FILTERS = [
  { mine: true, status: 'open', label: 'My open' },
  { mine: false, status: 'open', label: 'All open' },
  { mine: false, status: 'done', label: 'Done' },
] as const

export default function TasksPage() {
  const [i, setI] = useState(0)
  const f = FILTERS[i]
  const tasks = useTasks(f.mine, f.status)
  return (
    <div>
      <PageHeader title="Tasks" description="Follow-ups assigned by coordinators. Only a task's owner can mark it done." />
      <div className="mb-3 flex gap-1">
        {FILTERS.map((x, idx) => (
          <button
            key={x.label}
            onClick={() => setI(idx)}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted',
              i === idx && 'bg-background font-medium text-foreground shadow-sm ring-1 ring-border',
            )}
          >
            {x.label}
          </button>
        ))}
      </div>
      <div className="rounded-lg border bg-background px-4">
        {tasks.isLoading && <Loading />}
        {tasks.error && <ErrorState error={tasks.error} />}
        {tasks.data && <TaskList tasks={tasks.data} emptyText="No tasks in this list." />}
      </div>
    </div>
  )
}
