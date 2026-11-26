import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorState, Loading } from '@/components/common'
import { useSource } from '@/lib/api'
import { fmtDate } from '@/lib/format'

/** Opens one source by id through GET /api/sources/{id}: the server decides whether the current user may read it. */
export default function SourceDialog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const q = useSource(id)
  const s = q.data
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{s ? `${s.ref ?? 'Source'} · ${s.title ?? ''}` : 'Source'}</DialogTitle>
          <DialogDescription>
            {s ? `${s.author_role ?? 'Sender not stated'} · ${fmtDate(s.date)} · version ${s.version}${s.case ? ` · ${s.case.ref} ${s.case.employee}` : ''}` : 'Original evidence, verbatim'}
          </DialogDescription>
        </DialogHeader>
        {q.isLoading && <Loading />}
        {q.error && <ErrorState error={new Error('This source is not available to you.')} />}
        {s && <pre className="font-sans text-sm whitespace-pre-wrap">{s.body}</pre>}
      </DialogContent>
    </Dialog>
  )
}
