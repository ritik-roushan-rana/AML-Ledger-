import type {
  Account, AccountGraph, AlertDetail, AlertPage, AlertQuery, AskResponse, Health,
  Investigation, Report, Stats,
} from './types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) { super(detail); this.status = status }
}

/** Every backend error is `{ detail: string | ValidationError[] }`. */
async function request<T>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api${path}`, { headers: { Accept: 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, `Cannot reach backend at ${API_BASE}`)
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch { /* non-JSON body */ }
    throw new ApiError(res.status, detail)
  }
  return { status: res.status, body: (await res.json()) as T }
}

const get = async <T,>(path: string) => (await request<T>(path)).body
const post = async <T,>(path: string, body?: unknown) =>
  (await request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })).body

export const api = {
  health: () => get<Health>('/health'),
  stats: () => get<Stats>('/stats'),

  alerts: (q: AlertQuery) => {
    const p = new URLSearchParams()
    q.band?.forEach((b) => p.append('band', b))
    if (q.min_score != null) p.set('min_score', String(q.min_score))
    p.set('page', String(q.page))
    p.set('page_size', String(q.page_size))
    p.set('sort', (q.desc ? '-' : '') + q.sort)
    return get<AlertPage>(`/alerts?${p}`)
  },
  alert: (id: number) => get<AlertDetail>(`/alerts/${id}`),
  report: (id: number) => get<Report>(`/alerts/${id}/report`),

  /** 202 = queued/running, 200 = cached result. Both bodies are Investigation. */
  investigate: (id: number, force = false) =>
    post<Investigation>(`/alerts/${id}/investigate${force ? '?force=true' : ''}`),
  investigation: (id: number) => get<Investigation>(`/alerts/${id}/investigate`),

  ask: (question: string, ctx: { txn_id?: number; account_id?: string }) =>
    post<AskResponse>('/ask', { question, ...ctx }),
  askStatus: (jobId: string) => get<AskResponse>(`/ask/${jobId}`),

  account: (id: string) => get<Account>(`/accounts/${encodeURIComponent(id)}`),
  graph: (id: string, hops: 1 | 2, limit = 80) =>
    get<AccountGraph>(`/accounts/${encodeURIComponent(id)}/graph?hops=${hops}&limit=${limit}`),
}
