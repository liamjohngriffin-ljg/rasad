import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api, type Status } from './api'
import { useLang } from './i18n'

export default function App() {
  const { t, lang, setLang } = useLang()
  const [status, setStatus] = useState<Status | null>(null)
  useEffect(() => { api.status().then(setStatus).catch(() => setStatus(null)) }, [])
  const link = ({ isActive }: { isActive: boolean }) => `px-3 py-2 rounded-md text-sm ${isActive ? 'bg-[var(--bg-2)] text-[var(--ink)]' : 'muted hover:text-[var(--ink)]'}`
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-[var(--line)] bg-[var(--bg)]/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
          <div className="text-lg font-semibold tracking-wide">{t('app')} <span className="muted text-xs font-normal ms-1">v{status?.version ?? '0.1'}</span></div>
          <nav className="flex gap-1 ms-4">
            <NavLink to="/" end className={link}>{t('board')}</NavLink>
            <NavLink to="/positions" className={link}>{t('positions')}</NavLink>
            <NavLink to="/record" className={link}>{t('calibration')}</NavLink>
            <NavLink to="/queue" className={link}>{t('queue')} {status && status.pending_verification > 0 && <span className="tag ms-1">{status.pending_verification}</span>}</NavLink>
            <NavLink to="/sources" className={link}>{t('sources')}</NavLink>
          </nav>
          <div className="ms-auto flex items-center gap-3 text-sm">
            {status?.last_commit && <span className="muted">{t('asOf')} <span className="mono">{status.last_commit}</span></span>}
            <button className="btn" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t('lang')}</button>
          </div>
        </div>
        {status && status.synthetic_rows > 0 && (
          <div className="bg-[var(--accent)]/10 border-t border-[var(--accent)]/40 text-[var(--accent)] text-xs px-4 py-1.5 text-center">{t('demoBanner')}</div>
        )}
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6 w-full flex-1">
        <Outlet />
      </main>
    </div>
  )
}
