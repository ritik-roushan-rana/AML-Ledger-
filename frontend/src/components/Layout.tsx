import { Link, NavLink, Outlet } from 'react-router-dom'
import { useHealth } from '../api/hooks'
import { API_BASE } from '../api/client'
import { Icon } from './ui'
import { useTheme } from '../lib/theme'

function SystemPill() {
  const { data, error } = useHealth()
  const status = error ? 'down' : data?.status ?? 'loading'
  const dot = { ok: 'bg-ok', degraded: 'bg-medium', error: 'bg-high', down: 'bg-high', loading: 'bg-faint' }[status]
  const text = { ok: 'All systems normal', degraded: 'Degraded', error: 'Pipeline error', down: 'Backend unreachable', loading: 'Connecting' }[status]
  const title = error
    ? `backend unreachable at ${API_BASE}`
    : data
      ? [data.load_error, `neo4j ${data.neo4j.reachable ? 'ok' : 'down'}`, `iforest ${data.anomaly_model_loaded ? 'ok' : 'missing'}`,
         `llm ${data.llm_configured ? 'ok' : 'not configured'}`].filter(Boolean).join(' · ')
      : ''
  return (
    <span title={title} className="inline-flex items-center gap-2 h-7 px-3 rounded-full bg-well border border-line text-[12px] font-medium text-ink-2">
      <span className={`w-2 h-2 rounded-full ${dot}`} />
      {text}
      {data && <span className="text-faint tabular-nums">· {data.rows_scored.toLocaleString()} scored</span>}
    </span>
  )
}

const nav = ({ isActive }: { isActive: boolean }) =>
  `px-3 h-8 inline-flex items-center rounded-lg text-[13px] font-medium transition-colors ${isActive ? 'bg-primary-tint text-primary' : 'text-muted hover:text-ink hover:bg-well'}`

function ThemeToggle() {
  const { theme, pref, setPref } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button onClick={() => setPref(next)} onContextMenu={(e) => { e.preventDefault(); setPref('system') }}
      title={`Switch to ${next} mode${pref === 'system' ? ' (currently following system)' : ' · right-click to follow system'}`}
      className="w-8 h-8 rounded-lg border border-line bg-card hover:bg-well text-muted hover:text-ink flex items-center justify-center">
      <Icon name={theme === 'dark' ? 'light_mode' : 'dark_mode'} />
    </button>
  )
}

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 bg-card border-b border-line px-6 flex items-center gap-6 sticky top-0 z-20">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-lg bg-primary text-white flex items-center justify-center"><Icon name="shield" className="text-[16px]" /></span>
          <span className="text-[15px] font-semibold text-ink tracking-tight">AML Ledger</span>
          <span className="hidden md:inline text-[10px] font-semibold tracking-[0.05em] uppercase text-muted bg-well border border-line rounded px-1.5 py-0.5">Compliance suite</span>
        </Link>
        <nav className="flex items-center gap-1 ml-2">
          <NavLink to="/" end className={nav}>Queue</NavLink>
          <NavLink to="/overview" className={nav}>Overview</NavLink>
          <NavLink to="/ask" className={nav}>Ask</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2"><SystemPill /><ThemeToggle /></div>
      </header>
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-6 py-6 min-w-0">
        <Outlet />
      </main>
      <footer className="px-6 py-3 text-[11px] text-faint border-t border-line bg-card flex justify-between">
        <span>AML Ledger · XGBoost + rules + Isolation Forest + Neo4j + LLM</span>
        <span>Prioritisation aid, not a determination of wrongdoing</span>
      </footer>
    </div>
  )
}
