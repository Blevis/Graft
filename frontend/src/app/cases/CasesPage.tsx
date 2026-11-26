import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, FileUp, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, PageHeader, Segmented } from '@/components/common'
import { useCases, useMe } from '@/lib/api'
import { NewCaseDialog } from './NewCase'
import type { CaseView } from '@/lib/types'
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
        eyebrow="Portfolio"
        title="Cases"
        description="Each row puts the tracker's report next to what the evidence and the technical owner say."
        actions={
          <>
            <Button asChild variant="ghost"><a href={`/api/export/cases.csv?view=${view}`} download><Download /> Export CSV</a></Button>
            {coordinator && <Button asChild variant="outline"><Link to="/app/cases/import"><FileUp /> Import CSV</Link></Button>}
            {coordinator && <Button onClick={() => setCreating(true)}><Plus /> New case</Button>}
          </>
        }
      />
      <NewCaseDialog open={creating} onOpenChange={setCreating} />
      <div className="ow-filterbar">
        <Segmented label="Case view" options={VIEWS} value={view} onChange={(v) => setParams(q ? { view: v, q } : { view: v })} />
        {q && (
          <Button variant="outline" size="sm" onClick={() => setParams({ view })}>
            Search: “{q}” <X />
          </Button>
        )}
        {cases.data && <span className="ow-meta">{cases.data.length} {cases.data.length === 1 ? 'case' : 'cases'}</span>}
      </div>
      <section className="ow-panel">
        {cases.isLoading && <Loading />}
        {cases.error && <ErrorState error={cases.error} />}
        {cases.data && <CaseTable rows={cases.data} />}
        {cases.data && cases.data.length === 0 && view === 'needs_attention' && !q && (
          <p className="ow-note">Nothing needs attention. Switch to “All cases”{coordinator ? ', or create a new case' : ''}.</p>
        )}
      </section>
    </div>
  )
}
