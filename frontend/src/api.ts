export type Mover = { indicator: string; name_en: string; name_ar: string | null; state: string; log_lr: number }
export type HistoryPoint = { as_of: string; final_prob: number; machine_prob: number | null; panel_prob: number | null }
export type QuestionSummary = {
  code: string; title_en: string; title_ar: string | null; horizon_days: number; base_rate: number; status: string
  resolves_at: string; decision_hooks: string[]; final_prob: number | null; machine_prob: number | null; panel_prob: number | null
  as_of: string | null; delta_30d: number; history: HistoryPoint[]; movers: Mover[]; synthetic_share: number; commit_hash: string | null
}
export type EventRow = {
  id: number; event_date: string; event_type: string; location_name: string | null; country: string | null; actor: string | null
  target: string | null; fatalities: number | null; severity: number; description_en: string; description_ar: string | null
  provenance: Record<string, string>; verification: string; is_synthetic: boolean
}
export type IndicatorDetail = {
  code: string; name_en: string; name_ar: string | null; description: string | null; polarity: string | null; lr_present: number | null
  lr_absent: number | null; rule: Record<string, unknown> | null; state: string; log_lr: number; evidence: Record<string, unknown>; events: EventRow[]
}
export type QuestionDetail = QuestionSummary & {
  resolution_criteria: string; base_rate_note: string | null; opened_at: string
  machine: { prior: number; probability: number; log_odds: number } | null
  panel: { probability: number; median: number; low: number; high: number; n: number; raw_mean: number } | null
  machine_weight: number | null; indicators: IndicatorDetail[]; history_90: HistoryPoint[]; prev_hash: string | null
}
export type Position = { score: number | null; effective_n: number; n: number; spread: number | null; last_observed: string | null; top_refs: number[] }
export type IssueEntry = {
  actor: string; issue: string; as_of: string; stated: Position; revealed: Position; divergence: number | null
  change_points: { stated: { date: string; direction: string; magnitude: number }[]; revealed: { date: string; direction: string; magnitude: number }[] }
  silence: { recent_count: number; baseline_count: number; expected_in_window: number; ratio: number | null; flagged: boolean }
  series: { stated: [string, number | null][]; revealed: [string, number | null][] }
  issue_name_en: string; issue_name_ar: string | null; low_label_en: string; high_label_en: string
}
export type ActorBook = { actor: { code: string; name_en: string; name_ar: string | null; kind: string }; as_of: string; issues: IssueEntry[] }
export type Observation = {
  id: number; observed_at: string; track: string; channel: string; cost_class: string; speaker_level: string; language: string; score: number
  source_grade: string; model_confidence: number; text_excerpt: string; text_excerpt_en: string | null; provenance: Record<string, string>
  verification: string; is_synthetic: boolean; actor?: string; issue?: string
}
export type Status = {
  version: string; events: number; observations: number; series_points: number; forecasts: number; open_questions: number
  pending_verification: number; synthetic_rows: number; last_commit: string | null
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json() as Promise<T>
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json() as Promise<T>
}

export const api = {
  status: () => get<Status>('/api/status'),
  board: (asOf?: string) => get<{ as_of: string; questions: QuestionSummary[] }>(`/api/board${asOf ? `?as_of=${asOf}` : ''}`),
  question: (code: string, asOf?: string) => get<QuestionDetail>(`/api/questions/${code}${asOf ? `?as_of=${asOf}` : ''}`),
  events: (days = 120) => get<EventRow[]>(`/api/events?days=${days}`),
  series: (name: string, days = 365) => get<{ series: string; unit: string | null; points: { date: string; value: number; is_synthetic: boolean }[] }>(`/api/series/${name}?days=${days}`),
  actors: () => get<{ code: string; name_en: string; name_ar: string | null; kind: string; observations: number }[]>('/api/actors'),
  actorBook: (code: string, asOf?: string) => get<ActorBook>(`/api/actors/${code}/book${asOf ? `?as_of=${asOf}` : ''}`),
  observations: (actor: string, issue: string) => get<Observation[]>(`/api/actors/${actor}/issues/${issue}/observations`),
  calibration: () => get<CalibrationData>('/api/calibration'),
  brief: (code: string, lang: 'en' | 'ar', asOf?: string) => get<{ content_md: string; generator: string; generated_at: string }>(`/api/briefs/${code}?lang=${lang}${asOf ? `&as_of=${asOf}` : ''}`),
  queue: () => get<{ events: EventRow[]; observations: Observation[] }>('/api/verification/queue'),
  verify: (kind: 'event' | 'observation', id: number, decision: 'verified' | 'rejected', by: string, score?: number) => post(`/api/verification/${kind}/${id}`, { decision, by, score }),
  sources: () => get<{ code: string; name: string; tier: number; kind: string; url: string | null; language: string; licence_note: string | null; reuse_ok: boolean }[]>('/api/sources'),
  tasking: () => get<{ id: number; text: string; requested_by: string | null; status: string; created_at: string }[]>('/api/tasking'),
  createTasking: (text: string, requested_by: string) => post('/api/tasking', { text, requested_by }),
}

export type CalibrationData = {
  chain: { length: number; verified: boolean; first_bad_index: number | null; head: string | null }
  all: ScoreSummary; by_horizon: Record<string, ScoreSummary>
  resolved: { code: string; title_en: string; title_ar: string | null; resolved_at: string; outcome: boolean; notes: string | null; base_rate: number; forecasts: { as_of: string; final_prob: number; brier: number }[] }[]
}
export type ScoreSummary = { n: number; mean_brier: number | null; baseline_brier: number | null; skill: number | null; calibration: { bin: string; n: number; mean_forecast: number | null; observed_rate: number | null }[] }
