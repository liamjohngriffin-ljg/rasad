import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type AlertRow, type Changes } from '../api'
import { atLeast, useAuth } from '../auth'
import { pct, useLang } from '../i18n'

const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10) }

export function AlertLine({ a, onAck }: { a: AlertRow; onAck?: (id: number) => void }) {
  const { t, lang } = useLang()
  const sev = a.severity >= 3 ? 'present' : a.severity === 2 ? '' : 'absent'
  return (
    <div className="flex items-start gap-2 text-sm border-b border-[var(--line)] py-2">
      <span className={`tag ${sev} whitespace-nowrap`}>{a.kind.replace('_', ' ')}</span>
      <div className="flex-1">
        <div>{lang === 'ar' && a.title_ar ? a.title_ar : a.title_en}</div>
        <div className="muted text-xs mono">{a.created_at.slice(0, 16).replace('T', ' ')} {a.question_code && <Link className="accent ms-2" to={`/q/${a.question_code}`}>{a.question_code}</Link>}{a.acknowledged_by && <span className="ms-2">✓ {a.acknowledged_by}</span>}</div>
      </div>
      {onAck && !a.acknowledged_at && <button className="btn text-xs" onClick={() => onAck(a.id)}>{t('acknowledge')}</button>}
    </div>
  )
}

export default function Today() {
  const { t, lang } = useLang()
  const { me } = useAuth()
  const [since, setSince] = useState(daysAgo(1))
  const [ch, setCh] = useState<Changes | null>(null)
  const [alerts, setAlerts] = useState<AlertRow[]>([])
  const load = () => { api.changes(since).then(setCh); api.alerts().then(setAlerts) }
  useEffect(() => { load() }, [since]) // eslint-disable-line react-hooks/exhaustive-deps
  const canAck = atLeast(me?.role, 'analyst')
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold">{t('today')}</h1>
        <span className="muted text-sm">{t('since')}</span>
        <div className="flex gap-1">{[1, 7, 30].map((n) => <button key={n} className={`btn text-xs ${since === daysAgo(n) ? 'primary' : ''}`} onClick={() => setSince(daysAgo(n))}>{n} {t('days')}</button>)}</div>
        <input type="date" className="bg-transparent border border-[var(--line)] rounded px-2 py-1 text-sm" value={since} onChange={(e) => setSince(e.target.value)} />
        {ch && <span className="muted text-xs ms-auto">{ch.new_documents} {t('newDocs')} · {ch.new_observations} {t('newObs')}</span>}
      </div>

      <div className="card p-4">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-medium">{t('alerts')} <span className="muted text-sm">{alerts.length}</span></h2>
          {canAck && <button className="btn text-xs ms-auto" onClick={async () => { await api.scanAlerts(); load() }}>{t('scan')}</button>}
          {canAck && alerts.length > 0 && <button className="btn text-xs" onClick={async () => { await api.ackAll(); load() }}>{t('ackAll')}</button>}
        </div>
        {alerts.length === 0 && <div className="muted text-sm">{t('noAlerts')}</div>}
        {alerts.map((a) => <AlertLine key={a.id} a={a} onAck={canAck ? async (id) => { await api.ackAlert(id); load() } : undefined} />)}
      </div>

      {ch && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="card p-4">
            <h2 className="font-medium mb-2">{t('moves')}</h2>
            <table className="grid text-sm">
              <thead><tr><th>{t('questions')}</th><th>{t('since')}</th><th>{t('asOf')}</th><th>Δ</th></tr></thead>
              <tbody>
                {ch.moves.map((m) => (
                  <tr key={m.code}>
                    <td><Link className="hover:text-[var(--accent)]" to={`/q/${m.code}`}>{lang === 'ar' && m.title_ar ? m.title_ar : m.title_en}</Link>{m.flips.length > 0 && <div className="muted text-xs">{m.flips.length} {t('flips')}: {m.flips.map((f) => `${f.indicator} ${f.from} → ${f.to}`).join('; ')}</div>}</td>
                    <td className="mono">{m.from == null ? '-' : pct(m.from)}</td><td className="mono">{pct(m.to)}</td>
                    <td className={`mono ${m.delta_points > 0.5 ? 'text-[var(--up)]' : m.delta_points < -0.5 ? 'text-[var(--down)]' : 'muted'}`}>{m.delta_points > 0 ? '+' : ''}{m.delta_points.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card p-4">
            <h2 className="font-medium mb-2">{t('newEvents')} <span className="muted text-sm">{ch.events.length}</span></h2>
            <div className="space-y-2 text-sm">
              {ch.events.map((e) => (
                <div key={e.id} className="border-b border-[var(--line)] pb-2">
                  <div><span className="mono muted me-2">{e.event_date}</span><span className="tag me-1">{e.event_type}</span>{e.country && <span className="tag me-1">{e.country}</span>}<span className="tag">{'!'.repeat(e.severity)}</span>{e.verification !== 'verified' && <span className="tag ms-1 unknown">{e.verification}</span>}</div>
                  <div className="text-xs mt-1">{lang === 'ar' && e.description_ar ? e.description_ar : e.description_en}</div>
                  {e.source && <div className="muted text-[11px]">{e.source}</div>}
                </div>
              ))}
              {ch.events.length === 0 && <div className="muted">{t('queueEmpty')}</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
