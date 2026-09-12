import { Link } from 'react-router-dom'
import type { FlowRow } from '../api/types'
import { money, ts } from '../lib/format'
import { Empty, Mono } from './ui'

const acct = (id: string, focus: Set<string>) => (
  <Link to={`/accounts/${encodeURIComponent(id)}`} className={`hover:underline ${focus.has(id) ? 'text-ink font-medium' : 'text-muted'}`}><Mono>{id}</Mono></Link>
)

export function MoneyFlowTable({ rows, focus }: { rows: FlowRow[]; focus: Set<string> }) {
  if (!rows.length) return <Empty icon="timeline" title="No surrounding activity">Neither account moved funds in the 96h lookback.</Empty>
  return (
    <div className="overflow-x-auto">
      <table className="text-[13px]">
        <thead><tr><th className="w-40">Timestamp</th><th>Sender</th><th>Receiver</th><th className="num w-36">Amount</th><th className="w-24">Direction</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.txn_id} className={r.is_this ? 'bg-primary-tint' : ''}>
              <td className="tabular-nums text-muted">
                {r.is_this && <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mr-1.5 align-middle" />}{ts(r.timestamp)}
              </td>
              <td>{acct(r.from_id, focus)}</td>
              <td>{acct(r.to_id, focus)}</td>
              <td className={`num font-medium ${r.is_this ? 'text-primary' : r.direction === 'in' ? 'text-ok' : 'text-ink'}`}>{r.direction === 'in' ? '+' : '−'}{money(r.amount_usd)}</td>
              <td>
                {r.is_this ? <span className="inline-flex h-5 px-2 items-center rounded bg-primary text-white text-[10px] font-semibold uppercase tracking-[0.05em]">◀ Alert</span>
                  : <span className={`inline-flex h-5 px-2 items-center rounded text-[10px] font-semibold uppercase tracking-[0.05em] ${r.direction === 'in' ? 'bg-ok-tint text-ok' : 'bg-well text-muted border border-line'}`}>{r.direction === 'in' ? 'Feeder in' : 'Drain out'}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
