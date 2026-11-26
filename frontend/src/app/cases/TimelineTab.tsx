import { Bot, CheckCircle2, ClipboardCheck, FileText, Flag, GraduationCap, ListTodo, UserMinus, UserPlus } from 'lucide-react'
import { Empty, ErrorState, Loading, Section } from '@/components/common'
import { useTimeline } from '@/lib/api'
import { fmtDateTime } from '@/lib/format'
import type { TimelineEvent } from '@/lib/types'

const ICON: Record<TimelineEvent['type'], typeof FileText> = {
  source_received: FileText,
  analysis_run: Bot,
  finding_raised: Flag,
  task_created: ListTodo,
  task_done: CheckCircle2,
  review_saved: ClipboardCheck,
  training_recorded: GraduationCap,
  responsibility_assigned: UserPlus,
  responsibility_ended: UserMinus,
}

export default function TimelineTab({ caseId }: { caseId: string }) {
  const t = useTimeline(caseId)
  if (t.isLoading) return <Loading />
  if (t.error) return <ErrorState error={t.error} />
  return (
    <Section title="Activity">
      {(t.data ?? []).length === 0 ? (
        <Empty>No activity yet.</Empty>
      ) : (
        <ol className="space-y-3">
          {t.data!.map((e) => {
            const Icon = ICON[e.type]
            return (
              <li key={e.id} className="flex gap-3">
                <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div>
                  <div className="text-sm">{e.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {fmtDateTime(e.at)}
                    {e.actor ? ` · ${e.actor}` : ''}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Section>
  )
}
