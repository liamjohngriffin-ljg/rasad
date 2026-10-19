import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type IndicatorDef, type QuestionDef, type Vocab } from '../api'
import { useLang } from '../i18n'

const RULE_TEMPLATES: Record<string, Record<string, unknown>> = {
  event_count: { type: 'event_count', event_types: ['maritime_attack'], countries: ['HORMUZ', 'OM', 'AE'], window_days: 30, threshold: 1, min_severity: 1 },
  series_threshold: { type: 'series_threshold', series: 'war_risk_premium_hormuz_pct', op: '>=', value: 2.0, lookback_days: 30 },
  series_change: { type: 'series_change', series: 'hormuz_transits', window_days: 14, baseline_days: 90, op: '<=', ratio: 0.5 },
  position_level: { type: 'position_level', actor: 'IR', issue: 'hormuz_posture', track: 'stated', op: '>=', value: 0.4 },
  divergence: { type: 'divergence', actor: 'US', issue: 'gulf_force_posture', op: '>=', value: 0.4 },
  silence: { type: 'silence', actor: 'IR', issue: 'hormuz_posture' },
  change_point: { type: 'change_point', actor: 'US', issue: 'gulf_force_posture', track: 'revealed', within_days: 30, direction: 'down' },
}

const input = 'w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 text-sm'
const label = 'muted text-xs block mb-1'

function Field({ l, children }: { l: string; children: React.ReactNode }) {
  return <div><span className={label}>{l}</span>{children}</div>
}

function RuleEditor({ value, onChange, vocab }: { value: Record<string, unknown>; onChange: (r: Record<string, unknown>) => void; vocab: Vocab | null }) {
  const { t } = useLang()
  const [text, setText] = useState(JSON.stringify(value, null, 1))
  const [err, setErr] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ state: string; evidence: Record<string, unknown>; history: { as_of: string; state: string }[] } | null>(null)
  useEffect(() => { setText(JSON.stringify(value, null, 1)) }, [value])
  const apply = (s: string) => {
    setText(s)
    try { const r = JSON.parse(s); setErr(null); onChange(r) } catch (e) { setErr(String(e)) }
  }
  return (
    <div className="grid gap-2">
      <div className="flex gap-2 items-center">
        <span className={label + ' mb-0'}>{t('ruleType')}</span>
        <select className="bg-transparent border border-[var(--line)] rounded-md px-2 py-1 text-sm" value={String(value.type ?? '')} onChange={(e) => { const r = { ...RULE_TEMPLATES[e.target.value] }; onChange(r); setPreview(null) }}>
          {(vocab?.rule_types ?? Object.keys(RULE_TEMPLATES)).map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <button type="button" className="btn text-xs ms-auto" onClick={async () => { try { setPreview(await api.previewRule(value)) } catch (e) { setErr(String(e)) } }}>{t('preview')}</button>
      </div>
      <textarea className={input + ' mono text-xs'} rows={6} value={text} onChange={(e) => apply(e.target.value)} />
      {err && <div className="text-[var(--up)] text-xs">{err}</div>}
      {preview && (
        <div className="text-xs">
          <div><span className="muted">{t('previewHint')}</span></div>
          <div className="mt-1 flex gap-2 flex-wrap">{preview.history.map((h) => <span key={h.as_of} className={`tag ${h.state}`}>{h.as_of} {h.state}</span>)}</div>
          <pre className="muted mono text-[11px] whitespace-pre-wrap mt-1">{JSON.stringify(preview.evidence)}</pre>
        </div>
      )}
      {vocab && value.type === 'series_threshold' || value.type === 'series_change' ? <div className="muted text-[11px]">{t('series')}: {vocab?.series.join(', ')}</div> : null}
    </div>
  )
}

