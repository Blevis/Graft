import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  CircleDot,
  FileText,
  Fingerprint,
  FlaskConical,
  Folder,
  KeyRound,
  Network,
  Route,
  ScanLine,
  Users,
} from 'lucide-react'
import { useWorkspace } from './context'
import { Art, Empty, Go, Panel, RecordStrip, Rows, Spotlight, Tag, Tone } from './ui'
import { accessLabel, type Requirement } from './model'
import { categoryIcons, stageNames } from './catalog'

export function AccessList() {
  const w = useWorkspace()
  return (
    <Rows
      rows={w.data.access
        .filter((a) => a.ref === w.person?.ref)
        .map((a) => ({ title: a.system, detail: a.owner, status: accessLabel(a), icon: KeyRound }))}
    />
  )
}
export function EvidenceList() {
  const { data } = useWorkspace()
  return data.reports.length ? (
    <div className="ow-reports">
      {data.reports.map((r) => (
        <details key={r.id}>
          <summary>
            <FileText size={18} />
            <span>
              <b>{r.title}</b>
              <small>
                {r.id} · {r.author} · {r.date}
              </small>
            </span>
            <ChevronRight size={16} />
          </summary>
          <p>{r.body}</p>
        </details>
      ))}
    </div>
  ) : (
    <Empty>No source reports available in this view.</Empty>
  )
}
export function JourneyMap() {
  const w = useWorkspace()
  return (
    <Panel
      title="Readiness journey"
      sub={
        w.demo
          ? 'Illustrative roadmap · independent readiness requires a technical decision'
          : 'Stages are established by a scoped technical review'
      }
    >
      {w.demo && w.person?.ref === 'ONB-002' ? (
        <Art
          name="journey"
          alt="Leo’s roadmap from intake to access setup and onward to technical validation."
        />
      ) : (
        <div className="ow-steps">
          {stageNames.map((s, i) => (
            <span key={s}>
              <CircleDot size={16} />
              <small>{i + 1}</small>
              {s}
            </span>
          ))}
        </div>
      )}
    </Panel>
  )
}
export function CaseOverview({
  employee = false,
  transition = false,
}: {
  employee?: boolean
  transition?: boolean
}) {
  const w = useWorkspace(),
    p = w.person,
    [tab, setTab] = useState('Overview')
  if (!p) return <Empty>No visible employee case.</Empty>
  if (transition)
    return (
      <>
        <RecordStrip />
        <div className="ow-transition">
          <Panel title="Previous project" icon={Folder}>
            <strong>Unknown</strong>
            <p>Prior assignment and transferable skills are unconfirmed.</p>
          </Panel>
          <ArrowRight />
          <Panel title="Receiving project" icon={Folder} tone="lilac">
            <strong>{p.project}</strong>
            <p>
              {p.movement} · {p.status}
            </p>
          </Panel>
        </div>
        <JourneyMap />
        <div className="ow-grid equal">
          <Panel title="New access requirements">
            <AccessList />
          </Panel>
          <Spotlight
            label="Transferable capabilities"
            title="Start with recorded evidence."
            footer={
              <Go id={11} caseRef={p.ref}>
                Open knowledge passport
              </Go>
            }
          >
            Review observations in their original project scope before carrying a capability forward.
          </Spotlight>
        </div>
      </>
    )
  if (!employee && tab !== 'Overview')
    return (
      <>
        <RecordStrip />
        <Tabs
          values={['Overview', 'Access', 'Knowledge transfer', 'Evidence', 'History']}
          selected={tab}
          set={setTab}
        />
        <Panel title={tab}>
          {tab === 'Access' ? (
            <AccessList />
          ) : tab === 'Evidence' ? (
            <EvidenceList />
          ) : tab === 'History' ? (
            <Rows rows={w.data.reports.map((r) => ({ title: r.title, detail: r.author, status: r.date }))} />
          ) : (
            <Rows rows={w.data.training.map((title) => ({ title }))} />
          )}
        </Panel>
      </>
    )
  return (
    <>
      <RecordStrip />
      {!employee && (
        <Tabs
          values={['Overview', 'Access', 'Knowledge transfer', 'Evidence', 'History']}
          selected={tab}
          set={setTab}
        />
      )}
      <div className="ow-grid major">
        <Spotlight
          label={employee ? 'Your next step' : 'Case focus'}
          title={
            employee && w.demo && p.ref === 'ONB-002'
              ? 'Check that Nova VPN works for you.'
              : (p.flags[0] ?? 'Review the latest case record.')
          }
          footer={
            <Go id={employee ? 14 : 5} caseRef={p.ref}>
              {employee ? 'Document evidence' : 'Inspect dependencies'}
            </Go>
          }
        >
          {p.project} · {p.status}. {w.data.review}.
        </Spotlight>
        <Panel title="Accountability" icon={Users}>
          <Rows
            rows={[
              { title: 'Line manager', detail: w.data.manager },
              { title: 'Technical owner', detail: w.data.technicalOwner },
            ]}
          />
        </Panel>
      </div>
      <JourneyMap />
      <div className="ow-grid equal">
        <Panel title="Access requirements" sub="Approval, provisioning and usability">
          <AccessList />
        </Panel>
        <Panel
          title={employee ? 'People to contact' : 'Readiness evidence'}
          sub={employee ? 'Roles responsible for the next step' : 'Sources and review history'}
        >
          {employee ? (
            <Rows
              rows={w.data.access
                .filter((a) => a.ref === p.ref)
                .map((a) => ({ title: a.owner, detail: a.system, icon: Users }))}
            />
          ) : (
            <EvidenceList />
          )}
        </Panel>
      </div>
    </>
  )
}
export function Tabs({
  values,
  selected,
  set,
}: {
  values: string[]
  selected: string
  set: (s: string) => void
}) {
  return (
    <div className="ow-toggle">
      {values.map((v) => (
        <button key={v} aria-pressed={v === selected} onClick={() => set(v)}>
          {v}
        </button>
      ))}
    </div>
  )
}
export function Evidence() {
  const w = useWorkspace(),
    graphic = w.demo && w.person?.ref === 'ONB-005'
  return (
    <>
      <RecordStrip />
      <div className="ow-grid equal">
        {w.data.reports.slice(0, 2).map((r, i) => (
          <Panel
            key={r.id}
            title={r.author}
            sub={r.title}
            tone={i === 0 ? 'lilac' : 'blue'}
            aside={<Tag>{r.id}</Tag>}
          >
            <blockquote>{r.body}</blockquote>
            <small>{r.date} · Stakeholder report</small>
          </Panel>
        ))}
        {!w.data.reports.length && <Empty>No source reports available.</Empty>}
      </div>
      <div className="ow-grid major">
        <Panel title="Decision trace" sub="Stakeholder claims and the technical decision">
          {graphic ? (
            <Art
              name="evidence"
              alt="Two conflicting reports feed a provisional ready-with-support assessment. Independent readiness is unvalidated."
            />
          ) : (
            <Rows
              rows={[
                { title: 'Tracker report', detail: w.person?.status },
                { title: 'Technical review', detail: w.data.review },
              ]}
            />
          )}
        </Panel>
        <Spotlight
          label="Technical decision"
          title={w.person?.status ?? 'Unknown'}
          footer={
            <Go id={18} caseRef={w.person?.ref}>
              Review decision
            </Go>
          }
        >
          {w.data.review}. A technical owner reviews the practical evidence for the scope being assessed.
        </Spotlight>
      </div>
      <Panel title="Evidence provenance" sub="Open a report to read the source">
        <EvidenceList />
      </Panel>
    </>
  )
}
function ImpactPath({ state }: { state: string }) {
  return (
    <div className="ow-impact" aria-label="Illustrative dependency path">
      <span>
        <KeyRound size={17} />
        {state}
      </span>
      <ArrowRight size={15} />
      <span>
        <Route size={17} />
        Practical exercise
      </span>
      <ArrowRight size={15} />
      <span>
        <ScanLine size={17} />
        Technical review
      </span>
    </div>
  )
}
export function Dependency({ simulate = false, details = false }: { simulate?: boolean; details?: boolean }) {
  const w = useWorkspace(),
    [params, setParams] = useSearchParams()
  const items = w.data.access.filter((a) => a.ref === w.person?.ref),
    selected =
      items.find((a) => a.system === params.get('system')) ??
      items.find((a) => a.state === 'awaiting_approval') ??
      items[0]
  const [assume, setAssume] = useState('Approved'),
    [saved, setSaved] = useState(false)
  const pick = (v: string) => {
    const next = new URLSearchParams(params)
    next.set('system', v)
    setParams(next)
    setSaved(false)
  }
  const graphic = w.demo && w.person?.ref === 'ONB-002'
  return (
    <>
      <RecordStrip />
      <div className="ow-toolbar">
        <label>
          System{' '}
          <select value={selected?.system ?? ''} onChange={(e) => pick(e.target.value)}>
            {items.map((a) => (
              <option key={a.system}>{a.system}</option>
            ))}
          </select>
        </label>
        {simulate && (
          <label>
            Assume{' '}
            <select
              value={assume}
              onChange={(e) => {
                setAssume(e.target.value)
                setSaved(false)
              }}
            >
              {['Approved', 'Provisioned', 'Confirmed usable'].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {!selected ? (
        <Empty>No access requests for this case.</Empty>
      ) : simulate ? (
        <>
          <div className="ow-grid equal">
            <Panel title="Current state" icon={Network} sub="Recorded access requirements">
              <ImpactPath state={accessLabel(selected)} />
              <AccessList />
            </Panel>
            <Panel
              title="Simulated state"
              icon={FlaskConical}
              tone="lilac"
              sub="Illustrative intervention on the selected request"
            >
              <ImpactPath state={assume} />
              <Rows
                rows={items.map((a) => ({
                  title: a.system,
                  detail: a === selected ? 'Scenario assumption' : 'Recorded state',
                  status: a === selected ? assume : accessLabel(a),
                  icon: KeyRound,
                }))}
              />
            </Panel>
          </div>
          <div className="ow-grid major">
            <Panel title="What remains unresolved">
              <Rows
                rows={[
                  ...items
                    .filter((a) => a !== selected && a.state !== 'confirmed_usable')
                    .map((a) => ({ title: a.system, detail: accessLabel(a) })),
                  ...(assume === 'Confirmed usable'
                    ? []
                    : [{ title: selected.system, detail: 'Employee usability test still required' }]),
                  { title: 'Technical validation', detail: 'Practical evidence and authorized sign-off' },
                ]}
              />
            </Panel>
            <Spotlight
              label="Scenario only"
              title="Keep the assumption with the result."
              footer={
                <button
                  className="ow-button light"
                  onClick={() => {
                    const blob = new Blob(
                      [
                        JSON.stringify(
                          {
                            case: w.person?.ref,
                            system: selected.system,
                            recorded: accessLabel(selected),
                            assumption: assume,
                            mode: 'illustrative',
                          },
                          null,
                          2,
                        ),
                      ],
                      { type: 'application/json' },
                    )
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = 'graft-scenario.json'
                    a.click()
                    setTimeout(() => URL.revokeObjectURL(url), 1000)
                    setSaved(true)
                  }}
                >
                  {saved ? 'Download again' : 'Export scenario'}
                </button>
              }
            >
              This preview changes only the selected assumption. Recorded access and technical decisions stay
              in the case record.
            </Spotlight>
          </div>
        </>
      ) : (
        <>
          <div className="ow-grid major">
            <Panel
              title={details ? 'Request lifecycle' : 'Dependency canvas'}
              sub={
                details
                  ? selected.system
                  : 'Illustrative dependencies · inspect a system for its recorded state'
              }
              aside={<Network size={22} />}
            >
              {details ? (
                <>
                  <div className="ow-steps">
                    {['Requested', 'Approval', 'Provisioned', 'Usability'].map((s) => (
                      <span key={s}>
                        <CircleDot size={18} />
                        {s}
                      </span>
                    ))}
                  </div>
                  <Rows
                    rows={[
                      { title: 'Request date', detail: selected.date },
                      { title: 'Responsible role', detail: selected.owner },
                      { title: 'Current state', status: accessLabel(selected) },
                    ]}
                  />
                </>
              ) : graphic ? (
                <Art
                  name="dependencies"
                  alt="Illustrative Nimbus dependency graph connecting three systems to learning, practical exercises and technical validation."
                />
              ) : (
                <AccessList />
              )}
            </Panel>
            <div className="ow-stack">
              <Spotlight
                label="Selected requirement"
                title={selected.system}
                footer={<Tag tone="night">{accessLabel(selected)}</Tag>}
              >
                {selected.owner} · {w.person?.project}
              </Spotlight>
              <Panel title="Operational impact">
                <p>
                  Confirm provisioning and a successful employee test before relying on this system for
                  practical work.
                </p>
                {details && !w.demo && (
                  <Link className="ow-link" to={'/app/cases/' + w.person?.ref + '?tab=access'}>
                    Manage recorded access <ChevronRight size={15} />
                  </Link>
                )}
                {details ? (
                  <Go id={23}>Return to queue</Go>
                ) : (
                  <Go id={6} caseRef={w.person?.ref} extra={{ system: selected.system }}>
                    Open simulator
                  </Go>
                )}
              </Panel>
            </div>
          </div>
          {details && (
            <Panel title="Dependent activities" sub="Illustrative sequence">
              <div className="ow-steps">
                {['Usable system access', 'Practical exercise', 'Technical validation'].map((s) => (
                  <span key={s}>
                    <Route size={19} />
                    {s}
                  </span>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </>
  )
}
export function Queue({ employee = false }: { employee?: boolean }) {
  const w = useWorkspace()
  const items = employee ? w.data.access.filter((a) => a.ref === w.person?.ref) : w.data.access
  const groups = employee
    ? ['Available now', 'In progress', 'Blocked', 'Completed']
    : ['Requested', 'Approval', 'Provisioned', 'Confirmed usable']
  const blockedExercise = employee && w.demo && w.person?.ref === 'ONB-002'
  function group(a: Requirement) {
    if (a.state === 'confirmed_usable') return 3
    if (a.state === 'active') return employee ? 0 : 2
    if (a.state === 'awaiting_approval' || a.state === 'approved') return 1
    return employee ? 2 : 0
  }
  return (
    <>
      {employee && <RecordStrip />}
      <Panel
        title={employee ? 'Personal work board' : 'Request lifecycle'}
        sub={
          employee
            ? 'Access checks and dependencies for your selected case'
            : 'System requests by current recorded state'
        }
      >
        <div className="ow-board four">
          {groups.map((label, i) => (
            <section key={label}>
              <div className={'ow-lane ow-lane-' + i}>
                <span />
                {label}
                <b>{items.filter((a) => group(a) === i).length + (blockedExercise && i === 2 ? 1 : 0)}</b>
              </div>
              {items
                .filter((a) => group(a) === i)
                .map((a) => (
                  <Link
                    key={a.ref + a.system}
                    className="ow-board-card"
                    to={w.href(employee ? 14 : 24, a.ref, { system: a.system })}
                  >
                    <KeyRound size={22} />
                    <small>{a.ref}</small>
                    <h3>{a.system}</h3>
                    <p>{a.owner}</p>
                    <Tone text={accessLabel(a)} />
                  </Link>
                ))}
              {blockedExercise && i === 2 && (
                <div className="ow-board-card">
                  <Route size={22} />
                  <small>Illustrative dependency</small>
                  <h3>Practical exercise</h3>
                  <p>Requires usable project access.</p>
                  <Tone text="Blocked" />
                </div>
              )}
              {!items.some((a) => group(a) === i) && !(blockedExercise && i === 2) && (
                <small className="ow-lane-empty">No items in this lane</small>
              )}
            </section>
          ))}
        </div>
      </Panel>
      <div className="ow-grid equal">
        <Panel
          title={employee ? (w.demo ? 'Suggested follow-ups' : 'Assigned follow-ups') : 'Request ownership'}
        >
          <Rows
            rows={
              employee
                ? w.data.tasks
                    .filter((t) => t.ref === w.person?.ref)
                    .map((t) => ({ title: t.title, detail: t.owner, status: t.done ? 'Complete' : 'Open' }))
                : items.map((a) => ({ title: a.system, detail: a.owner, icon: Users }))
            }
          />
        </Panel>
        <Spotlight
          label="Usability check"
          title="An active account still needs a test."
          footer={
            <Go id={employee ? 14 : 24} caseRef={w.person?.ref}>
              {employee ? 'Record an observation' : 'Inspect request'}
            </Go>
          }
        >
          Record a successful test from the designated user before marking a requirement usable.
        </Spotlight>
      </div>
    </>
  )
}
export function Passport() {
  const w = useWorkspace(),
    p = w.person
  return (
    <>
      <RecordStrip />
      <div className="ow-grid minor">
        <Spotlight
          label="Knowledge passport"
          title={p?.name ?? 'No case selected'}
          footer={<Tag tone="night">{p?.status ?? 'Unknown'}</Tag>}
        >
          {p?.project} · {p?.movement}. Scope is limited to the activities covered by the source.
        </Spotlight>
        <Panel
          title="Competency clusters"
          sub={
            w.demo
              ? 'Illustrative clusters based on reported activities'
              : 'Reported capabilities organized by scope'
          }
        >
          {w.demo && p?.ref === 'ONB-010' ? (
            <Art
              name="passport"
              alt="Owen reports independent standard Vega activities and support for exceptions and production changes. Prior experience is unknown."
            />
          ) : (
            <EvidenceList />
          )}
        </Panel>
      </div>
      <div className="ow-grid equal">
        <Panel title="Project experience" icon={Fingerprint}>
          <Rows
            rows={[
              { title: p?.project ?? 'Unknown', detail: p?.movement, status: p?.status },
              { title: 'Technical review', detail: w.data.review },
            ]}
          />
        </Panel>
        <Panel title="Supporting evidence" icon={ScanLine}>
          <EvidenceList />
        </Panel>
      </div>
    </>
  )
}
export function Hub() {
  const w = useWorkspace(),
    [filter, set] = useState('All resources'),
    [opened, open] = useState('')
  const resources = w.data.resources
  return (
    <>
      <Tabs
        values={['All resources', ...new Set(resources.map((r) => r.category))]}
        selected={filter}
        set={set}
      />
      <div className="ow-resources">
        {resources
          .filter((r) => filter === 'All resources' || r.category === filter)
          .map((r, i) => {
            const Icon = categoryIcons[i % categoryIcons.length]
            return (
              <button
                type="button"
                className="ow-resource"
                key={r.title + i}
                onClick={() => open(opened === r.title ? '' : r.title)}
                aria-expanded={opened === r.title}
              >
                <span className="ow-tile-icon">
                  <Icon size={24} />
                </span>
                <h2>{r.title}</h2>
                <p>{r.detail}</p>
                <Tag>{r.location ? 'Location supplied' : 'Reference category'}</Tag>
                {opened === r.title && (
                  <strong>
                    {r.location ?? 'No approved location or contact supplied for this category.'}
                  </strong>
                )}
              </button>
            )
          })}
      </div>
      {!resources.length && <Empty>No project resources available.</Empty>}
      <Panel title="Resource ownership" icon={BookOpen}>
        <p>
          Use the project-owned location for the current version of each resource. Keep the reference and its
          owner together.
        </p>
      </Panel>
    </>
  )
}
