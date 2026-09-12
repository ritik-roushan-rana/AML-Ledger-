import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAsk, useHealth } from '../api/hooks'
import type { ToolCall } from '../api/types'
import { Button, Card, ErrorBox, Icon, Mono, SourceTag, type Source } from '../components/ui'

const TOOL_SOURCE: Record<string, Source> = {
  account_lookup: 'neo4j', graph_search: 'neo4j', path_analysis: 'neo4j', money_flow: 'neo4j', find_cycles: 'neo4j', community_detection: 'neo4j',
  shap_explanation: 'shap', rule_check: 'rules', xgboost_prediction: 'xgboost', anomaly_detection: 'iforest',
  risk_lookup: 'xgboost', transaction_search: 'store', aggregation: 'store',
}
const EXAMPLES = [
  'Why was transaction {txn} flagged, and which rules fired?',
  'Does money sent by {acct} come back to it?',
  'Who are the biggest counterparties of {acct} and is it part of a ring?',
  'Is there a payment path from {acct} to 14325-801A21E40?',
]

function Trace({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!calls.length) return <div className="text-[13px] text-muted p-4">No tools called yet.</div>
  return (
    <ol className="space-y-2 p-4">
      {calls.map((c, i) => {
        const err = typeof c.result === 'object' && c.result !== null && 'error' in (c.result as object)
        const isOpen = open === i
        return (
          <li key={i} className={`rounded-lg border ${err ? 'border-high-line' : 'border-line'} ${isOpen ? 'bg-well' : 'bg-card'}`}>
            <button onClick={() => setOpen(isOpen ? null : i)} className="w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-well rounded-lg">
              <span className={`text-[12px] font-semibold tabular-nums w-5 ${err ? 'text-high' : 'text-primary'}`}>{i + 1}.</span>
              <span className="min-w-0 flex-1">
                <Mono className={`block ${err ? 'text-high' : 'text-ink'}`}>{c.tool}</Mono>
                <Mono className="block text-[11px] text-muted truncate">{Object.entries(c.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' · ')} · {c.ms >= 1000 ? `${(c.ms / 1000).toFixed(1)}s` : `${c.ms}ms`}{err && <span className="text-high"> (error)</span>}</Mono>
              </span>
              <SourceTag source={TOOL_SOURCE[c.tool] ?? 'store'} />
              <Icon name={isOpen ? 'expand_less' : 'expand_more'} className="text-faint" />
            </button>
            {isOpen && <pre className="mono text-[11px] text-ink-2 bg-card border-t border-line rounded-b-lg p-3 overflow-auto max-h-72 whitespace-pre">{JSON.stringify(c.result, null, 2)}</pre>}
          </li>
        )
      })}
    </ol>
  )
}