function IndicatorForm({ initial, vocab, onSave, onCancel }: { initial: IndicatorDef; vocab: Vocab | null; onSave: (i: IndicatorDef) => Promise<void>; onCancel: () => void }) {
  const { t } = useLang()
  const [ind, setInd] = useState<IndicatorDef>(initial)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: keyof IndicatorDef, v: unknown) => setInd({ ...ind, [k]: v })
  return (
    <form className="card p-4 grid gap-3" onSubmit={async (e) => { e.preventDefault(); try { await onSave(ind); setErr(null) } catch (ex) { setErr(String(ex)) } }}>
      <div className="grid md:grid-cols-3 gap-3">
        <Field l={t('code')}><input className={input + ' mono'} value={ind.code} disabled={initial.id != null} onChange={(e) => set('code', e.target.value)} /></Field>
        <Field l={t('lrPresent')}><input className={input} type="number" step="0.1" min="0.05" max="10" value={ind.lr_present} onChange={(e) => set('lr_present', Number(e.target.value))} /></Field>
        <Field l={t('lrAbsent')}><input className={input} type="number" step="0.05" min="0.05" max="10" value={ind.lr_absent} onChange={(e) => set('lr_absent', Number(e.target.value))} /></Field>
        <Field l={t('titleEn')}><input className={input} value={ind.name_en} onChange={(e) => set('name_en', e.target.value)} /></Field>
        <Field l={t('titleAr')}><input className={input} dir="rtl" value={ind.name_ar ?? ''} onChange={(e) => set('name_ar', e.target.value || null)} /></Field>
        <Field l={t('polarity')}><select className={input} value={ind.polarity} onChange={(e) => set('polarity', e.target.value)}><option value="emerging">emerging</option><option value="not_emerging">not_emerging</option></select></Field>
      </div>
      <Field l={t('description')}><textarea className={input} rows={2} value={ind.description ?? ''} onChange={(e) => set('description', e.target.value || null)} /></Field>
      <Field l={t('rule')}><RuleEditor value={ind.rule} onChange={(r) => set('rule', r)} vocab={vocab} /></Field>
      {err && <div className="text-[var(--up)] text-xs">{t('errorPrefix')}: {err}</div>}
      <div className="flex gap-2"><button className="btn primary text-sm" type="submit">{t('save')}</button><button className="btn text-sm" type="button" onClick={onCancel}>×</button></div>
    </form>
  )
}

