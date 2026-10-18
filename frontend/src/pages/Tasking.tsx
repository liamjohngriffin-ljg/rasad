import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type QuestionDef, type TaskingRow } from '../api'
import { atLeast, useAuth } from '../auth'
import { Markdown } from '../components'
import { useLang } from '../i18n'

const input = 'w-full bg-transparent border border-[var(--line)] rounded-md px-3 py-2 text-sm'

function Row({ t0, questions, canEdit, reload }: { t0: TaskingRow; questions: QuestionDef[]; canEdit: boolean; reload: () => void }) {
  const { t } = useLang()
  const [frame, setFrame] = useState(t0.question ?? '')
  const [answer, setAnswer] = useState(t0.answer_md ?? '')
  const [err, setErr] = useState<string | null>(null)
  const tagCls = t0.status === 'answered' ? 'present' : t0.status === 'framed' ? '' : 'unknown'
  return (
    <div className="card p-4 grid gap-2 text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`tag ${tagCls}`}>{t0.status === 'open' ? t('open') : t0.status === 'framed' ? t('framed') : t('answered')}</span>
        <span className="mono muted text-xs">{t0.created_at.slice(0, 10)}</span>
        {t0.requested_by && <span className="muted text-xs">{t('requestedBy')} {t0.requested_by}</span>}
        {t0.question && <Link className="accent text-xs ms-auto mono" to={`/q/${t0.question}`}>{t0.question}</Link>}
      </div>
      <div>{t0.text}</div>
      {t0.answer_md && <div className="border-t border-[var(--line)] pt-2"><Markdown md={t0.answer_md} /></div>}
      {canEdit && t0.status !== 'answered' && (
        <div className="grid gap-2 border-t border-[var(--line)] pt-2">
          <div className="flex gap-2 items-center">
            <select className="bg-transparent border border-[var(--line)] rounded-md px-2 py-1 text-sm" value={frame} onChange={(e) => setFrame(e.target.value)}>
              <option value="">{t('frame')}…</option>
              {questions.map((q) => <option key={q.code} value={q.code}>{q.code}</option>)}
            </select>
            <button className="btn text-xs" disabled={!frame} onClick={async () => { try { await api.frameTasking(t0.id, frame); reload() } catch (e) { setErr(String(e)) } }}>{t('frame')}</button>
            <Link className="btn text-xs" to="/questions">{t('newQuestion')}</Link>
          </div>
          <textarea className={input} rows={4} placeholder={t('answerMd')} value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <div className="flex gap-2 items-center"><button className="btn primary text-xs" disabled={answer.trim().length < 10} onClick={async () => { try { await api.answerTasking(t0.id, answer); reload() } catch (e) { setErr(String(e)) } }}>{t('answer')}</button>{err && <span className="text-[var(--up)] text-xs">{err}</span>}</div>
        </div>
      )}
    </div>
  )
}

export default function Tasking() {
  const { t } = useLang()
  const { me } = useAuth()
  const [rows, setRows] = useState<TaskingRow[] | null>(null)
  const [questions, setQuestions] = useState<QuestionDef[]>([])
  const [text, setText] = useState('')
  const load = () => api.tasking().then(setRows)
  useEffect(() => { load(); api.questions().then((q) => setQuestions(q.filter((x) => x.status === 'open'))).catch(() => setQuestions([])) }, [])
  if (!rows) return <div className="muted">…</div>
  const canEdit = atLeast(me?.role, 'analyst')
  return (
    <div className="grid gap-4">
      <form className="card p-4 flex gap-2" onSubmit={async (e) => { e.preventDefault(); if (!text.trim()) return; await api.createTasking(text.trim(), me?.display_name ?? ''); setText(''); load() }}>
        <input className={input} placeholder={t('taskingPlaceholder')} value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn primary text-sm whitespace-nowrap" type="submit">{t('newTasking')}</button>
      </form>
      {rows.length === 0 && <div className="muted text-sm">{t('queueEmpty')}</div>}
      {rows.map((r) => <Row key={r.id + r.status + (r.answer_md?.length ?? 0)} t0={r} questions={questions} canEdit={canEdit} reload={load} />)}
    </div>
  )
}
