import { useEffect, useState } from 'react'
import { api, type EventRow, type Observation } from '../api'
import { DemoTag } from '../components'
import { useLang } from '../i18n'

export default function Queue() {
  const { t, lang } = useLang()
  const [q, setQ] = useState<{ events: EventRow[]; observations: Observation[] } | null>(null)
  const [by, setBy] = useState(() => localStorage.getItem('rasad.analyst') || 'analyst')
  const load = () => api.queue().then(setQ)
  useEffect(() => { load() }, [])
  const decide = async (kind: 'event' | 'observation', id: number, d: 'verified' | 'rejected', score?: number) => { await api.verify(kind, id, d, by, score); load() }
  if (!q) return <div className="muted">…</div>
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-2 text-sm"><span className="muted">analyst</span><input className="bg-transparent border border-[var(--line)] rounded px-2 py-1" value={by} onChange={(e) => { setBy(e.target.value); localStorage.setItem('rasad.analyst', e.target.value) }} /></div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">{t('pendingEvents')} <span className="muted text-sm">{q.events.length}</span></h2>
        {q.events.length === 0 && <div className="muted text-sm">{t('queueEmpty')}</div>}
        <div className="space-y-3">
          {q.events.map((e) => (
            <div key={e.id} className="border-b border-[var(--line)] pb-3 text-sm">
              <div><span className="mono muted me-2">{e.event_date}</span><span className="tag me-2">{e.event_type}</span>{e.country && <span className="tag me-2">{e.country}</span>}<DemoTag show={e.is_synthetic} /></div>
              <div className="mt-1">{lang === 'ar' && e.description_ar ? e.description_ar : e.description_en}</div>
              <div className="muted text-xs mt-1">{e.provenance?.source} {e.provenance?.url && <a className="accent" href={e.provenance.url} target="_blank" rel="noreferrer">link</a>} {e.provenance?.quote && <span>· “{e.provenance.quote}”</span>}</div>
              <div className="mt-2 flex gap-2"><button className="btn text-xs" onClick={() => decide('event', e.id, 'verified')}>{t('accept')}</button><button className="btn text-xs" onClick={() => decide('event', e.id, 'rejected')}>{t('reject')}</button></div>
            </div>
          ))}
        </div>
      </div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">{t('pendingObs')} <span className="muted text-sm">{q.observations.length}</span></h2>
        {q.observations.length === 0 && <div className="muted text-sm">{t('queueEmpty')}</div>}
        <div className="space-y-3">
          {q.observations.map((o) => <ObsRow key={o.id} o={o} decide={decide} />)}
        </div>
      </div>
    </div>
  )
}

function ObsRow({ o, decide }: { o: Observation; decide: (k: 'observation', id: number, d: 'verified' | 'rejected', score?: number) => void }) {
  const { t } = useLang()
  const [score, setScore] = useState(o.score)
  return (
    <div className="border-b border-[var(--line)] pb-3 text-sm">
      <div><span className="mono muted me-2">{o.observed_at}</span><span className="tag me-2">{o.actor}</span><span className="tag me-2">{o.issue}</span><span className="tag me-2">{o.track}</span><span className="tag me-2">{o.cost_class}</span><span className="tag me-2">{o.speaker_level}</span><span className="muted text-xs">{t('confidence')} {o.model_confidence}</span><DemoTag show={o.is_synthetic} /></div>
      <div className="mt-1" dir="auto">{o.text_excerpt}</div>
      {o.text_excerpt_en && <div className="muted text-xs" dir="ltr">{o.text_excerpt_en}</div>}
      <div className="muted text-xs mt-1">{o.provenance?.source} {o.provenance?.url && <a className="accent" href={o.provenance.url} target="_blank" rel="noreferrer">link</a>}</div>
      <div className="mt-2 flex items-center gap-2">
        <span className="muted text-xs">{t('score')}</span>
        <input type="range" min={-1} max={1} step={0.1} value={score} onChange={(e) => setScore(parseFloat(e.target.value))} />
        <span className="mono text-xs w-10">{score.toFixed(1)}</span>
        <button className="btn text-xs" onClick={() => decide('observation', o.id, 'verified', score)}>{t('accept')}</button>
        <button className="btn text-xs" onClick={() => decide('observation', o.id, 'rejected')}>{t('reject')}</button>
      </div>
    </div>
  )
}
