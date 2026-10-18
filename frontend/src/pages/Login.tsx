import { useState } from 'react'
import { useAuth } from '../auth'
import { useLang } from '../i18n'

export default function Login() {
  const { login } = useAuth()
  const { t, lang, setLang } = useLang()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <form className="card p-8 w-full max-w-sm" onSubmit={async (e) => { e.preventDefault(); setBusy(true); setErr(await login(u, p)); setBusy(false) }}>
        <div className="flex items-baseline justify-between mb-6">
          <div className="text-2xl font-semibold tracking-wide">{t('app')}</div>
          <button type="button" className="btn text-xs" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t('lang')}</button>
        </div>
        <label className="block text-sm muted mb-1">{t('username')}</label>
        <input className="w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 mb-3" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus />
        <label className="block text-sm muted mb-1">{t('password')}</label>
        <input type="password" className="w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 mb-4" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" />
        {err && <div className="text-[var(--up)] text-sm mb-3">{err}</div>}
        <button className="btn primary w-full" disabled={busy} type="submit">{t('signIn')}</button>
      </form>
    </div>
  )
}
