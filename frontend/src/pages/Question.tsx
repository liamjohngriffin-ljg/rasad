import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type IndicatorDetail, type QuestionDetail } from '../api'
import { Delta, DemoTag, Prob, Sparkline, StateTag } from '../components'
import { pct, useLang } from '../i18n'

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

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-5"><h2 className="font-medium mb-2">{t('decisions')}</h2><ul className="list-disc ps-5 text-sm">{q.decision_hooks.map((h) => <li key={h}>{h}</li>)}</ul></div>
        <div className="card p-5"><h2 className="font-medium mb-2">{t('resolution')}</h2><p className="text-sm">{q.resolution_criteria}</p></div>
      </div>
    </div>
  )
}
