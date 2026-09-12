import { Link } from 'react-router-dom'
import { useAlerts, useHealth, useStats } from '../api/hooks'
import { DailyAlertsChart } from '../components/DailyAlertsChart'
import { BandPill, BlockSkeleton, Card, ErrorBox, Icon, Mono, Stat } from '../components/ui'
import { BAND, BANDS, money, num, pct, ts } from '../lib/format'

export function OverviewPage() {
  const stats = useStats()
  const health = useHealth()
  const top = useAlerts({ band: ['HIGH'], page: 1, page_size: 10, sort: 'risk_score', desc: true })
  const s = stats.data, h = health.data
  const hi = s?.bands[0]

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight text-ink">Risk Overview</h1>
          <p className="text-[13px] text-muted mt-0.5">Operational performance & triage metrics{s && <> · <span className="tabular-nums">{s.period_start.slice(0, 10)} → {s.period_end.slice(0, 10)}</span></>}</p>
        </div>
        {s && <span className="inline-flex items-center gap-2 h-8 px-3 rounded-lg bg-card border border-line text-[12.5px] text-ink-2"><Icon name="calendar_month" className="text-muted" /> Held-out test period · {s.daily_alerts.length} days</span>}
      </div>
      {stats.error && <ErrorBox error={stats.error} onRetry={() => stats.refetch()} />}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Stat label="Transactions scored" sources={['store']} value={s ? num(s.rows_scored) : '…'} sub={s && <span className="tabular-nums">{s.period_start.slice(0, 10)} → {s.period_end.slice(0, 10)}</span>} />
        <Stat label="Alerts generated" sources={['xgboost', 'rules']} value={s ? num(s.alert_count) : '…'} sub={s && <><b className="text-primary">{pct(s.alert_count / s.rows_scored, 2)}</b> of scored volume</>} />
        <Stat label="Base rate" sources={['truth']} value={s ? pct(s.base_rate, 3) : '…'} sub={s && `${num(s.n_positives)} labelled positives in window`} />
        <Stat label="High-band precision" sources={['xgboost']} accent="text-high" value={hi ? pct(hi.precision, 1) : '…'} sub={s && hi && `${Math.round((hi.precision ?? 0) / s.base_rate)}× lift over base (${num(hi.count)} alerts)`} />
        <Stat label="System status" value={h ? <span className="inline-flex items-center gap-2 text-[18px]"><span className={`w-3 h-3 rounded-full ${h.status === 'ok' ? 'bg-ok' : h.status === 'degraded' ? 'bg-medium' : 'bg-high'}`} />{h.status === 'ok' ? 'All normal' : h.status}</span> : health.error ? <span className="text-high text-[18px]">Backend down</span> : '…'}
          sub={h && `XGB ${h.model_loaded ? '✓' : '✗'} · iForest ${h.anomaly_model_loaded ? '✓' : '✗'} · Neo4j ${h.neo4j.reachable ? '✓' : '✗'} · LLM ${h.llm_configured ? '✓' : '✗'}`} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[2fr_1fr] gap-4">
        <Card title="Alert Volume Per Day" sources={['store', 'xgboost']}>
          {s ? <DailyAlertsChart days={s.daily_alerts} /> : <BlockSkeleton lines={7} />}
        </Card>
        <Card title="Precision by Band" sources={['xgboost', 'shap']} pad={false}>
          {s ? (
            <>
              <table className="text-[13px]">
                <thead><tr><th>Band</th><th className="num">Count</th><th className="num">Positives</th><th className="num w-32">Precision</th></tr></thead>
                <tbody>{BANDS.map((b) => { const r = s.bands.find((x) => x.band === b)!; return (
                  <tr key={b}>
                    <td><Link to={`/?band=${b}`}><BandPill band={b} /></Link></td>
                    <td className="num">{num(r.count)}</td>
                    <td className="num text-muted">{num(r.positives)}</td>
                    <td className="num"><div className={`font-semibold ${BAND[b].text}`}>{pct(r.precision, r.precision != null && r.precision < 0.01 ? 2 : 1)}</div>
                      <div className="h-1 bg-line-soft rounded-full mt-1"><div className={`h-full rounded-full ${BAND[b].bg}`} style={{ width: `${(r.precision ?? 0) * 100}%` }} /></div></td>
                  </tr>) })}</tbody>
              </table>
              <div className="m-4 rounded-lg bg-primary-tint border border-primary-line p-3 text-[12px] text-ink-2 flex gap-2"><Icon name="info" className="text-primary shrink-0" />Bands come from the XGBoost percentile; rules can escalate one band. Isolation Forest results serve as supporting evidence only.</div>
            </>
          ) : <div className="p-4"><BlockSkeleton /></div>}
        </Card>
      </div>

      <Card title="Top High-Risk Alerts" sub={hi ? `(10 of ${num(hi.count)})` : ''} sources={['xgboost', 'rules', 'neo4j']} pad={false}
        right={<Link to="/?band=HIGH" className="inline-flex items-center gap-1 text-[12.5px] text-primary hover:underline">View full queue <Icon name="arrow_forward" className="text-[16px]" /></Link>}>
        {top.error ? <div className="p-4"><ErrorBox error={top.error} /></div> : !top.data ? <div className="p-4"><BlockSkeleton lines={5} /></div> : (
          <table className="text-[13px]">
            <thead><tr><th className="num w-20">Score</th><th className="w-28">Band</th><th className="num w-36">Amount</th><th>Sender</th><th>Receiver</th><th className="w-40">Timestamp</th><th>Rules</th><th className="w-24" /></tr></thead>
            <tbody>{top.data.items.map((a) => (
              <tr key={a.txn_id} className={`border-l-[3px] ${BAND[a.band].rail}`}>
                <td className="num font-semibold text-high">{a.risk_score.toFixed(1)}</td>
                <td><BandPill band={a.band} /></td>
                <td className="num font-medium text-ink">{money(a.amount_usd)}</td>
                <td><Mono>{a.from_id}</Mono></td><td><Mono>{a.to_id}</Mono></td>
                <td className="tabular-nums text-muted">{ts(a.timestamp)}</td>
                <td>{a.n_rules ? <span className="inline-flex h-5 px-2 items-center rounded bg-high-tint text-high border border-high-line text-[11px] font-medium">{a.n_rules} rule{a.n_rules > 1 ? 's' : ''}</span> : <span className="text-faint text-[12px]">model only</span>}</td>
                <td><Link to={`/alerts/${a.txn_id}`} className="inline-flex items-center gap-1 h-8 px-3 rounded-md bg-primary-tint text-primary text-[12.5px] font-medium hover:bg-primary hover:text-white transition-colors">Open <Icon name="arrow_forward" className="text-[14px]" /></Link></td>
              </tr>))}</tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
