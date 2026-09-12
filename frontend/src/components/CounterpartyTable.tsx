import { Link } from 'react-router-dom'
import type { Counterparty } from '../api/types'
import { money } from '../lib/format'
import { Empty, Mono } from './ui'

export function CounterpartyTable({ rows }: { rows: Counterparty[] }) {
  if (!rows.length) return <Empty icon="group_off" title="No third-party counterparties">Nothing outside the two accounts in the lookback window.</Empty>
  return (
    <div className="overflow-x-auto">
      <table className="text-[13px]">
        <thead><tr><th>Entity / account</th><th className="w-32">Flow</th><th className="num w-20">Volume</th><th className="num w-32">Total</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.account}-${r.role}-${i}`}>
              <td><Link to={`/accounts/${encodeURIComponent(r.account)}`} className="hover:underline"><Mono>{r.account}</Mono></Link></td>
              <td><span className={`inline-flex h-5 px-2 items-center rounded text-[10px] font-semibold uppercase tracking-[0.05em] ${r.role === 'received from' ? 'bg-ok-tint text-ok' : 'bg-well text-muted border border-line'}`}>{r.role}</span></td>
              <td className="num text-muted">{r.n} txn{r.n > 1 ? 's' : ''}</td>
              <td className="num font-medium text-ink">{money(r.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
