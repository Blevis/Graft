import { useWorkspace } from './context'
import { type ReactNode } from 'react'
import { ArrowUpRight, ChevronRight, CircleDot, type LucideIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { screens } from './catalog'
import { initials, type Person } from './model'

export function Panel({
  title,
  sub,
  children,
  aside,
  tone = '',
  className = '',
  icon: Icon,
}: {
  title: string
  sub?: string
  children?: ReactNode
  aside?: ReactNode
  tone?: string
  className?: string
  icon?: LucideIcon
}) {
  return (
    <section className={`ow-panel ${tone} ${className}`}>
      <header className="ow-panel-head">
        <div>
          {Icon && <Icon className="ow-panel-icon" size={22} />}
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  )
}
export function Tag({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return (
    <span className={`ow-tag ${tone}`}>
      <i />
      {children}
    </span>
  )
}
export function Tone({ text }: { text: string }) {
  const value = text.toLowerCase()
  const tone = /not provisioned|blocked|conflict/.test(value)
    ? 'red'
    : /pending|support|partial|outstanding|unconfirmed|awaiting|missing/.test(value)
      ? 'amber'
      : /confirmed usable|validated|complete/.test(value)
        ? 'green'
        : 'violet'
  return <Tag tone={tone}>{text}</Tag>
}
export function Go({
  id,
  children,
  caseRef,
  primary,
  extra,
}: {
  id: number
  children?: ReactNode
  caseRef?: string
  primary?: boolean
  extra?: Record<string, string>
}) {
  const w = useWorkspace()
  // Links to a different persona are available only in the public, fictional walkthrough.
  if (!w.demo && screens[id - 1].role !== w.screen.role) {
    const target = caseRef
      ? '/app/cases/' + encodeURIComponent(caseRef)
      : ((
          { 7: '/app/tasks', 8: '/app/projects', 13: '/app/knowledge', 25: '/app/insights' } as Record<
            number,
            string
          >
        )[id] ?? '/app/cases')
    return (
      <Link className={primary ? 'ow-button' : 'ow-link'} to={target}>
        {children ?? 'Open record'}
        <ArrowUpRight size={15} />
      </Link>
    )
  }
  return (
    <Link className={primary ? 'ow-button' : 'ow-link'} to={w.href(id, caseRef, extra)}>
      {children ?? screens[id - 1].title}
      <ArrowUpRight size={15} />
    </Link>
  )
}
export function Empty({ children }: { children?: ReactNode }) {
  return (
    <div className="ow-empty">
      <CircleDot size={16} />
      {children ?? 'No records in this view.'}
    </div>
  )
}
export function Rows({
  rows,
}: {
  rows: { title: string; detail?: string; status?: string; icon?: LucideIcon; to?: string }[]
}) {
  if (!rows.length) return <Empty />
  return (
    <div className="ow-rows">
      {rows.map((r, i) => {
        const Icon = r.icon
        const body = (
          <>
            {Icon && (
              <span className="ow-tile-icon">
                <Icon size={19} />
              </span>
            )}
            <span className="ow-row-text">
              <b>{r.title}</b>
              {r.detail && <small>{r.detail}</small>}
            </span>
            {r.status && <Tone text={r.status} />} {r.to && <ChevronRight size={16} />}
          </>
        )
        return r.to ? (
          <Link className="ow-row" key={i} to={r.to}>
            {body}
          </Link>
        ) : (
          <div className="ow-row" key={i}>
            {body}
          </div>
        )
      })}
    </div>
  )
}
export function Stats({ items }: { items: [string, string | number, string][] }) {
  return (
    <div className="ow-stats">
      {items.map(([label, value, detail]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{detail}</small>
        </div>
      ))}
    </div>
  )
}
export function PeopleTable({
  people,
  target = 3,
  limit,
}: {
  people: Person[]
  target?: number
  limit?: number
}) {
  const w = useWorkspace()
  return people.length ? (
    <div className="ow-table-wrap">
      <table className="ow-table">
        <thead>
          <tr>
            <th>Employee</th>
            <th>Project</th>
            <th>Movement</th>
            <th>Tracker report</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {people.slice(0, limit).map((p) => (
            <tr key={p.ref}>
              <td>
                <span className="ow-identity">
                  <span className="ow-avatar">{initials(p.name)}</span>
                  <span>
                    <b>{p.name}</b>
                    <small>{p.ref}</small>
                  </span>
                </span>
              </td>
              <td>{p.project}</td>
              <td>{p.movement}</td>
              <td>
                <Tone text={p.status} />
              </td>
              <td>
                <Link
                  className="ow-arrow"
                  aria-label={'Open ' + p.name}
                  to={
                    w.demo || screens[target - 1].role === w.screen.role
                      ? w.href(target, p.ref)
                      : '/app/cases/' + p.ref
                  }
                >
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty />
  )
}
export function Art({ name, alt }: { name: string; alt: string }) {
  return <img className={'ow-art art-' + name} src={'/orchid/' + name + '.svg'} alt={alt} />
}
export function Spotlight({
  label,
  title,
  children,
  footer,
}: {
  label: string
  title: string
  children?: ReactNode
  footer?: ReactNode
}) {
  return (
    <section className="ow-spot">
      <div className="ow-orbit" aria-hidden="true" />
      <div className="ow-spot-inner">
        <span className="ow-kicker">{label}</span>
        <h2>{title}</h2>
        {children && <p>{children}</p>}
        {footer}
      </div>
    </section>
  )
}
export function RecordStrip() {
  const w = useWorkspace(),
    person = w.person,
    navigate = useNavigate()
  if (!person) return <Empty>No case selected.</Empty>
  return (
    <div className="ow-record">
      <span className="ow-avatar large">{initials(person.name)}</span>
      <span>
        <small>{person.ref}</small>
        <select
          aria-label="Select case"
          value={person.ref}
          onChange={(e) => navigate(w.href(w.screen.id, e.target.value))}
        >
          {w.data.people.map((p) => (
            <option key={p.ref} value={p.ref}>
              {p.name}
            </option>
          ))}
        </select>
      </span>
      <span>
        <small>Project</small>
        <b>{person.project}</b>
      </span>
      <span>
        <small>Movement</small>
        <b>{person.movement}</b>
      </span>
      <Tone text={person.status} />
    </div>
  )
}
