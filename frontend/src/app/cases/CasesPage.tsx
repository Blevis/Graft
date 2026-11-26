import { useSearchParams } from 'react-router-dom'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading, PageHeader } from '@/components/common'
import { useCases } from '@/lib/api'
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

  return (
    <div>
      <PageHeader
        title="Cases"
        description="Each row puts the tracker's report next to what the evidence and the technical owner say."
      />
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
      </div>
    </div>
  )
}
