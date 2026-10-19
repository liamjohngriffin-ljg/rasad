import { useState } from 'react'
import { useAuth } from '../auth'
import { useLang } from '../i18n'

const field = 'bg-transparent border border-[var(--line)] rounded px-3 py-2'

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Rasad-Client': 'web' }, body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail ?? String(r.status))
  return data as T
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  const { t } = useLang()
  return (
    <div className="border border-[var(--accent)]/50 rounded p-3 mt-2">
      <div className="text-sm mb-2">{t('recoveryCodesHint')}</div>
      <div className="grid grid-cols-2 gap-1 mono text-sm">{codes.map((c) => <span key={c}>{c}</span>)}</div>
      <button className="btn text-xs mt-2" onClick={() => navigator.clipboard?.writeText(codes.join('\n'))}>{t('copy')}</button>
    </div>
  )
}

function TwoFactor() {
  const { me, refresh } = useAuth()
  const { t } = useLang()
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null)
  const [code, setCode] = useState('')
  const [pw, setPw] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const run = async (f: () => Promise<void>) => { try { setMsg(null); await f() } catch (e) { setMsg((e as Error).message) } }
  if (!me) return null
  return (
    <div className="card p-6 mt-4">
      <h2 className="font-medium mb-1">{t('mfaTitle')}</h2>
      {me.must_enrol_mfa && <div className="text-[var(--accent)] text-sm mb-2">{t('mfaRequiredHint')}</div>}
      {me.mfa_enabled ? (
        <div className="grid gap-2 text-sm">
          <div><span className="tag present">{t('mfaOn')}</span> <span className="muted ms-2">{t('recoveryLeft')}: {me.recovery_codes_left}</span></div>
          <input type="password" className={field} placeholder={t('currentPassword')} value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" />
          <div className="flex gap-2">
            <button className="btn text-xs" onClick={() => run(async () => { const r = await post<{ recovery_codes: string[] }>('/api/auth/mfa/recovery', { password: pw }); setCodes(r.recovery_codes); setPw(''); refresh() })}>{t('newRecoveryCodes')}</button>
            <button className="btn text-xs" onClick={() => run(async () => { await post('/api/auth/mfa/disable', { password: pw }); setPw(''); refresh() })}>{t('mfaTurnOff')}</button>
          </div>
        </div>
      ) : !setup ? (
        <div className="text-sm">
          <p className="muted mb-2">{t('mfaIntro')}</p>
          <button className="btn primary text-sm" onClick={() => run(async () => setSetup(await post('/api/auth/mfa/setup')))}>{t('mfaStart')}</button>
        </div>
      ) : (
        <div className="grid gap-2 text-sm">
          <p className="muted">{t('mfaScan')}</p>
          <div className="bg-white rounded p-2 w-fit" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <div className="muted text-xs">{t('mfaManual')} <span className="mono select-all">{setup.secret.replace(/(.{4})/g, '$1 ').trim()}</span></div>
          <div className="flex gap-2">
            <input className={field + ' mono tracking-widest w-36'} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" />
            <button className="btn primary text-sm" onClick={() => run(async () => { const r = await post<{ recovery_codes: string[] }>('/api/auth/mfa/enable', { code }); setCodes(r.recovery_codes); setSetup(null); setCode(''); refresh() })}>{t('verify')}</button>
          </div>
        </div>
      )}
      {codes && <RecoveryCodes codes={codes} />}
      {msg && <div className="text-[var(--up)] text-sm mt-2">{msg}</div>}
    </div>
  )
}

export default function Account() {
  const { me, refresh } = useAuth()
  const { t } = useLang()
  const [cur, setCur] = useState('')
  const [nw, setNw] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  return (
    <div className="max-w-md mx-auto">
      <div className="card p-6">
        <h2 className="font-medium mb-1">{me?.display_name} <span className="muted text-sm">({me?.username}, {me?.role})</span></h2>
        {me?.must_change_password && <div className="text-[var(--accent)] text-sm mb-3">{t('mustChangeHint')}</div>}
        <form className="grid gap-2 mt-3" onSubmit={async (e) => {
          e.preventDefault()
          try { await post('/api/auth/password', { current_password: cur, new_password: nw }); setMsg(t('passwordUpdated')); setCur(''); setNw(''); refresh() } catch (ex) { setMsg((ex as Error).message) }
        }}>
          <input type="password" className={field} placeholder={t('currentPassword')} value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
          <input type="password" className={field} placeholder={t('newPassword')} value={nw} onChange={(e) => setNw(e.target.value)} autoComplete="new-password" />
          <button className="btn primary" type="submit">{t('changePassword')}</button>
          {msg && <div className="text-sm muted">{msg}</div>}
        </form>
      </div>
      <TwoFactor />
      <div className="card p-6 mt-4 text-sm">
        <h2 className="font-medium mb-1">{t('sessionsTitle')}</h2>
        <p className="muted mb-2">{t('sessionsHint')}</p>
        <button className="btn text-xs" onClick={async () => { await post('/api/auth/sessions/revoke'); setMsg(t('sessionsRevoked')) }}>{t('signOutElsewhere')}</button>
      </div>
    </div>
  )
}
