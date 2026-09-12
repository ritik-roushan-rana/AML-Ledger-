/* Shared primitives, styled to stitch_aml_alert_triage_console/aml_ledger/DESIGN.md */
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'
import type { Band } from '../api/types'
import { BAND } from '../lib/format'

export const Icon = ({ name, className = '' }: { name: string; className?: string }) => (
  <span className={`material-symbols-outlined ${className}`} aria-hidden>{name}</span>
)

/** Pill risk badge: tinted bg, coloured text, 1px tinted border. */
export function BandPill({ band, className = '' }: { band: Band; className?: string }) {
  const b = BAND[band]
  return (
    <span className={`inline-flex items-center gap-1.5 h-6 px-2 rounded-full border text-[11px] font-semibold uppercase tracking-[0.05em] ${b.tint} ${b.text} ${b.line} ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${b.bg}`} />
      {band}
    </span>
  )
}

export type Source = 'neo4j' | 'llm' | 'xgboost' | 'shap' | 'iforest' | 'rules' | 'store' | 'truth'
const SOURCE: Record<Source, { label: string; dot: string }> = {
  neo4j: { label: 'NEO4J', dot: 'bg-neo' },
  llm: { label: 'LLM', dot: 'bg-llm' },
  xgboost: { label: 'XGBOOST', dot: 'bg-primary' },
  shap: { label: 'SHAP', dot: 'bg-high' },
  iforest: { label: 'ISOLATION FOREST', dot: 'bg-primary' },
  rules: { label: 'RULES', dot: 'bg-medium' },
  store: { label: 'FEATURE STORE', dot: 'bg-faint' },
  truth: { label: 'GROUND TRUTH', dot: 'bg-high' },
}
/** Engine-origin tag: neutral pill with a coloured prefix dot. */
export function SourceTag({ source }: { source: Source }) {
  const s = SOURCE[source]
  return (
    <span className="inline-flex items-center gap-1.5 h-5 px-2 rounded-full bg-well border border-line text-[10px] font-semibold uppercase tracking-[0.05em] text-muted whitespace-nowrap">
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

export function Card({ title, sub, sources, right, children, className = '', pad = true }: {
  title?: ReactNode; sub?: ReactNode; sources?: Source[]; right?: ReactNode
  children: ReactNode; className?: string; pad?: boolean
}) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      {title && (
        <header className="flex items-center gap-2 px-4 py-3 border-b border-line">
          <h2 className="text-[14px] font-semibold text-ink tracking-tight">{title}</h2>
          {sub && <span className="text-[12px] text-muted">{sub}</span>}
          {sources?.map((s) => <SourceTag key={s} source={s} />)}
          {right && <div className="ml-auto flex items-center gap-2">{right}</div>}
        </header>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, sources, accent, className = '' }: {
  label: ReactNode; value: ReactNode; sub?: ReactNode; sources?: Source[]; accent?: string; className?: string
}) {
  return (
    <div className={`card p-4 ${className}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[12px] font-medium text-muted">{label}</span>
        <span className="flex gap-1">{sources?.map((s) => <SourceTag key={s} source={s} />)}</span>
      </div>
      <div className={`text-[26px] leading-none font-semibold tracking-tight tabular-nums ${accent ?? 'text-ink'}`}>{value}</div>
      {sub && <div className="text-[12px] text-muted mt-2">{sub}</div>}
    </div>
  )
}

export const Mono = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <span className={`mono ${className}`}>{children}</span>
)

export function Button({ children, onClick, disabled, variant = 'primary', icon, className = '', busy }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean
  variant?: 'primary' | 'secondary' | 'danger'; icon?: string; className?: string; busy?: boolean
}) {
  const base = 'inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg text-[13px] font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none'
  const v = {
    primary: 'bg-primary text-white border border-primary-dark hover:bg-primary-dark shadow-sm',
    secondary: 'bg-card text-ink-2 border border-line hover:bg-well hover:border-faint',
    danger: 'bg-card text-high border border-high-line hover:bg-high-tint',
  }[variant]
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${v} ${className}`}>
      {busy ? <span className="inline-block w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" /> : icon && <Icon name={icon} />}
      {children}
    </button>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error)
  const status = error instanceof ApiError ? error.status : null
  return (
    <div role="alert" className="rounded-lg border border-high-line bg-high-tint text-[13px] text-high px-3.5 py-2.5 flex items-start gap-3">
      <Icon name="error" className="text-high shrink-0" />
      <span className="font-semibold shrink-0">{status ? `Error ${status}` : 'Error'}</span>
      <span className="flex-1 break-words">{msg}</span>
      {onRetry && <button onClick={onRetry} className="underline shrink-0 hover:text-high">retry</button>}
    </div>
  )
}

export function Empty({ icon = 'inbox', title, children }: { icon?: string; title?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-8 px-4 text-[13px] text-muted">
      <span className="w-10 h-10 rounded-full bg-well border border-line flex items-center justify-center mb-3"><Icon name={icon} className="text-faint" /></span>
      {title && <div className="font-semibold text-ink mb-1">{title}</div>}
      {children}
    </div>
  )
}

export const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`animate-pulse bg-line-soft rounded ${className}`} />
)
export function TableSkeleton({ rows = 12, cols }: { rows?: number; cols: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>{Array.from({ length: cols }).map((_, c) => <td key={c}><Skeleton className="h-3.5 my-1" /></td>)}</tr>
      ))}
    </tbody>
  )
}
export function BlockSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: lines }).map((_, i) => <Skeleton key={i} className={`h-3.5 ${i % 3 === 2 ? 'w-2/3' : 'w-full'}`} />)}
    </div>
  )
}

/** Key/value list used in detail cards. */
export function Kv({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[140px_1fr] gap-y-2 gap-x-3 text-[13px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="text-ink-2 min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  )
}
