import { Link, useNavigate } from 'react-router-dom'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Avatar, Empty, Pill, SeverityBadge } from '@/components/common'
import { ageLabel, DASH, DISPOSITION_LABEL, fmtDate, ROLE_LABEL, STAGE_LABEL } from '@/lib/format'
import type { CaseRow } from '@/lib/types'
import { cn } from '@/lib/utils'

export function ReviewStatePill({ state }: { state: CaseRow['review_state'] }) {
  if (state === 'none') return <Pill className="bg-slate-50 text-slate-600 ring-slate-200">Not reviewed</Pill>
  const cls = state === 'keep_open' ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-primary/10 text-primary ring-primary/30'
  return <Pill className={cls}>{DISPOSITION_LABEL[state]}</Pill>
}

export default function CaseTable({ rows, compact }: { rows: CaseRow[]; compact?: boolean }) {
  const navigate = useNavigate()
  if (rows.length === 0) return <Empty>No cases in this view.</Empty>
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Employee</TableHead>
          {!compact && <TableHead>Project</TableHead>}
          <TableHead>Tracker report</TableHead>
          <TableHead>Why it needs attention</TableHead>
          {!compact && <TableHead>Next task</TableHead>}
          <TableHead>Technical review</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id} className="cursor-pointer" onClick={() => navigate(`/app/cases/${r.ref}`)}>
            <TableCell>
              <Link to={`/app/cases/${r.ref}`} onClick={(e) => e.stopPropagation()} className="ow-identity group/id">
                <Avatar name={r.employee} />
                <span>
                  <b className="group-hover/id:text-primary">{r.employee}</b>
                  <small>{r.ref}</small>
                </span>
              </Link>
            </TableCell>
            {!compact && <TableCell>{r.project ?? DASH}</TableCell>}
            <TableCell>
              <div className="font-semibold">{r.tracker_status ?? DASH}</div>
              <div className={cn('text-xs text-muted-foreground', (r.tracker_age_days ?? 0) > 7 && 'font-semibold text-[#875800]')}>
                updated {ageLabel(r.tracker_age_days)}
              </div>
            </TableCell>
            <TableCell className="whitespace-normal">
              <div className="flex max-w-md flex-wrap gap-1.5">
                {r.reasons.length === 0 && !r.ownership_gaps?.length ? (
                  <span className="text-xs text-muted-foreground">No open flags</span>
                ) : (
                  r.reasons.map((x) => (
                    <span key={x.rule_id} title={x.message}>
                      <SeverityBadge severity={x.severity} rule={x.rule_id} />
                    </span>
                  ))
                )}
                {r.ownership_gaps?.map((g) => (
                  <Pill key={g} className="border-dashed bg-background text-amber-800 ring-amber-300" title="Required responsibility nobody holds">
                    No {ROLE_LABEL[g].split(' /')[0].toLowerCase()}
                  </Pill>
                ))}
                {r.note && <span className="w-full text-xs text-muted-foreground">{r.note}</span>}
              </div>
            </TableCell>
            {!compact && (
              <TableCell className="max-w-56 whitespace-normal">
                {r.next_task ? (
                  <div>
                    <div className="truncate font-semibold">{r.next_task.title}</div>
                    <div className={cn('text-xs text-muted-foreground', r.next_task.overdue && 'font-semibold text-[#a2374b]')}>
                      {r.next_task.owner_name ?? DASH} · due {fmtDate(r.next_task.due_date)}
                      {r.next_task.overdue && ' · overdue'}
                    </div>
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">{DASH}</span>
                )}
              </TableCell>
            )}
            <TableCell>
              <ReviewStatePill state={r.review_state} />
              {r.stage && <div className="mt-0.5 text-xs text-muted-foreground">{STAGE_LABEL[r.stage]}</div>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
