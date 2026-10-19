import { useEffect, useState } from 'react'
import { Markdown } from '../components'
import { useLang } from '../i18n'

export default function Guide() {
  const { lang } = useLang()
  const [md, setMd] = useState<{ lang: string; content_md: string } | null>(null)
  useEffect(() => { fetch(`/api/guide?lang=${lang}`).then((r) => r.json()).then(setMd).catch(() => setMd(null)) }, [lang])
  if (!md) return <div className="muted">…</div>
  return <div className="card p-6 max-w-3xl mx-auto brief" dir={md.lang === 'ar' ? 'rtl' : 'ltr'}><Markdown md={md.content_md} /></div>
}
