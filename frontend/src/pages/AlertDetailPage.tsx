import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAlert, useHealth } from '../api/hooks'
import { CounterpartyTable } from '../components/CounterpartyTable'
import { InvestigationPanel } from '../components/InvestigationPanel'
import { MiniGraph } from '../components/MiniGraph'
import { MoneyFlowTable } from '../components/MoneyFlowTable'
import { ReportView } from '../components/ReportView'
import { RulesList } from '../components/RulesList'
import { ShapChart } from '../components/ShapChart'
import { BandPill, BlockSkeleton, Card, ErrorBox, Icon, Kv, Mono, Skeleton, SourceTag, type Source } from '../components/ui'
import { ACTION_TEXT, BAND, caseId, money, ts } from '../lib/format'

const AcctLink = ({ id }: { id: string }) => (
  <Link to={`/accounts/${encodeURIComponent(id)}`} className="text-primary hover:underline"><Mono>{id}</Mono></Link>
)

const MODULES: { id: string; label: string; source: Source }[] = [
  { id: 'transaction', label: 'Transaction', source: 'store' },
  { id: 'why', label: 'Why flagged', source: 'shap' },
  { id: 'rules', label: 'Rules fired', source: 'rules' },
  { id: 'counterparties', label: 'Counterparties', source: 'store' },
  { id: 'flow', label: 'Money flow', source: 'store' },
  { id: 'network', label: 'Network graph', source: 'neo4j' },
  { id: 'narrative', label: 'Narrative AI', source: 'llm' },
]

