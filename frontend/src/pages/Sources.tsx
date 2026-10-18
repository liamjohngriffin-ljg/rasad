import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLang } from '../i18n'

export default function Sources() {
  const { t } = useLang()
  const [rows, setRows] = useState<Awaited<ReturnType<typeof api.sources>>>([])
  useEffect(() => { api.sources().then(setRows) }, [])
  return (
    <div className="card p-4">
      <table className="grid text-sm">
        <thead><tr><th>{t('tier')}</th><th>source</th><th>kind</th><th>lang</th><th>{t('licence')}</th><th>{t('reuse')}</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.code}>
              <td className="mono">{s.tier}</td>
              <td>{s.url ? <a className="accent" href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</td>
              <td className="muted">{s.kind}</td><td className="muted">{s.language}</td>
              <td className="muted text-xs">{s.licence_note}</td>
              <td>{s.reuse_ok ? '✓' : '✗'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