export function AskPage() {
  const [sp] = useSearchParams()
  const txn = sp.get('txn') ? Number(sp.get('txn')) : undefined
  const acct = sp.get('account') ?? undefined
  const [q, setQ] = useState(sp.get('q') ?? '')
  const ask = useAsk()
  const health = useHealth()
  const llmOff = health.data && !health.data.llm_configured
  const fill = (t: string) => setQ(t.replace('{txn}', String(txn ?? 4565663)).replace('{acct}', acct ?? '11-800924840'))
  const go = () => q.trim().length >= 3 && !ask.running && ask.submit({ question: q.trim(), txn_id: txn, account_id: acct })
  const job = ask.job
  const secs = job?.finished_at ? ((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000).toFixed(2) : null
  const sources = [...new Set((job?.trace ?? []).map((c) => TOOL_SOURCE[c.tool] ?? 'store'))]

  return (
    <div className="space-y-4 max-w-[1100px] mx-auto">
      <div className="card p-6">
        <div className="flex items-start gap-4">
          <span className="w-10 h-10 rounded-xl bg-primary-tint text-primary flex items-center justify-center shrink-0"><Icon name="smart_toy" className="text-[22px]" /></span>
          <div className="flex-1 min-w-0">
            <h1 className="text-[20px] font-semibold tracking-tight text-ink">Ask the Investigation Agent</h1>
            <p className="text-[13px] text-muted">Tool-calling LLM over the same ToolBox the pipeline uses — every figure is cited from a tool result.</p>
          </div>
          {(txn || acct) && (
            <span className="inline-flex items-center gap-2 h-8 px-3 rounded-full bg-primary-tint border border-primary-line text-[12.5px] text-ink-2">
              <Icon name="link" className="text-primary text-[16px]" /> Context:
              {txn && <Link to={`/alerts/${txn}`} className="text-primary font-medium hover:underline"><Mono>txn {txn}</Mono></Link>}
              {acct && <Link to={`/accounts/${encodeURIComponent(acct)}`} className="text-primary font-medium hover:underline"><Mono>{acct}</Mono></Link>}
            </span>
          )}
        </div>
        {llmOff && <div className="mt-4"><ErrorBox error="GEMINI_API_KEY is not configured on the backend — the agent cannot run." /></div>}
        <div className="mt-5 rounded-xl border border-line bg-well p-4 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
          <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={3}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); go() } }}
            placeholder="e.g. Why was transaction 4565663 flagged, does money sent by 11-800924840 loop back, and which deterministic rules fired?"
            className="w-full bg-transparent text-[14px] text-ink placeholder:text-faint focus:outline-none resize-none" />
          <div className="flex items-center gap-3 mt-2">
            <Button onClick={go} disabled={ask.running || q.trim().length < 3 || !!llmOff} busy={ask.running} icon="bolt">{ask.running ? 'Working' : 'Ask'}</Button>
            {job?.status === 'done' && <Button variant="secondary" icon="refresh" onClick={go} disabled={ask.running}>Re-run agent</Button>}
            <span className="text-[12px] text-faint">⌘ + Enter to submit</span>
            {job?.status === 'done' && <span className="ml-auto inline-flex items-center gap-1.5 text-[12px] text-ok"><Icon name="check_circle" className="text-[16px]" /> Completed in {secs}s · {job.trace.length} tool calls</span>}
          </div>
        </div>
        <div className="mt-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-muted mb-2">Suggested analytical prompts</div>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((e) => <button key={e} onClick={() => fill(e)} className="h-8 px-3 rounded-full bg-well border border-line text-[12.5px] text-ink-2 hover:border-primary hover:text-primary">{e.replace('{txn}', 'this transaction').replace('{acct}', 'this account')}</button>)}
          </div>
        </div>
        <p className="mt-4 text-[12px] text-muted flex gap-2"><Icon name="verified_user" className="text-primary shrink-0" />The assistant chooses which ToolBox tools to call — transaction feature store, risk engine, SHAP, deterministic rules, and Neo4j graph queries — and may only cite figures those tools return. Every call is documented in the execution trace.</p>
      </div>

      {ask.error && <ErrorBox error={ask.error} />}

      {job && ask.running && (
        <div className="rounded-xl border border-primary-line bg-primary-tint px-4 py-3 flex items-center gap-3 text-[13px]">
          <span className="inline-block w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <span>Job <Mono className="text-primary">{job.job_id}</Mono> · {job.trace.length ? `${job.trace.length} tool call(s) so far — last: ${job.trace[job.trace.length - 1].tool}` : 'planning tool calls…'}</span>
        </div>
      )}

      {job && (
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
          <Card title="Agent Synthesis" sources={['llm']} right={<span className="text-[11px] text-faint tabular-nums">Job <Mono>{job.job_id}</Mono>{job.rounds != null && ` · ${job.rounds} round${job.rounds === 1 ? '' : 's'}`}</span>}>
            <div className="rounded-lg bg-well border border-line p-3 text-[13px] italic text-muted mb-4">“{job.question}”</div>
            {job.answer ? <div className="text-[13.5px] leading-relaxed text-ink-2 whitespace-pre-line">{job.answer}</div>
              : ask.running ? <div className="text-[13px] text-muted">Waiting for the agent…</div> : null}
          </Card>
          <Card title="Tool Execution Trace" sub={`${job.trace.length} operation${job.trace.length === 1 ? '' : 's'}`} pad={false}
            right={<span className="flex gap-1">{sources.map((s) => <SourceTag key={s} source={s} />)}</span>}>
            <Trace calls={job.trace} />
          </Card>
        </div>
      )}
    </div>
  )
}
