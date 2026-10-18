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
  pending_verification: number; synthetic_rows: number; last_commit: string | null; open_alerts: number; marking: string
  org_name: string; product_name: string; licence: Licence
}
export type Licence = { mode: 'licensed' | 'grace' | 'evaluation'; licensee: string; seats: number; features: string[]; expires: string | null; licence_id: string | null; reason: string | null; seats_used?: number; evaluation_seats?: number }
export type ApiKeyRow = { id: number; name: string; prefix: string; role: string; created_by: string | null; created_at: string; last_used_at: string | null; revoked_at: string | null; token?: string }
export type Settings = Record<string, string>
export type AlertRow = { id: number; created_at: string; kind: string; severity: number; question_code: string | null; title_en: string; title_ar: string | null; detail: Record<string, unknown>; acknowledged_by: string | null; acknowledged_at: string | null }
export type Changes = {
  since: string
  moves: { code: string; title_en: string; title_ar: string | null; from: number | null; to: number; delta_points: number; as_of: string; flips: { indicator: string; from: string | null; to: string }[] }[]
  events: { id: number; event_date: string; event_type: string; country: string | null; severity: number; description_en: string; description_ar: string | null; verification: string; source: string | null }[]
  new_observations: number; new_documents: number; alerts: AlertRow[]
}
export type DocRow = { id: number; source: string; source_name: string; external_id: string; title: string | null; url: string | null; language: string; published_at: string | null; fetched_at: string; status: string; meta: Record<string, unknown>; snippet: string; score?: number }
export type SearchResult = { q: string; events: EventRow[]; observations: Observation[]; documents: DocRow[] }

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json() as Promise<T>
}
async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method, headers: { 'Content-Type': 'application/json', 'X-Rasad-Client': 'web' }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!r.ok) {
    let detail = `${r.status}`
    try { const j = await r.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* no body */ }
    throw new Error(detail)
  }
  return r.json() as Promise<T>
}
const post = <T,>(path: string, body: unknown) => send<T>('POST', path, body)
const put = <T,>(path: string, body: unknown) => send<T>('PUT', path, body)
const del = <T,>(path: string) => send<T>('DELETE', path)

