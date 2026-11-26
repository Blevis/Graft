import type { ReactNode, SelectHTMLAttributes } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MODE_LABEL, RULE_LABEL, SEVERITY_CLASS } from '@/lib/format'
import type { AnalysisMode, Severity } from '@/lib/types'

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Pill({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap', className)}
    >
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
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
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

export function StatTile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'alert' | 'ok' }) {
  return (
    <div className="rounded-lg border bg-background p-4">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={cn('mt-1 text-2xl font-semibold tabular-nums', tone === 'alert' && 'text-red-700', tone === 'ok' && 'text-primary')}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}

export function Section({ title, actions, children, className }: { title: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('rounded-lg border bg-background', className)}>
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        {actions}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-3 text-sm text-muted-foreground">{children}</p>
}

export function Loading() {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> Loading…
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <AlertTriangle className="size-4" />
      {error instanceof Error ? error.message : 'Something went wrong'}
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  )
}

export function NativeSelect({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
        className,
      )}
      {...props}
    />
  )
}
