import { useState } from 'react'
import type { DailyVolume } from '../api/types'
import { BAND, num } from '../lib/format'
import { chartColors, useTheme } from '../lib/theme'

const SERIES = ['HIGH', 'MEDIUM', 'LOW'] as const
const H = 220, PAD_L = 48, PAD_B = 26, PAD_T = 10, GAP = 2

/** Stacked bars per day, one colour per band (fixed order). Hover tooltip; table toggle. */
export function DailyAlertsChart({ days }: { days: DailyVolume[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [table, setTable] = useState(false)
  const [log, setLog] = useState(true)
  const c = chartColors(useTheme().theme)
  if (!days.length) return <div className="text-[13px] text-muted">No alerts in period.</div>

  const W = 760, plotW = W - PAD_L - 12
  const slot = plotW / days.length, bw = Math.max(6, Math.min(36, slot - 10))
  const max = Math.max(...days.map((d) => d.total))
  const y = (v: number) => (log ? Math.log10(v + 1) / Math.log10(max + 1) : v / max) * (H - PAD_T - PAD_B)
  const ticks = log ? [1, 10, 100, 1000, 10000].filter((t) => t <= max) : [0, max / 2, max]
  const avg = (k: typeof SERIES[number]) => Math.round(days.reduce((a, d) => a + d[k], 0) / days.length)
  const seg = 'h-7 px-2.5 rounded-md text-[12px] font-medium'

  return (
    <div>
      <div className="flex items-center gap-4 text-[12px] text-muted mb-3">
        {SERIES.map((s) => <span key={s} className="inline-flex items-center gap-1.5"><i className={`w-2.5 h-2.5 rounded-sm ${BAND[s].bg}`} /><b className="text-ink">{s}</b> ~{num(avg(s))}/day</span>)}
        <div className="ml-auto inline-flex rounded-lg border border-line bg-well p-0.5">
          <button onClick={() => { setLog(true); setTable(false) }} className={`${seg} ${log && !table ? 'bg-card shadow-sm text-ink' : ''}`}>Log scale</button>
          <button onClick={() => { setLog(false); setTable(false) }} className={`${seg} ${!log && !table ? 'bg-card shadow-sm text-ink' : ''}`}>Linear</button>
          <button onClick={() => setTable(true)} className={`${seg} ${table ? 'bg-card shadow-sm text-ink' : ''}`}>View as table</button>
        </div>
      </div>
      {table ? (
        <table className="text-[13px]">
          <thead><tr><th>Date</th><th className="num">HIGH</th><th className="num">MEDIUM</th><th className="num">LOW</th><th className="num">Total</th></tr></thead>
          <tbody>{days.map((d) => <tr key={d.date}><td className="tabular-nums">{d.date}</td><td className="num">{num(d.HIGH)}</td><td className="num">{num(d.MEDIUM)}</td><td className="num">{num(d.LOW)}</td><td className="num font-semibold">{num(d.total)}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="alerts per day by band">
            {ticks.map((t) => { const yy = H - PAD_B - y(t); return (
              <g key={t}><line x1={PAD_L} x2={W - 12} y1={yy} y2={yy} stroke={c.grid} /><text x={PAD_L - 6} y={yy + 3} textAnchor="end" fontSize={10} fill={c.tick}>{num(Math.round(t))}</text></g>) })}
            <line x1={PAD_L} x2={W - 12} y1={H - PAD_B} y2={H - PAD_B} stroke={c.axis} />
            {days.map((d, i) => {
              const x = PAD_L + i * slot + (slot - bw) / 2
              let cum = 0
              const segs = SERIES.map((s) => { const y0 = y(cum), y1 = y(cum + d[s]); cum += d[s]; return { s, top: H - PAD_B - y1, h: Math.max(0, y1 - y0 - (d[s] ? GAP : 0)) } })
              const dim = hover !== null && hover !== i
              return (
                <g key={d.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={x - 5} y={PAD_T} width={bw + 10} height={H - PAD_T - PAD_B} fill="transparent" />
                  {segs.map((g, j) => g.h > 0 && <rect key={g.s} x={x} y={g.top} width={bw} height={g.h} rx={j === SERIES.length - 1 || segs.slice(j + 1).every((k) => k.h <= 0) ? 3 : 0} fill={BAND[g.s].hex} opacity={dim ? 0.35 : 1} />)}
                  <text x={x + bw / 2} y={H - PAD_B + 14} textAnchor="middle" fontSize={10} fill={hover === i ? c.tickActive : c.tick} fontWeight={hover === i ? 600 : 400}>{d.date.slice(5)}</text>
                </g>)
            })}
          </svg>
          {hover !== null && (
            <div className="absolute top-2 left-1/2 -translate-x-1/2 rounded-lg bg-tooltip text-on-tooltip text-[12px] px-3 py-2 shadow-pop tabular-nums pointer-events-none min-w-44">
              <div className="opacity-60 text-[10px] uppercase tracking-[0.05em]">{days[hover].date}</div>
              <div className="font-semibold mb-1">Total: {num(days[hover].total)} alerts</div>
              {SERIES.map((s) => <div key={s} className="flex justify-between gap-4"><span className="opacity-75">{s}</span><span>{num(days[hover][s])} <span className="opacity-60">({days[hover].total ? ((days[hover][s] / days[hover].total) * 100).toFixed(1) : 0}%)</span></span></div>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