export type IndicatorDef = { id?: number; code: string; name_en: string; name_ar: string | null; description: string | null; lr_present: number; lr_absent: number; polarity: string; rule: Record<string, unknown> }
export type QuestionDef = {
  code: string; title_en: string; title_ar: string | null; horizon_days: number; resolution_criteria: string; decision_hooks: string[]; base_rate: number
  base_rate_note: string | null; status: string; opened_at: string; resolves_at: string; order: number; indicators: IndicatorDef[]
}
export type Vocab = {
  rule_types: string[]; event_types: string[]; cost_classes: string[]; speaker_levels: string[]; channels: string[]; ops: string[]; series: string[]
  actors: { code: string; name_en: string; name_ar: string | null }[]; issues: { code: string; name_en: string; name_ar: string | null }[]; countries: string[]
}
export type PanelView = {
  question: string; latest: { forecaster: string; code: string; as_of: string; probability: number; rationale: string | null; skill_weight: number }[]
  mine: { as_of: string; probability: number; rationale: string | null } | null; history: { forecaster: string; as_of: string; probability: number }[]
}
export type TaskingRow = { id: number; text: string; requested_by: string | null; status: string; created_at: string; answer_md: string | null; answered_at: string | null; question: string | null }

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
  sources: () => get<{ code: string; name: string; tier: number; kind: string; url: string | null; language: string; licence_note: string | null; reuse_ok: boolean; documents: number; last_fetched: string | null; last_published: string | null }[]>('/api/sources'),
  seriesIndex: () => get<{ series: string; points: number; first: string; last: string; synthetic: number; unit: string | null; latest_value: number | null; latest_source: string | null; days_stale: number }[]>('/api/series'),
  verifyBulk: (kind: 'event' | 'observation', ids: number[], decision: 'verified' | 'rejected') => post<{ n: number }>('/api/verification/bulk', { kind, ids, decision }),
  tasking: () => get<TaskingRow[]>('/api/tasking'),
  createTasking: (text: string, requested_by: string) => post('/api/tasking', { text, requested_by }),
  frameTasking: (id: number, question_code: string) => post(`/api/tasking/${id}/frame`, { question_code }),
  answerTasking: (id: number, answer_md: string) => post(`/api/tasking/${id}/answer`, { answer_md }),
  vocab: () => get<Vocab>('/api/reference/vocab'),
  questions: () => get<QuestionDef[]>('/api/questions'),
  questionDef: (code: string) => get<QuestionDef>(`/api/questions/${code}/definition`),
  createQuestion: (q: Omit<QuestionDef, 'status' | 'opened_at' | 'resolves_at' | 'order'> & { opened_at?: string }) => post<QuestionDef>('/api/questions', q),
  updateQuestion: (code: string, patch: Partial<QuestionDef>) => put<QuestionDef>(`/api/questions/${code}`, patch),
  resolveQuestion: (code: string, outcome: boolean, notes: string, resolved_at?: string) => post(`/api/questions/${code}/resolve`, { outcome, notes, resolved_at }),
  addIndicator: (code: string, ind: IndicatorDef) => post<IndicatorDef>(`/api/questions/${code}/indicators`, ind),
  updateIndicator: (id: number, patch: Partial<IndicatorDef>) => put<IndicatorDef>(`/api/indicators/${id}`, patch),
  deleteIndicator: (id: number) => del(`/api/indicators/${id}`),
  previewRule: (rule: Record<string, unknown>, as_of?: string) => post<{ as_of: string; state: string; evidence: Record<string, unknown>; history: { as_of: string; state: string }[] }>('/api/indicators/preview', { rule, as_of }),
  panel: (code: string) => get<PanelView>(`/api/questions/${code}/panel`),
  submitPanel: (code: string, probability: number, rationale: string) => post(`/api/questions/${code}/panel`, { probability, rationale }),
  createEvent: (e: Record<string, unknown>) => post<{ id: number }>('/api/events', e),
  createObservation: (o: Record<string, unknown>) => post<{ id: number }>('/api/observations', o),
  addSeriesPoint: (p: { series: string; date: string; value: number; unit: string; source: string }) => post('/api/series', p),
  alerts: (all = false) => get<AlertRow[]>(`/api/alerts?all=${all}`),
  ackAlert: (id: number) => post<AlertRow>(`/api/alerts/${id}/ack`, {}),
  ackAll: () => post<{ acknowledged: number }>('/api/alerts/ack-all', {}),
  scanAlerts: () => post<{ raised: number }>('/api/alerts/scan', {}),
  changes: (since?: string) => get<Changes>(`/api/changes${since ? `?since=${since}` : ''}`),
  search: (q: string, days = 365, kind = 'all') => get<SearchResult>(`/api/search?q=${encodeURIComponent(q)}&days=${days}&kind=${kind}`),
  document: (id: number) => get<DocRow & { text: string; events: { id: number; event_type: string; event_date: string; verification: string; description_en: string }[]; observations: { id: number; actor: string; issue: string; score: number; verification: string }[] }>(`/api/documents/${id}`),
  questionDocuments: (code: string, days = 14) => get<{ question: string; terms: string[]; documents: DocRow[] }>(`/api/questions/${code}/documents?days=${days}`),
  licence: () => get<Licence>('/api/licence'),
  installLicence: (document: unknown) => post<Licence>('/api/licence', { document }),
  keys: () => get<ApiKeyRow[]>('/api/keys'),
  createKey: (name: string, role: string) => post<ApiKeyRow>('/api/keys', { name, role }),
  revokeKey: (id: number) => del<ApiKeyRow>(`/api/keys/${id}`),
  settings: () => get<Settings>('/api/settings'),
  saveSettings: (values: Settings) => put<Settings>('/api/settings', { values }),
}

export type CalibrationData = {
  chain: { length: number; verified: boolean; first_bad_index: number | null; head: string | null }
  all: ScoreSummary; by_horizon: Record<string, ScoreSummary>
  resolved: { code: string; title_en: string; title_ar: string | null; resolved_at: string; outcome: boolean; notes: string | null; base_rate: number; forecasts: { as_of: string; final_prob: number; brier: number }[] }[]
}
export type ScoreSummary = { n: number; mean_brier: number | null; baseline_brier: number | null; skill: number | null; calibration: { bin: string; n: number; mean_forecast: number | null; observed_rate: number | null }[] }
