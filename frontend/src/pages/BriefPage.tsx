import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { Markdown } from '../components'
import { useLang } from '../i18n'

export default function BriefPage() {
  const { code } = useParams()
  const { t, lang } = useLang()
  const [brief, setBrief] = useState<{ content_md: string; generator: string; generated_at: string } | null>(null)
  useEffect(() => { if (code) { setBrief(null); api.brief(code, lang).then(setBrief) } }, [code, lang])
  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-3 text-sm">
        <Link className="btn" to={`/q/${code}`}>←</Link>
        <span className="muted">{t('brief')}</span>
        {brief && <span className="muted ms-auto text-xs">{t('generator')} {brief.generator} · {brief.generated_at.slice(0, 16)}</span>}
        <button className="btn" onClick={() => window.print()}>PDF</button>
      </div>
      <div className="card p-8">{brief ? <Markdown md={brief.content_md} /> : <div className="muted">…</div>}</div>
    </div>
  )
}
