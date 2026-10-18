import { useEffect, useMemo, useState } from 'react'
import { api, type EventRow } from '../api'
import land from '../gulf_land.json'
import { useLang } from '../i18n'

// Equirectangular plot of the Gulf, Red Sea and Gulf of Aden with land from Natural Earth (public
// domain), so the page works in a sovereign deployment with no map tiles. Events without a
// position are placed at the centroid of their area with a small deterministic offset and drawn
// hollow, so the picture never pretends to know more than the ledger does.
const BBOX = (land as { bbox: number[] }).bbox
const RINGS = (land as { rings: number[][][] }).rings
const W = 1100, H = 780
const px = (lon: number) => ((lon - BBOX[0]) / (BBOX[2] - BBOX[0])) * W
const py = (lat: number) => H - ((lat - BBOX[1]) / (BBOX[3] - BBOX[1])) * H

const CENTROIDS: Record<string, [number, number]> = {
  HORMUZ: [26.4, 56.4], ARABIAN_GULF: [26.5, 51.8], RED_SEA: [16.5, 41.2], GULF_OF_ADEN: [12.6, 47.5], OM: [23.0, 58.8], AE: [25.0, 55.2], QA: [25.3, 51.5],
  SA: [25.0, 47.0], KW: [29.2, 48.0], BH: [26.1, 50.6], IQ: [30.4, 47.9], IR: [27.2, 56.3], YE: [14.0, 45.5], IL: [31.5, 34.9], SO: [8.0, 50.5],
}
const COLOURS: Record<string, string> = {
  maritime_attack: '#d06a5c', missile_strike: '#e0483a', drone_strike: '#e8894a', seizure: '#c9a0dc', maritime_harassment: '#d9a441', mine_warning: '#f2d16b',
  gnss_interference: '#7aa6d9', intercept: '#5fa97a', closure: '#ffffff', designation: '#8d8d8d', insurer_listing: '#8d8d8d', ceasefire: '#5fa97a',
}
const hash = (n: number) => { let x = Math.sin(n * 9301 + 49297) * 233280; return x - Math.floor(x) }

