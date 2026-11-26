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
    <Section title="Activity" sub="Evidence, analysis, flags, tasks and decisions in one chronological record.">
      {(t.data ?? []).length === 0 ? (
        <Empty>No activity yet.</Empty>
      ) : (
        <ol className="ow-timeline">
          {t.data!.map((e) => {
            const Icon = ICON[e.type]
            return (
              <li key={e.id}>
                <span className="ow-tile-icon"><Icon size={16} /></span>
                <div>
                  <div className="text-sm font-semibold">{e.title}</div>
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
