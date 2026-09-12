import type { Band, Stats } from '../api/types'
import { BAND, BANDS, num, pct } from '../lib/format'
import { BandPill, Icon, Skeleton, SourceTag } from './ui'

const SOURCES: Record<Band, ('xgboost' | 'rules' | 'iforest')[]> = {
  HIGH: ['xgboost', 'rules'], MEDIUM: ['xgboost', 'rules'], LOW: ['xgboost'], CLEAR: ['xgboost'],
}

export function BandCards({ stats, active, onToggle }: { stats: Stats | undefined; active: Band[]; onToggle: (b: Band) => void }) {
  const maxPrec = Math.max(...(stats?.bands.map((b) => b.precision ?? 0) ?? [1]), 0.0001)
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {BANDS.map((b) => {
        const s = stats?.bands.find((x) => x.band === b)
        const on = active.includes(b)
        return (
          <button key={b} onClick={() => onToggle(b)} aria-pressed={on}
            className={`card text-left p-4 group transition-all hover:shadow-pop ${on ? 'ring-2 ring-primary bg-primary-tint/30' : ''}`}>
            <div className="flex items-center justify-between mb-3">
              <BandPill band={b} />
              <span className="flex gap-1">{SOURCES[b].map((s) => <SourceTag key={s} source={s} />)}</span>
            </div>
            {s ? (
              <>
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-[30px] leading-none font-semibold tracking-tight tabular-nums text-ink">{num(s.count)}</span>
                  <Icon name={on ? 'check_circle' : 'radio_button_unchecked'} className={on ? 'text-primary' : 'text-line'} />
                </div>
                <div className="flex items-center justify-between text-[12px] text-muted">
                  <span>Precision {pct(s.precision, s.precision != null && s.precision < 0.01 ? 2 : 0)} · {pct(s.share, s.share < 0.01 ? 2 : 1)} of volume</span>
                  <Icon name="chevron_right" className="text-[16px]" />
                </div>
                <div className="mt-3 h-1 w-full bg-line-soft rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${BAND[b].bg}`} style={{ width: `${Math.max(2, ((s.precision ?? 0) / maxPrec) * 100)}%` }} />
                </div>
              </>
            ) : <Skeleton className="h-16" />}
          </button>
        )
      })}
    </div>
  )
}
