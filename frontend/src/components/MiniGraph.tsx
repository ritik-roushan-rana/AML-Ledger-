import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { AccountGraph } from '../api/types'
import { Card, ErrorBox, Icon, Skeleton } from './ui'
import { ForceGraph } from './ForceGraph'

/** 1-hop neighbourhood of BOTH parties of an alert, merged into one graph. */
export function MiniGraph({ from, to }: { from: string; to: string }) {
  const nav = useNavigate()
  const q = useQuery({
    queryKey: ['minigraph', from, to],
    queryFn: async () => {
      const [a, b] = await Promise.allSettled([api.graph(from, 1, 20), api.graph(to, 1, 20)])
      const ok = [a, b].filter((r): r is PromiseFulfilledResult<AccountGraph> => r.status === 'fulfilled').map((r) => r.value)
      if (!ok.length) throw (a.status === 'rejected' ? a.reason : (b as PromiseRejectedResult).reason)
      return ok
    },
    staleTime: 5 * 60_000,
  })
  const merged = useMemo<AccountGraph | null>(() => {
    if (!q.data) return null
    const nodes = new Map<string, AccountGraph['nodes'][number]>()
    const edges = new Map<string, AccountGraph['edges'][number]>()
    for (const g of q.data) {
      for (const n of g.nodes) { const p = nodes.get(n.id); nodes.set(n.id, { ...n, hop: p ? Math.min(p.hop, n.hop) : n.hop, is_root: false }) }
      for (const e of g.edges) edges.set(e.txn_id != null ? String(e.txn_id) : `${e.source}>${e.target}>${e.amount}`, e)
    }
    return { account_id: to, hops: 1, nodes: [...nodes.values()], edges: [...edges.values()], truncated: q.data.some((g) => g.truncated) }
  }, [q.data, to])

  return (
    <Card title="Relationship Network" sub="1 hop around both parties" sources={['neo4j']} pad={false}
      right={<Link to={`/accounts/${encodeURIComponent(to)}?hops=2`} className="inline-flex items-center gap-1 text-[12.5px] text-primary hover:underline">Open interactive graph <Icon name="open_in_new" className="text-[15px]" /></Link>}>
      {q.error ? <div className="p-4"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></div>
        : !merged ? <Skeleton className="h-[300px] rounded-none" />
        : merged.nodes.length === 0 ? <div className="p-6 text-[13px] text-muted">Neither account is in the graph (only alerted neighbourhoods are loaded).</div>
        : <>
            <ForceGraph graph={merged} height={300} compact focus={[from, to]} onNodeClick={(id) => nav(`/accounts/${encodeURIComponent(id)}`)} />
            <div className="px-4 py-2 border-t border-line text-[11px] text-muted tabular-nums">{merged.nodes.length} accounts · {merged.edges.length} transfers{q.data && q.data.length === 1 && ' · one party not in graph'}</div>
          </>}
    </Card>
  )
}
