import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ApiKeyRow, type Licence, type Settings } from '../api'
import { useLang } from '../i18n'

const input = 'w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 text-sm'
const label = 'muted text-xs block mb-1'

function LicenceCard() {
  const { t } = useLang()
  const [lic, setLic] = useState<Licence | null>(null)
  const [text, setText] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => { api.licence().then(setLic) }, [])
  return (
    <div className="card p-5 grid gap-3">
      <h2 className="font-medium">{t('licenceTitle')}</h2>
      {lic && (
        <div className="grid md:grid-cols-5 gap-3 text-sm">
          <div><div className={label}>{t('mode')}</div><span className={`tag ${lic.mode === 'licensed' ? 'present' : lic.mode === 'grace' ? '' : 'unknown'}`}>{lic.mode}</span></div>
          <div><div className={label}>{t('licensee')}</div>{lic.licensee}</div>
          <div><div className={label}>{t('seats')}</div><span className="mono">{lic.seats_used ?? '?'} / {lic.seats}</span></div>
          <div><div className={label}>{t('expires')}</div><span className="mono">{lic.expires ?? '-'}</span></div>
          <div><div className={label}>{t('features')}</div>{lic.features.join(', ')}</div>
          {lic.reason && <div className="md:col-span-5 muted text-xs">{lic.reason}</div>}
        </div>
      )}
      <details>
        <summary className="cursor-pointer text-sm accent">{t('installLicence')}</summary>
        <div className="muted text-xs my-2">{t('licenceHint')}</div>
        <textarea className={input + ' mono text-xs'} rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder='{"payload": {...}, "signature": "...", "format": "rasad-licence-1"}' />
        <div className="flex items-center gap-3 mt-2">
          <button className="btn primary text-sm" onClick={async () => { try { const l = await api.installLicence(JSON.parse(text)); setLic({ ...l, seats_used: lic?.seats_used }); setMsg(t('saved')); setText('') } catch (e) { setMsg(`${t('errorPrefix')}: ${String(e)}`) } }}>{t('installLicence')}</button>
          {msg && <span className="muted text-xs">{msg}</span>}
        </div>
      </details>
    </div>
  )
}

