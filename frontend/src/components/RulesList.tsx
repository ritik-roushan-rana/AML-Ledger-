import type { RuleFired } from '../api/types'
import { Empty } from './ui'

export function RulesList({ rules }: { rules: RuleFired[] }) {
  if (!rules.length) {
    return <Empty icon="rule" title="No deterministic rules triggered">This alert rests on the model score alone and warrants closer analyst scrutiny.</Empty>
  }
  return (
    <ul className="space-y-2.5">
      {rules.map((r) => (
        <li key={r.name} className="flex items-start gap-3">
          <span className="mono inline-flex h-6 px-2 items-center rounded bg-high text-white text-[11px] font-medium uppercase tracking-[0.05em] shrink-0">{r.name}</span>
          <span className="text-[13px] text-ink-2 leading-6">{r.description}</span>
        </li>
      ))}
    </ul>
  )
}
