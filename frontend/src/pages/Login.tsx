import { useState } from 'react'
import { useAuth } from '../auth'
import { useLang } from '../i18n'

const field = 'w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2'

export default function Login() {
  const { login } = useAuth()
  const { t, lang, setLang } = useLang()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [code, setCode] = useState('')
  const [needCode, setNeedCode] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    const e = await login(u, p, needCode ? code : undefined)
    setBusy(false)
    if (e === 'mfa_required') { setNeedCode(true); setErr(null); return }
    setErr(e === 'mfa_invalid' ? t('mfaInvalid') : e)
  }
  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <form className="card p-8 w-full max-w-sm" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <div className="flex items-baseline justify-between mb-6">
          <div className="text-2xl font-semibold tracking-wide">{t('app')}</div>
          <button type="button" className="btn text-xs" onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}>{t('lang')}</button>
        </div>
        {!needCode ? (
          <>
            <label className="block text-sm muted mb-1">{t('username')}</label>
            <input className={field + ' mb-3'} value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus />
            <label className="block text-sm muted mb-1">{t('password')}</label>
            <input type="password" className={field + ' mb-4'} value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" />
          </>
        ) : (
          <>
            <div className="text-sm mb-3">{t('mfaPrompt')}</div>
            <input className={field + ' mono text-lg tracking-widest mb-2'} value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="text" autoFocus placeholder="123456" />
            <div className="muted text-xs mb-4">{t('mfaRecoveryHint')}</div>
          </>
        )}
        {err && <div className="text-[var(--up)] text-sm mb-3">{err}</div>}
        <button className="btn primary w-full" disabled={busy} type="submit">{needCode ? t('verify') : t('signIn')}</button>
        {needCode && <button type="button" className="btn w-full mt-2 text-xs" onClick={() => { setNeedCode(false); setCode(''); setErr(null) }}>{t('back')}</button>}
      </form>
    </div>
  )
}
