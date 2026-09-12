import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark'
type Pref = Theme | 'system'
const KEY = 'aml-theme'

const system = (): Theme =>
  window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'

const readPref = (): Pref => {
  try { const v = localStorage.getItem(KEY); if (v === 'light' || v === 'dark') return v } catch { /* private mode */ }
  return 'system'
}

const Ctx = createContext<{ theme: Theme; pref: Pref; setPref: (p: Pref) => void }>({ theme: 'light', pref: 'system', setPref: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<Pref>(readPref)
  const [sys, setSys] = useState<Theme>(system)
  const theme: Theme = pref === 'system' ? sys : pref

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => setSys(system())
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  const setPref = (p: Pref) => {
    setPrefState(p)
    try { p === 'system' ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, p) } catch { /* ignore */ }
  }
  return <Ctx.Provider value={{ theme, pref, setPref }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)

/** Chart/canvas colours that cannot come from Tailwind classes. */
export const chartColors = (t: Theme) => t === 'dark'
  ? { grid: '#1F2733', axis: '#273040', tick: '#64748B', tickActive: '#60A5FA', edge: '#3B4657', edgeHigh: '#7F1D1D', nodeUnscored: '#3B4657', nodeStroke: '#161C25', label: '#F1F5F9', labelBg: 'rgba(22,28,37,0.95)', labelLine: '#273040', focus: '#3B82F6', focusBg: '#F1F5F9', focusText: '#0F1419', halo: 'rgba(59,130,246,0.25)' }
  : { grid: '#F3F4F6', axis: '#E5E7EB', tick: '#9CA3AF', tickActive: '#2563EB', edge: '#CBD5E1', edgeHigh: '#FCA5A5', nodeUnscored: '#D1D5DB', nodeStroke: '#FFFFFF', label: '#111827', labelBg: 'rgba(255,255,255,0.95)', labelLine: '#E5E7EB', focus: '#2563EB', focusBg: '#111827', focusText: '#FFFFFF', halo: 'rgba(37,99,235,0.15)' }
