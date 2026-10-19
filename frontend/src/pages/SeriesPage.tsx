import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type EventRow } from '../api'
import { useLang } from '../i18n'

// A line chart of one series with reported events overlaid as ticks, so an analyst can see the
// transit collapse against the attack tempo on one axis. Plain SVG, no dependency, works offline.
type Pt = { date: string; value: number; is_synthetic: boolean }
const W = 1000, H = 360, PAD = { l: 48, r: 16, t: 16, b: 36 }
const EVENT_COLOURS: Record<string, string> = { maritime_attack: '#d06a5c', missile_strike: '#e0483a', drone_strike: '#e8894a', seizure: '#c9a0dc', mine_warning: '#f2d16b', maritime_harassment: '#d9a441', closure: '#ffffff', ceasefire: '#5fa97a' }

function Chart({ points, events, days }: { points: Pt[]; events: EventRow[]; days: number }) {
  const { lang } = useLang()
  const [hover, setHover] = useState<Pt | null>(null)
  if (points.length < 2) return <div className="muted text-sm p-4">…</div>
  const t0 = new Date(points[0].date).getTime(), t1 = new Date(points[points.length - 1].date).getTime()
  const vals = points.map((p) => p.value)
  const vmax = Math.max(...vals) * 1.08 || 1, vmin = Math.min(0, ...vals)
  const x = (d: string) => PAD.l + ((new Date(d).getTime() - t0) / Math.max(1, t1 - t0)) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - (v - vmin) / (vmax - vmin || 1)) * (H - PAD.t - PAD.b)
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  // 7-day rolling mean
  const roll: [string, number][] = points.map((p, i) => { const win = points.slice(Math.max(0, i - 6), i + 1); return [p.date, win.reduce((a, b) => a + b.value, 0) / win.length] })
  const rpath = roll.map(([d, v], i) => `${i ? 'L' : 'M'}${x(d).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const ticks = 5
  const months: string[] = []
  for (let t = t0; t <= t1; t += 86400000 * (days > 400 ? 90 : days > 120 ? 30 : 7)) months.push(new Date(t).toISOString().slice(0, 10))
  const evs = events.filter((e) => { const tt = new Date(e.event_date).getTime(); return tt >= t0 && tt <= t1 })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" onMouseLeave={() => setHover(null)}>
      {Array.from({ length: ticks + 1 }).map((_, i) => { const v = vmin + ((vmax - vmin) * i) / ticks; return <g key={i}><line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth="0.6" /><text x={PAD.l - 6} y={y(v) + 4} fill="var(--ink-2)" fontSize="11" textAnchor="end">{v.toFixed(v < 10 ? 1 : 0)}</text></g> })}
      {months.map((m) => <text key={m} x={x(m)} y={H - 10} fill="var(--ink-2)" fontSize="11" textAnchor="middle">{m.slice(0, 7)}</text>)}
      {evs.map((e) => <line key={e.id} x1={x(e.event_date)} x2={x(e.event_date)} y1={PAD.t} y2={H - PAD.b} stroke={EVENT_COLOURS[e.event_type] ?? '#888'} strokeWidth="1" opacity="0.45"><title>{e.event_date} {e.event_type} {e.country ?? ''}: {(lang === 'ar' && e.description_ar ? e.description_ar : e.description_en).slice(0, 120)}</title></line>)}
      <path d={path} fill="none" stroke="var(--ink-2)" strokeWidth="1" opacity="0.7" />
      <path d={rpath} fill="none" stroke="var(--accent)" strokeWidth="2" />
      {points.map((p) => <circle key={p.date} cx={x(p.date)} cy={y(p.value)} r={hover?.date === p.date ? 4 : 2.2} fill={p.is_synthetic ? 'none' : 'var(--ink)'} stroke="var(--ink)" strokeWidth="0.8" onMouseEnter={() => setHover(p)} />)}
      {hover && <text x={Math.min(x(hover.date), W - 160)} y={PAD.t + 12} fill="var(--ink)" fontSize="12" className="mono">{hover.date}: {hover.value}{hover.is_synthetic ? ' (demo)' : ''}</text>}
    </svg>
  )
}

export default function SeriesPage() {
  const { t } = useLang()
  const [params, setParams] = useSearchParams()
  const [index, setIndex] = useState<Awaited<ReturnType<typeof api.seriesIndex>>>([])
  const [name, setName] = useState(params.get('s') || 'hormuz_transits')
  const [days, setDays] = useState(Number(params.get('days') || 365))
  const [data, setData] = useState<{ series: string; unit: string | null; points: Pt[] } | null>(null)
  const [events, setEvents] = useState<EventRow[]>([])
  const [types, setTypes] = useState<Set<string>>(new Set(['maritime_attack', 'seizure', 'mine_warning', 'closure', 'ceasefire']))
  useEffect(() => { api.seriesIndex().then(setIndex) }, [])
  useEffect(() => { setParams({ s: name, days: String(days) }); api.series(name, days).then(setData); api.events(days).then(setEvents) }, [name, days]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = useMemo(() => events.filter((e) => types.has(e.event_type) && e.verification !== 'rejected' && !e.is_synthetic), [events, types])
  const meta = index.find((r) => r.series === name)
  const allTypes = Array.from(new Set(events.map((e) => e.event_type))).filter((x) => !['designation', 'insurer_listing'].includes(x)).sort()
  const toggle = (ty: string) => { const n = new Set(types); if (n.has(ty)) n.delete(ty); else n.add(ty); setTypes(n) }
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap text-sm">
        <h1 className="text-xl font-semibold me-2">{t('series')}</h1>
        <select className="bg-transparent border border-[var(--line)] rounded-md px-2 py-1 mono text-sm" value={name} onChange={(e) => setName(e.target.value)}>
          {index.map((r) => <option key={r.series} value={r.series}>{r.series} ({r.points})</option>)}
        </select>
        {[90, 180, 365, 730, 1100].map((n) => <button key={n} className={`btn text-xs ${days === n ? 'primary' : ''}`} onClick={() => setDays(n)}>{n} {t('days')}</button>)}
        {meta && <span className="ms-auto muted text-xs">{meta.unit} · {t('latest')} {meta.latest_value} ({meta.last}) · {meta.latest_source}</span>}
      </div>
      <div className="flex gap-1 flex-wrap">
        {allTypes.map((ty) => <button key={ty} className={`tag ${types.has(ty) ? '' : 'opacity-40'}`} style={{ borderColor: EVENT_COLOURS[ty] ?? 'var(--line)', color: EVENT_COLOURS[ty] ?? 'var(--ink-2)' }} onClick={() => toggle(ty)}>{ty}</button>)}
      </div>
      <div className="card p-3">{data ? <Chart points={data.points} events={shown} days={days} /> : <div className="muted">…</div>}</div>
      <div className="muted text-[11px]">{t('seriesNote')}</div>
    </div>
  )
}
