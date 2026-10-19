import { useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { api, type Status } from './api'
import { atLeast, useAuth } from './auth'
import { useLang } from './i18n'
import Login from './pages/Login'

export default function App() {
  const { t, lang, setLang } = useLang()
  const { me, loading, logout } = useAuth()
  const location = useLocation()
  const [status, setStatus] = useState<Status | null>(null)
  useEffect(() => { if (me) api.status().then(setStatus).catch(() => setStatus(null)) }, [me])
  useEffect(() => { if (me) api.settings().then((s) => { if (s.accent && /^#[0-9a-fA-F]{6}$/.test(s.accent)) document.documentElement.style.setProperty('--accent', s.accent); if (s.logo_data_url) setLogo(s.logo_data_url) }).catch(() => {}) }, [me])
  const [logo, setLogo] = useState<string | null>(null)
  if (loading) return <div className="min-h-full flex items-center justify-center muted">…</div>
  if (!me) return <Login />
  if (me.must_change_password && location.pathname !== '/account') return <Navigate to="/account" replace />
  const link = ({ isActive }: { isActive: boolean }) => `px-2.5 py-1.5 rounded-md text-sm whitespace-nowrap ${isActive ? 'bg-[var(--bg-2)] text-[var(--ink)]' : 'muted hover:text-[var(--ink)]'}`
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-[var(--line)] bg-[var(--bg)]/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-3">
          <div className="text-lg font-semibold tracking-wide flex items-center gap-2">{logo && <img src={logo} alt="" className="h-7" />}{status?.product_name || t('app')} <span className="muted text-xs font-normal">v{status?.version ?? '0.1'}</span>{status?.org_name && <span className="muted text-xs font-normal hidden xl:inline">· {status.org_name}</span>}</div>
          <nav className="flex gap-0.5 ms-2 flex-wrap">
            <NavLink to="/" end className={link}>{t('board')}</NavLink>
            <NavLink to="/today" className={link}>{t('today')} {status && status.open_alerts > 0 && <span className="tag present ms-1">{status.open_alerts}</span>}</NavLink>
            <NavLink to="/map" className={link}>{t('map')}</NavLink>
            <NavLink to="/series" className={link}>{t('series')}</NavLink>
            <NavLink to="/positions" className={link}>{t('positions')}</NavLink>
            <NavLink to="/record" className={link}>{t('calibration')}</NavLink>
            {atLeast(me.role, 'analyst') && <NavLink to="/queue" className={link}>{t('queue')} {status && status.pending_verification > 0 && <span className="tag ms-1">{status.pending_verification}</span>}</NavLink>}
            {atLeast(me.role, 'analyst') && <NavLink to="/questions" className={link}>{t('questions')}</NavLink>}
            {atLeast(me.role, 'analyst') && <NavLink to="/evidence" className={link}>{t('evidenceEntry')}</NavLink>}
            <NavLink to="/tasking" className={link}>{t('taskingNav')}</NavLink>
            <NavLink to="/search" className={link}>{t('search')}</NavLink>
            <NavLink to="/sources" className={link}>{t('sources')}</NavLink>
            {me.role === 'admin' && <NavLink to="/admin" className={link}>{t('admin')}</NavLink>}
          </nav>
          <div className="ms-auto flex items-center gap-3 text-sm">
            {status?.marking && <span className="tag">{status.marking}</span>}
            {status?.last_commit && <span className="muted whitespace-nowrap hidden lg:inline">{t('asOf')} <span className="mono">{status.last_commit}</span></span>}
            <NavLink to="/account" className="muted hover:text-[var(--ink)]">{me.display_name}</NavLink>
            <button className="btn" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t('lang')}</button>
            <button className="btn" onClick={logout}>{t('signOut')}</button>
          </div>
        </div>
        {status && status.synthetic_rows > 0 && (
          <div className="bg-[var(--accent)]/10 border-t border-[var(--accent)]/40 text-[var(--accent)] text-xs px-4 py-1.5 text-center">{t('demoBanner')} <NavLink to="/sources" className="underline">{status.synthetic_rows}</NavLink></div>
        )}
        {status?.licence && status.licence.mode !== 'licensed' && (
          <div className="bg-[var(--up)]/10 border-t border-[var(--up)]/40 text-[var(--up)] text-xs px-4 py-1.5 text-center">{status.licence.mode === 'grace' ? t('graceBanner') : t('evaluationBanner')}</div>
        )}
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6 w-full flex-1">
        <Outlet />
      </main>
    </div>
  )
}
