import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ActorBook, type IssueEntry, type Observation } from '../api'
import { DemoTag, Sparkline } from '../components'
import { useLang } from '../i18n'

function Gauge({ v }: { v: number | null }) {
  if (v == null) return <span className="muted text-xs">n/a</span>
  const x = ((v + 1) / 2) * 100
  return (
    <div className="relative h-2 rounded bg-[var(--line)] w-full">
      <div className="absolute top-[-3px] h-[14px] w-[3px] bg-[var(--accent)] rounded" style={{ insetInlineStart: `calc(${x}% - 1px)` }} />
      <div className="absolute top-0 h-2 w-px bg-[var(--ink-2)]" style={{ insetInlineStart: '50%' }} />
    </div>
  )
}

function IssueCard({ e }: { e: IssueEntry }) {
  const { t, lang } = useLang()
  const [obs, setObs] = useState<Observation[] | null>(null)
  const cps = [...e.change_points.stated.map((c) => ({ ...c, track: 'stated' })), ...e.change_points.revealed.map((c) => ({ ...c, track: 'revealed' }))]
  return (
    <div className="card p-4">
      <div className="flex items-baseline gap-2">
        <div className="font-medium">{lang === 'ar' && e.issue_name_ar ? e.issue_name_ar : e.issue_name_en}</div>
        <div className="muted text-xs">{e.low_label_en} ← → {e.high_label_en}</div>
        {e.divergence != null && e.divergence >= 0.4 && <span className="tag present ms-auto">{t('divergence')} {e.divergence.toFixed(2)}</span>}
        {e.silence.flagged && <span className="tag demo">{t('silence')}</span>}
      </div>
      <div className="grid md:grid-cols-2 gap-4 mt-3">
        {(['stated', 'revealed'] as const).map((tr) => (
          <div key={tr}>
            <div className="flex items-center justify-between text-xs muted"><span>{t(tr)}</span><span className="mono">{e[tr].score == null ? 'n/a' : e[tr].score!.toFixed(2)} · n {e[tr].n} · w {e[tr].effective_n.toFixed(2)}</span></div>
            <Gauge v={e[tr].score} />
            <div className="mt-1"><Sparkline points={e.series[tr].map((p) => p[1])} width={260} height={34} accent={tr === 'revealed'} /></div>
          </div>
        ))}
      </div>
      {cps.length > 0 && <div className="muted text-xs mt-2">{t('changePoints')}: {cps.map((c) => `${c.track} ${c.direction} ${c.date}`).join(' · ')}</div>}
      <div className="mt-2">
        <button className="btn text-xs" onClick={() => obs ? setObs(null) : api.observations(e.actor, e.issue).then(setObs)}>{t('observations')}</button>
        {obs && (
          <table className="grid mt-2 text-xs">
            <thead><tr><th>date</th><th>track</th><th>cost</th><th>speaker</th><th>{t('score')}</th><th>grade</th><th>text</th></tr></thead>
            <tbody>
              {obs.map((o) => (
                <tr key={o.id}>
                  <td className="mono">{o.observed_at}</td><td>{o.track}</td><td>{o.cost_class}</td><td>{o.speaker_level}</td>
                  <td className="mono">{o.score.toFixed(2)}</td><td className="mono">{o.source_grade}</td>
                  <td>{o.text_excerpt}{o.text_excerpt_en && <div className="muted">{o.text_excerpt_en}</div>}{o.provenance?.url ? <a className="accent" href={o.provenance.url} target="_blank" rel="noreferrer"> [{o.provenance.source}]</a> : <span className="muted"> [{o.provenance?.source}]</span>}<DemoTag show={o.is_synthetic} />{o.verification !== 'verified' && <span className="tag ms-1">{o.verification}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default function Positions() {
  const { actor } = useParams()
  const { t, lang } = useLang()
  const [actors, setActors] = useState<{ code: string; name_en: string; name_ar: string | null; observations: number }[]>([])
  const [book, setBook] = useState<ActorBook | null>(null)
  useEffect(() => { api.actors().then((a) => setActors(a.filter((x) => x.observations > 0))) }, [])
  useEffect(() => { if (actor) api.actorBook(actor).then(setBook); else setBook(null) }, [actor])
  return (
    <div className="grid md:grid-cols-[220px_1fr] gap-4">
      <div className="card p-2 h-fit">
        {actors.map((a) => (
          <Link key={a.code} to={`/positions/${a.code}`} className={`block px-3 py-2 rounded-md text-sm ${actor === a.code ? 'bg-[var(--bg)] text-[var(--accent)]' : 'hover:bg-[var(--bg)]'}`}>
            {lang === 'ar' && a.name_ar ? a.name_ar : a.name_en} <span className="muted text-xs mono">{a.observations}</span>
          </Link>
        ))}
      </div>
      <div className="grid gap-3">
        {!book && <div className="muted">{t('noSelection')}</div>}
        {book && <h1 className="text-xl font-semibold">{lang === 'ar' && book.actor.name_ar ? book.actor.name_ar : book.actor.name_en} <span className="muted text-sm font-normal">{t('asOf')} {book.as_of}</span></h1>}
        {book?.issues.map((e) => <IssueCard key={e.issue} e={e} />)}
      </div>
    </div>
  )
}
