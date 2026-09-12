import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAccount, useAccountGraph } from '../api/hooks'
import { ForceGraph } from '../components/ForceGraph'
import { BandPill, Card, Empty, ErrorBox, Icon, Mono, Skeleton } from '../components/ui'
import { money, num } from '../lib/format'

export function AccountGraphPage() {
  const id = decodeURIComponent(useParams().id ?? '')
  const [sp, setSp] = useSearchParams()
  const hops = sp.get('hops') === '2' ? 2 : 1
  const nav = useNavigate()
  const graph = useAccountGraph(id, hops)
  const acct = useAccount(id)
  const a = acct.data

  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Account <Mono className="text-[20px]">{id}</Mono></h1>
          {a?.risk.worst_band && <BandPill band={a.risk.worst_band} />}
          <div className="ml-auto flex items-center gap-3">
            <div className="inline-flex rounded-lg border border-line bg-well p-0.5">
              {([1, 2] as const).map((h) => (
                <button key={h} onClick={() => setSp({ hops: String(h) })} className={`h-7 px-3 rounded-md text-[12.5px] font-medium ${hops === h ? 'bg-primary text-white shadow-sm' : 'text-muted hover:text-ink'}`}>{h}-Hop</button>
              ))}
            </div>
            <Link to={`/ask?account=${encodeURIComponent(id)}`} className="inline-flex items-center gap-1 text-[12.5px] text-primary hover:underline">Ask agent <Icon name="arrow_forward" className="text-[16px]" /></Link>
            <Link to="/" className="inline-flex items-center gap-1 text-[12.5px] text-muted hover:text-ink"><Icon name="arrow_back" className="text-[16px]" /> Back to queue</Link>
          </div>
        </div>
        {a ? (
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-well border border-line p-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted">Alerts resolution</div>
              <div className="flex items-end justify-between mt-1">
                <div className="text-[22px] font-semibold tabular-nums text-ink leading-none">{a.risk.n_alerts} <span className="text-[12px] text-muted font-normal">/ {a.risk.n_scored_txns} scored</span></div>
                <div className="text-[12px] text-high font-medium">{a.risk.n_scored_txns ? ((a.risk.n_alerts / a.risk.n_scored_txns) * 100).toFixed(1) : 0}% triage</div>
              </div>
              <div className="mt-2 h-1 bg-line-soft rounded-full"><div className="h-full bg-high rounded-full" style={{ width: `${a.risk.n_scored_txns ? (a.risk.n_alerts / a.risk.n_scored_txns) * 100 : 0}%` }} /></div>
            </div>
            <div className="rounded-lg bg-well border border-line p-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted"><Icon name="north_east" className="text-[14px] text-high" /> Outflow</div>
              <div className="flex items-end justify-between mt-1"><div className="text-[22px] font-semibold tabular-nums text-ink leading-none">{money(a.activity.total_sent)}</div>
                <div className="text-[12px] text-muted text-right">{a.activity.n_sent} transactions<br />across {a.activity.distinct_destinations} accounts</div></div>
            </div>
            <div className="rounded-lg bg-well border border-line p-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted"><Icon name="south_west" className="text-[14px] text-ok" /> Inflow</div>
              <div className="flex items-end justify-between mt-1"><div className="text-[22px] font-semibold tabular-nums text-ink leading-none">{money(a.activity.total_received)}</div>
                <div className="text-[12px] text-muted text-right">{a.activity.n_received} transactions<br />from {a.activity.distinct_sources} accounts</div></div>
            </div>
          </div>
        ) : acct.error ? <ErrorBox error={acct.error} onRetry={() => acct.refetch()} /> : (
          <div className="grid grid-cols-3 gap-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
        )}
      </div>

      <Card title="Entity Transaction Graph" sub={`graph depth: ${hops} hop${hops > 1 ? 's' : ''} · layout: force-directed`} sources={['neo4j']} pad={false}
        right={graph.data && <span className="text-[12px] text-muted tabular-nums">{num(graph.data.nodes.length)} nodes · {num(graph.data.edges.length)} edges{graph.data.truncated && <span className="ml-2 h-5 px-2 inline-flex items-center rounded bg-medium-tint text-medium border border-medium-line text-[10px] font-semibold uppercase">Showing subset</span>}</span>}>
        {graph.error ? <div className="p-4"><ErrorBox error={graph.error} onRetry={() => graph.refetch()} /></div>
          : graph.data ? (graph.data.nodes.length <= 1 ? <Empty icon="hub" title="No counterparties loaded">Account is in the graph but isolated.</Empty>
            : <ForceGraph graph={graph.data} onNodeClick={(n) => n !== id && nav(`/accounts/${encodeURIComponent(n)}?hops=${hops}`)} />)
          : <Skeleton className="h-[480px] rounded-none" />}
      </Card>

      {a && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card title="Graph Counterparties" sub={`· ${a.counterparties.length}`} sources={['neo4j']} pad={false}>
            {!a.graph_available ? <div className="p-4"><ErrorBox error={a.graph_error ?? 'graph unavailable'} /></div>
              : a.counterparties.length === 0 ? <Empty icon="group_off" title="None" />
              : <table className="text-[13px]"><thead><tr><th>Account</th><th>Direction</th><th className="num">Txns</th><th className="num">Total</th></tr></thead>
                <tbody>{a.counterparties.map((c, i) => (
                  <tr key={i}><td><Link className="hover:underline" to={`/accounts/${encodeURIComponent(c.account)}`}><Mono>{c.account}</Mono></Link></td>
                    <td><span className={`inline-flex h-5 px-2 items-center rounded text-[10px] font-semibold uppercase tracking-[0.05em] ${c.direction === 'received from' ? 'bg-ok-tint text-ok' : 'bg-well text-muted border border-line'}`}>{c.direction === 'received from' ? 'Received' : 'Paid to'}</span></td>
                    <td className="num text-muted">{c.n_txns}</td><td className={`num font-medium ${c.direction === 'received from' ? 'text-ok' : 'text-ink'}`}>{money(c.total)}</td></tr>
                ))}</tbody></table>}
          </Card>
          <Card title="Cycles Back to This Account" sub={`· ${a.cycles.length}`} sources={['neo4j']}>
            {!a.graph_available ? <ErrorBox error={a.graph_error ?? 'graph unavailable'} />
              : a.cycles.length === 0 ? <Empty icon="sync_disabled" title="No cycles within 6 hops" />
              : <ul className="space-y-2">{a.cycles.map((c, i) => (
                <li key={i} className="rounded-lg border border-high-line bg-high-tint p-3">
                  <div className="flex items-center justify-between mb-1.5"><span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.05em] text-high"><Icon name="cycle" className="text-[14px]" /> {c.hops} hops · cycle</span><span className="text-[13px] font-semibold tabular-nums text-ink">{money(c.total)}</span></div>
                  <div className="mono text-[11.5px] text-ink-2 break-all">{c.path.map((p, j) => <span key={j}>{j > 0 && <span className="text-high mx-1">→</span>}{p}</span>)}</div>
                </li>))}</ul>}
          </Card>
          <Card title="Shared-Counterparty Peers" sub={`· ${a.ring.length}`} sources={['neo4j']} pad={a.ring.length > 0 ? false : true}>
            {!a.graph_available ? <ErrorBox error={a.graph_error ?? 'graph unavailable'} />
              : a.ring.length === 0 ? <Empty icon="hub" title="No peers sharing ≥ 3 counterparties">No external accounts share 3 or more nodes with this one.<div className="mt-3 inline-flex h-6 px-2 items-center rounded bg-well border border-line text-[11px] text-muted">Threshold: ≥3 shared nodes</div></Empty>
              : <table className="text-[13px]"><thead><tr><th>Account</th><th className="num">Shared</th></tr></thead>
                <tbody>{a.ring.map((r) => <tr key={r.account}><td><Link className="hover:underline" to={`/accounts/${encodeURIComponent(r.account)}`}><Mono>{r.account}</Mono></Link></td><td className="num">{r.shared_cp}</td></tr>)}</tbody></table>}
          </Card>
        </div>
      )}
    </div>
  )
}
