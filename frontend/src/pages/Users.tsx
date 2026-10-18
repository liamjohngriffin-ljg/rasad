import { useEffect, useState } from 'react'
import { useLang } from '../i18n'

type U = { id: number; username: string; display_name: string; role: string; active: boolean; must_change_password: boolean; last_login_at: string | null }
type Audit = { id: number; at: string; user: string | null; action: string; target: string | null; detail: Record<string, unknown>; ip: string | null }

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.status }))).detail)
  return r.json()
}

export default function Users() {
  const { t } = useLang()
  const [users, setUsers] = useState<U[]>([])
  const [audit, setAudit] = useState<Audit[]>([])
  const [form, setForm] = useState({ username: '', display_name: '', role: 'viewer', password: '' })
  const [msg, setMsg] = useState<string | null>(null)
  const load = () => { j<U[]>('/api/users').then(setUsers); j<Audit[]>('/api/audit?limit=100').then(setAudit) }
  useEffect(load, [])
  const patch = async (id: number, body: Record<string, unknown>) => { try { await j(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }); setMsg(null); load() } catch (e) { setMsg(String((e as Error).message)) } }
  return (
    <div className="grid gap-4">
      <div className="card p-4">
        <h2 className="font-medium mb-3">{t('users')}</h2>
        <table className="grid text-sm">
          <thead><tr><th>{t('username')}</th><th>{t('name')}</th><th>{t('role')}</th><th>{t('status')}</th><th>{t('lastLogin')}</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td className="mono">{u.username}</td><td>{u.display_name}</td>
                <td><select className="bg-transparent border border-[var(--line)] rounded px-1" value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}>{['viewer', 'analyst', 'admin'].map((r) => <option key={r} value={r}>{r}</option>)}</select></td>
                <td>{u.active ? t('active') : t('inactive')}{u.must_change_password && <span className="tag ms-2">{t('mustChange')}</span>}</td>
                <td className="mono muted text-xs">{u.last_login_at?.slice(0, 16) ?? '-'}</td>
                <td className="text-end">
                  <button className="btn text-xs me-1" onClick={() => { const p = prompt(t('newPasswordFor') + ' ' + u.username); if (p) patch(u.id, { password: p }) }}>{t('resetPassword')}</button>
                  <button className="btn text-xs" onClick={() => patch(u.id, { active: !u.active })}>{u.active ? t('deactivate') : t('activate')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="grid md:grid-cols-5 gap-2 mt-4 items-end" onSubmit={async (e) => { e.preventDefault(); try { await j('/api/users', { method: 'POST', body: JSON.stringify(form) }); setForm({ username: '', display_name: '', role: 'viewer', password: '' }); setMsg(null); load() } catch (err) { setMsg(String((err as Error).message)) } }}>
          <input className="bg-transparent border border-[var(--line)] rounded px-2 py-1" placeholder={t('username')} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input className="bg-transparent border border-[var(--line)] rounded px-2 py-1" placeholder={t('name')} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          <select className="bg-transparent border border-[var(--line)] rounded px-2 py-1" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{['viewer', 'analyst', 'admin'].map((r) => <option key={r} value={r}>{r}</option>)}</select>
          <input className="bg-transparent border border-[var(--line)] rounded px-2 py-1" type="password" placeholder={t('tempPassword')} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <button className="btn primary" type="submit">{t('addUser')}</button>
        </form>
        {msg && <div className="text-[var(--up)] text-sm mt-2">{msg}</div>}
        <div className="muted text-xs mt-2">{t('userHint')}</div>
      </div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">{t('auditLog')}</h2>
        <table className="grid text-xs">
          <thead><tr><th>at</th><th>user</th><th>action</th><th>target</th><th>detail</th><th>ip</th></tr></thead>
          <tbody>{audit.map((a) => <tr key={a.id}><td className="mono">{a.at.slice(0, 19)}</td><td>{a.user ?? '-'}</td><td>{a.action}</td><td className="mono">{a.target ?? ''}</td><td className="muted">{JSON.stringify(a.detail)}</td><td className="mono muted">{a.ip ?? ''}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}
