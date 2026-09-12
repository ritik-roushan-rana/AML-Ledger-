import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'
import type { AccountGraph, GraphEdge, GraphNode } from '../api/types'
import { BAND, money0 } from '../lib/format'
import { Icon } from './ui'
import { chartColors, useTheme } from '../lib/theme'

type N = GraphNode & { degree: number; alerted: boolean }
type L = GraphEdge & { width: number }
type NodeT = NodeObject<N>
type LinkT = LinkObject<N, L>

const RED = '#DC2626'

export function ForceGraph({ graph, onNodeClick, height, focus, compact = false }: {
  graph: AccountGraph; onNodeClick: (id: string) => void
  height?: number; focus?: string[]; compact?: boolean
}) {
  const focusSet = useMemo(() => new Set(focus ?? []), [focus])
  const c = chartColors(useTheme().theme)
  const wrap = useRef<HTMLDivElement>(null)
  const fg = useRef<ForceGraphMethods<NodeT, LinkT> | undefined>(undefined)
  const [size, setSize] = useState({ w: 800, h: height ?? 560 })
  const [hover, setHover] = useState<string | null>(null)

  useEffect(() => {
    if (!wrap.current) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: height ?? Math.max(460, window.innerHeight - 320) }))
    ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [height])

  // The library mutates node/link objects, so hand it fresh copies.
  const data = useMemo(() => {
    const degree = new Map<string, number>()
    for (const e of graph.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
    }
    const amts = graph.edges.map((e) => Math.log10(Math.max(e.amount, 1)))
    const lo = Math.min(...amts, 0), hi = Math.max(...amts, 1)
    return {
      nodes: graph.nodes.map<N>((n) => ({ ...n, degree: degree.get(n.id) ?? 0, alerted: n.n_alerts > 0 })),
      links: graph.edges.map<L>((e) => ({ ...e, width: 0.4 + 2.5 * ((Math.log10(Math.max(e.amount, 1)) - lo) / Math.max(hi - lo, 1e-9)) })),
    }
  }, [graph])

  const pad = compact ? 16 : 40
  useEffect(() => {
    const t = setTimeout(() => fg.current?.zoomToFit(300, pad), 500)
    return () => clearTimeout(t)
  }, [data, pad])

  const isFocus = (n: N) => n.is_root || focusSet.has(n.id)
  const radius = (n: N) => (compact ? 2 : 2.5) + Math.sqrt(n.degree) * (compact ? 0.6 : 0.8) + (isFocus(n) ? 2.5 : 0)

  const drawNode = (node: NodeT, ctx: CanvasRenderingContext2D, scale: number) => {
    const r = radius(node), x = node.x ?? 0, y = node.y ?? 0
    if (isFocus(node)) {                       // soft halo like the design
      ctx.beginPath(); ctx.arc(x, y, r + 3, 0, 2 * Math.PI); ctx.fillStyle = c.halo; ctx.fill()
    }
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI)
    ctx.fillStyle = node.worst_band ? BAND[node.worst_band].hex : c.nodeUnscored
    ctx.fill()
    ctx.lineWidth = isFocus(node) ? 1.6 : 0.8
    ctx.strokeStyle = isFocus(node) ? c.focus : node.alerted ? RED : c.nodeStroke
    ctx.stroke()
    if (isFocus(node) || node.id === hover || scale > 5) {
      const fs = Math.max(11 / scale, 2)
      ctx.font = `${isFocus(node) ? '600 ' : ''}${fs}px "JetBrains Mono", ui-monospace, monospace`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      const label = node.id, ty = y + r + 2
      const w = ctx.measureText(label).width + 8 / scale, h = fs + 5 / scale
      ctx.fillStyle = isFocus(node) ? c.focusBg : c.labelBg
      ctx.strokeStyle = isFocus(node) ? c.focusBg : c.labelLine; ctx.lineWidth = 0.6 / scale
      ctx.beginPath(); ctx.roundRect(x - w / 2, ty - 2 / scale, w, h, 2 / scale); ctx.fill(); ctx.stroke()
      ctx.fillStyle = isFocus(node) ? c.focusText : c.label
      ctx.fillText(label, x, ty)
    }
  }

  const legend = [['bg-primary', 'Focus account'], ['bg-high', 'High risk'], ['bg-medium', 'Medium risk'], ['bg-low', 'Low risk'], ['bg-faint', 'Unscored / clear']]

  return (
    <div ref={wrap} className="relative bg-card">
      <ForceGraph2D<N, L>
        ref={fg} width={size.w} height={size.h} graphData={data}
        cooldownTicks={150} d3VelocityDecay={0.3}
        onEngineStop={() => fg.current?.zoomToFit(300, pad)}
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, colour, ctx) => { ctx.beginPath(); ctx.arc(node.x ?? 0, node.y ?? 0, radius(node) + 2, 0, 2 * Math.PI); ctx.fillStyle = colour; ctx.fill() }}
        nodeLabel={(n) => `${n.id}\n${n.n_alerts} alerts · ${n.n_scored_txns} scored · ${n.degree} edges`}
        onNodeHover={(n) => setHover(n?.id ?? null)}
        onNodeClick={(n) => onNodeClick(n.id)}
        linkWidth={(l) => l.width}
        linkColor={(l) => (l.is_laundering ? RED : l.band === 'HIGH' ? c.edgeHigh : c.edge)}
        linkLineDash={(l) => (l.is_laundering ? [3, 2] : null)}
        linkDirectionalArrowLength={3} linkDirectionalArrowRelPos={1} linkCurvature={0.15}
        linkLabel={(l) => `${money0(l.amount)}${l.timestamp ? ' · ' + l.timestamp.slice(0, 16) : ''}${l.band ? ' · ' + l.band : ''}${l.is_laundering ? ' · LAUNDERING' : ''}`}
      />
      {!compact && (
        <div className="absolute top-3 right-3 flex gap-1">
          {[['add', () => fg.current?.zoom((fg.current.zoom() ?? 1) * 1.4, 200)], ['remove', () => fg.current?.zoom((fg.current.zoom() ?? 1) / 1.4, 200)], ['center_focus_weak', () => fg.current?.zoomToFit(300, pad)]].map(([ic, fn]) => (
            <button key={ic as string} onClick={fn as () => void} className="w-8 h-8 rounded-md bg-card border border-line shadow-card hover:bg-well flex items-center justify-center"><Icon name={ic as string} /></button>
          ))}
        </div>
      )}
      <div className="absolute bottom-2 left-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted bg-card/90 px-2 py-1 rounded">
        {legend.map(([c, l]) => <span key={l} className="inline-flex items-center gap-1.5"><i className={`w-2.5 h-2.5 rounded-full ${c}`} />{l}</span>)}
        <span className="inline-flex items-center gap-1.5"><i className="w-4 border-t-2 border-dashed border-high" />Laundering link</span>
        {!compact && <span className="text-faint">size = degree · width = amount</span>}
      </div>
    </div>
  )
}
