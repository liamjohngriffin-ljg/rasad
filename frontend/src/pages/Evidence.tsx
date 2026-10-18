import { useEffect, useState } from 'react'
import { api, type Vocab } from '../api'
import { useLang } from '../i18n'

const input = 'w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 text-sm'
const label = 'muted text-xs block mb-1'
const today = () => new Date().toISOString().slice(0, 10)

function Field({ l, children }: { l: string; children: React.ReactNode }) {
  return <div><span className={label}>{l}</span>{children}</div>
}

function EventForm({ vocab }: { vocab: Vocab }) {
  const { t, lang } = useLang()
  const [f, setF] = useState({ event_date: today(), event_type: 'maritime_attack', country: 'HORMUZ', location_name: '', severity: 3, description_en: '', description_ar: '', actor: '', target: '', source: '', url: '', grade: 'B2', verified: true, fatalities: '' })
  const [msg, setMsg] = useState<string | null>(null)
  const set = (k: string, v: unknown) => setF({ ...f, [k]: v })
  return (
    <form className="card p-5 grid gap-3" onSubmit={async (e) => {
      e.preventDefault()
      try {
        const r = await api.createEvent({ ...f, actor: f.actor || null, target: f.target || null, location_name: f.location_name || null, description_ar: f.description_ar || null, url: f.url || null, fatalities: f.fatalities === '' ? null : Number(f.fatalities) })
        setMsg(`${t('entered')} #${r.id}`); setF({ ...f, description_en: '', description_ar: '', location_name: '', url: '' })
      } catch (ex) { setMsg(`${t('errorPrefix')}: ${String(ex)}`) }
    }}>
      <h2 className="font-medium">{t('eventEntry')}</h2>
      <div className="grid md:grid-cols-4 gap-3">
        <Field l={t('date')}><input className={input} type="date" value={f.event_date} onChange={(e) => set('event_date', e.target.value)} /></Field>
        <Field l={t('eventType')}><select className={input} value={f.event_type} onChange={(e) => set('event_type', e.target.value)}>{vocab.event_types.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field l={t('country')}><select className={input} value={f.country} onChange={(e) => set('country', e.target.value)}>{vocab.countries.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field l={t('severity')}><input className={input} type="number" min={1} max={5} value={f.severity} onChange={(e) => set('severity', Number(e.target.value))} /></Field>
        <Field l={t('location')}><input className={input} value={f.location_name} onChange={(e) => set('location_name', e.target.value)} /></Field>
        <Field l={t('actor')}><select className={input} value={f.actor} onChange={(e) => set('actor', e.target.value)}><option value="">-</option>{vocab.actors.map((a) => <option key={a.code} value={a.code}>{lang === 'ar' && a.name_ar ? a.name_ar : a.name_en}</option>)}</select></Field>
        <Field l="Target"><select className={input} value={f.target} onChange={(e) => set('target', e.target.value)}><option value="">-</option>{vocab.actors.map((a) => <option key={a.code} value={a.code}>{lang === 'ar' && a.name_ar ? a.name_ar : a.name_en}</option>)}</select></Field>
        <Field l="Fatalities"><input className={input} type="number" min={0} value={f.fatalities} onChange={(e) => set('fatalities', e.target.value)} /></Field>
      </div>
      <Field l={t('description')}><textarea className={input} rows={3} required value={f.description_en} onChange={(e) => set('description_en', e.target.value)} /></Field>
      <Field l={t('description') + ' (ar)'}><textarea className={input} dir="rtl" rows={2} value={f.description_ar} onChange={(e) => set('description_ar', e.target.value)} /></Field>
      <div className="grid md:grid-cols-3 gap-3">
        <Field l={t('source')}><input className={input} required value={f.source} onChange={(e) => set('source', e.target.value)} /></Field>
        <Field l={t('url')}><input className={input} value={f.url} onChange={(e) => set('url', e.target.value)} /></Field>
        <Field l={t('grade')}><input className={input + ' mono'} pattern="[A-F][1-6]" value={f.grade} onChange={(e) => set('grade', e.target.value.toUpperCase())} /></Field>
      </div>
      <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={f.verified} onChange={(e) => set('verified', e.target.checked)} /> {t('markVerified')}</label>
      <div className="flex items-center gap-3"><button className="btn primary text-sm" type="submit">{t('submit')}</button>{msg && <span className="muted text-xs">{msg}</span>}</div>
    </form>
  )
}

function ObservationForm({ vocab }: { vocab: Vocab }) {
  const { t, lang } = useLang()
  const [f, setF] = useState({ actor: vocab.actors[0]?.code ?? '', issue: vocab.issues[0]?.code ?? '', observed_at: today(), track: 'stated', channel: 'statement', cost_class: 'cheap_talk', speaker_level: 'institution', language: 'en', score: 0, source_grade: 'B2', text_excerpt: '', text_excerpt_en: '', source: '', url: '', verified: true })
  const [msg, setMsg] = useState<string | null>(null)
  const set = (k: string, v: unknown) => setF({ ...f, [k]: v })
  return (
    <form className="card p-5 grid gap-3" onSubmit={async (e) => {
      e.preventDefault()
      try { const r = await api.createObservation({ ...f, text_excerpt_en: f.text_excerpt_en || null, url: f.url || null }); setMsg(`${t('entered')} #${r.id}`); setF({ ...f, text_excerpt: '', text_excerpt_en: '', url: '' }) }
      catch (ex) { setMsg(`${t('errorPrefix')}: ${String(ex)}`) }
    }}>
      <h2 className="font-medium">{t('observationEntry')}</h2>
      <div className="grid md:grid-cols-4 gap-3">
        <Field l={t('actor')}><select className={input} value={f.actor} onChange={(e) => set('actor', e.target.value)}>{vocab.actors.map((a) => <option key={a.code} value={a.code}>{lang === 'ar' && a.name_ar ? a.name_ar : a.name_en}</option>)}</select></Field>
        <Field l={t('issue')}><select className={input} value={f.issue} onChange={(e) => set('issue', e.target.value)}>{vocab.issues.map((i) => <option key={i.code} value={i.code}>{lang === 'ar' && i.name_ar ? i.name_ar : i.name_en}</option>)}</select></Field>
        <Field l={t('date')}><input className={input} type="date" value={f.observed_at} onChange={(e) => set('observed_at', e.target.value)} /></Field>
        <Field l={t('track')}><select className={input} value={f.track} onChange={(e) => set('track', e.target.value)}><option value="stated">stated</option><option value="revealed">revealed</option></select></Field>
        <Field l={t('channel')}><select className={input} value={f.channel} onChange={(e) => set('channel', e.target.value)}>{vocab.channels.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field l={t('costClass')}><select className={input} value={f.cost_class} onChange={(e) => set('cost_class', e.target.value)}>{vocab.cost_classes.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field l={t('speakerLevel')}><select className={input} value={f.speaker_level} onChange={(e) => set('speaker_level', e.target.value)}>{vocab.speaker_levels.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field l={`${t('score')} (-1 … +1)`}><input className={input} type="number" step="0.1" min={-1} max={1} value={f.score} onChange={(e) => set('score', Number(e.target.value))} /></Field>
      </div>
      <Field l={t('excerpt')}><textarea className={input} rows={3} required dir="auto" value={f.text_excerpt} onChange={(e) => set('text_excerpt', e.target.value)} /></Field>
      <Field l={t('excerptEn')}><textarea className={input} rows={2} value={f.text_excerpt_en} onChange={(e) => set('text_excerpt_en', e.target.value)} /></Field>
      <div className="grid md:grid-cols-4 gap-3">
        <Field l="Language"><select className={input} value={f.language} onChange={(e) => set('language', e.target.value)}><option value="en">en</option><option value="ar">ar</option><option value="fa">fa</option><option value="he">he</option></select></Field>
        <Field l={t('source')}><input className={input} required value={f.source} onChange={(e) => set('source', e.target.value)} /></Field>
        <Field l={t('url')}><input className={input} value={f.url} onChange={(e) => set('url', e.target.value)} /></Field>
        <Field l={t('grade')}><input className={input + ' mono'} pattern="[A-F][1-6]" value={f.source_grade} onChange={(e) => set('source_grade', e.target.value.toUpperCase())} /></Field>
      </div>
      <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={f.verified} onChange={(e) => set('verified', e.target.checked)} /> {t('markVerified')}</label>
      <div className="flex items-center gap-3"><button className="btn primary text-sm" type="submit">{t('submit')}</button>{msg && <span className="muted text-xs">{msg}</span>}</div>
    </form>
  )
}

function SeriesForm({ vocab }: { vocab: Vocab }) {
  const { t } = useLang()
  const [f, setF] = useState({ series: 'war_risk_premium_hormuz_pct', date: today(), value: 0, unit: 'pct_hull', source: '' })
  const [msg, setMsg] = useState<string | null>(null)
  return (
    <form className="card p-5 grid gap-3" onSubmit={async (e) => { e.preventDefault(); try { await api.addSeriesPoint(f); setMsg(t('entered')) } catch (ex) { setMsg(`${t('errorPrefix')}: ${String(ex)}`) } }}>
      <h2 className="font-medium">{t('seriesEntry')}</h2>
      <div className="grid md:grid-cols-5 gap-3">
        <Field l={t('series')}><input className={input + ' mono'} list="series-list" value={f.series} onChange={(e) => setF({ ...f, series: e.target.value })} /><datalist id="series-list">{vocab.series.map((s) => <option key={s} value={s} />)}</datalist></Field>
        <Field l={t('date')}><input className={input} type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field l={t('value')}><input className={input} type="number" step="any" value={f.value} onChange={(e) => setF({ ...f, value: Number(e.target.value) })} /></Field>
        <Field l={t('unit')}><input className={input} value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></Field>
        <Field l={t('source')}><input className={input} required value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} /></Field>
      </div>
      <div className="flex items-center gap-3"><button className="btn primary text-sm" type="submit">{t('submit')}</button>{msg && <span className="muted text-xs">{msg}</span>}</div>
    </form>
  )
}

export default function Evidence() {
  const [vocab, setVocab] = useState<Vocab | null>(null)
  useEffect(() => { api.vocab().then(setVocab) }, [])
  if (!vocab) return <div className="muted">…</div>
  return (
    <div className="grid gap-4">
      <EventForm vocab={vocab} />
      <ObservationForm vocab={vocab} />
      <SeriesForm vocab={vocab} />
    </div>
  )
}
