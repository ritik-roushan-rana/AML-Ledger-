import { useSearchParams } from 'react-router-dom'
import { useAlerts, useStats } from '../api/hooks'
import type { AlertQuery, Band, SortField } from '../api/types'
import { AlertTable } from '../components/AlertTable'
import { BandCards } from '../components/BandCards'
import { Pagination } from '../components/Pagination'
import { Empty, ErrorBox, Icon } from '../components/ui'
import { BANDS, num, pct } from '../lib/format'

const PAGE_SIZE = 50
const SORTS: SortField[] = ['risk_score', 'timestamp', 'amount_usd', 'n_rules', 'txn_id']

/** Filter state lives in the URL so back/forward and sharing work. */
function parse(sp: URLSearchParams): AlertQuery {
  const band = sp.getAll('band').filter((b): b is Band => (BANDS as string[]).includes(b))
  const rawSort = sp.get('sort') ?? '-risk_score'
  const sortKey = rawSort.replace(/^-/, '') as SortField
  const ms = Number(sp.get('min_score'))
  return {
    band: band.length ? band : undefined,
    min_score: sp.has('min_score') && Number.isFinite(ms) ? ms : undefined,
    page: Math.max(1, Number(sp.get('page')) || 1),
    page_size: PAGE_SIZE,
    sort: SORTS.includes(sortKey) ? sortKey : 'risk_score',
    desc: rawSort.startsWith('-'),
  }
}

export function QueuePage() {
  const [sp, setSp] = useSearchParams()
  const q = parse(sp)
  const stats = useStats()
  const alerts = useAlerts(q)

  const update = (patch: Partial<Record<'band' | 'sort' | 'page' | 'min_score', string | string[] | null>>) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) {
      next.delete(k)
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x))
      else if (v != null && v !== '') next.set(k, v)
    }
    if (!('page' in patch)) next.delete('page')
    setSp(next)
  }
  const toggleBand = (b: Band) => {
    const cur = q.band ?? []
    update({ band: cur.includes(b) ? cur.filter((x) => x !== b) : [...cur, b] })
  }
  const onSort = (f: SortField) => update({ sort: f === q.sort ? (q.desc ? f : `-${f}`) : `-${f}` })
  const filtered = !!(q.band?.length || q.min_score != null || q.sort !== 'risk_score' || !q.desc)

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight text-ink">Triage Alert Queue</h1>
          <p className="text-[13px] text-muted mt-0.5">Transactions ranked by XGBoost percentile, escalated by deterministic typology rules.</p>
        </div>
      </div>

      {stats.error && <ErrorBox error={stats.error} onRetry={() => stats.refetch()} />}
      <BandCards stats={stats.data} active={q.band ?? []} onToggle={toggleBand} />
      {stats.data && (
        <div className="flex items-center gap-2 text-[12px] text-muted -mt-2 px-1">
          <Icon name="database" className="text-[16px]" />
          <b className="text-ink tabular-nums">{num(stats.data.rows_scored)}</b> txns scored ·
          <b className="text-high tabular-nums">{num(stats.data.alert_count)}</b> alerts · base rate {pct(stats.data.base_rate, 2)} ·
          <span className="tabular-nums">{stats.data.period_start.slice(0, 10)} → {stats.data.period_end.slice(0, 10)}</span>
        </div>
      )}

      <div className="card">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-line">
          <span className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-well border border-line text-[12.5px] text-ink-2">
            <Icon name="filter_list" className="text-primary" />
            Risk band: <b>{q.band?.length ? q.band.join(', ') : 'HIGH, MEDIUM, LOW'}</b>
          </span>
          <label className="inline-flex items-center gap-2 h-8 px-3 rounded-lg bg-well border border-line text-[11px] font-semibold uppercase tracking-[0.05em] text-muted">
            Min score
            <input type="number" min={0} max={100} step={0.5} defaultValue={q.min_score ?? ''} key={q.min_score ?? 'none'}
              onBlur={(e) => update({ min_score: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              className="w-16 h-6 px-1.5 rounded border border-line bg-card text-[12.5px] normal-case tracking-normal font-normal text-ink tabular-nums focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
          </label>
          {filtered && (
            <button onClick={() => setSp({})} className="inline-flex items-center gap-1 text-[12.5px] text-primary hover:underline"><Icon name="restart_alt" className="text-[16px]" /> Reset filters</button>
          )}
          <span className="ml-auto text-[12px] text-faint">{alerts.isFetching ? 'Refreshing…' : alerts.data ? `${num(alerts.data.total)} matching` : ''}</span>
        </div>

        {alerts.error ? (
          <div className="p-4"><ErrorBox error={alerts.error} onRetry={() => alerts.refetch()} /></div>
        ) : alerts.data && alerts.data.total === 0 ? (
          <Empty icon="filter_alt_off" title="No alerts match these filters">Try widening the band selection or lowering the minimum score.</Empty>
        ) : (
          <>
            <AlertTable items={alerts.data?.items} loading={alerts.isFetching} sort={q.sort} desc={q.desc} onSort={onSort} />
            {alerts.data && (
              <Pagination page={alerts.data.page} pages={alerts.data.pages} total={alerts.data.total} pageSize={PAGE_SIZE} onPage={(p) => update({ page: String(p) })} />
            )}
          </>
        )}
      </div>
    </div>
  )
}
