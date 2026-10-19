import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useLang } from '../i18n'

export default function Sources() {
  const { t } = useLang()
  const [rows, setRows] = useState<Awaited<ReturnType<typeof api.sources>>>([])
  const [idx, setIdx] = useState<Awaited<ReturnType<typeof api.seriesIndex>>>([])
  useEffect(() => { api.sources().then(setRows); api.seriesIndex().then(setIdx) }, [])
  return (
    <div className="grid gap-4">
      <div className="card p-4">
        <table className="grid text-sm">
          <thead><tr><th>{t('tier')}</th><th>source</th><th>kind</th><th>lang</th><th>{t('documents')}</th><th>{t('lastFetched')}</th><th>{t('licence')}</th><th>{t('reuse')}</th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.code}>
                <td className="mono">{s.tier}</td>
                <td>{s.url ? <a className="accent" href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</td>
                <td className="muted">{s.kind}</td><td className="muted">{s.language}</td>
                <td className="mono">{s.documents}</td>
                <td className="mono text-xs muted">{s.last_fetched?.slice(0, 16).replace('T', ' ') ?? '-'}</td>
                <td className="muted text-xs">{s.licence_note}</td>
                <td>{s.reuse_ok ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">{t('freshness')}</h2>
        <table className="grid text-sm">
          <thead><tr><th>{t('series')}</th><th>{t('n')}</th><th>{t('since')}</th><th>{t('latest')}</th><th>{t('value')}</th><th>{t('stale')}</th><th>{t('source')}</th></tr></thead>
          <tbody>
            {idx.map((r) => (
              <tr key={r.series} className={r.synthetic > 0 ? 'opacity-80' : ''}>
                <td className="mono text-xs"><Link className="hover:text-[var(--accent)]" to={`/series?s=${r.series}`}>{r.series}</Link>{r.synthetic > 0 && <span className="tag demo ms-2">{r.synthetic} demo</span>}</td>
                <td className="mono">{r.points}</td><td className="mono text-xs">{r.first}</td><td className="mono text-xs">{r.last}</td>
                <td className="mono">{r.latest_value}</td>
                <td className={`mono ${r.days_stale > 30 ? 'text-[var(--up)]' : ''}`}>{r.days_stale}</td>
                <td className="muted text-xs">{r.latest_source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
