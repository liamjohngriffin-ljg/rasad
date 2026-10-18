import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type QuestionSummary } from '../api'
import { Delta, DemoTag, HistorySpark, Prob, StateTag } from '../components'
import { useLang } from '../i18n'

export default function Board() {
  const { t, lang } = useLang()
  const [qs, setQs] = useState<QuestionSummary[]>([])
  const [asOf, setAsOf] = useState<string>('')
  const [text, setText] = useState('')
  const [sent, setSent] = useState(false)
  useEffect(() => { api.board().then((b) => { setQs(b.questions); setAsOf(b.as_of) }) }, [])
  const title = (q: QuestionSummary) => (lang === 'ar' && q.title_ar ? q.title_ar : q.title_en)
  return (
    <div>
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">{t('board')}</h1>
        <span className="muted text-sm">{t('asOf')} <span className="mono">{asOf}</span></span>
      </div>
      <div className="grid gap-3">
        {qs.map((q) => (
          <Link to={`/q/${q.code}`} key={q.code} className="card p-4 grid grid-cols-12 gap-4 items-center hover:border-[var(--accent)]">
            <div className="col-span-12 md:col-span-6">
              <div className="font-medium leading-snug">{title(q)}</div>
              <div className="muted text-xs mt-1">{t('horizon')} {q.horizon_days} {t('days')} · {t('baseRate')} {Math.round(q.base_rate * 100)}% <DemoTag show={q.synthetic_share > 0} /></div>
              <div className="mt-2 flex flex-wrap gap-1">
                {q.movers.map((m) => (
                  <span key={m.indicator} className="text-xs muted me-2"><StateTag state={m.state} /> {lang === 'ar' && m.name_ar ? m.name_ar : m.name_en}</span>
                ))}
              </div>
            </div>
            <div className="col-span-6 md:col-span-3"><Prob p={q.final_prob} big /></div>
            <div className="col-span-3 md:col-span-1 text-end"><Delta d={q.delta_30d} /><div className="muted text-[10px]">{t('movement30')}</div></div>
            <div className="col-span-3 md:col-span-2 flex justify-end"><HistorySpark history={q.history} /></div>
          </Link>
        ))}
      </div>
      <div className="card p-4 mt-6">
        <div className="font-medium mb-2">{t('tasking')}</div>
        <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!text.trim()) return; await api.createTasking(text.trim(), 'principal'); setText(''); setSent(true) }}>
          <input className="flex-1 bg-transparent border border-[var(--line)] rounded-md px-3 py-2" placeholder={t('taskingPlaceholder')} value={text} onChange={(e) => setText(e.target.value)} />
          <button className="btn primary" type="submit">{t('submit')}</button>
        </form>
        {sent && <div className="muted text-xs mt-2">✓</div>}
      </div>
    </div>
  )
}
