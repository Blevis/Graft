/**
 * Hand-rolled charts (no chart library): HTML and SVG marks styled by styles/orchid.css.
 *
 * Rules every chart here follows:
 * - the form follows the job (ranked bars for magnitude, a segmented bar for one whole, a meter for a ratio,
 *   columns for change over time);
 * - text wears text colours, never the series colour; identity comes from a swatch beside the label;
 * - every mark answers hover and keyboard focus with a tooltip, and every card offers a table of the same numbers;
 * - motion plays once on entry and is disabled under prefers-reduced-motion (in CSS).
 */
import { useRef, useState, type CSSProperties, type FocusEvent, type PointerEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3, Table2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Categorical slots, validated as an adjacent set (CVD and normal-vision separation, 3:1 on white). Fixed order. */
export const SERIES = ['#5831bc', '#3987e5', '#e0733a', '#17a2a8'] as const
/** Status colours are reserved for state and always ship with a label. */
export const STATUS = { good: '#2f8a5c', warn: '#c08510', bad: '#c8475f', neutral: '#a79dbd', accent: '#5831bc', soft: '#b9a5e6' } as const

/** Text set inside a coloured block is white or near-black, whichever the fill's luminance calls for. */
function inkOn(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.3 ? '#211b35' : '#ffffff'
}

// ---------------------------------------------------------------------------------------------------------------
// Tooltip

type TipContent = { title: ReactNode; value: ReactNode; note?: ReactNode; color?: string }
type Tip = (TipContent & { x: number; y: number }) | null

function useTip() {
  const ref = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<Tip>(null)
  const show = (e: PointerEvent | FocusEvent, t: TipContent) => {
    const box = ref.current?.getBoundingClientRect()
    if (!box) return
    const r = (e.currentTarget as Element).getBoundingClientRect()
    const raw = 'clientX' in e && e.clientX ? e.clientX - box.left : r.left + r.width / 2 - box.left
    setTip({ ...t, x: Math.min(Math.max(raw, 84), Math.max(84, box.width - 84)), y: r.top - box.top })
  }
  const hide = () => setTip(null)
  const bind = (t: TipContent) => ({
    tabIndex: 0,
    onPointerMove: (e: PointerEvent) => show(e, t),
    onPointerLeave: hide,
    onFocus: (e: FocusEvent) => show(e, t),
    onBlur: hide,
  })
  const node = tip && (
    <div className="ow-tip" role="status" style={{ left: tip.x, top: tip.y }}>
      <strong>{tip.value}</strong>
      <span>
        {tip.color && <i style={{ background: tip.color }} />}
        {tip.title}
      </span>
      {tip.note && <small>{tip.note}</small>}
    </div>
  )
  return { ref, bind, node }
}

// ---------------------------------------------------------------------------------------------------------------
// Card with a table view of the same numbers

export type ChartTable = { head: string[]; rows: (string | number)[][] }

export function ChartCard({
  title, sub, children, table, className, footer,
}: { title: ReactNode; sub?: ReactNode; children: ReactNode; table?: ChartTable; className?: string; footer?: ReactNode }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className={cn('ow-panel ow-chart', className)}>
      <header className="ow-panel-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {table && (
          <button
            type="button"
            className="ow-chart-toggle"
            aria-pressed={asTable}
            title={asTable ? 'Show the chart' : 'Show the numbers as a table'}
            onClick={() => setAsTable(!asTable)}
          >
            {asTable ? <BarChart3 size={15} /> : <Table2 size={15} />}
            <span className="sr-only">{asTable ? 'Show the chart' : 'Show as table'}</span>
          </button>
        )}
      </header>
      {asTable && table ? (
        <div className="ow-table-wrap">
          <table className="ow-table">
            <thead>
              <tr>{table.head.map((h) => <th key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
      {footer && <p className="ow-note mt-3.5 border-t pt-3">{footer}</p>}
    </section>
  )
}

export function ChartEmpty({ children }: { children: ReactNode }) {
  return <div className="ow-chart-empty">{children}</div>
}

// ---------------------------------------------------------------------------------------------------------------
// Ranked bars and meters

export type BarRow = {
  key: string
  /** Plain-text name, used in the tooltip and for assistive technology. */
  name: string
  /** What is shown beside the bar; defaults to the name. */
  label?: ReactNode
  value: number
  /** A limit turns the row into a meter: the bar fills value / of on a lighter track. */
  of?: number
  note?: string
  to?: string
  color?: string
}

/**
 * One hue, one baseline. Without `of`, bars are scaled to the largest value; with it, each row is a meter against
 * its own limit. Rows keep the order they are given (pass them sorted when rank is the point).
 */
export function Bars({ rows, color = STATUS.accent, unit = '', empty = 'Nothing to show.' }: {
  rows: BarRow[]; color?: string; unit?: string; empty?: string
}) {
  const tip = useTip()
  if (rows.length === 0) return <ChartEmpty>{empty}</ChartEmpty>
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="ow-hbars" ref={tip.ref}>
      {rows.map((r, i) => {
        const meter = r.of !== undefined
        const share = meter ? (r.of ? r.value / r.of : 0) : r.value / max
        const figure = meter ? `${r.value} / ${r.of}` : `${r.value}${unit}`
        const body = (
          <>
            <span className="ow-hbar-label">{r.label ?? r.name}</span>
            <span className={cn('ow-hbar-track', meter && 'meter')}>
              {r.value > 0 && (
                <i style={{ '--w': `${Math.max(2, share * 100)}%`, '--d': `${i * 55}ms`, background: r.color ?? color } as CSSProperties} />
              )}
            </span>
            <span className="ow-hbar-value">{figure}</span>
          </>
        )
        const props = {
          className: 'ow-hbar',
          'aria-label': `${r.name}: ${figure}${r.note ? `, ${r.note}` : ''}`,
          ...tip.bind({ title: r.name, value: figure, note: r.note, color: r.color ?? color }),
        }
        return r.to ? <Link key={r.key} to={r.to} {...props}>{body}</Link> : <div key={r.key} {...props}>{body}</div>
      })}
      {tip.node}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Segmented bar: one whole split into parts

export type Part = { key: string; name: string; value: number; color: string; note?: string }

/** Tall segmented bar with a legend. Hovering a block or its legend entry lifts that part and quiets the rest. */
export function Segments({ parts, unit = '', empty = 'Nothing to show.' }: { parts: Part[]; unit?: string; empty?: string }) {
  const tip = useTip()
  const [active, setActive] = useState<string | null>(null)
  const total = parts.reduce((n, p) => n + p.value, 0)
  if (total === 0) return <ChartEmpty>{empty}</ChartEmpty>
  const pct = (v: number) => Math.round((v / total) * 100)
  return (
    <div className="ow-seg" ref={tip.ref}>
      <div className="ow-seg-bar" role="img" aria-label={parts.map((p) => `${p.name} ${p.value}`).join(', ')}>
        {parts.filter((p) => p.value > 0).map((p, i) => (
          <span
            key={p.key}
            className={cn(active && active !== p.key && 'is-dim')}
            style={{ flexGrow: p.value, background: p.color, color: inkOn(p.color), '--d': `${i * 80}ms` } as CSSProperties}
            {...tip.bind({ title: p.name, value: `${p.value}${unit} · ${pct(p.value)}%`, note: p.note, color: p.color })}
            onPointerEnter={() => setActive(p.key)}
            onPointerOut={() => setActive(null)}
          >
            {p.value / total >= 0.1 && <b>{pct(p.value)}%</b>}
          </span>
        ))}
      </div>
      <ul className="ow-legend">
        {parts.map((p) => (
          <li
            key={p.key}
            className={cn(active && active !== p.key && 'is-dim', p.value === 0 && 'is-zero')}
            onPointerEnter={() => p.value > 0 && setActive(p.key)}
            onPointerLeave={() => setActive(null)}
          >
            <i style={{ background: p.color }} />
            <span>{p.name}</span>
            <b>{p.value}</b>
          </li>
        ))}
      </ul>
      {tip.node}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Ring meter: one ratio against its limit

export function Ring({ value, total, label, caption, color = STATUS.accent, size = 132 }: {
  value: number; total: number; label: string; caption?: ReactNode; color?: string; size?: number
}) {
  const share = total > 0 ? value / total : 0
  const r = 52
  const c = 2 * Math.PI * r
  return (
    <div className="ow-ring" style={{ width: size }}>
      <svg viewBox="0 0 120 120" role="img" aria-label={`${label}: ${value} of ${total}`}>
        <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeOpacity="0.14" strokeWidth="11" />
        {share > 0 && (
          <circle
            className="ow-ring-arc"
            cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round"
            strokeDasharray={c}
            style={{ '--from': c, '--to': c * (1 - share) } as CSSProperties}
            transform="rotate(-90 60 60)"
          />
        )}
      </svg>
      <div>
        <strong>{total > 0 ? Math.round(share * 100) : '—'}{total > 0 && <small>%</small>}</strong>
        {caption && <span>{caption}</span>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Columns over time

export type Column = { key: string; label: string; value: number; tick?: string }

/** A single series over time: thin columns on one baseline, hairline gridlines, integer ticks. */
export function Columns({ data, unit, color = STATUS.accent, empty = 'Nothing in this period.' }: {
  data: Column[]; unit: [string, string]; color?: string; empty?: string
}) {
  const tip = useTip()
  const top = Math.max(...data.map((d) => d.value), 0)
  if (top === 0) return <ChartEmpty>{empty}</ChartEmpty>
  const step = top <= 4 ? 1 : top <= 10 ? 2 : Math.ceil(top / 4)
  const max = Math.ceil(top / step) * step
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)
  return (
    <div className="ow-cols" ref={tip.ref}>
      <div className="ow-cols-plot">
        {ticks.map((t) => (
          <span key={t} className="ow-cols-grid" style={{ bottom: `${(t / max) * 100}%` }}>
            <em>{t}</em>
          </span>
        ))}
        <div className="ow-cols-marks">
          {data.map((d, i) => (
            <span
              key={d.key}
              aria-label={`${d.label}: ${d.value} ${d.value === 1 ? unit[0] : unit[1]}`}
              {...tip.bind({ title: d.label, value: `${d.value} ${d.value === 1 ? unit[0] : unit[1]}`, color })}
            >
              {d.value > 0 && <i style={{ height: `${(d.value / max) * 100}%`, background: color, '--d': `${i * 18}ms` } as CSSProperties} />}
            </span>
          ))}
        </div>
      </div>
      <div className="ow-cols-axis">
        {data.map((d) => <span key={d.key}>{d.tick ?? ''}</span>)}
      </div>
      {tip.node}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------------
// Ordered steps: counts along a fixed sequence (a pipeline)

export type Step = { key: string; name: string; value: number; note?: string; tone?: 'good' | 'warn' | 'bad' }

/** A sequence with a natural order (KT stages, access states). Height shows the count; order is never re-ranked. */
export function Steps({ steps, empty = 'Nothing to show.' }: { steps: Step[]; empty?: string }) {
  const tip = useTip()
  const max = Math.max(...steps.map((s) => s.value), 0)
  if (max === 0) return <ChartEmpty>{empty}</ChartEmpty>
  return (
    <div className="ow-steps-chart" ref={tip.ref}>
      {steps.map((s, i) => {
        const color = s.tone ? STATUS[s.tone] : STATUS.accent
        return (
          <div
            key={s.key}
            className={cn(s.value === 0 && 'is-zero')}
            aria-label={`${s.name}: ${s.value}`}
            {...tip.bind({ title: s.name, value: s.value, note: s.note, color })}
          >
            <b>{s.value}</b>
            <span><i style={{ height: `${s.value ? Math.max(8, (s.value / max) * 100) : 0}%`, background: color, '--d': `${i * 70}ms` } as CSSProperties} /></span>
            <small>{s.name}</small>
          </div>
        )
      })}
      {tip.node}
    </div>
  )
}
