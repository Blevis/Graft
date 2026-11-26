import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  CalendarDays,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Folder,
  GitBranch,
  Layers3,
  Network,
  Search,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { useWorkspace } from './context'
import { Art, Go, Panel, PeopleTable, Rows, Spotlight, Stats, Tag, Tone } from './ui'
import { stageNames } from './catalog'
import { initials, type Person } from './model'

export function Attention({ limit = 5, target = 3 }: { limit?: number; target?: number }) {
  const w = useWorkspace()
  const suggested = ['ONB-002', 'ONB-005', 'ONB-004', 'ONB-007', 'ONB-009', 'ONB-010']
  const visible = w.demo
    ? suggested.flatMap((ref) => w.data.people.filter((p) => p.ref === ref))
    : w.data.people
  const people = visible.filter((p) => p.flags.length).slice(0, limit)
  return (
    <Rows
      rows={people.map((p) => ({
        title: p.flags[0],
        detail: p.name + '  ·  ' + p.project,
        icon: AlertCircle,
        to: w.demo || w.screen.role === 'pmo' || target !== 3 ? w.href(target, p.ref) : '/app/cases/' + p.ref,
      }))}
    />
  )
}
function MovementStats() {
  const {
    data: { people },
  } = useWorkspace()
  return (
    <Stats
      items={[
        ['Active cases', people.length, 'In this workspace'],
        [
          'New hires',
          people.filter((p) => p.movement.toLowerCase() === 'new hire').length,
          'New to the organization',
        ],
        [
          'Reallocations',
          people.filter((p) => p.movement.toLowerCase() === 'reallocation').length,
          'Internal transitions',
        ],
        [
          'Project unconfirmed',
          people.filter((p) => p.project === 'Unconfirmed').length,
          'Assignment needs review',
        ],
      ]}
    />
  )
}
export function CommandCenter() {
  const w = useWorkspace()
  return (
    <>
      <div className="ow-grid major">
        <Panel
          title="Onboarding pipeline"
          sub="Six stages from intake to independently ready"
          tone="night"
          aside={<Tag tone="night">{w.data.people.length} active cases</Tag>}
        >
          {w.demo ? (
            <Art
              name="pipeline"
              alt="Illustrative pipeline placement for the ten fictional cases, with technical sign-off pending."
            />
          ) : (
            <StageDistribution />
          )}
          <div className="ow-card-foot">
            <span>{w.demo ? 'Illustrative stage mapping' : 'Stages from technical reviews'}</span>
            <Go id={2}>Explore pipeline</Go>
          </div>
        </Panel>
        <Panel
          title="Priority actions"
          sub="Issues that need a human follow-up"
          aside={<AlertCircle size={21} />}
        >
          <Attention limit={4} />
        </Panel>
      </div>
      <div className="ow-grid equal">
        <Panel title="Active cases" sub="Latest recorded tracker status" aside={<Go id={2}>View board</Go>}>
          <PeopleTable people={w.data.people} limit={4} />
        </Panel>
        <div className="ow-stack">
          <Spotlight
            label="Evidence review"
            title={
              w.demo ? 'Two reports. One unresolved decision.' : 'Review the evidence behind a decision.'
            }
            footer={<Go id={4}>Compare evidence</Go>}
          >
            {w.demo
              ? 'Eva Stone’s technical and line manager reports disagree on independent execution.'
              : 'Compare source reports with the latest recorded technical decision.'}
          </Spotlight>
          <Panel title="Project coverage" aside={<Go id={8}>Projects</Go>}>
            <p className="ow-large-value">
              {new Set(w.data.people.map((p) => p.project).filter((p) => p !== 'Unconfirmed')).size}{' '}
              <small>assigned projects</small>
            </p>
          </Panel>
        </div>
      </div>
    </>
  )
}
function StageDistribution() {
  const {
    data: { people },
  } = useWorkspace()
  return (
    <div className="ow-distribution">
      {Object.entries(
        people.reduce<Record<string, number>>((m, p) => ({ ...m, [p.stage]: (m[p.stage] ?? 0) + 1 }), {}),
      ).map(([name, count]) => (
        <div key={name}>
          <span>{name}</span>
          <i style={{ width: Math.max(2, (100 * count) / people.length) + '%' }} />
          <b>{count}</b>
        </div>
      ))}
    </div>
  )
}
export function Board({
  groups,
  target,
  label,
}: {
  groups: { name: string; people: Person[] }[]
  target: number
  label: string
}) {
  const w = useWorkspace()
  return (
    <div
      className="ow-board"
      aria-label={label}
      style={{ gridTemplateColumns: `repeat(${groups.length},minmax(150px,1fr))` }}
    >
      {groups.map((g, i) => (
        <section key={g.name}>
          <div className={'ow-lane ow-lane-' + i}>
            <span />
            {g.name}
            <b>{g.people.length}</b>
          </div>
          {g.people.map((p) => (
            <Link className="ow-board-card" to={w.href(target, p.ref)} key={p.ref}>
              <small>{p.ref}</small>
              <span className="ow-identity">
                <i className="ow-avatar">{initials(p.name)}</i>
                <b>{p.name}</b>
              </span>
              <p>{p.project}</p>
              <Tone text={p.status} />
            </Link>
          ))}
          {!g.people.length && <small className="ow-lane-empty">No cases</small>}
        </section>
      ))}
    </div>
  )
}
export function Pipeline({ planner = false }: { planner?: boolean }) {
  const w = useWorkspace(),
    [view, setView] = useState('Board'),
    [q, setQ] = useState('')
  const people = w.data.people.filter((p) =>
    [p.name, p.status, p.project].join(' ').toLowerCase().includes(q.toLowerCase()),
  )
  const lanes = planner
    ? ['Shadowing', 'Supported execution', 'Independent execution', 'Technical validation']
    : [...stageNames, 'Needs confirmation']
  const sampleLanes: string[][] = planner
    ? [['001'], ['005'], ['010'], ['005', '010']]
    : [['003', '006'], ['002'], ['001', '004', '009'], ['005', '010'], [], [], ['007', '008']]
  const liveNames = planner
    ? ['Shadowing', 'Supported execution', 'Independent execution', 'Validated']
    : [
        'Pre-onboarding',
        'Access',
        'Shadowing',
        'Supported execution',
        'Independent execution',
        'Validated',
        'Unreviewed',
      ]
  const groups = lanes.map((name, i) => ({
    name,
    people: people.filter((p) =>
      w.demo ? sampleLanes[i].includes(p.ref.slice(-3)) : p.stage === liveNames[i],
    ),
  }))
  return (
    <>
      <Panel
        title={planner ? 'Learning plan' : 'Case progression'}
        sub={
          w.demo
            ? 'Illustrative lanes based on the reported snapshot'
            : 'Placement from the most recent technical review'
        }
        aside={
          <div className="ow-toggle">
            {['Board', 'Table'].map((v) => (
              <button aria-pressed={v === view} key={v} onClick={() => setView(v)}>
                {v}
              </button>
            ))}
          </div>
        }
      >
        <label className="ow-search">
          <Search size={16} />
          <input
            placeholder="Filter by employee, project or status"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        {view === 'Board' ? (
          <Board label="Case lanes" groups={groups} target={planner ? 17 : 3} />
        ) : (
          <PeopleTable people={people} target={planner ? 17 : 3} />
        )}
      </Panel>
      <div className="ow-grid equal">
        <Panel
          title={planner ? 'Session planning' : 'Stage confirmation'}
          icon={planner ? CalendarDays : Layers3}
        >
          <p>
            {planner
              ? 'Record the scope, mentor and evidence expected from the session.'
              : 'A tracker report can guide a follow-up. Only a scoped technical review establishes the observed stage.'}
          </p>
          {planner ? <Go id={17}>Open practical assessment</Go> : <Go id={4}>Inspect supporting evidence</Go>}
        </Panel>
        <Spotlight
          label={planner ? 'Technical review' : 'Review queue'}
          title={planner ? 'Plan for observed execution.' : 'Keep uncertain cases visible.'}
          footer={<Go id={planner ? 18 : 5}>{planner ? 'Review sign-off' : 'Inspect dependencies'}</Go>}
        >
          {planner
            ? 'Capture the tasks a person can complete and where support is still needed.'
            : 'Unconfirmed stages stay open until someone reviews the evidence.'}
        </Spotlight>
      </div>
    </>
  )
}
export function Projects() {
  const w = useWorkspace(),
    groups: Record<string, Person[]> = Object.create(null)
  for (const p of w.data.people) if (p.project !== 'Unconfirmed') (groups[p.project] ??= []).push(p)
  return (
    <>
      <div className="ow-projects">
        {Object.entries(groups).map(([name, ps]) => (
          <Link className="ow-project" key={name} to={w.href(3, ps![0].ref)}>
            <Folder size={24} />
            <small>
              {ps!.length} {ps!.length === 1 ? 'case' : 'cases'}
            </small>
            <h2>{name}</h2>
            <p>{ps!.map((p) => p.name).join(', ')}</p>
            <Tone text={ps![0].status} />
          </Link>
        ))}
      </div>
      <Panel title="Unconfirmed project assignment" sub="Cases awaiting a confirmed project">
        <PeopleTable people={w.data.people.filter((p) => p.project === 'Unconfirmed')} />
      </Panel>
    </>
  )
}
export function CalendarPage() {
  const w = useWorkspace(),
    [view, setView] = useState('Week'),
    [offset, setOffset] = useState(0)
  const monday = new Date((w.demo ? '2026-10-19' : w.date) + 'T12:00:00Z')
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7) + offset * 7)
  const days = Array.from({ length: 5 }, (_, i) => new Date(monday.valueOf() + i * 86400000))
  return (
    <>
      <Panel
        title="Weekly plan"
        sub={
          w.demo ? 'Illustrative dates · sessions await confirmation' : 'Assigned tasks grouped by due date'
        }
        aside={
          <div className="ow-toggle">
            {['Week', 'List'].map((v) => (
              <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>
                {v}
              </button>
            ))}
          </div>
        }
      >
        {view === 'Week' ? (
          <>
            <div className="ow-week-nav">
              <button aria-label="Previous week" onClick={() => setOffset(offset - 1)}>
                <ChevronLeft size={16} />
              </button>
              <b>Week of {monday.toLocaleDateString('en-GB', { dateStyle: 'long', timeZone: 'UTC' })}</b>
              <button aria-label="Next week" onClick={() => setOffset(offset + 1)}>
                <ChevronRight size={16} />
              </button>
            </div>
            <div className="ow-week">
              {days.map((day) => (
                <section key={day.toISOString()}>
                  <small>{day.toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' })}</small>
                  <strong>{day.getUTCDate()}</strong>
                  {w.data.tasks
                    .filter((t) => t.date === day.toISOString().slice(0, 10))
                    .map((t, i) => (
                      <div className="ow-event" key={i}>
                        <b>{t.title}</b>
                        <small>{t.owner}</small>
                      </div>
                    ))}
                </section>
              ))}
            </div>
          </>
        ) : (
          <Rows
            rows={w.data.tasks.map((t) => ({
              title: t.title,
              detail: t.owner + ' · ' + (t.date || 'Unscheduled'),
              status: t.done ? 'Complete' : 'Open',
            }))}
          />
        )}
      </Panel>
      <Panel
        title="Follow-up queue"
        sub={w.demo ? 'Suggested from the recorded issues' : 'Actions from visible case findings'}
      >
        <Attention limit={4} />
      </Panel>
    </>
  )
}
export function Department({ kind }: { kind: 'hr' | 'manager' | 'technical' }) {
  const w = useWorkspace(),
    tech = kind === 'technical',
    hr = kind === 'hr',
    target = hr ? 20 : tech ? 17 : 22
  const people =
    w.demo && !hr
      ? w.data.people.filter((p) =>
          (tech ? ['001', '005', '010'] : ['005', '007', '010']).includes(p.ref.slice(-3)),
        )
      : w.data.people
  return (
    <>
      {hr ? (
        <MovementStats />
      ) : (
        <Stats
          items={[
            [tech ? 'Cases for review' : 'Team cases', people.length, 'In the current view'],
            ['With open issues', people.filter((p) => p.flags.length).length, 'Recorded follow-up signals'],
            [
              'Awaiting decision',
              people.filter((p) => p.review === 'No signed decision').length,
              'No signed review recorded',
            ],
          ]}
        />
      )}
      <div className="ow-grid major">
        <Panel
          title={hr ? 'Employee movements' : tech ? 'Technical attention' : 'Team roster'}
          sub={
            w.demo && kind === 'manager'
              ? 'Illustrative roster for the historical snapshot'
              : 'Recorded case information'
          }
        >
          <PeopleTable people={people} target={kind === 'hr' ? 3 : target} limit={7} />
        </Panel>
        <div className="ow-stack">
          <Spotlight
            label={hr ? 'Employee intake' : tech ? 'Decision queue' : 'Follow-up focus'}
            title={
              hr
                ? 'Start with clear ownership.'
                : tech
                  ? 'Validate the work in scope.'
                  : 'Capture the support still needed.'
            }
            footer={
              <Go id={target}>{hr ? 'Prepare a case' : tech ? 'Open assessment' : 'Write a check-in'}</Go>
            }
          >
            {hr
              ? 'Prepare employee details, project assignment and responsible stakeholders.'
              : tech
                ? 'Compare the practical evidence with the reported level of independence.'
                : 'A line manager observation gives the technical owner context for the next review.'}
          </Spotlight>
          <Panel title={hr ? 'Information gaps' : 'Review opportunities'}>
            <Rows
              rows={people
                .filter((p) => p.flags.length)
                .slice(0, 3)
                .map((p) => ({ title: p.name, detail: p.flags[0], icon: CircleDot }))}
            />
          </Panel>
        </div>
      </div>
    </>
  )
}
export function Management({ bottlenecks = false }: { bottlenecks?: boolean }) {
  const w = useWorkspace(),
    people = w.data.people
  if (bottlenecks)
    return (
      <>
        <div className="ow-grid major">
          <Panel title="Recorded bottleneck signals" sub="One snapshot · visible findings by employee">
            <div className="ow-table-wrap">
              <table className="ow-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Project</th>
                    <th>Intervention</th>
                  </tr>
                </thead>
                <tbody>
                  {people
                    .filter((p) => p.flags.length)
                    .map((p) => (
                      <tr key={p.ref}>
                        <td>
                          <b>{p.name}</b>
                        </td>
                        <td>{p.project}</td>
                        <td>{p.flags[0]}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <div className="ow-stack">
            <Spotlight label="Interpretation" title="Priorities in this snapshot.">
              A single reporting date supports a review of current issues. Recurrence needs observations over
              time.
            </Spotlight>
            <Panel title="Intervention priorities">
              <Rows
                rows={[
                  'Resolve access gaps',
                  'Confirm ownership',
                  'Validate readiness',
                  'Refresh evidence',
                ].map((s, i) => ({ title: s, icon: [Network, Users, ShieldCheck, CheckCheck][i] }))}
              />
            </Panel>
          </div>
        </div>
        <Panel
          title="Dependency example"
          sub="Illustrative relationship between access, practical work and validation"
        >
          <div className="ow-steps">
            {['Access verification', 'Practical exercise', 'Technical validation'].map((s) => (
              <span key={s}>
                <GitBranch size={18} />
                {s}
              </span>
            ))}
          </div>
        </Panel>
      </>
    )
  const count = people.filter((p) => p.movement.toLowerCase() === 'new hire').length
  const statuses = Object.entries(
    people.reduce<Record<string, number>>((m, p) => ({ ...m, [p.status]: (m[p.status] ?? 0) + 1 }), {}),
  ).sort((a, b) => b[1] - a[1])
  return (
    <>
      <MovementStats />
      <div className="ow-grid equal">
        <Panel title="Movement distribution" sub="Recorded employee movements">
          <div className="ow-donut-block">
            <div
              className="ow-donut"
              style={{
                background: `conic-gradient(#794fe2 0 ${(count / Math.max(people.length, 1)) * 100}%, #c8b9f3 0)`,
              }}
            >
              <strong>
                {people.length}
                <small>cases</small>
              </strong>
            </div>
            <div>
              <Rows
                rows={[
                  { title: 'New hires', status: String(count) },
                  { title: 'Other movements', status: String(people.length - count) },
                ]}
              />
            </div>
          </div>
        </Panel>
        <Panel title="Recorded readiness signals" sub="Tracker descriptions across the portfolio">
          <div className="ow-bars">
            {statuses.slice(0, 6).map(([key, n]) => (
              <div key={key}>
                <b>{key}</b>
                <span>
                  <i style={{ width: (n / Math.max(1, ...statuses.map((x) => x[1]))) * 100 + '%' }} />
                </span>
                <strong>{n}</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="ow-grid major">
        <Panel title="Management attention">
          <Attention limit={3} />
        </Panel>
        <Spotlight
          label="Data quality"
          title={
            people.filter((p) => p.project === 'Unconfirmed').length + ' project assignments unconfirmed.'
          }
          footer={<Go id={26}>Inspect bottlenecks</Go>}
        >
          Review missing assignments before drawing project-level conclusions.
        </Spotlight>
      </div>
    </>
  )
}
