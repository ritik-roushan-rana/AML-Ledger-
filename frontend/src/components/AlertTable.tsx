import { useNavigate } from 'react-router-dom'
import type { AlertSummary, SortField } from '../api/types'
import { BAND, money, ts } from '../lib/format'
import { BandPill, Icon, Mono, TableSkeleton } from './ui'

const COLS: { key: SortField | null; label: string; cls?: string }[] = [
  { key: 'risk_score', label: 'Score', cls: 'num w-24' },
  { key: null, label: 'Band', cls: 'w-28' },
  { key: 'amount_usd', label: 'Amount', cls: 'num w-36' },
  { key: null, label: 'Sender' },
  { key: null, label: 'Receiver' },
  { key: 'timestamp', label: 'Timestamp', cls: 'w-40' },
  { key: 'n_rules', label: 'Rules', cls: 'w-28' },
  { key: null, label: 'Action', cls: 'w-28 text-right' },
]

export function AlertTable({ items, loading, sort, desc, onSort }: {
  items: AlertSummary[] | undefined; loading: boolean; sort: SortField; desc: boolean; onSort: (f: SortField) => void
}) {
  const nav = useNavigate()
  return (
    <div className="overflow-x-auto">
      <table className="text-[13px]">
        <thead>
          <tr>
            {COLS.map((c) => (
              <th key={c.label} className={`${c.cls ?? ''} ${c.key ? 'cursor-pointer hover:text-ink' : ''}`}
                onClick={c.key ? () => onSort(c.key!) : undefined}
                aria-sort={c.key === sort ? (desc ? 'descending' : 'ascending') : undefined}>
                <span className={c.key === sort ? 'text-primary' : ''}>{c.label}</span>
                {c.key === sort && <Icon name={desc ? 'arrow_downward' : 'arrow_upward'} className="text-[14px] text-primary ml-0.5" />}
              </th>
            ))}
          </tr>
        </thead>
        {loading && !items ? <TableSkeleton cols={COLS.length} rows={15} /> : (
          <tbody className={loading ? 'opacity-50' : ''}>
            {items?.map((a) => (
              <tr key={a.txn_id} onClick={() => nav(`/alerts/${a.txn_id}`)}
                className={`cursor-pointer hover:bg-hover border-l-[3px] ${BAND[a.band].rail} group`}>
                <td className={`num font-semibold ${BAND[a.band].text}`}>{a.risk_score.toFixed(2)}</td>
                <td><BandPill band={a.band} /></td>
                <td className="num font-medium text-ink">{money(a.amount_usd)}</td>
                <td><Mono>{a.from_id}</Mono></td>
                <td><Mono>{a.to_id}</Mono></td>
                <td className="tabular-nums text-muted">{ts(a.timestamp)}</td>
                <td>
                  {a.n_rules ? (
                    <span className="inline-flex items-center h-5 px-2 rounded bg-well border border-line text-[11px] font-medium text-ink-2">{a.n_rules} trigger{a.n_rules > 1 ? 's' : ''}</span>
                  ) : <span className="text-faint text-[12px]">model only</span>}
                </td>
                <td className="text-right">
                  <span className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] font-medium text-primary group-hover:bg-primary group-hover:text-white transition-colors">
                    {a.action === 'REPORT' ? 'Report' : a.action === 'REVIEW' ? 'Review' : a.action === 'MONITOR' ? 'Monitor' : 'None'} <Icon name="arrow_forward" className="text-[14px]" />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        )}
      </table>
    </div>
  )
}
