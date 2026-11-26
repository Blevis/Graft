import { useState } from 'react'
import { CheckCircle2, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, NativeSelect, Pill, Section } from '@/components/common'
import { useCreateAccess, useUpdateAccess } from '@/lib/api'
import { ACCESS_LABEL, DASH, fmtDate } from '@/lib/format'
import type { AccessState, CaseDetail } from '@/lib/types'

const COORD_STATES: AccessState[] = ['requested', 'awaiting_approval', 'approved', 'not_provisioned', 'active']
const CLASS: Record<AccessState, string> = {
  requested: 'bg-slate-50 text-slate-700 ring-slate-200',
  awaiting_approval: 'bg-amber-50 text-amber-800 ring-amber-200',
  approved: 'bg-sky-50 text-sky-800 ring-sky-200',
  not_provisioned: 'bg-red-50 text-red-700 ring-red-200',
  active: 'bg-sky-50 text-sky-800 ring-sky-200',
  confirmed_usable: 'bg-primary/10 text-primary ring-primary/30',
}

export default function AccessTab({ d }: { d: CaseDetail }) {
  const update = useUpdateAccess()
  const create = useCreateAccess(d.case.id)
  const [system, setSystem] = useState('')
  const ref = (id: string) => d.sources.find((s) => s.id === id)?.ref ?? 'source'
  const onErr = (e: Error) => toast.error(e.message)

  return (
    <Section title="System access" actions={<span className="text-xs text-muted-foreground">Requested ≠ approved ≠ active ≠ usable. Only the designated tester's successful test (by default the employee's) counts as usable.</span>}>
      {d.access_items.length === 0 ? (
        <Empty>No systems are tracked for this case.</Empty>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>System</TableHead>
              <TableHead>Reported state</TableHead>
              <TableHead>Requested</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Tester</TableHead>
              <TableHead>Evidence</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {d.access_items.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">{a.system}</TableCell>
                <TableCell>
                  {d.permissions.can_edit_access && a.state !== 'confirmed_usable' ? (
                    <NativeSelect
                      className="w-48"
                      value={a.state}
                      onChange={(e) => update.mutate({ id: a.id, state: e.target.value as AccessState }, { onError: onErr })}
                    >
                      {COORD_STATES.map((s) => (
                        <option key={s} value={s}>{ACCESS_LABEL[s]}</option>
                      ))}
                    </NativeSelect>
                  ) : (
                    <Pill className={CLASS[a.state]}>{ACCESS_LABEL[a.state]}</Pill>
                  )}
                </TableCell>
                <TableCell>{fmtDate(a.requested_at)}</TableCell>
                <TableCell>{a.owner_role ?? DASH}</TableCell>
                <TableCell className="text-xs">
                  {a.tested_by ? (
                    <span>Tested by {a.tested_by.name} · {fmtDate(a.tested_at)}</span>
                  ) : (
                    a.tester?.name ?? 'Employee'
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs">{a.evidence_source_ids.map(ref).join(', ') || DASH}</TableCell>
                <TableCell className="text-right">
                  {d.permissions.can_confirm_access_ids.includes(a.id) && a.state !== 'confirmed_usable' && (
                    <Button size="sm" variant="outline" onClick={() => update.mutate({ id: a.id, state: 'confirmed_usable' }, { onError: onErr, onSuccess: () => toast.success(`${a.system} confirmed usable`) })}>
                      <CheckCircle2 /> I tested it, it works
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {d.permissions.can_edit_access && (
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { system: system.trim(), state: 'requested', requested_at: null, owner_role: 'Access Support' },
              { onSuccess: () => setSystem(''), onError: onErr },
            )
          }}
        >
          <Input value={system} onChange={(e) => setSystem(e.target.value)} placeholder="Track another system, e.g. Jira" className="max-w-xs" />
          <Button type="submit" variant="outline" disabled={system.trim().length < 2 || create.isPending}>
            <Plus /> Add system
          </Button>
        </form>
      )}
    </Section>
  )
}
