import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type DocRow, type IndicatorDetail, type PanelView, type QuestionDetail } from '../api'
import { atLeast, useAuth } from '../auth'
import { Delta, DemoTag, Prob, Sparkline, StateTag } from '../components'
import { pct, useLang } from '../i18n'
import { DocCard, DocViewer } from './Search'

function RelatedDocs({ code }: { code: string }) {
  const { t } = useLang()
  const [docs, setDocs] = useState<{ terms: string[]; documents: DocRow[] } | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  useEffect(() => { api.questionDocuments(code, 30).then(setDocs) }, [code])
  return (
    <div className="card p-5">
      <h2 className="font-medium mb-1">{t('relatedDocs')} <span className="muted text-sm">{docs?.documents.length ?? ''}</span></h2>
      {docs && <div className="muted text-[11px] mb-2">{t('routedBy')}: {docs.terms.join(', ')}</div>}
      {docs?.documents.slice(0, 12).map((d) => <DocCard key={d.id} d={d} onOpen={setOpen} />)}
      {docs && docs.documents.length === 0 && <div className="muted text-sm">{t('noResults')}</div>}
      {open != null && <DocViewer id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function PanelBlock({ code, open }: { code: string; open: boolean }) {
  const { t } = useLang()
  const { me } = useAuth()
  const [pv, setPv] = useState<PanelView | null>(null)
  const [p, setP] = useState(50)
  const [why, setWhy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const load = () => api.panel(code).then((v) => { setPv(v); if (v.mine) { setP(Math.round(v.mine.probability * 100)); setWhy(v.mine.rationale ?? '') } })
  useEffect(() => { load() }, [code]) // eslint-disable-line react-hooks/exhaustive-deps
  const canForecast = open && atLeast(me?.role, 'analyst')
  return (
    <div className="card p-5">
      <h2 className="font-medium mb-1">{t('panel')}</h2>
      <div className="muted text-xs mb-3">{t('panelHint')}</div>
      {canForecast && (
        <form className="grid gap-2 mb-4" onSubmit={async (e) => { e.preventDefault(); try { await api.submitPanel(code, p / 100, why); setMsg(t('saved')); load() } catch (ex) { setMsg(String(ex)) } }}>
          <div className="flex items-center gap-3">
            <span className="muted text-xs">{t('yourEstimate')}</span>
            <input type="range" min={1} max={99} value={p} onChange={(e) => setP(Number(e.target.value))} className="flex-1" />
            <input type="number" min={1} max={99} value={p} onChange={(e) => setP(Number(e.target.value))} className="w-16 bg-transparent border border-[var(--line)] rounded px-2 py-1 mono text-sm" />
            <span className="mono text-sm">%</span>
          </div>
          <textarea className="w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 text-sm" rows={2} placeholder={t('rationale')} value={why} onChange={(e) => setWhy(e.target.value)} />
          <div className="flex items-center gap-3"><button className="btn primary text-sm" type="submit">{t('submitEstimate')}</button>{msg && <span className="muted text-xs">{msg}</span>}</div>
        </form>
      )}
      {pv && pv.latest.length > 0 && (
        <table className="grid text-sm">
          <thead><tr><th>{t('panelLatest')}</th><th>{t('asOf')}</th><th>{t('probability')}</th><th>{t('rationale')}</th></tr></thead>
          <tbody>{pv.latest.map((r) => <tr key={r.code}><td>{r.forecaster}</td><td className="mono text-xs">{r.as_of}</td><td className="mono">{pct(r.probability)}</td><td className="muted text-xs">{r.rationale}</td></tr>)}</tbody>
        </table>
      )}
    </div>
  )
}

function EvidenceBlock({ ind }: { ind: IndicatorDetail }) {
  const { lang } = useLang()
  const ev = ind.evidence as Record<string, unknown>
  const rows: string[] = []
  if (ev.series && ev.value !== undefined) rows.push(`${ev.series} = ${ev.value} ${ev.unit ?? ''} (${ev.date})${ev.is_synthetic ? ' · demo' : ''}`)
  if (ev.recent_mean !== undefined) rows.push(`${ev.series}: ${ev.recent_mean} vs ${ev.baseline_mean} (ratio ${ev.ratio}, threshold ${ev.threshold})`)
  if (ev.score !== undefined && ev.actor) rows.push(`${ev.actor} / ${ev.issue} (${ev.track ?? ''}): ${ev.score} from ${ev.n} observations`)
  if (ev.divergence !== undefined) rows.push(`${ev.actor} / ${ev.issue}: divergence ${ev.divergence} (threshold ${ev.threshold})`)
  if (ev.recent_count !== undefined && ev.expected_in_window !== undefined) rows.push(`${ev.actor} / ${ev.issue}: ${ev.recent_count} statements vs ${ev.expected_in_window} expected`)
  if (ev.count !== undefined) rows.push(`${ev.count} / ${ev.threshold} in ${ev.window_days} days`)
  if (ev.reason) rows.push(String(ev.reason))
  return (
    <div className="mt-2 text-sm">
      {rows.map((r, i) => <div key={i} className="muted mono text-xs">{r}</div>)}
      {ind.events.length > 0 && (
        <ul className="mt-1 space-y-1">
          {ind.events.map((e) => (
            <li key={e.id} className="text-xs">
              <span className="mono muted me-2">{e.event_date}</span>
              {lang === 'ar' && e.description_ar ? e.description_ar : e.description_en}
              {e.provenance?.url ? <a className="accent ms-1" href={e.provenance.url} target="_blank" rel="noreferrer">[{e.provenance.source}]</a> : <span className="muted ms-1">[{e.provenance?.source}]</span>}
              <DemoTag show={e.is_synthetic} />
              {e.verification !== 'verified' && <span className="tag ms-1">{e.verification}</span>}
            </li>
          ))}
        </ul>
      )}
      {ind.rule && <details className="mt-1"><summary className="muted text-xs cursor-pointer">rule</summary><pre className="text-[11px] muted whitespace-pre-wrap">{JSON.stringify(ind.rule)}</pre></details>}
    </div>
  )
}

export default function Question() {
  const { code } = useParams()
  const { t, lang } = useLang()
  const [q, setQ] = useState<QuestionDetail | null>(null)
  useEffect(() => { if (code) api.question(code).then(setQ) }, [code])
  if (!q) return <div className="muted">…</div>
  const present = q.indicators.filter((i) => i.state === 'present').sort((a, b) => Math.abs(b.log_lr) - Math.abs(a.log_lr))
  const rest = q.indicators.filter((i) => i.state !== 'present')
  return (
    <div className="grid gap-4">
      <div className="card p-5">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1 min-w-[280px]">
            <h1 className="text-xl font-semibold leading-snug">{lang === 'ar' && q.title_ar ? q.title_ar : q.title_en}</h1>
            <div className="muted text-xs mt-1">{t('horizon')} {q.horizon_days} {t('days')} · {t('baseRate')} {pct(q.base_rate)} · {t('asOf')} <span className="mono">{q.as_of}</span> <DemoTag show={q.synthetic_share > 0} /></div>
            {q.base_rate_note && <div className="muted text-sm mt-2">{q.base_rate_note}</div>}
          </div>
          <div className="text-end">
            <Prob p={q.final_prob} big />
            <div className="mt-1"><Delta d={q.delta_30d} /> <span className="muted text-xs">{t('movement30')}</span></div>
            <div className="mt-2"><Sparkline points={q.history_90.map((h) => h.final_prob)} width={220} height={48} accent /></div>
            <div className="mt-2 flex gap-2 justify-end">
              <Link className="btn primary" to={`/q/${q.code}/brief`}>{t('openBrief')}</Link>
            </div>
          </div>
        </div>
        <div className="grid md:grid-cols-3 gap-3 mt-4 text-sm">
          <div className="card p-3"><div className="muted text-xs">{t('machine')}</div><div className="mono text-lg">{pct(q.machine_prob)}</div><div className="muted text-xs">{t('weight')} {q.machine_weight ?? 1}</div></div>
          <div className="card p-3"><div className="muted text-xs">{t('panel')}</div><div className="mono text-lg">{pct(q.panel_prob)}</div>{q.panel && <div className="muted text-xs">n {q.panel.n} · {pct(q.panel.low)} to {pct(q.panel.high)}</div>}</div>
          <div className="card p-3"><div className="muted text-xs">{t('final')}</div><div className="mono text-lg">{pct(q.final_prob)}</div><div className="muted text-[10px] mono truncate">{t('commit')} {q.commit_hash?.slice(0, 16)}</div></div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-5">
          <h2 className="font-medium mb-3">{t('movers')}</h2>
          {present.length === 0 && <div className="muted text-sm">{t('baseRate')}</div>}
          <div className="space-y-4">
            {present.map((ind) => (
              <div key={ind.code}>
                <div className="flex items-center gap-2"><StateTag state={ind.state} /><span className="font-medium text-sm">{lang === 'ar' && ind.name_ar ? ind.name_ar : ind.name_en}</span><span className="mono muted text-xs ms-auto">{ind.log_lr > 0 ? '+' : ''}{ind.log_lr.toFixed(2)}</span></div>
                <EvidenceBlock ind={ind} />
              </div>
            ))}
          </div>
        </div>
        <div className="card p-5">
          <h2 className="font-medium mb-3">{t('watch')}</h2>
          <div className="space-y-4">
            {rest.map((ind) => (
              <div key={ind.code}>
                <div className="flex items-center gap-2"><StateTag state={ind.state} /><span className="text-sm">{lang === 'ar' && ind.name_ar ? ind.name_ar : ind.name_en}</span><span className="mono muted text-xs ms-auto">LR+ {ind.lr_present} / LR- {ind.lr_absent}</span></div>
                <EvidenceBlock ind={ind} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <PanelBlock code={q.code} open={q.status === 'open'} />
      <RelatedDocs code={q.code} />

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-5"><h2 className="font-medium mb-2">{t('decisions')}</h2><ul className="list-disc ps-5 text-sm">{q.decision_hooks.map((h) => <li key={h}>{h}</li>)}</ul></div>
        <div className="card p-5"><h2 className="font-medium mb-2">{t('resolution')}</h2><p className="text-sm">{q.resolution_criteria}</p></div>
      </div>
    </div>
  )
}
