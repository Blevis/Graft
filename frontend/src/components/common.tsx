import type { ReactNode, SelectHTMLAttributes } from 'react'
import { AlertTriangle, CircleDot, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MODE_LABEL, RULE_LABEL, SEVERITY_CLASS } from '@/lib/format'
import type { AnalysisMode, Severity } from '@/lib/types'

/** Page title block in the Orchid language: overline, fluid headline, one-line purpose, actions. */
export function PageHeader({
  title, description, actions, eyebrow, compact,
}: { title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode; compact?: boolean }) {
  return (
    <header className={cn('ow-heading', compact && 'compact')}>
      <div>
        {eyebrow && (
          <div className="ow-overline">
            <span />
            {eyebrow}
          </div>
        )}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="ow-heading-actions">{actions}</div>}
    </header>
  )
}

export type Tone = 'neutral' | 'amber' | 'green' | 'red' | 'violet' | 'blue' | 'night'

// Call sites describe intent with colour utilities (amber = waiting, red = blocking, primary = positive ...).
// They map onto the six Orchid tag tones here, so the product has exactly one status vocabulary.
function toneOf(className = ''): Tone {
  if (/\b(?:bg|text|ring)-(?:red|rose)/.test(className) || /destructive/.test(className)) return 'red'
  if (/\b(?:bg|text|ring)-(?:amber|yellow|orange)/.test(className)) return 'amber'
  if (/\b(?:bg|text|ring)-(?:sky|blue|cyan)/.test(className)) return 'blue'
  if (/\b(?:bg|text|ring)-(?:violet|purple|indigo)/.test(className)) return 'violet'
  if (/\b(?:bg|text|ring)-(?:primary|green|emerald)/.test(className)) return 'green'
  return 'neutral'
}

export function Pill({
  className, children, title, tone, dot = true,
}: { className?: string; children: ReactNode; title?: string; tone?: Tone; dot?: boolean }) {
  const t = tone ?? toneOf(className)
  const spacing = (className ?? '').split(/\s+/).filter((c) => /^-?m[lrtbxy]?-/.test(c)).join(' ')
  return (
    <span
      title={title}
      className={cn('ow-tag', t !== 'neutral' && t, /border-dashed/.test(className ?? '') && 'dashed', !dot && 'bare', spacing)}
    >
      {dot && <i />}
      {children}
    </span>
  )
}

export function SeverityBadge({ severity, rule }: { severity: Severity; rule?: string }) {
  return <Pill className={SEVERITY_CLASS[severity]}>{rule ? (RULE_LABEL[rule] ?? rule) : severity}</Pill>
}

const MODE_CLASS: Record<AnalysisMode, string> = {
  live: 'bg-primary/10 text-primary ring-primary/30',
  cached: 'bg-sky-50 text-sky-800 ring-sky-200',
  replay: 'bg-violet-50 text-violet-800 ring-violet-200',
  unavailable: 'bg-slate-100 text-slate-600 ring-slate-200',
}

export function ModeBadge({ mode, model, prompt }: { mode: AnalysisMode; model?: string | null; prompt?: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <Pill className={MODE_CLASS[mode]}>{MODE_LABEL[mode]}</Pill>
      {model && (
        <span className="font-mono">
          {model}
          {prompt ? ` · ${prompt}` : ''}
        </span>
      )}
    </span>
  )
}

/** A divided strip of headline numbers. Children are StatTile cells. */
export function StatStrip({ children, inset, className }: { children: ReactNode; inset?: boolean; className?: string }) {
  return <div className={cn('ow-stats', inset && 'inset', className)}>{children}</div>
}

export function StatTile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'alert' | 'ok' }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function Section({
  title, sub, actions, children, className, tone,
}: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; tone?: 'lilac' | 'blue' | 'subtle' }) {
  return (
    <section className={cn('ow-panel', tone, className)}>
      <header className="ow-panel-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {actions && <div className="ow-panel-actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}

export function Empty({ children, boxed }: { children: ReactNode; boxed?: boolean }) {
  return (
    <div className={cn('ow-empty', boxed && 'boxed')}>
      <CircleDot size={16} className="shrink-0" />
      <span>{children}</span>
    </div>
  )
}

/** Segmented control for saved views and filters. */
export function Segmented<T extends string>({
  options, value, onChange, label,
}: { options: { id: T; label: ReactNode; count?: number }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="ow-toggle" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" aria-pressed={value === o.id} onClick={() => onChange(o.id)}>
          {o.label}
          {o.count !== undefined && <em>{o.count}</em>}
        </button>
      ))}
    </div>
  )
}

export function Avatar({ name, large }: { name: string; large?: boolean }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')
  return <span className={cn('ow-avatar', large && 'large')} aria-hidden="true">{initials || '·'}</span>
}

export function Loading() {
  return (
    <div className="flex items-center gap-2 py-10 text-[13px] text-muted-foreground" role="status">
      <Loader2 className="size-4 animate-spin text-primary" /> Loading…
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  return (
    <div role="alert" className="flex items-center gap-2.5 rounded-xl border border-[#f3c9d1] bg-[#fdf0f2] px-4 py-3 text-[13px] font-semibold text-[#8f2d40]">
      <AlertTriangle className="size-4 shrink-0" />
      {error instanceof Error ? error.message : 'Something went wrong'}
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-[13px]">
      <span className="font-bold">{label}</span>
      {children}
      {hint && <span className="text-xs font-medium text-muted-foreground">{hint}</span>}
    </label>
  )
}

export function NativeSelect({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'h-9 w-full cursor-pointer rounded-[9px] border border-input bg-[#fdfcfe] px-2.5 text-sm font-medium outline-none focus-visible:border-ring focus-visible:bg-white focus-visible:ring-3 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
