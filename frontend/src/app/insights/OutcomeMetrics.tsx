import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Input } from '@/components/ui/input'
import { ErrorState, Field, Loading, NativeSelect, Section, StatTile } from '@/components/common'
import { useMetrics, useProjects } from '@/lib/api'
import type { Metrics } from '@/lib/types'

const DEFINITIONS = {
  blocker: 'From a high/medium flag first being detected to a named person owning work on it (task created with an owner, claimed or reassigned). Flags detected in the range; unowned ones are counted as open and excluded from the median.',
  signoff: 'From the case start date to its current final sign-off, for sign-offs in the range. Cases not signed off are counted as open and excluded.',
  closes: 'Final sign-off reviews recorded in the range that used a documented exception, or were recorded before the closure gate (checks unverified), divided by all final sign-offs in the range.',
}

/** Outcome metrics with their definitions, filters and the cases behind each number. */
export default function OutcomeMetrics() {
  const projects = useProjects()
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [project, setProject] = useState('')
  const m = useMetrics({ start, end, project_id: project })
  const d: Metrics | undefined = m.data
  return (
    <Section title="Outcomes">
      <div className="mb-3 grid gap-3 sm:grid-cols-3">
        <Field label="From"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        <Field label="Project">
          <NativeSelect value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">All projects you can see</option>
            {(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </NativeSelect>
        </Field>
      </div>
      {m.isLoading && <Loading />}
      {m.error && <ErrorState error={m.error} />}
      {d && (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">{d.filters.cases_in_scope} case(s) in scope.</p>
          <div className="grid gap-3 md:grid-cols-3">
            <StatTile label="Blocker → owner (median h)" value={d.blocker_to_owner_hours.median ?? '—'}
              hint={`p90 ${d.blocker_to_owner_hours.p90 ?? '—'} h · n=${d.blocker_to_owner_hours.n} · ${d.blocker_to_owner_hours.open} unowned`} />
            <StatTile label="Start → sign-off (median days)" value={d.start_to_signoff_days.median ?? '—'}
              hint={`p90 ${d.start_to_signoff_days.p90 ?? '—'} d · n=${d.start_to_signoff_days.n} · ${d.start_to_signoff_days.open} open`} />
            <StatTile label="Closes with unmet checks" value={d.closes_with_unmet_checks.share === null ? '—' : `${Math.round(d.closes_with_unmet_checks.share * 100)}%`}
              hint={`${d.closes_with_unmet_checks.flagged} of ${d.closes_with_unmet_checks.closes} · ${d.closes_with_unmet_checks.exceptions} exception(s), ${d.closes_with_unmet_checks.legacy_unverified} legacy`}
              tone={d.closes_with_unmet_checks.flagged ? 'alert' : undefined} />
          </div>
          <div className="grid gap-3 text-xs md:grid-cols-3">
            <Drill title="Blocker → owner" def={DEFINITIONS.blocker} rows={d.blocker_to_owner_hours.cases.map((c) => [c.ref, c.values.map((v) => `${v} h`).join(', ')])} extra={d.blocker_to_owner_hours.open_cases.map((r) => [r, 'no owner yet'])} />
            <Drill title="Start → sign-off" def={DEFINITIONS.signoff} rows={d.start_to_signoff_days.cases.map((c) => [c.ref, `${c.values[0]} d`])} extra={d.start_to_signoff_days.missing_start.map((r) => [r, 'no start date'])} />
            <Drill title="Closes with unmet checks" def={DEFINITIONS.closes} rows={d.closes_with_unmet_checks.cases.map((r) => [r, 'exception or legacy'])} />
          </div>
        </div>
      )}
    </Section>
  )
}

function Drill({ title, def, rows, extra = [] }: { title: string; def: string; rows: string[][]; extra?: string[][] }) {
  return (
    <details className="rounded-md border p-2">
      <summary className="cursor-pointer font-medium">{title}: definition and cases ({rows.length + extra.length})</summary>
      <p className="mt-1 text-muted-foreground">{def}</p>
      <ul className="mt-1 space-y-0.5">
        {[...rows, ...extra].map(([ref, v], i) => (
          <li key={`${ref}-${i}`}><Link className="font-mono hover:underline" to={`/app/cases/${ref}`}>{ref}</Link> · {v}</li>
        ))}
        {rows.length + extra.length === 0 && <li className="text-muted-foreground">No cases.</li>}
      </ul>
    </details>
  )
}