export function AlertDetailPage() {
  const id = Number(useParams().id)
  const q = useAlert(id)
  const health = useHealth()
  const [tab, setTab] = useState<'detail' | 'report'>('detail')
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const band = d?.risk.band

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-[12.5px]">
        <nav className="flex items-center gap-2 text-muted">
          <Link to="/" className="inline-flex items-center gap-1 text-primary hover:underline"><Icon name="arrow_back" className="text-[16px]" /> Back to queue</Link>
          <span className="text-faint">/</span><span>Queue</span><span className="text-faint">/</span>
          <Mono className="text-ink">{caseId(id)}</Mono>
        </nav>
        <Link to={`/ask?txn=${id}`} className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary-tint text-primary text-[12.5px] font-medium hover:bg-primary-line/40">
          <Icon name="smart_toy" className="text-[16px]" /> Ask agent about this
        </Link>
      </div>

      {/* case header */}
      <div className={`card border-t-4 ${band ? BAND[band].rail.replace('border-l-', 'border-t-') : 'border-t-line'} p-5`}>
        {d ? (
          <>
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <h1 className="text-[22px] font-semibold tracking-tight text-ink">Case <Mono className="text-[20px]">{caseId(d.transaction.txn_id)}</Mono></h1>
              <BandPill band={d.risk.band} />
              {d.risk.escalated && <span className="inline-flex items-center gap-1 h-6 px-2 rounded-full bg-medium-tint text-medium border border-medium-line text-[11px] font-semibold"><Icon name="trending_up" className="text-[14px]" /> Escalated by rules</span>}
              {d.risk.ground_truth_label != null && (
                <span className={`inline-flex items-center gap-1.5 h-6 px-2 rounded-full border text-[11px] font-semibold ${d.risk.ground_truth_label ? 'bg-high-tint text-high border-high-line' : 'bg-well text-muted border-line'}`}>
                  <SourceTag source="truth" />{d.risk.ground_truth_label ? 'Labelled laundering' : 'Labelled legitimate'}
                </span>
              )}
              <span className="ml-auto text-[12px] text-faint tabular-nums">txn {d.transaction.txn_id} · {ts(d.transaction.timestamp)}</span>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="rounded-lg bg-well border border-line p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted mb-1">Deterministic risk score</div>
                <div className={`text-[28px] leading-none font-semibold tabular-nums ${BAND[d.risk.band].text}`}>{d.risk.risk_score.toFixed(1)} <span className="text-[13px] text-faint font-normal">/ 100</span></div>
                {d.risk.anomaly_pct != null && <div className="text-[12px] text-muted mt-1.5">Anomaly percentile <b className={d.risk.anomaly_pct >= 99 ? 'text-medium' : 'text-ink'}>top {(100 - d.risk.anomaly_pct).toFixed(1)}%</b> <SourceTag source="iforest" /></div>}
              </div>
              <div className="rounded-lg bg-well border border-line p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted mb-1">Recommended disposition</div>
                <div className={`text-[16px] font-semibold ${d.risk.action === 'REPORT' ? 'text-high' : 'text-ink'}`}><Icon name={d.risk.action === 'REPORT' ? 'priority_high' : 'flag'} className="text-[18px]" /> {d.risk.action}</div>
                <div className="text-[12px] text-muted mt-1">{ACTION_TEXT[d.risk.action]}</div>
              </div>
              <div className="rounded-lg bg-well border border-line p-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted mb-1">Pattern classification</div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {d.rules_fired.length ? d.rules_fired.map((r) => <span key={r.name} className="mono h-5 px-1.5 inline-flex items-center rounded bg-high-tint text-high border border-high-line text-[10.5px] uppercase">{r.name}</span>)
                    : <span className="text-[12px] text-muted">Model-only alert · no typology rule matched</span>}
                </div>
              </div>
              <div className="rounded-lg bg-well border border-line p-3 text-[12px] tabular-nums space-y-1">
                <div className="flex justify-between"><span className="text-muted">Model percentile</span><Mono className="text-ink">{d.risk.model_pct.toFixed(3)}</Mono></div>
                <div className="flex justify-between"><span className="text-muted">Raw probability</span><Mono className="text-ink">{d.risk.model_score.toFixed(4)}</Mono></div>
                <div className="flex justify-between"><span className="text-muted">Rule score</span><Mono className="text-ink">{d.risk.rule_score.toFixed(0)} <span className="text-faint">({d.risk.n_rules} triggered)</span></Mono></div>
              </div>
            </div>
          </>
        ) : <div className="space-y-3"><Skeleton className="h-7 w-72" /><Skeleton className="h-24" /></div>}
      </div>

      {/* tabs */}
      <div className="flex items-center gap-6 border-b border-line">
        {([['detail', 'Detail workspace', 'space_dashboard'], ['report', 'Investigation report (SAR draft)', 'description']] as const).map(([t, l, ic]) => (
          <button key={t} onClick={() => setTab(t)} className={`inline-flex items-center gap-1.5 h-10 -mb-px border-b-2 text-[13px] font-medium ${tab === t ? 'border-primary text-primary' : 'border-transparent text-muted hover:text-ink'}`}>
            <Icon name={ic} className="text-[17px]" />{l}
          </button>
        ))}
      </div>

      {tab === 'report' ? (
        <Card title="Investigation Report" sub="assembled from fusion + rules + SHAP + narrative"><ReportView txnId={id} /></Card>
      ) : !d ? (
        <div className="grid grid-cols-2 gap-4"><Card title="Transaction"><BlockSkeleton /></Card><Card title="Why flagged"><BlockSkeleton lines={6} /></Card></div>
      ) : (
        <div className="grid grid-cols-[210px_1fr] gap-4 items-start">
          {/* case modules rail */}
          <aside className="card p-3 sticky top-[72px] hidden lg:block">
            <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted mb-2 px-1">Case modules</div>
            <ul className="space-y-0.5">
              {MODULES.map((m) => (
                <li key={m.id}><a href={`#${m.id}`} className="flex items-center justify-between gap-2 px-2 h-8 rounded-md text-[12.5px] text-ink-2 hover:bg-well whitespace-nowrap">
                  {m.label}<SourceTag source={m.source} /></a></li>
              ))}
            </ul>
          </aside>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 min-w-0">
            <Card title="Transaction Details" sources={['store']} right={<Mono className="text-faint text-[11px]">ID {d.transaction.txn_id}</Mono>}>
              <div id="transaction" className="rounded-lg bg-well border border-line p-3 mb-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted">Settled amount</div>
                <div className="text-[24px] font-semibold tabular-nums text-ink leading-tight">{money(d.transaction.amount_usd)} <span className="text-[13px] text-muted font-normal">USD</span></div>
                {d.transaction.currency_paid && d.transaction.amount_paid != null && d.transaction.currency_paid !== 'US Dollar' && (
                  <div className="text-[12px] text-muted mt-0.5">{d.transaction.amount_paid.toLocaleString()} {d.transaction.currency_paid}{d.transaction.currency_received !== d.transaction.currency_paid ? ` → ${d.transaction.amount_received?.toLocaleString()} ${d.transaction.currency_received}` : ''}</div>
                )}
              </div>
              <Kv rows={[
                ['Sender account', <AcctLink id={d.transaction.from_id} />],
                ['Beneficiary account', <AcctLink id={d.transaction.to_id} />],
                ['Timestamp', <span className="tabular-nums">{ts(d.transaction.timestamp)}</span>],
                ['Routing', `${d.transaction.from_bank ?? '?'} → ${d.transaction.to_bank ?? '?'}${d.transaction.is_cross_bank ? ' · cross-bank' : ''}${d.transaction.is_cross_currency ? ' · cross-currency' : ''}`],
                ['Format', d.transaction.payment_format ?? '—'],
                ['Sender 96h', `${d.activity.sender_96h_payments} payments → ${d.activity.sender_96h_counterparties} accounts`],
                ['Receiver 96h', `${d.activity.receiver_96h_deposits} deposits ← ${d.activity.receiver_96h_sources} sources`],
                ...(d.activity.chain_depth ? [['Layering chain', <span className="text-medium">{d.activity.chain_depth} hops forward</span>] as [string, React.ReactNode]] : []),
                ...(d.activity.cycle_len ? [['Cycle', <span className="text-high">returns to sender in {d.activity.cycle_len} hops</span>] as [string, React.ReactNode]] : []),
              ]} />
            </Card>

            <Card title="Why Flagged" sources={['xgboost', 'shap']} right={<span className="text-[11px] text-faint">top {d.shap_drivers.length} · pct {d.risk.model_pct.toFixed(2)}</span>}>
              <div id="why"><ShapChart drivers={d.shap_drivers} /></div>
            </Card>

            <Card title="Rules Fired" sub={`${d.rules_fired.length} of 9 triggered`} sources={['rules']}>
              <div id="rules"><RulesList rules={d.rules_fired} /></div>
              <p className="text-[11px] text-faint mt-3 pt-3 border-t border-line">Deterministic engine · thresholds from configs/rules.yaml · rules can escalate one band</p>
            </Card>

            <Card title="Counterparties" sub={`${d.counterparties.length} accounts involved`} sources={['store']} pad={false}>
              <div id="counterparties"><CounterpartyTable rows={d.counterparties} /></div>
            </Card>

            <Card title="Money Flow" sub={`96-hour chronology · ${d.money_flow.length} transits`} sources={['store']} pad={false} className="xl:col-span-2">
              <div id="flow"><MoneyFlowTable rows={d.money_flow} focus={new Set([d.transaction.from_id, d.transaction.to_id])} /></div>
            </Card>

            <div id="network" className="xl:col-span-2"><MiniGraph from={d.transaction.from_id} to={d.transaction.to_id} /></div>
            <div id="narrative" className="xl:col-span-2"><InvestigationPanel txnId={id} llmConfigured={health.data?.llm_configured} /></div>
          </div>
        </div>
      )}
    </div>
  )
}