function QuestionEditor({ q, vocab, onChanged }: { q: QuestionDef; vocab: Vocab | null; onChanged: () => void }) {
  const { t } = useLang()
  const [form, setForm] = useState({ title_en: q.title_en, title_ar: q.title_ar ?? '', horizon_days: q.horizon_days, base_rate: q.base_rate, base_rate_note: q.base_rate_note ?? '', resolution_criteria: q.resolution_criteria, resolution_criteria_ar: q.resolution_criteria_ar ?? '', hooks: q.decision_hooks.join('\n'), hooks_ar: (q.decision_hooks_ar ?? []).join('\n') })
  const [msg, setMsg] = useState<string | null>(null)
  const [editing, setEditing] = useState<IndicatorDef | null>(null)
  const [resolve, setResolve] = useState<{ outcome: boolean; notes: string } | null>(null)
  const frozen = q.status !== 'open'
  const save = async () => {
    try {
      await api.updateQuestion(q.code, { title_en: form.title_en, title_ar: form.title_ar || null, horizon_days: form.horizon_days, base_rate: form.base_rate, base_rate_note: form.base_rate_note || null, resolution_criteria: form.resolution_criteria, resolution_criteria_ar: form.resolution_criteria_ar || null, decision_hooks: form.hooks.split('\n').map((s) => s.trim()).filter(Boolean), decision_hooks_ar: form.hooks_ar.split('\n').map((s) => s.trim()).filter(Boolean) })
      setMsg(t('saved')); onChanged()
    } catch (e) { setMsg(`${t('errorPrefix')}: ${String(e)}`) }
  }
  return (
    <div className="card p-5 grid gap-4">
      <div className="flex items-center gap-2">
        <span className="mono text-sm">{q.code}</span><span className={`tag ${q.status === 'open' ? 'present' : ''}`}>{q.status}</span>
        <span className="muted text-xs">{q.opened_at} → {q.resolves_at}</span>
        <Link className="btn text-xs ms-auto" to={`/q/${q.code}`}>{t('openBrief').replace('brief', '').trim() || 'open'}</Link>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <Field l={t('titleEn')}><input className={input} disabled={frozen} value={form.title_en} onChange={(e) => setForm({ ...form, title_en: e.target.value })} /></Field>
        <Field l={t('titleAr')}><input className={input} dir="rtl" disabled={frozen} value={form.title_ar} onChange={(e) => setForm({ ...form, title_ar: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field l={t('horizonDays')}><input className={input} type="number" disabled={frozen} value={form.horizon_days} onChange={(e) => setForm({ ...form, horizon_days: Number(e.target.value) })} /></Field>
          <Field l={t('baseRate')}><input className={input} type="number" step="0.01" min="0.01" max="0.99" disabled={frozen} value={form.base_rate} onChange={(e) => setForm({ ...form, base_rate: Number(e.target.value) })} /></Field>
        </div>
        <Field l={t('baseRateNote')}><input className={input} disabled={frozen} value={form.base_rate_note} onChange={(e) => setForm({ ...form, base_rate_note: e.target.value })} /></Field>
        <Field l={t('criteria')}><textarea className={input} rows={3} disabled={frozen} value={form.resolution_criteria} onChange={(e) => setForm({ ...form, resolution_criteria: e.target.value })} /></Field>
        <Field l={t('hooks')}><textarea className={input} rows={3} disabled={frozen} value={form.hooks} onChange={(e) => setForm({ ...form, hooks: e.target.value })} /></Field>
        <Field l={t('criteria') + ' (ar)'}><textarea className={input} dir="rtl" rows={3} disabled={frozen} value={form.resolution_criteria_ar} onChange={(e) => setForm({ ...form, resolution_criteria_ar: e.target.value })} /></Field>
        <Field l={t('hooks') + ' (ar)'}><textarea className={input} dir="rtl" rows={3} disabled={frozen} value={form.hooks_ar} onChange={(e) => setForm({ ...form, hooks_ar: e.target.value })} /></Field>
      </div>
      {!frozen && (
        <div className="flex gap-2 items-center">
          <button className="btn primary text-sm" onClick={save}>{t('save')}</button>
          <button className="btn text-sm" onClick={() => setResolve(resolve ? null : { outcome: true, notes: '' })}>{t('resolve')}</button>
          {msg && <span className="muted text-xs">{msg}</span>}
        </div>
      )}
      {resolve && !frozen && (
        <div className="card p-3 grid gap-2 text-sm">
          <div className="muted text-xs">{t('resolveHint')}</div>
          <div className="flex gap-3 items-center">
            <label className="flex items-center gap-1"><input type="radio" checked={resolve.outcome} onChange={() => setResolve({ ...resolve, outcome: true })} /> {t('yes')}</label>
            <label className="flex items-center gap-1"><input type="radio" checked={!resolve.outcome} onChange={() => setResolve({ ...resolve, outcome: false })} /> {t('no')}</label>
          </div>
          <input className={input} placeholder={t('notes')} value={resolve.notes} onChange={(e) => setResolve({ ...resolve, notes: e.target.value })} />
          <div><button className="btn primary text-sm" onClick={async () => { try { await api.resolveQuestion(q.code, resolve.outcome, resolve.notes); setResolve(null); onChanged() } catch (e) { setMsg(String(e)) } }}>{t('resolve')}</button></div>
        </div>
      )}
      <div>
        <div className="flex items-center gap-2 mb-2"><h3 className="font-medium text-sm">{t('indicators')} <span className="muted">{q.indicators.length}</span></h3>
          {!frozen && <button className="btn text-xs ms-auto" onClick={() => setEditing({ code: '', name_en: '', name_ar: null, description: null, lr_present: 2.0, lr_absent: 0.7, polarity: 'emerging', rule: { ...RULE_TEMPLATES.event_count } })}>{t('addIndicator')}</button>}
        </div>
        <table className="grid text-sm">
          <thead><tr><th>{t('code')}</th><th>{t('name')}</th><th>LR+</th><th>LR-</th><th>{t('ruleType')}</th><th></th></tr></thead>
          <tbody>
            {q.indicators.map((i) => (
              <tr key={i.id}>
                <td className="mono text-xs">{i.code}</td><td>{i.name_en}</td><td className="mono">{i.lr_present}</td><td className="mono">{i.lr_absent}</td><td className="mono text-xs">{String(i.rule.type)}</td>
                <td className="text-end whitespace-nowrap">{!frozen && <><button className="btn text-xs me-1" onClick={() => setEditing(i)}>✎</button><button className="btn text-xs" onClick={async () => { if (i.id && confirm(`${t('delete')} ${i.code}?`)) { await api.deleteIndicator(i.id); onChanged() } }}>{t('delete')}</button></>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {editing && (
          <div className="mt-3">
            <IndicatorForm initial={editing} vocab={vocab} onCancel={() => setEditing(null)} onSave={async (ind) => {
              if (ind.id) await api.updateIndicator(ind.id, { name_en: ind.name_en, name_ar: ind.name_ar, description: ind.description, lr_present: ind.lr_present, lr_absent: ind.lr_absent, polarity: ind.polarity, rule: ind.rule })
              else await api.addIndicator(q.code, ind)
              setEditing(null); onChanged()
            }} />
          </div>
        )}
      </div>
    </div>
  )
}

function NewQuestion({ onCreated }: { onCreated: () => void }) {
  const { t } = useLang()
  const [f, setF] = useState({ code: '', title_en: '', title_ar: '', horizon_days: 90, base_rate: 0.2, base_rate_note: '', resolution_criteria: '', hooks: '' })
  const [err, setErr] = useState<string | null>(null)
  return (
    <form className="card p-5 grid gap-3" onSubmit={async (e) => {
      e.preventDefault()
      try {
        await api.createQuestion({ code: f.code, title_en: f.title_en, title_ar: f.title_ar || null, horizon_days: f.horizon_days, base_rate: f.base_rate, base_rate_note: f.base_rate_note || null, resolution_criteria: f.resolution_criteria, resolution_criteria_ar: null, decision_hooks: f.hooks.split('\n').map((s) => s.trim()).filter(Boolean), decision_hooks_ar: null, indicators: [] })
        setF({ ...f, code: '', title_en: '', title_ar: '', resolution_criteria: '', hooks: '' }); setErr(null); onCreated()
      } catch (ex) { setErr(String(ex)) }
    }}>
      <h2 className="font-medium">{t('newQuestion')}</h2>
      <div className="grid md:grid-cols-2 gap-3">
        <Field l={t('code')}><input className={input + ' mono'} placeholder="hormuz_reopen_90" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field l={t('horizonDays')}><input className={input} type="number" value={f.horizon_days} onChange={(e) => setF({ ...f, horizon_days: Number(e.target.value) })} /></Field>
          <Field l={t('baseRate')}><input className={input} type="number" step="0.01" min="0.01" max="0.99" value={f.base_rate} onChange={(e) => setF({ ...f, base_rate: Number(e.target.value) })} /></Field>
        </div>
        <Field l={t('titleEn')}><input className={input} placeholder="Will ... by ...?" value={f.title_en} onChange={(e) => setF({ ...f, title_en: e.target.value })} /></Field>
        <Field l={t('titleAr')}><input className={input} dir="rtl" value={f.title_ar} onChange={(e) => setF({ ...f, title_ar: e.target.value })} /></Field>
        <Field l={t('criteria')}><textarea className={input} rows={3} value={f.resolution_criteria} onChange={(e) => setF({ ...f, resolution_criteria: e.target.value })} /></Field>
        <Field l={t('hooks')}><textarea className={input} rows={3} value={f.hooks} onChange={(e) => setF({ ...f, hooks: e.target.value })} /></Field>
        <Field l={t('baseRateNote')}><input className={input} value={f.base_rate_note} onChange={(e) => setF({ ...f, base_rate_note: e.target.value })} /></Field>
      </div>
      {err && <div className="text-[var(--up)] text-xs">{t('errorPrefix')}: {err}</div>}
      <div><button className="btn primary text-sm" type="submit">{t('create')}</button></div>
    </form>
  )
}

export default function Questions() {
  const { t } = useLang()
  const [qs, setQs] = useState<QuestionDef[] | null>(null)
  const [vocab, setVocab] = useState<Vocab | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  const load = () => api.questions().then((r) => { setQs(r); if (!sel && r.length) setSel(r[0].code) })
  useEffect(() => { load(); api.vocab().then(setVocab) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  if (!qs) return <div className="muted">…</div>
  const current = qs.find((q) => q.code === sel) ?? null
  return (
    <div className="grid md:grid-cols-[260px_1fr] gap-4">
      <div className="card p-3 self-start">
        <div className="flex items-center mb-2"><h2 className="font-medium text-sm">{t('questions')}</h2><button className="btn text-xs ms-auto" onClick={() => setShowNew(!showNew)}>{t('newQuestion')}</button></div>
        {qs.length === 0 && <div className="muted text-sm">{t('noQuestions')}</div>}
        <ul className="text-sm space-y-1">
          {qs.map((q) => (
            <li key={q.code}><button className={`w-full text-start px-2 py-1 rounded ${sel === q.code ? 'bg-[var(--bg)]' : ''}`} onClick={() => { setSel(q.code); setShowNew(false) }}>
              <span className={`tag me-2 ${q.status === 'open' ? 'present' : ''}`}>{q.status === 'open' ? t('open') : t('resolved')}</span><span className="mono text-xs">{q.code}</span>
            </button></li>
          ))}
        </ul>
      </div>
      <div className="grid gap-4">
        {showNew && <NewQuestion onCreated={() => { setShowNew(false); load() }} />}
        {current && <QuestionEditor key={current.code + current.indicators.length + current.status} q={current} vocab={vocab} onChanged={load} />}
      </div>
    </div>
  )
}
