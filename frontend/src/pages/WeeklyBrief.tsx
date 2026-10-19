import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Markdown } from '../components'
import { useLang } from '../i18n'

export default function WeeklyBrief() {
  const { t, lang } = useLang()
  const [days, setDays] = useState(7)
  const [brief, setBrief] = useState<{ content_md: string; generated_at: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setBrief(null); setErr(null)
    fetch(`/api/briefs/weekly?lang=${lang}&days=${days}`, { headers: { 'X-Rasad-Client': 'web' } })
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail ?? String(r.status)); return j })
      .then(setBrief).catch((e) => setErr(String(e.message ?? e)))
  }, [lang, days])
  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-3 text-sm flex-wrap">
        <Link className="btn" to="/">←</Link>
        <span className="muted">{t('weeklyBrief')}</span>
        {[7, 14, 30].map((n) => <button key={n} className={`btn text-xs ${days === n ? 'primary' : ''}`} onClick={() => setDays(n)}>{n} {t('days')}</button>)}
        {brief?.generated_at && <span className="muted ms-auto text-xs">{brief.generated_at.slice(0, 16)}</span>}
        <a className="btn" href={`/api/briefs/weekly/docx?lang=${lang}&days=${days}`}>{t('downloadWord')}</a>
        <button className="btn" onClick={() => window.print()}>PDF</button>
      </div>
      <div className="card p-8">{brief ? <Markdown md={brief.content_md} /> : err ? <div className="text-[var(--up)] text-sm">{err}</div> : <div className="muted">…</div>}</div>
    </div>
  )
}
