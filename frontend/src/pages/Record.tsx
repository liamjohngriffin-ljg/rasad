import { useEffect, useState } from 'react'
import { api, type CalibrationData, type ScoreSummary } from '../api'
import { pct, useLang } from '../i18n'

function Score({ s, label }: { s: ScoreSummary; label: string }) {
  const { t } = useLang()
  return (
    <div className="card p-4">
      <div className="muted text-xs">{label}</div>
      <div className="mono text-2xl mt-1">{s.skill == null ? 'n/a' : s.skill.toFixed(2)}</div>
      <div className="muted text-xs">{t('skill')}</div>
      <div className="muted text-xs mt-2 mono">{t('meanBrier')} {s.mean_brier ?? 'n/a'} · {t('baselineBrier')} {s.baseline_brier ?? 'n/a'} · {t('n')} {s.n}</div>
    </div>
  )
}

export default function Record() {
  const { t, lang } = useLang()
  const [c, setC] = useState<CalibrationData | null>(null)
  useEffect(() => { api.calibration().then(setC) }, [])
  if (!c) return <div className="muted">…</div>
  return (
    <div className="grid gap-4">
      <div className="card p-4 flex items-center gap-4 text-sm">
        <span className="font-medium">{t('chain')}</span>
        <span className={`tag ${c.chain.verified ? 'absent' : 'present'}`}>{c.chain.verified ? t('verified') : t('notVerified')}</span>
        <span className="muted mono text-xs">{c.chain.length} commits · head {c.chain.head?.slice(0, 20)}</span>
      </div>
      <div className="text-xs muted">{t('demoRecord')}</div>
      <div className="grid md:grid-cols-4 gap-3">
        <Score s={c.all} label="All" />
        {Object.entries(c.by_horizon).map(([h, s]) => <Score key={h} s={s} label={`T-${h}`} />)}
      </div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">{t('resolvedQuestions')}</h2>
        <table className="grid text-sm">
          <thead><tr><th>question</th><th>{t('outcome')}</th><th>{t('baseRate')}</th><th>forecasts (Brier)</th></tr></thead>
          <tbody>
            {c.resolved.map((r) => (
              <tr key={r.code}>
                <td><div>{lang === 'ar' && r.title_ar ? r.title_ar : r.title_en}</div><div className="muted text-xs">{r.resolved_at} · {r.notes}</div></td>
                <td>{r.outcome ? t('yes') : t('no')}</td>
                <td className="mono">{pct(r.base_rate)}</td>
                <td className="mono text-xs">{r.forecasts.map((f) => <div key={f.as_of}>{f.as_of}: {pct(f.final_prob)} ({f.brier.toFixed(2)})</div>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card p-4">
        <h2 className="font-medium mb-2">Calibration</h2>
        <table className="grid text-sm"><thead><tr><th>bin</th><th>n</th><th>mean forecast</th><th>observed</th></tr></thead>
          <tbody>{c.all.calibration.map((b) => <tr key={b.bin}><td className="mono">{b.bin}</td><td className="mono">{b.n}</td><td className="mono">{b.mean_forecast ?? 'n/a'}</td><td className="mono">{b.observed_rate ?? 'n/a'}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}
