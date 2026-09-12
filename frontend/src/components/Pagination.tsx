import { num } from '../lib/format'
import { Icon } from './ui'

export function Pagination({ page, pages, total, pageSize, onPage, label = 'flagged transactions' }: {
  page: number; pages: number; total: number; pageSize: number; onPage: (p: number) => void; label?: string
}) {
  const lo = total === 0 ? 0 : (page - 1) * pageSize + 1
  const hi = Math.min(page * pageSize, total)
  const btn = 'w-8 h-8 inline-flex items-center justify-center rounded-md border border-line bg-card hover:bg-well disabled:opacity-30 disabled:hover:bg-card'
  const around = [page - 1, page, page + 1].filter((p) => p >= 1 && p <= pages)
  return (
    <div className="flex items-center gap-3 text-[13px] text-muted px-4 py-3 border-t border-line bg-well/50">
      <span>Showing <b className="text-ink">{num(lo)}–{num(hi)}</b> of <b className="text-ink">{num(total)}</b> {label}</span>
      <div className="ml-auto flex items-center gap-1">
        <button className={btn} disabled={page <= 1} onClick={() => onPage(1)}><Icon name="first_page" /></button>
        <button className={btn} disabled={page <= 1} onClick={() => onPage(page - 1)}><Icon name="chevron_left" /></button>
        {around[0] > 1 && <span className="px-1 text-faint">…</span>}
        {around.map((p) => (
          <button key={p} onClick={() => onPage(p)}
            className={`min-w-8 h-8 px-2 rounded-md text-[12px] font-medium tabular-nums ${p === page ? 'bg-primary text-white' : 'border border-line bg-card hover:bg-well'}`}>{num(p)}</button>
        ))}
        {around[around.length - 1] < pages && <><span className="px-1 text-faint">…</span>
          <button onClick={() => onPage(pages)} className="min-w-8 h-8 px-2 rounded-md text-[12px] tabular-nums border border-line bg-card hover:bg-well">{num(pages)}</button></>}
        <button className={btn} disabled={page >= pages} onClick={() => onPage(page + 1)}><Icon name="chevron_right" /></button>
        <button className={btn} disabled={page >= pages} onClick={() => onPage(pages)}><Icon name="last_page" /></button>
      </div>
    </div>
  )
}
