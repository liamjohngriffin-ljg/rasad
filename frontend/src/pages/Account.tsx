import { useState } from 'react'
import { useAuth } from '../auth'
import { useLang } from '../i18n'

export default function Account() {
  const { me, refresh } = useAuth()
  const { t } = useLang()
  const [cur, setCur] = useState('')
  const [nw, setNw] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  return (
    <div className="max-w-md mx-auto card p-6">
      <h2 className="font-medium mb-1">{me?.display_name} <span className="muted text-sm">({me?.username}, {me?.role})</span></h2>
      {me?.must_change_password && <div className="text-[var(--accent)] text-sm mb-3">{t('mustChangeHint')}</div>}
      <form className="grid gap-2 mt-3" onSubmit={async (e) => {
        e.preventDefault()
        const r = await fetch('/api/auth/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: cur, new_password: nw }) })
        setMsg(r.ok ? t('passwordUpdated') : (await r.json()).detail)
        if (r.ok) { setCur(''); setNw(''); refresh() }
      }}>
        <input type="password" className="bg-transparent border border-[var(--line)] rounded px-3 py-2" placeholder={t('currentPassword')} value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
        <input type="password" className="bg-transparent border border-[var(--line)] rounded px-3 py-2" placeholder={t('newPassword')} value={nw} onChange={(e) => setNw(e.target.value)} autoComplete="new-password" />
        <button className="btn primary" type="submit">{t('changePassword')}</button>
        {msg && <div className="text-sm muted">{msg}</div>}
      </form>
    </div>
  )
}
