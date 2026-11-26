import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, FileUp, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, PageHeader } from '@/components/common'
import { useCases, useMe } from '@/lib/api'
import { NewCaseDialog } from './NewCase'
import type { CaseView } from '@/lib/types'
import { cn } from '@/lib/utils'
import CaseTable from './CaseTable'

const VIEWS: { id: CaseView; label: string }[] = [
  { id: 'needs_attention', label: 'Needs attention' },
  { id: 'mine', label: 'Mine' },
  { id: 'stale', label: 'Stale tracker' },
  { id: 'access_blocked', label: 'Access blocked' },
  { id: 'missing_owner', label: 'Missing owners' },
  { id: 'all', label: 'All cases' },
]

export default function CasesPage() {
  const [params, setParams] = useSearchParams()
  const view = (params.get('view') as CaseView) || 'needs_attention'
  const q = params.get('q') ?? ''
  const cases = useCases(view, q)
  const me = useMe()
  const [creating, setCreating] = useState(false)
  const coordinator = !!me.data?.roles.some((r) => r === 'org_admin' || r === 'pmo_coordinator')

  return (
    <div>
      <PageHeader
        title="Cases"
        description="Each row puts the tracker's report next to what the evidence and the technical owner say."
        actions={
          <>
            <Button asChild variant="ghost" size="sm"><a href={`/api/export/cases.csv?view=${view}`} download><Download /> Export CSV</a></Button>
            {coordinator && <Button asChild variant="outline" size="sm"><Link to="/app/cases/import"><FileUp /> Import CSV</Link></Button>}
            {coordinator && <Button size="sm" onClick={() => setCreating(true)}><Plus /> New case</Button>}
          </>
        }
      />
      <NewCaseDialog open={creating} onOpenChange={setCreating} />
      <div className="mb-3 flex flex-wrap items-center gap-1">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            onClick={() => setParams(q ? { view: v.id, q } : { view: v.id })}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted',
              view === v.id && 'bg-background font-medium text-foreground shadow-sm ring-1 ring-border',
            )}
          >
            {v.label}
          </button>
        ))}
        {q && (
          <Button variant="ghost" size="sm" className="ml-2" onClick={() => setParams({ view })}>
            Search: “{q}” <X />
          </Button>
        )}
        {cases.data && <span className="ml-auto text-xs text-muted-foreground">{cases.data.length} cases</span>}
      </div>
      <div className="rounded-lg border bg-background">
        {cases.isLoading && <Loading />}
        {cases.error && <ErrorState error={cases.error} />}
        {cases.data && <CaseTable rows={cases.data} />}
        {cases.data && cases.data.length === 0 && view === 'needs_attention' && !q && (
          <p className="px-4 pb-3 text-xs text-muted-foreground">Nothing needs attention. Switch to “All cases”{coordinator ? ', or create a new case' : ''}.</p>
        )}
      </div>
    </div>
  )
}
