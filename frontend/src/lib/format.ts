import type { Band } from '../api/types'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const money = (v: number | null | undefined) => (v == null ? '—' : usd.format(v))
export const money0 = (v: number) => usd.format(v).replace(/\.\d\d$/, '')

/** "2022-09-11T15:04:00" -> "2022-09-11 15:04". Backend times are naive UTC; no TZ shift. */
export const ts = (iso: string | null | undefined) => (iso ? iso.slice(0, 16).replace('T', ' ') : '—')

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : `${(v * 100).toFixed(digits)}%`

export const num = (v: number) => v.toLocaleString('en-US')

export const BANDS: Band[] = ['HIGH', 'MEDIUM', 'LOW', 'CLEAR']

// Tailwind classes must be literal so the compiler sees them.
export const BAND = {
  HIGH:   { text: 'text-high',   bg: 'bg-high',   tint: 'bg-high-tint',   line: 'border-high-line',   rail: 'border-l-high',   hex: '#DC2626' },
  MEDIUM: { text: 'text-medium', bg: 'bg-medium', tint: 'bg-medium-tint', line: 'border-medium-line', rail: 'border-l-medium', hex: '#D97706' },
  LOW:    { text: 'text-low',    bg: 'bg-low',    tint: 'bg-low-tint',    line: 'border-low-line',    rail: 'border-l-low',    hex: '#2563EB' },
  CLEAR:  { text: 'text-clear',  bg: 'bg-clear',  tint: 'bg-clear-tint',  line: 'border-clear-line',  rail: 'border-l-clear',  hex: '#9CA3AF' },
} as const satisfies Record<Band, unknown>

export const ACTION_TEXT: Record<string, string> = {
  REPORT: 'File SAR · escalate to MLRO',
  REVIEW: 'Analyst review within 48h',
  MONITOR: '30-day watch on both accounts',
  NONE: 'No action required',
}

export const caseId = (txnId: number) => `AML-${String(txnId).padStart(8, '0')}`