export default function MapPage() {
  const { t, lang } = useLang()
  const [events, setEvents] = useState<EventRow[]>([])
  const [days, setDays] = useState(60)
  const [types, setTypes] = useState<Set<string>>(new Set())
  const [sel, setSel] = useState<EventRow | null>(null)
  const [showPending, setShowPending] = useState(true)
  useEffect(() => { api.events(days).then(setEvents) }, [days])
  const placed = useMemo(() => events.flatMap((e) => {
    if (e.event_type === 'designation' || e.event_type === 'insurer_listing') return []
    if (!showPending && e.verification !== 'verified') return []
    if (types.size && !types.has(e.event_type)) return []
    let lat = e.lat, lon = e.lon, approx = false
    if (lat == null || lon == null) {
      const c = CENTROIDS[e.country ?? '']
      if (!c) return []
      lat = c[0] + (hash(e.id) - 0.5) * 1.2; lon = c[1] + (hash(e.id + 7) - 0.5) * 1.6; approx = true
    }
    if (lat < BBOX[1] || lat > BBOX[3] || lon < BBOX[0] || lon > BBOX[2]) return []
    return [{ e, x: px(lon), y: py(lat), approx }]
  }), [events, types, showPending])
  const allTypes = Array.from(new Set(events.map((e) => e.event_type))).filter((x) => x !== 'designation' && x !== 'insurer_listing').sort()
  const toggle = (ty: string) => { const n = new Set(types); if (n.has(ty)) n.delete(ty); else n.add(ty); setTypes(n) }
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap text-sm">
        <h1 className="text-xl font-semibold me-2">{t('map')}</h1>
        {[30, 60, 120, 365].map((n) => <button key={n} className={`btn text-xs ${days === n ? 'primary' : ''}`} onClick={() => setDays(n)}>{n} {t('days')}</button>)}
        <label className="ms-2 flex items-center gap-1 text-xs"><input type="checkbox" checked={showPending} onChange={(e) => setShowPending(e.target.checked)} /> {t('showPending')}</label>
        <span className="ms-auto muted text-xs">{placed.length} / {events.length}</span>
      </div>
      <div className="flex gap-1 flex-wrap">
        {allTypes.map((ty) => (
          <button key={ty} className={`tag ${types.size === 0 || types.has(ty) ? '' : 'opacity-40'}`} style={{ borderColor: COLOURS[ty] ?? 'var(--line)', color: COLOURS[ty] ?? 'var(--ink-2)' }} onClick={() => toggle(ty)}>{ty}</button>
        ))}
        {types.size > 0 && <button className="tag" onClick={() => setTypes(new Set())}>{t('filterAll')}</button>}
      </div>
      <div className="grid lg:grid-cols-[1fr_320px] gap-3">
        <div className="card p-2 overflow-hidden">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" style={{ background: '#0c1d2b' }}>
            {RINGS.map((r, i) => <path key={i} d={r.map((p, j) => `${j ? 'L' : 'M'}${px(p[0]).toFixed(1)} ${py(p[1]).toFixed(1)}`).join(' ') + 'Z'} fill="#222b35" stroke="#3a4654" strokeWidth="0.8" />)}
            {[['Strait of Hormuz', 26.6, 56.3], ['Bab el-Mandeb', 12.6, 43.3], ['Gulf of Aden', 12.0, 48.5], ['Red Sea', 20.0, 38.5], ['Arabian Gulf', 27.0, 51.0], ['Gulf of Oman', 24.3, 58.6]].map(([n, la, lo]) => (
              <text key={String(n)} x={px(Number(lo))} y={py(Number(la))} fill="#5e6b78" fontSize="13" textAnchor="middle">{String(n)}</text>
            ))}
            {placed.map(({ e, x, y, approx }) => (
              <g key={e.id} onClick={() => setSel(e)} style={{ cursor: 'pointer' }}>
                <circle cx={x} cy={y} r={3 + e.severity * 1.3} fill={approx ? 'none' : (COLOURS[e.event_type] ?? '#aaa')} stroke={COLOURS[e.event_type] ?? '#aaa'} strokeWidth={e.verification === 'verified' ? 1.5 : 1} strokeDasharray={e.verification === 'verified' ? undefined : '2 2'} opacity={sel && sel.id !== e.id ? 0.45 : 0.9}>
                  <title>{e.event_date} {e.event_type} {e.country ?? ''}{approx ? ' (approximate position)' : ''}</title>
                </circle>
              </g>
            ))}
          </svg>
          <div className="muted text-[11px] px-2 pb-1">{t('mapNote')}</div>
        </div>
        <div className="card p-4 text-sm self-start">
          {sel ? (
            <div>
              <div className="flex items-center gap-2 flex-wrap mb-2"><span className="mono muted">{sel.event_date}</span><span className="tag">{sel.event_type}</span>{sel.country && <span className="tag">{sel.country}</span>}<span className="tag">{'!'.repeat(sel.severity)}</span>{sel.verification !== 'verified' && <span className="tag unknown">{sel.verification}</span>}</div>
              {sel.location_name && <div className="muted text-xs mb-1">{sel.location_name}{sel.lat != null && <span className="mono ms-2">{sel.lat.toFixed(2)}, {sel.lon?.toFixed(2)}</span>}</div>}
              <div>{lang === 'ar' && sel.description_ar ? sel.description_ar : sel.description_en}</div>
              <div className="muted text-xs mt-2">{sel.provenance?.source} {sel.provenance?.url && <a className="accent" href={sel.provenance.url} target="_blank" rel="noreferrer">↗</a>}</div>
            </div>
          ) : <div className="muted">{t('mapHint')}</div>}
        </div>
      </div>
    </div>
  )
}
