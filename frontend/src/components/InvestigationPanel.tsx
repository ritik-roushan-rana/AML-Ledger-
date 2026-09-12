import { useInvestigation } from '../api/hooks'
import { Button, Card, ErrorBox, Mono } from './ui'

export function InvestigationPanel({ txnId, llmConfigured }: { txnId: number; llmConfigured: boolean | undefined }) {
  const inv = useInvestigation(txnId)
  const job = inv.job
  const busy = inv.starting || inv.running
  const secs = job?.finished_at && job.started_at ? ((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000).toFixed(1) : null

  return (
    <Card title="Investigator Narrative" sources={['neo4j', 'shap', 'rules', 'llm']}
      right={<>
        <span className="hidden md:inline-flex items-center gap-1 text-[11px] text-faint mr-2">
          {(['idle', 'running', 'done'] as const).map((s) => {
            const cur = !job ? 'idle' : busy ? 'running' : 'done'
            return <span key={s} className={`px-1.5 py-0.5 rounded ${cur === s ? 'bg-well border border-line text-ink-2' : ''}`}>{s === 'done' ? 'Synthesised' : s[0].toUpperCase() + s.slice(1)}</span>
          })}
        </span>
        <Button onClick={inv.start} disabled={busy} busy={busy} icon={job?.status === 'done' ? 'refresh' : 'auto_awesome'}>
          {job?.status === 'done' ? 'Re-run investigation' : busy ? 'Investigating' : 'Run investigation'}
        </Button>
      </>}>
      {inv.error && <ErrorBox error={inv.error} onRetry={inv.start} />}
      {!job && !inv.error && (
        <p className="text-[13px] text-muted">
          Gathers graph evidence via the tool layer (counterparties, cycles, ring, aggregation) and asks the LLM to narrate it. Figures come only from tool output. Takes 5–30s.
          {llmConfigured === false && <span className="block mt-1 text-medium">No LLM key configured — backend will return the deterministic template narrative.</span>}
        </p>
      )}
      {busy && job && (
        <div className="flex items-center gap-3 text-[13px] text-muted tabular-nums">
          <span className="inline-block w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          Job <Mono>{job.job_id}</Mono> · {job.status} · started {job.started_at.slice(11, 19)}
        </div>
      )}
      {job?.status === 'done' && job.narrative && (
        <div className="max-w-4xl">
          <div className="text-[13.5px] leading-relaxed text-ink-2 whitespace-pre-line">{job.narrative}</div>
          <div className="mt-3 pt-3 border-t border-line text-[11px] text-faint tabular-nums">Execution {secs}s · job <Mono>{job.job_id}</Mono> · figures sourced from tool calls only</div>
        </div>
      )}
    </Card>
  )
}
