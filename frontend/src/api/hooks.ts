import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { AlertQuery, AskResponse, Investigation } from './types'

const polling = (s: string | undefined) => (s === 'queued' || s === 'running' ? 1500 : false)

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000, retry: false })

export const useStats = () =>
  useQuery({ queryKey: ['stats'], queryFn: api.stats, staleTime: Infinity })

export const useAlerts = (q: AlertQuery) =>
  useQuery({ queryKey: ['alerts', q], queryFn: () => api.alerts(q), placeholderData: (prev) => prev })

export const useAlert = (id: number) =>
  useQuery({ queryKey: ['alert', id], queryFn: () => api.alert(id), enabled: Number.isFinite(id) })

export const useReport = (id: number, enabled: boolean) =>
  useQuery({ queryKey: ['report', id], queryFn: () => api.report(id), enabled, staleTime: 0 })

export const useAccount = (id: string) =>
  useQuery({ queryKey: ['account', id], queryFn: () => api.account(id), staleTime: 5 * 60_000 })

export const useAccountGraph = (id: string, hops: 1 | 2) =>
  useQuery({ queryKey: ['graph', id, hops], queryFn: () => api.graph(id, hops), staleTime: 5 * 60_000, placeholderData: (prev) => prev })

/**
 * POST kicks the job off; the status query is then enabled and polls until
 * the job leaves queued/running. Disabled until the POST has happened so a
 * fresh page load doesn't 404 on the status endpoint.
 */
export function useInvestigation(id: number) {
  const qc = useQueryClient()
  const key = ['investigation', id]
  const [started, setStarted] = useState(false)

  const status = useQuery<Investigation>({
    queryKey: key, queryFn: () => api.investigation(id), enabled: started, retry: false,
    refetchInterval: (q) => polling(q.state.data?.status),
  })
  const start = useMutation({
    mutationFn: (force: boolean) => api.investigate(id, force),
    onSuccess: (job) => {
      qc.setQueryData(key, job)
      setStarted(true)
      if (job.status === 'done') void qc.invalidateQueries({ queryKey: ['report', id] })
    },
  })
  const job = status.data
  return {
    job,
    start: () => start.mutate(job?.status === 'done' || job?.status === 'failed'),
    starting: start.isPending,
    running: job?.status === 'queued' || job?.status === 'running',
    error: start.error ?? (job?.status === 'failed' ? new Error(job.error ?? 'failed') : null),
  }
}

/** Ask-agent job: POST, then poll the job id until done/failed. */
export function useAsk() {
  const [jobId, setJobId] = useState<string | null>(null)
  const qc = useQueryClient()
  const status = useQuery<AskResponse>({
    queryKey: ['ask', jobId], queryFn: () => api.askStatus(jobId!), enabled: jobId !== null, retry: false,
    refetchInterval: (q) => polling(q.state.data?.status),
  })
  const submit = useMutation({
    mutationFn: (v: { question: string; txn_id?: number; account_id?: string }) =>
      api.ask(v.question, { txn_id: v.txn_id, account_id: v.account_id }),
    onSuccess: (job) => { qc.setQueryData(['ask', job.job_id], job); setJobId(job.job_id) },
  })
  const job = status.data
  return {
    job,
    submit: submit.mutate,
    running: submit.isPending || job?.status === 'queued' || job?.status === 'running',
    error: submit.error ?? (job?.status === 'failed' ? new Error(job.error ?? 'failed') : null),
    reset: () => setJobId(null),
  }
}
