import { Link } from 'react-router-dom'
import { Check, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Empty, Pill } from '@/components/common'
import { useMe, useSetTaskStatus } from '@/lib/api'
import { fmtDate, fmtDateTime, ROLE_LABEL } from '@/lib/format'
import type { Task } from '@/lib/types'
import { cn } from '@/lib/utils'

export function canChangeTask(t: Task, userId?: string, role?: string) {
  return t.owner_user?.id === userId || (!t.owner_user && t.owner_role === role) || role === 'admin'
}

export default function TaskList({ tasks, emptyText, showCase = true }: { tasks: Task[]; emptyText: string; showCase?: boolean }) {
  const me = useMe()
  const setStatus = useSetTaskStatus()
  if (tasks.length === 0) return <Empty>{emptyText}</Empty>
  return (
    <ul className="divide-y">
      {tasks.map((t) => {
        const mine = canChangeTask(t, me.data?.user.id, me.data?.role)
        return (
          <li key={t.id} className="flex items-start justify-between gap-4 py-2.5">
            <div className="min-w-0">
              <div className={cn('text-sm font-medium', t.status === 'done' && 'text-muted-foreground line-through')}>{t.title}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                {showCase && t.case && (
                  <Link to={`/app/cases/${t.case.ref}`} className="font-mono hover:underline">
                    {t.case.ref} · {t.case.employee}
                  </Link>
                )}
                <span>Owner: {t.owner_user?.name ?? (t.owner_role ? ROLE_LABEL[t.owner_role] : '—')}</span>
                <span className={cn(t.overdue && 'font-medium text-red-700')}>
                  Due {fmtDate(t.due_date)}
                  {t.overdue && ' · overdue'}
                </span>
                {t.origin === 'ai_suggested_edited' && <Pill className="bg-violet-50 text-violet-800 ring-violet-200">AI-drafted, human-edited</Pill>}
                {t.status === 'done' && <span>Done {fmtDateTime(t.completed_at)}</span>}
                {t.created_by && <span>Assigned by {t.created_by.name}</span>}
              </div>
            </div>
            {mine && (
              <Button
                size="sm"
                variant={t.status === 'open' ? 'outline' : 'ghost'}
                disabled={setStatus.isPending}
                onClick={() =>
                  setStatus.mutate(
                    { id: t.id, status: t.status === 'open' ? 'done' : 'open' },
                    { onError: (e) => toast.error(e.message), onSuccess: () => toast.success(t.status === 'open' ? 'Task done' : 'Task reopened') },
                  )
                }
              >
                {t.status === 'open' ? <><Check /> Mark done</> : <><RotateCcw /> Reopen</>}
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