function KeysCard() {
  const { t } = useLang()
  const [keys, setKeys] = useState<ApiKeyRow[]>([])
  const [name, setName] = useState('')
  const [role, setRole] = useState('viewer')
  const [fresh, setFresh] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = () => api.keys().then(setKeys)
  useEffect(() => { load() }, [])
  return (
    <div className="card p-5 grid gap-3">
      <h2 className="font-medium">{t('apiKeys')}</h2>
      <div className="muted text-xs">{t('integrationsHint')}</div>
      <form className="flex gap-2 items-end flex-wrap" onSubmit={async (e) => { e.preventDefault(); try { const k = await api.createKey(name, role); setFresh(k.token ?? null); setName(''); setErr(null); load() } catch (ex) { setErr(String(ex)) } }}>
        <div className="flex-1 min-w-[200px]"><span className={label}>{t('keyName')}</span><input className={input} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></div>
        <div><span className={label}>{t('role')}</span><select className={input} value={role} onChange={(e) => setRole(e.target.value)}><option value="viewer">viewer</option><option value="analyst">analyst</option></select></div>
        <button className="btn primary text-sm" type="submit">{t('createKey')}</button>
      </form>
      {err && <div className="text-[var(--up)] text-xs">{err}</div>}
      {fresh && <div className="card p-3 text-sm"><div className="muted text-xs mb-1">{t('keyShownOnce')}</div><code className="mono break-all select-all">{fresh}</code></div>}
      <table className="grid text-sm">
        <thead><tr><th>{t('name')}</th><th>{t('role')}</th><th>prefix</th><th>{t('lastUsed')}</th><th></th></tr></thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id} className={k.revoked_at ? 'opacity-50' : ''}>
              <td>{k.name}</td><td>{k.role}</td><td className="mono text-xs">{k.prefix}…</td><td className="mono text-xs">{k.last_used_at?.slice(0, 16) ?? '-'}</td>
              <td className="text-end">{k.revoked_at ? <span className="tag">{t('revoked')}</span> : <button className="btn text-xs" onClick={async () => { await api.revokeKey(k.id); load() }}>{t('revoke')}</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SettingsCard() {
  const { t } = useLang()
  const [s, setS] = useState<Settings | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => { api.settings().then(setS) }, [])
  if (!s) return null
  const set = (k: string, v: string) => setS({ ...s, [k]: v })
  const onLogo = (f: File | null) => {
    if (!f) return
    const r = new FileReader()
    r.onload = () => set('logo_data_url', String(r.result))
    r.readAsDataURL(f)
  }
  return (
    <div className="card p-5 grid gap-3">
      <h2 className="font-medium">{t('settingsTitle')}</h2>
      <div className="grid md:grid-cols-3 gap-3">
        <div><span className={label}>{t('orgName')}</span><input className={input} value={s.org_name} onChange={(e) => set('org_name', e.target.value)} /></div>
        <div><span className={label}>{t('productName')}</span><input className={input} value={s.product_name} onChange={(e) => set('product_name', e.target.value)} /></div>
        <div><span className={label}>{t('marking')}</span><input className={input} value={s.marking} onChange={(e) => set('marking', e.target.value)} /></div>
        <div><span className={label}>{t('accent')}</span><div className="flex gap-2"><input type="color" value={s.accent} onChange={(e) => set('accent', e.target.value)} /><input className={input + ' mono'} value={s.accent} onChange={(e) => set('accent', e.target.value)} /></div></div>
        <div><span className={label}>{t('logo')}</span><input type="file" accept="image/png,image/svg+xml" onChange={(e) => onLogo(e.target.files?.[0] ?? null)} />{s.logo_data_url && <img src={s.logo_data_url} alt="" className="h-8 mt-1" />}</div>
        <div><span className={label}>Digest recipients</span><input className={input} value={s.digest_to} onChange={(e) => set('digest_to', e.target.value)} placeholder="analysts@example.org" /></div>
        <div><span className={label}>{t('requireMfa')}</span><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={['true', '1', 'yes', 'on'].includes((s.require_mfa ?? '').toLowerCase())} onChange={(e) => set('require_mfa', e.target.checked ? 'true' : 'false')} />{t('requireMfaHint')}</label></div>
        <div className="md:col-span-3"><span className={label}>Footer note</span><input className={input} value={s.footer_note} onChange={(e) => set('footer_note', e.target.value)} /></div>
      </div>
      <div className="flex items-center gap-3"><button className="btn primary text-sm" onClick={async () => { try { setS(await api.saveSettings(s)); setMsg(t('saved')); window.location.reload() } catch (e) { setMsg(String(e)) } }}>{t('save')}</button>{msg && <span className="muted text-xs">{msg}</span>}</div>
    </div>
  )
}

export default function Admin() {
  const { t } = useLang()
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3"><h1 className="text-xl font-semibold">{t('admin')}</h1><Link className="btn text-xs" to="/users">{t('users')}</Link></div>
      <LicenceCard />
      <SettingsCard />
      <KeysCard />
      <div className="card p-5 grid gap-2">
        <h2 className="font-medium">{t('exports')}</h2>
        <div className="muted text-xs">{t('exportHint')}</div>
        <div className="flex gap-2 flex-wrap text-sm">
          <a className="btn" href="/api/export/events.csv?days=730">events.csv</a>
          <a className="btn" href="/api/export/observations.csv?days=730">observations.csv</a>
          <a className="btn" href="/api/export/series.csv?name=hormuz_transits">hormuz_transits.csv</a>
          <a className="btn" href="/api/export/series.csv?name=bab_el_mandeb_transits">bab_el_mandeb_transits.csv</a>
          <a className="btn" href="/api/export/forecasts.csv">forecasts.csv</a>
          <a className="btn" href="/api/export/forecasts.json">forecasts.json</a>
        </div>
      </div>
    </div>
  )
}
