import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, type DocRow, type SearchResult } from '../api'
import { DemoTag } from '../components'
import { useLang } from '../i18n'

export function DocCard({ d, onOpen }: { d: DocRow; onOpen: (id: number) => void }) {
  const { t } = useLang()
  return (
    <div className="border-b border-[var(--line)] py-2 text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="tag">{d.source}</span>
        <span className="mono muted text-xs">{(d.published_at ?? d.fetched_at).slice(0, 10)}</span>
        {d.score != null && <span className="muted text-xs">{t('routedBy')} {d.score}</span>}
        <span className="font-medium" dir="auto">{d.title ?? d.external_id}</span>
        <span className="ms-auto flex gap-2">
          {d.url && <a className="accent text-xs" href={d.url} target="_blank" rel="noreferrer">↗</a>}
          <button className="btn text-xs" onClick={() => onOpen(d.id)}>{t('readDoc')}</button>
        </span>
      </div>
      <div className="muted text-xs mt-1" dir="auto">{d.snippet}</div>
    </div>
  )
}

export function DocViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useLang()
  const [doc, setDoc] = useState<Awaited<ReturnType<typeof api.document>> | null>(null)
  useEffect(() => { api.document(id).then(setDoc) }, [id])
  return (
    <div className="fixed inset-0 bg-black/60 z-20 flex items-start justify-center p-4 overflow-auto" onClick={onClose}>
      <div className="card p-5 max-w-3xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-3">
          <span className="tag">{doc?.source}</span>
          <span className="font-medium" dir="auto">{doc?.title ?? doc?.external_id}</span>
          {doc?.url && <a className="accent text-xs ms-2" href={doc.url} target="_blank" rel="noreferrer">↗</a>}
          <button className="btn text-xs ms-auto" onClick={onClose}>{t('close')}</button>
        </div>
        {doc && (doc.events.length > 0 || doc.observations.length > 0) && (
          <div className="text-xs muted mb-3">
            {doc.events.map((e) => <div key={'e' + e.id}>event #{e.id} {e.event_type} {e.event_date} · {e.verification}</div>)}
            {doc.observations.map((o) => <div key={'o' + o.id}>observation #{o.id} {o.actor}/{o.issue} {o.score} · {o.verification}</div>)}
          </div>
        )}
        <pre className="whitespace-pre-wrap text-sm font-sans max-h-[70vh] overflow-auto" dir="auto">{doc ? doc.text : '…'}</pre>
      </div>
    </div>
  )
}

export default function Search() {
  const { t, lang } = useLang()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [res, setRes] = useState<SearchResult | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const run = async (term: string) => { if (term.trim().length < 2) return; setParams({ q: term }); setRes(await api.search(term.trim(), 730)) }
  useEffect(() => { const p = params.get('q'); if (p) run(p) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="grid gap-4">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run(q) }}>
        <input className="flex-1 bg-transparent border border-[var(--line)] rounded-md px-3 py-2" placeholder={t('searchPlaceholder')} value={q} onChange={(e) => setQ(e.target.value)} dir="auto" />
        <button className="btn primary" type="submit">{t('search')}</button>
      </form>
      {res && (
        <div className="grid gap-4">
          {res.events.length + res.observations.length + res.documents.length === 0 && <div className="muted">{t('noResults')}</div>}
          {res.events.length > 0 && (
            <div className="card p-4"><h2 className="font-medium mb-2">{t('evidence')} <span className="muted text-sm">{res.events.length}</span></h2>
              {res.events.map((e) => (
                <div key={e.id} className="border-b border-[var(--line)] py-2 text-sm">
                  <div><span className="mono muted me-2">{e.event_date}</span><span className="tag me-1">{e.event_type}</span>{e.country && <span className="tag me-1">{e.country}</span>}<DemoTag show={e.is_synthetic} />{e.verification !== 'verified' && <span className="tag ms-1 unknown">{e.verification}</span>}</div>
                  <div className="text-xs mt-1">{lang === 'ar' && e.description_ar ? e.description_ar : e.description_en}</div>
                  <div className="muted text-[11px]">{e.provenance?.source} {e.provenance?.url && <a className="accent" href={e.provenance.url} target="_blank" rel="noreferrer">↗</a>}</div>
                </div>
              ))}
            </div>
          )}
          {res.observations.length > 0 && (
            <div className="card p-4"><h2 className="font-medium mb-2">{t('observations')} <span className="muted text-sm">{res.observations.length}</span></h2>
              {res.observations.map((o) => (
                <div key={o.id} className="border-b border-[var(--line)] py-2 text-sm">
                  <div><span className="mono muted me-2">{o.observed_at}</span><span className="tag me-1">{o.actor}</span><span className="tag me-1">{o.issue}</span><span className="tag me-1">{o.track}</span><span className="mono text-xs">{o.score > 0 ? '+' : ''}{o.score}</span></div>
                  <div className="text-xs mt-1" dir="auto">{o.text_excerpt_en ?? o.text_excerpt}</div>
                </div>
              ))}
            </div>
          )}
          {res.documents.length > 0 && (
            <div className="card p-4"><h2 className="font-medium mb-2">{t('documents')} <span className="muted text-sm">{res.documents.length}</span></h2>
              {res.documents.map((d) => <DocCard key={d.id} d={d} onOpen={setOpen} />)}
            </div>
          )}
        </div>
      )}
      {open != null && <DocViewer id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
