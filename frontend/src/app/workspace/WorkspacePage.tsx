import { useEffect, useState, type ReactNode } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowUpRight,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Download,
  Layers,
  Menu,
  UserRound,
  X,
} from 'lucide-react'
import { api, ApiError, useCases, useMe } from '@/lib/api'
import type { AccessItem, CaseDetail, KnowledgeRef, Me, Task } from '@/lib/types'
import { ErrorState, Loading } from '@/components/common'
import { availableRoles, roles, screens, type Persona, type Screen } from './catalog'
import { defaultCase, fromCase, fromLive, initials, sampleData, type Dataset } from './model'
import { WorkspaceContext, useWorkspace } from './context'
import { CalendarPage, CommandCenter, Department, Management, Pipeline, Projects } from './Portfolio'
import { CaseOverview, Dependency, Evidence, Hub, Passport, Queue } from './CaseWork'
import { Editor, Intake } from './Editors'
import { TrainingSection } from '../cases/StakeholdersPanel'
import TaskDialog from '../cases/TaskDialog'
import PlanningDialog from './PlanningDialog'
import WorkspaceSearch from './WorkspaceSearch'
import type { Action } from './model'
import { Panel, Rows } from './ui'

const caseScreens = [3, 4, 5, 6, 9, 10, 11, 12, 14, 16, 17, 18, 22, 24]
const actionTargets: Record<number, [number, string]> = {
  1: [20, 'New onboarding case'],
  2: [3, 'Inspect case'],
  3: [5, 'View dependencies'],
  4: [18, 'Review sign-off'],
  5: [6, 'Open simulator'],
  7: [2, 'View pipeline'],
  8: [2, 'View cases'],
  9: [10, 'View my tasks'],
  10: [14, 'Prepare evidence'],
  11: [14, 'View evidence'],
  12: [9, 'View journey'],
  15: [17, 'Open assessment'],
  16: [17, 'Assess practical work'],
  17: [18, 'Review sign-off'],
  19: [20, 'New onboarding case'],
  21: [22, 'Write check-in'],
  23: [24, 'Inspect request'],
  24: [23, 'View queue'],
  26: [7, 'View action queue'],
}
function Contents() {
  const w = useWorkspace()
  switch (w.screen.id) {
    case 1:
      return <CommandCenter />
    case 2:
      return <Pipeline />
    case 3:
      return <CaseOverview />
    case 4:
      return <Evidence />
    case 5:
      return <Dependency />
    case 6:
      return <Dependency simulate />
    case 7:
      return <CalendarPage />
    case 8:
      return <Projects />
    case 9:
      return <CaseOverview employee />
    case 10:
      return <Queue employee />
    case 11:
      return <Passport />
    case 12:
      return <CaseOverview transition />
    case 13:
      return <Hub />
    case 14:
      return <Editor kind="evidence" />
    case 15:
      return <Department kind="technical" />
    case 16:
      return (
        <>
          <Pipeline planner />
          {w.detail && <TrainingSection d={w.detail} />}
        </>
      )
    case 17:
      return <Editor kind="assessment" />
    case 18:
      return <Editor kind="signoff" />
    case 19:
      return <Department kind="hr" />
    case 20:
      return <Intake />
    case 21:
      return <Department kind="manager" />
    case 22:
      return <Editor kind="checkin" />
    case 23:
      return <Queue />
    case 24:
      return <Dependency details />
    case 25:
      return <Management />
    case 26:
      return <Management bottlenecks />
  }
}
function Frame({
  screen,
  data,
  detail,
  me,
  allowed,
  selected,
  error,
  pending,
}: {
  screen: Screen
  data: Dataset
  detail?: CaseDetail
  me?: Me
  allowed: Persona[]
  selected?: string
  error?: unknown
  pending?: boolean
}) {
  const demo = !me,
    base = demo ? '/orchid' : '/app/workspace',
    navigate = useNavigate()
  const person = data.people.find((p) => p.ref === selected)
  const [menu, setMenu] = useState(false),
    [task, setTask] = useState(false)
  const [planning, setPlanning] = useState(false)
  const planKey = 'graft-orchid:preview:' + (screen.id === 16 ? 'kt' : 'actions')
  const [plans, setPlans] = useState<Action[]>(() => {
    if (!demo) return []
    try {
      const value = JSON.parse(sessionStorage.getItem(planKey) ?? '[]')
      return Array.isArray(value)
        ? value.filter((a) => a && typeof a.title === 'string' && typeof a.ref === 'string')
        : []
    } catch {
      return []
    }
  })
  function addPlan(item: Action) {
    const next = [...plans, item]
    sessionStorage.setItem(planKey, JSON.stringify(next))
    setPlans(next)
  }
  const role = roles[screen.role],
    date = me?.org.as_of_date ?? '2026-10-14'
  const href = (id: number, ref?: string, extra?: Record<string, string>) => {
    const params = new URLSearchParams(extra)
    if (ref) params.set('case', ref)
    return base + '/' + screens[id - 1].slug + (params.size ? '?' + params.toString() : '')
  }
  const draftKey = [
    'graft-orchid',
    me?.org.id ?? 'historical',
    me?.user.id ?? 'preview',
    screen.slug,
    screen.id === 20 ? 'intake' : (person?.ref ?? 'general'),
  ].join(':')
  useEffect(() => {
    document.title = screen.title + ' · Graft'
    window.scrollTo(0, 0)
  }, [screen])
  const target = actionTargets[screen.id]
  let action: ReactNode = null
  if (target && (demo || allowed.includes(screens[target[0] - 1].role)))
    action = (
      <Link
        className="ow-button"
        to={href(target[0], caseScreens.includes(screen.id) ? selected : undefined)}
      >
        {target[1]}
        <ArrowUpRight size={16} />
      </Link>
    )
  if (screen.id === 25)
    action = (
      <button className="ow-button" onClick={() => window.print()}>
        <Download size={16} />
        Export snapshot
      </button>
    )
  if (!demo && [5, 7, 24].includes(screen.id) && detail?.permissions.can_create_task)
    action = (
      <button className="ow-button" onClick={() => setTask(true)}>
        Create follow-up
        <ArrowUpRight size={16} />
      </button>
    )
  if (
    (screen.id === 16 && (demo || detail?.permissions.can_record_training)) ||
    (demo && [5, 7, 23, 24].includes(screen.id))
  ) {
    action = (
      <button className="ow-button" onClick={() => setPlanning(true)}>
        {screen.id === 16 ? 'Plan session' : screen.id === 7 ? 'Schedule action' : 'Create follow-up'}
        <ArrowUpRight size={16} />
      </button>
    )
  }
  const workspaceData = demo && screen.id === 7 ? { ...data, tasks: [...data.tasks, ...plans] } : data
  return (
    <WorkspaceContext.Provider
      value={{
        screen,
        demo,
        data: workspaceData,
        person,
        detail,
        date,
        href,
        draftKey,
      }}
    >
      <div className="orchid">
        <a className="ow-skip" href="#workspace-main">
          Skip to workspace
        </a>
        {menu && <button className="ow-scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
        <aside className={'ow-sidebar ' + (menu ? 'is-open' : '')}>
          <Link to={demo ? '/' : '/app/home'} className="ow-brand">
            <img src="/orchid/graft.svg" alt="" />
            Graft
          </Link>
          <label className="ow-role-select">
            <small>Workspace</small>
            <span>
              <Layers size={17} />
              <select
                aria-label="Choose role workspace"
                value={screen.role}
                onChange={(e) => navigate(href(screens.find((s) => s.role === e.target.value)!.id))}
              >
                {allowed.map((r) => (
                  <option key={r} value={r}>
                    {roles[r].name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </span>
          </label>
          <nav aria-label="Role workspace">
            {screens
              .filter((s) => s.role === screen.role)
              .map((s) => (
                <Link aria-current={s.id === screen.id ? 'page' : undefined} key={s.id} to={href(s.id)}>
                  <s.icon size={19} />
                  {s.title}
                </Link>
              ))}
          </nav>
          <div className="ow-sidebar-bottom">
            <Link to={demo ? '/login' : '/app/home'}>
              <ArrowLeft size={16} />
              {demo ? 'Open signed-in workspace' : 'Return to workspace home'}
            </Link>
            <div className="ow-org">
              <span>
                <Layers size={18} />
              </span>
              <div>
                <b>{me?.org.name ?? 'Royal Orchid'}</b>
                <small>{demo ? 'Fictional demo workspace' : 'Organization workspace'}</small>
              </div>
            </div>
          </div>
        </aside>
        <div className="ow-main">
          <header className="ow-top">
            <button
              className="ow-mobile-menu"
              aria-label={menu ? 'Close navigation' : 'Open navigation'}
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X /> : <Menu />}
            </button>
            <span className="ow-crumb">
              Workspace <ChevronRight size={13} /> <b>{role.name}</b>
            </span>
            <WorkspaceSearch allowed={allowed} />
            <div className="ow-top-right">
              <span>
                <CalendarDays size={16} />
                {new Date(date + 'T12:00:00Z').toLocaleDateString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  timeZone: 'UTC',
                })}
              </span>
              <i />
              <span className="ow-profile">{me ? initials(me.user.name) : role.initials}</span>
            </div>
          </header>
          <main id="workspace-main" className="ow-content">
            <header className="ow-heading">
              <div>
                <div className="ow-overline">
                  <span />
                  {role.name}
                </div>
                <h1>{screen.title}</h1>
                <p>{screen.description}</p>
              </div>
              {action}
            </header>
            {screen.id === 16 && data.people.length > 0 && (
              <label className="ow-case-switch">
                <UserRound size={15} />
                <span>Case</span>
                <select
                  aria-label="Select case"
                  value={selected ?? ''}
                  onChange={(e) => navigate(href(screen.id, e.target.value))}
                >
                  {data.people.map((p) => (
                    <option key={p.ref} value={p.ref}>
                      {p.name} · {p.ref}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {pending ? (
              <Loading />
            ) : error ? (
              <ErrorState error={error} />
            ) : (
              <div className="ow-body" key={screen.slug + '-' + selected}>
                <Contents />
                {demo && screen.id === 16 && plans.length > 0 && (
                  <Panel title="Planned sessions">
                    <Rows
                      rows={plans.map((p) => ({
                        title: p.title,
                        detail: p.ref + ' · ' + p.owner,
                        status: p.date,
                      }))}
                    />
                  </Panel>
                )}
              </div>
            )}
            <footer className="ow-footer">
              <span>
                <CircleDot size={12} />
                {demo ? 'Historical fictional snapshot' : 'Organization records'} · {date}
              </span>
              <span>Graft / {screen.title}</span>
            </footer>
          </main>
        </div>
      </div>
      {planning && <PlanningDialog open={planning} onOpenChange={setPlanning} add={addPlan} />}
      {detail && task && <TaskDialog d={detail} open={task} onOpenChange={setTask} />}
    </WorkspaceContext.Provider>
  )
}
export function PreviewWorkspace() {
  const { slug } = useParams(),
    [params] = useSearchParams(),
    s = screens.find((x) => x.slug === slug)
  if (!s) return <Navigate to="/orchid/command-center" replace />
  const requested = params.get('case'),
    ref =
      requested && sampleData(requested).people.some((p) => p.ref === requested)
        ? requested
        : defaultCase(s.id)
  return (
    <Frame
      key={s.slug}
      screen={s}
      data={sampleData(ref)}
      selected={ref}
      allowed={Object.keys(roles) as Persona[]}
    />
  )
}
export function LiveWorkspace() {
  const me = useMe(),
    { slug } = useParams()
  if (me.isPending) return <Loading />
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace />
  if (!me.data) return <ErrorState error={me.error} />
  const allowed = availableRoles(me.data.roles)
  const preferred = me.data.working_role && availableRoles([me.data.working_role])[0]
  const firstRole = preferred && allowed.includes(preferred) ? preferred : allowed[0]
  const s = screens.find((x) => x.slug === slug)
  if (!allowed.length) return <Navigate to="/app/home" replace />
  if (!s || !allowed.includes(s.role))
    return <Navigate to={'/app/workspace/' + screens.find((x) => x.role === firstRole)!.slug} replace />
  return <LiveData me={me.data} screen={s} allowed={allowed} />
}
function LiveData({ me, screen, allowed }: { me: Me; screen: Screen; allowed: Persona[] }) {
  const [params] = useSearchParams(),
    cases = useCases('all')
  const people = (cases.data ?? []).map(fromCase),
    preferred = params.get('case')
  const ref = people.find((p) => p.ref === preferred)?.ref ?? people[0]?.ref
  const detail = useQuery({
    queryKey: ['case', ref],
    queryFn: () => api.get<CaseDetail>('/cases/' + ref),
    enabled: !!ref && [...caseScreens, 7].includes(screen.id),
  })
  const mine = screen.id === 10
  const tasks = useQuery({
    queryKey: ['tasks', mine, 'all'],
    queryFn: () => api.get<Task[]>('/tasks?status=all&mine=' + (mine ? '1' : '0')),
    enabled: [7, 10].includes(screen.id),
  })
  const knowledge = useQuery({
    queryKey: ['knowledge'],
    queryFn: () => api.get<KnowledgeRef[]>('/knowledge'),
    enabled: screen.id === 13,
  })
  const queue = useQueries({
    queries: (screen.id === 23 ? people : []).map((p) => ({
      queryKey: ['access-items', p.ref],
      queryFn: () => api.get<AccessItem[]>('/cases/' + p.ref + '/access-items'),
    })),
  })
  const data = fromLive(people, detail.data, tasks.data ?? [], knowledge.data ?? [])
  if (screen.id === 23)
    data.access = queue.flatMap((q, i) =>
      (q.data ?? []).map((a) => ({
        ref: people[i].ref,
        system: a.system,
        state: a.state,
        owner: a.owner_role ?? 'Unconfirmed',
        date: a.requested_at ?? 'Date unknown',
      })),
    )
  const queries = [cases, detail, tasks, knowledge, ...queue].filter(
    (q) => q.fetchStatus !== 'idle' || q.isError,
  )
  return (
    <Frame
      key={screen.slug}
      me={me}
      screen={screen}
      allowed={allowed}
      data={data}
      detail={detail.data}
      selected={ref}
      pending={queries.some((q) => q.isLoading)}
      error={queries.find((q) => q.isError)?.error}
    />
  )
}
