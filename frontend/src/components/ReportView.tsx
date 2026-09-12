import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useReport } from '../api/hooks'
import { BlockSkeleton, ErrorBox } from './ui'

export function ReportView({ txnId }: { txnId: number }) {
  const r = useReport(txnId, true)
  if (r.error) return <ErrorBox error={r.error} onRetry={() => r.refetch()} />
  if (!r.data) return <BlockSkeleton lines={10} />
  return (
    <div className="prose-report text-[13px] text-ink-2 max-w-3xl">
      <Markdown remarkPlugins={[remarkGfm]}>{r.data.markdown}</Markdown>
    </div>
  )
}
