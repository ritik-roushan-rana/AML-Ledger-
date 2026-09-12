import type { ShapDriver } from '../api/types'
import { Empty } from './ui'

const fmtVal = (v: ShapDriver['value']) =>
  v == null ? '—' : typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : v

/** Horizontal bars, longest = strongest driver. Pure CSS. */
export function ShapChart({ drivers }: { drivers: ShapDriver[] }) {
  if (!drivers.length) return <Empty icon="analytics" title="No positive SHAP drivers">Model score rests on the baseline.</Empty>
  const max = Math.max(...drivers.map((d) => Math.abs(d.shap)))
  return (
    <div className="space-y-3">
      {drivers.map((d) => {
        const up = d.shap > 0
        return (
          <div key={d.feature} title={`${d.feature} = ${fmtVal(d.value)}`}>
            <div className="flex items-baseline justify-between gap-3 text-[13px] mb-1">
              <span className="truncate text-ink-2">{d.label} <span className="text-muted">= {fmtVal(d.value)}</span></span>
              <span className={`tabular-nums font-semibold shrink-0 ${up ? 'text-high' : 'text-primary'}`}>{up ? '+' : ''}{d.shap.toFixed(2)}</span>
            </div>
            <div className="h-1.5 bg-line-soft rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${up ? 'bg-high' : 'bg-primary'}`} style={{ width: `${(Math.abs(d.shap) / max) * 100}%` }} />
            </div>
          </div>
        )
      })}
      <p className="text-[11px] text-faint pt-1">Gradient-boosted trees (XGBoost), exact TreeExplainer attribution. Positive = pushes toward laundering.</p>
    </div>
  )
}
