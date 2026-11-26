import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorState, Loading, PageHeader } from '@/components/common'
import { useKnowledge } from '@/lib/api'
import { DASH, fmtDate } from '@/lib/format'

export default function KnowledgePage() {
  const k = useKnowledge()
  return (
    <div>
      <PageHeader
        title="Knowledge"
        description="A central index of where each project keeps its KT material. Graft stores the location only; documents stay project-owned."
      />
      <div className="rounded-lg border bg-background">
        {k.isLoading && <Loading />}
        {k.error && <ErrorState error={k.error} />}
        {k.data && k.data.length === 0 && <div className="px-4"><Empty>No references recorded yet.</Empty></div>}
        {k.data && k.data.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Project</TableHead>
                <TableHead>What</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Last verified</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {k.data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.project?.name ?? DASH}</TableCell>
                  <TableCell>{r.title}</TableCell>
                  <TableCell className="font-mono text-xs">{r.location}</TableCell>
                  <TableCell>{r.owner_role ?? DASH}</TableCell>
                  <TableCell>{fmtDate(r.last_verified)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        A folder reference does not show that anyone has used the material or completed knowledge transfer.
      </p>
    </div>
  )
}
