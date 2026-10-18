import type { HistoryPoint } from './api'
import { useLang, pct, yardstick } from './i18n'

export function Sparkline({ points, width = 160, height = 40, accent = false }: { points: (number | null)[]; width?: number; height?: number; accent?: boolean }) {
  const vals = points.map((v) => (v == null ? null : v))
  const present = vals.filter((v): v is number => v != null)
  if (present.length < 2) return <svg width={width} height={height} />
  const min = Math.min(...present, 0), max = Math.max(...present, 1)
  const x = (i: number) => (i / (vals.length - 1)) * (width - 4) + 2
  const y = (v: number) => height - 2 - ((v - min) / (max - min || 1)) * (height - 4)
  let d = ''
  vals.forEach((v, i) => { if (v != null) d += (d ? ' L' : 'M') + `${x(i).toFixed(1)} ${y(v).toFixed(1)}` })
  const last = present[present.length - 1]
  return (
    <svg width={width} height={height} aria-hidden>
      <path d={d} fill="none" stroke={accent ? 'var(--accent)' : 'var(--ink-2)'} strokeWidth="1.5" />
      <circle cx={x(vals.length - 1)} cy={y(last)} r="2.5" fill={accent ? 'var(--accent)' : 'var(--ink)'} />
    </svg>
  )
}

export function HistorySpark({ history }: { history: HistoryPoint[] }) {
  return <Sparkline points={history.map((h) => h.final_prob)} accent />
}

export function Prob({ p, big = false }: { p: number | null; big?: boolean }) {
  const { lang } = useLang()
  if (p == null) return <span className="muted">n/a</span>
  return (
    <span>
      <span className={`mono ${big ? 'text-4xl font-semibold' : 'text-xl font-semibold'}`}>{pct(p)}</span>
      <span className="muted text-sm ms-2">{yardstick(p, lang)}</span>
    </span>
  )
}

export function Delta({ d }: { d: number }) {
  const cls = d > 0.5 ? 'text-[var(--up)]' : d < -0.5 ? 'text-[var(--down)]' : 'muted'
  return <span className={`mono ${cls}`}>{d > 0 ? '+' : ''}{d.toFixed(0)}</span>
}

export function StateTag({ state }: { state: string }) {
  const { t } = useLang()
  const k = state as 'present' | 'absent' | 'unknown'
  return <span className={`tag ${state}`}>{t(k) ?? state}</span>
}

export function DemoTag({ show }: { show: boolean }) {
  return show ? <span className="tag demo ms-2">demo</span> : null
}

export function Markdown({ md }: { md: string }) {
  // Minimal renderer for the brief: headings, bullets, emphasis, paragraphs. No HTML passthrough.
  const lines = md.split('\n')
  const out: React.ReactNode[] = []
  let list: string[] = []
  const flush = () => { if (list.length) { out.push(<ul key={out.length}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>); list = [] } }
  // Emphasis only when the whole line is wrapped in underscores (identifiers such as
  // series names contain underscores and must render as written).
  const inline = (s: string) => {
    const t = s.trim()
    return t.length > 2 && t.startsWith('_') && t.endsWith('_') ? <em>{t.slice(1, -1)}</em> : <span>{s}</span>
  }
  lines.forEach((ln, i) => {
    if (ln.startsWith('# ')) { flush(); out.push(<h1 key={i}>{ln.slice(2)}</h1>) }
    else if (ln.startsWith('## ')) { flush(); out.push(<h2 key={i}>{ln.slice(3)}</h2>) }
    else if (ln.startsWith('    - ')) { list.push('    ' + ln.slice(6)) }
    else if (ln.startsWith('- ')) { list.push(ln.slice(2)) }
    else if (ln.trim() === '') { flush() }
    else { flush(); out.push(<p key={i}>{inline(ln)}</p>) }
  })
  flush()
  return <div className="prose">{out}</div>
}
