import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, PageHeader, Section, StatTile } from '@/components/common'
import { useCases, useInsights, useMe, useTasks } from '@/lib/api'
import { ROLE_LABEL } from '@/lib/format'
import CaseTable from '../cases/CaseTable'
import TaskList from '../tasks/TaskList'

export default function HomePage() {
  const me = useMe()
  const insights = useInsights()
  const attention = useCases('needs_attention')
  const myTasks = useTasks(true, 'open')
  const t = insights.data?.totals

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Good day, ${me.data?.user.name.split(' ')[0] ?? ''}`}
        description={`Signed in as ${me.data ? ROLE_LABEL[me.data.role] : ''}. Graft shows the evidence behind each status and who acts next.`}
      />
      {insights.error && <ErrorState error={insights.error} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Need attention" value={t?.cases_needing_attention ?? '—'} hint={`of ${t?.cases ?? '—'} cases`} tone="alert" />
        <StatTile label="My open tasks" value={myTasks.data?.length ?? '—'} />
        <StatTile label="Overdue tasks" value={t?.overdue_tasks ?? '—'} hint={`as of ${insights.data?.as_of_date ?? ''}`} />
        <StatTile label="Technical reviews" value={t?.reviews_recorded ?? '—'} hint="cases with a recorded decision" tone="ok" />
      </div>
      <Section
        title="My open tasks"
        actions={<Button asChild variant="ghost" size="sm"><Link to="/app/tasks">All tasks <ArrowRight /></Link></Button>}
      >
        {myTasks.isLoading ? <Loading /> : <TaskList tasks={myTasks.data ?? []} emptyText="Nothing assigned to you right now." />}
      </Section>
      <Section
        title="Needs attention"
        actions={<Button asChild variant="ghost" size="sm"><Link to="/app/cases">All cases <ArrowRight /></Link></Button>}
      >
        {attention.isLoading ? <Loading /> : <CaseTable rows={attention.data ?? []} compact />}
      </Section>
    </div>
  )
}
