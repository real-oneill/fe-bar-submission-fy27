import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
// The worker is bundled by Vite and served by the app itself (no external hosts).
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { Citation, LineItem, Preview, Sheet } from './api'
import { colLetter, lineFieldLabel, parseCellRef, targetLabel, targetOf, type TargetKey } from './citations'
import EmailView from './EmailView'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

/** ai_parse_document boxes are in pixels of the page rendered at 200 DPI; PDF user space is 72 per inch. */
const PX200_TO_PT = 72 / 200
const MAX_PAGES = 60

interface Cited { c: Citation; t: TargetKey }

export interface DocPaneProps {
  preview: Preview | null
  previewError: string | null
  citations: Citation[]
  lines: LineItem[]
  headerOrderIdx: number
  /** selected field / line, and a counter bumped on every click (re-scroll + flash even when unchanged) */
  active: TargetKey | null
  nonce: number
  hover: TargetKey | null
  onHover: (keys: TargetKey[] | null) => void
  onPick: (key: TargetKey) => void
  fallbackText: string
}

type Tip = { x: number; y: number; body: ReactNode } | null

/** Scroll `el` to the middle of the scroll container `box` (not the window). */
function scrollIntoBox(box: HTMLElement | null, el: Element | null, smooth = true) {
  if (!box || !el) return
  const b = box.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  const top = box.scrollTop + (r.top - b.top) - box.clientHeight / 2 + r.height / 2
  const left = r.width > box.clientWidth ? box.scrollLeft + (r.left - b.left) - 16
    : box.scrollLeft + (r.left - b.left) - box.clientWidth / 2 + r.width / 2
  box.scrollTo({ top: Math.max(0, top), left: Math.max(0, left), behavior: smooth ? 'smooth' : 'auto' })
}

function state(targets: TargetKey[], active: TargetKey | null, hover: TargetKey | null) {
  const on = active != null && targets.includes(active)
  return { on, muted: active != null && !on, hover: hover != null && targets.includes(hover) }
}

/** Tooltip body: which form fields a mark backs, with the values read there. */
function tipBody(cited: Cited[], lines: LineItem[]): ReactNode {
  const by = new Map<TargetKey, Citation[]>()
  for (const x of cited) by.set(x.t, [...(by.get(x.t) ?? []), x.c])
  const keys = [...by.keys()]
  const shown = keys.slice(0, 6)
  return (
    <>
      <div className="tip-title">{keys.length === 1 ? `Supports ${targetLabel(keys[0], lines)}` : `Supports ${keys.length} fields`}</div>
      {shown.map((k) => {
        const cs = by.get(k)!
        const vals = k.startsWith('h:')
          ? [...new Set(cs.filter((c) => c.field !== 'po_number_label').map((c) => c.value).filter(Boolean))].join(', ')
          : [...new Map(cs.filter((c) => ['quantity', 'unit_price', 'uom'].includes(c.field) && c.value)
              .map((c) => [c.field, `${lineFieldLabel(c.field)} ${fmtVal(c.value)}`])).values()].join(' · ')
        return <div key={k} className="tip-row">{keys.length > 1 && <b>{targetLabel(k, lines)}</b>}{vals && <span>{vals}</span>}</div>
      })}
      {keys.length > shown.length && <div className="tip-row muted">and {keys.length - shown.length} more</div>}
    </>
  )
}

const fmtVal = (v: string | null) => (v && /^-?\d+\.0$/.test(v) ? v.slice(0, -2) : v ?? '')

function useTip() {
  const [tip, setTip] = useState<Tip>(null)
  const show = (e: React.MouseEvent, body: ReactNode) => setTip({ x: e.clientX, y: e.clientY, body })
  const el = tip && (
    <div className="cite-tip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 300), top: tip.y + 16 }}>
      {tip.body}
    </div>
  )
  return { el, show, hide: () => setTip(null) }
}

export default function DocPane(p: DocPaneProps) {
  const cited = useMemo(() => p.citations
    .map((c) => ({ c, t: targetOf(c, p.headerOrderIdx) }))
    .filter((x): x is Cited => x.t != null), [p.citations, p.headerOrderIdx])
  const [tab, setTab] = useState<'doc' | 'email'>('doc')
  const emailUrl = p.preview?.email_url

  if (p.previewError) {
    return <div className="doc-empty">This document can't be shown here ({p.previewError}).
      {p.fallbackText && <pre className="doc-text">{p.fallbackText}</pre>}</div>
  }
  if (!p.preview) return <div className="doc-empty">Opening the document…</div>
  const doc = <DocView {...p} preview={p.preview} cited={cited} />
  if (!emailUrl) return doc
  // the order came from an attached email: the document it was read from, or the email itself
  return (
    <>
      <div className="doc-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'doc'} className={tab === 'doc' ? 'on' : ''} onClick={() => setTab('doc')}>Document</button>
        <button role="tab" aria-selected={tab === 'email'} className={tab === 'email' ? 'on' : ''} onClick={() => setTab('email')}>Email</button>
      </div>
      {tab === 'doc' ? doc : <EmailView emailUrl={emailUrl} renderDoc={(pv) => <DocView {...BLANK} preview={pv} cited={[]} />} />}
    </>
  )
}

/** Props for a document without citations (an attachment opened from an email). */
const BLANK: Omit<DocPaneProps, 'preview'> = {
  previewError: null, citations: [], lines: [], headerOrderIdx: 0, active: null, nonce: 0, hover: null,
  onHover: () => {}, onPick: () => {}, fallbackText: '',
}

function DocView(p: DocPaneProps & { preview: Preview; cited: Cited[] }) {
  const pv = p.preview
  if (pv.kind === 'pdf' && pv.url) return <PdfView {...p} url={pv.url} cited={p.cited} />
  if (pv.kind === 'sheet' && pv.sheets) return <SheetView {...p} sheets={pv.sheets} cited={p.cited} />
  if (pv.kind === 'image' && pv.url) {
    return <div className="doc-scroll"><img className="doc-image" src={pv.url} alt={pv.name ?? 'attachment'} /></div>
  }
  if (pv.kind === 'file') {
    return <div className="doc-empty">This attachment can't be shown here{pv.note ? ` (${pv.note})` : ''}.
      {pv.url && <> <a href={pv.url}>Download {pv.name ?? 'the file'}</a></>}</div>
  }
  return <TextView {...p} text={pv.text ?? p.fallbackText} cited={p.cited} />
}

// =============================================================================================== PDF
interface BoxMark {
  id: string; page: number; x1: number; y1: number; x2: number; y2: number
  kind: 'box' | 'table' | 'band'; cited: Cited[]; targets: TargetKey[]
}

function pdfMarks(cited: Cited[]): BoxMark[] {
  const m = new Map<string, BoxMark>()
  const add = (id: string, base: Omit<BoxMark, 'id' | 'cited' | 'targets'>, x: Cited) => {
    const cur = m.get(id) ?? { id, ...base, cited: [], targets: [] }
    cur.cited.push(x)
    if (!cur.targets.includes(x.t)) cur.targets.push(x.t)
    m.set(id, cur)
  }
  for (const x of cited) {
    const c = x.c
    if (c.source_kind !== 'layout' || c.page_index == null || c.x1 == null || c.y1 == null || c.x2 == null || c.y2 == null) continue
    const box = `${c.page_index}:${c.x1}:${c.y1}:${c.x2}:${c.y2}`
    const base = { page: c.page_index, x1: c.x1, y1: c.y1, x2: c.x2, y2: c.y2 }
    const n = c.table_row_count ?? 0
    if (c.element_type === 'table' && c.table_row_index != null && n > 0) {
      // ai_extract cites the whole table; the row is approximated (contract): centre y1 + h·(i+0.5)/n, height h/n
      add(`t:${box}`, { ...base, kind: 'table' }, x)
      const h = (c.y2 - c.y1) / n
      const cy = c.y1 + (c.y2 - c.y1) * (c.table_row_index + 0.5) / n
      add(`b:${box}:${c.table_row_index}`, { ...base, y1: cy - h / 2, y2: cy + h / 2, kind: 'band' }, x)
    } else {
      add(`x:${box}`, { ...base, kind: 'box' }, x)
    }
  }
  return [...m.values()]
}

function PdfView(p: DocPaneProps & { url: string; cited: Cited[] }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [sizes, setSizes] = useState<{ w: number; h: number }[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [width, setWidth] = useState(0)
  const marks = useMemo(() => pdfMarks(p.cited), [p.cited])
  const snap = useRowSnap(doc, marks, sizes.length)
  const tip = useTip()

  useEffect(() => {
    let dead = false
    const task = pdfjsLib.getDocument({ url: p.url, withCredentials: true, isEvalSupported: false })
    task.promise.then(async (d) => {
      const n = Math.min(d.numPages, MAX_PAGES)
      const s: { w: number; h: number }[] = []
      for (let i = 1; i <= n; i++) {
        const vp = (await d.getPage(i)).getViewport({ scale: 1 })   // PDF points, rotation applied
        s.push({ w: vp.width, h: vp.height })
      }
      if (!dead) { setDoc(d); setSizes(s) }
    }).catch((e) => { if (!dead) setErr(String(e?.message ?? e)) })
    return () => { dead = true; task.destroy() }
  }, [p.url])

  useLayoutEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(Math.max(320, el.clientWidth - 28)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // click-to-locate: scroll to the selected field's box (the row band for a line), then flash it
  useEffect(() => {
    if (!p.active || !boxRef.current || !sizes.length || !width) return
    const el = boxRef.current.querySelector('.pdf-mark.on:not(.table)') ?? boxRef.current.querySelector('.pdf-mark.on')
    scrollIntoBox(boxRef.current, el)
  }, [p.active, p.nonce, sizes.length, width])

  if (err) return <div className="doc-empty">The PDF could not be displayed ({err}).</div>
  return (
    <div className="doc-scroll pdf-scroll" ref={boxRef}>
      {!doc && <div className="doc-empty">Opening the PDF…</div>}
      {doc && width > 0 && sizes.map((sz, i) => {
        const scale = width / sz.w                                  // CSS px per PDF point
        const k = PX200_TO_PT * scale                               // CSS px per 200-DPI pixel
        return (
          <div key={i} className="pdf-page" style={{ width, height: sz.h * scale }}>
            <PdfCanvas doc={doc} num={i + 1} scale={scale} />
            {marks.filter((m) => m.page === i).map((m0) => {
              const sn = snap[m0.id]
              const m = sn ? { ...m0, y1: sn.y1, y2: sn.y2 } : m0
              const s = state(m.targets, p.active, p.hover)
              const cls = ['pdf-mark', m.kind, s.on && 'on', s.muted && 'muted', s.hover && 'hover'].filter(Boolean).join(' ')
              return (
                <div
                  key={s.on ? `${m.id}-${p.nonce}` : m.id}
                  className={cls}
                  style={{ left: m.x1 * k, top: m.y1 * k, width: (m.x2 - m.x1) * k, height: (m.y2 - m.y1) * k }}
                  onMouseEnter={m.kind === 'table' ? undefined : (e) => { p.onHover(m.targets); tip.show(e, tipBody(m.cited, p.lines)) }}
                  onMouseMove={m.kind === 'table' ? undefined : (e) => tip.show(e, tipBody(m.cited, p.lines))}
                  onMouseLeave={m.kind === 'table' ? undefined : () => { p.onHover(null); tip.hide() }}
                  onClick={m.kind === 'table' ? undefined : () => p.onPick(m.targets.includes(p.active ?? '') ? p.active! : m.targets[0])}
                >
                  {m.kind === 'band' && s.on && <span className="approx-tag">{sn ? 'row found by its product code' : 'approximate row'}</span>}
                </div>
              )
            })}
            {sizes.length > 1 && <div className="pdf-page-no">Page {i + 1} of {doc.numPages}</div>}
          </div>
        )
      })}
      {doc && marks.some((m) => m.kind === 'band') && (
        <div className="doc-note pdf-legend">
          Dashed outline: the table a line was read from. The line’s row inside it is located by its product code, or
          approximated from its position in the table.
        </div>
      )}
      {doc && doc.numPages > MAX_PAGES && (
        <div className="doc-note">Showing the first {MAX_PAGES} of {doc.numPages} pages.</div>
      )}
      {tip.el}
    </div>
  )
}

/** ai_extract cites a whole table for each line; the contract's band (row i of n, uniform rows) is only approximate
 * because header rows are taller. Where the page's text layer has the line's product code inside the table box, centre
 * the band on that text instead (nearest occurrence to the approximate row). Units: 200-DPI pixels, like the marks. */
function useRowSnap(doc: PDFDocumentProxy | null, marks: BoxMark[], nPages: number) {
  const [snap, setSnap] = useState<Record<string, { y1: number; y2: number }>>({})
  useEffect(() => {
    if (!doc || !nPages) return
    let dead = false
    const K = 200 / 72
    const norm = (v: string) => v.toUpperCase().replace(/\s+/g, '')
    ;(async () => {
      const out: Record<string, { y1: number; y2: number }> = {}
      const pages = [...new Set(marks.filter((m) => m.kind === 'band').map((m) => m.page))].filter((pi) => pi < nPages)
      for (const pi of pages) {
        const page = await doc.getPage(pi + 1)
        const vp = page.getViewport({ scale: 1 })
        const tc = await page.getTextContent()
        const items = tc.items.flatMap((it) => {
          if (!('str' in it) || !it.str.trim()) return []
          const [x, y] = vp.convertToViewportPoint(it.transform[4], it.transform[5])   // baseline, top-left origin
          const h = (Math.hypot(it.transform[2], it.transform[3]) || it.height || 8) * K
          return [{ toks: [norm(it.str), ...it.str.split(/\s+/).map(norm)], x: x * K, y: y * K, h }]
        })
        for (const m of marks) {
          if (m.kind !== 'band' || m.page !== pi) continue
          const t = m.cited[0].c
          const code = norm(m.cited.find((x) => x.c.field === 'material_or_sku' && x.c.value)?.c.value ?? '')
          if (code.length < 3) continue
          const cy = (m.y1 + m.y2) / 2
          let best: { y: number; h: number } | null = null
          for (const it of items) {
            if (!it.toks.includes(code)) continue
            if (it.x < t.x1! - 8 || it.x > t.x2! + 8 || it.y < t.y1! - 4 || it.y - it.h > t.y2! + 4) continue
            const c = it.y - it.h * 0.35
            if (!best || Math.abs(c - cy) < Math.abs(best.y - best.h * 0.35 - cy)) best = it
          }
          if (best) {
            const c = best.y - best.h * 0.35
            out[m.id] = { y1: c - best.h * 0.8, y2: c + best.h * 0.8 }
          }
        }
      }
      if (!dead) setSnap(out)
    })().catch(() => {})
    return () => { dead = true }
  }, [doc, marks, nPages])
  return snap
}

function PdfCanvas({ doc, num, scale }: { doc: PDFDocumentProxy; num: number; scale: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let task: RenderTask | null = null
    let dead = false
    doc.getPage(num).then((page) => {
      if (dead || !ref.current) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2.5)
      const vp = page.getViewport({ scale: scale * dpr })
      const cv = ref.current
      cv.width = Math.floor(vp.width)
      cv.height = Math.floor(vp.height)
      task = page.render({ canvasContext: cv.getContext('2d')!, viewport: vp })
      task.promise.catch(() => {})
    })
    return () => { dead = true; task?.cancel() }
  }, [doc, num, scale])
  return <canvas ref={ref} className="pdf-canvas" />
}

// =============================================================================================== sheets
function SheetView(p: DocPaneProps & { sheets: Sheet[]; cited: Cited[]; }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const [i, setI] = useState(0)
  const tip = useTip()
  const sheetPos = (c: Citation) => {
    let k = p.sheets.findIndex((s) => s.index === c.sheet_index)
    if (k < 0 && c.sheet_name) k = p.sheets.findIndex((s) => s.name === c.sheet_name)
    return k
  }
  // cell / row -> what it backs
  const { cells, rows } = useMemo(() => {
    const cells = new Map<string, Cited[]>()
    const rows = new Map<string, Cited[]>()
    for (const x of p.cited) {
      if (x.c.source_kind !== 'sheet' || x.c.row_number == null) continue
      const s = sheetPos(x.c)
      if (s < 0) continue
      const rk = `${s}:${x.c.row_number}`
      rows.set(rk, [...(rows.get(rk) ?? []), x])
      const ref = parseCellRef(x.c.cell_ref)
      if (ref) {
        const ck = `${s}:${ref.row}:${ref.col}`
        cells.set(ck, [...(cells.get(ck) ?? []), x])
      }
    }
    return { cells, rows }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.cited, p.sheets])

  // click-to-locate: switch to the sheet of the selected field/line, then scroll to its cell (or row)
  useEffect(() => {
    if (!p.active) return
    const x = p.cited.find((y) => y.t === p.active && y.c.source_kind === 'sheet' && (p.active!.startsWith('h:') ? y.c.cell_ref : true))
      ?? p.cited.find((y) => y.t === p.active && y.c.source_kind === 'sheet')
    if (!x) return
    const s = sheetPos(x.c)
    if (s >= 0 && s !== i) setI(s)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.active, p.nonce])
  useEffect(() => {
    if (!p.active || !boxRef.current) return
    const el = boxRef.current.querySelector('td.cited.on') ?? boxRef.current.querySelector('tr.on')
    const t = window.setTimeout(() => scrollIntoBox(boxRef.current, el), 30)
    return () => window.clearTimeout(t)
  }, [p.active, p.nonce, i])

  const sheet = p.sheets[i]
  if (!sheet) return <div className="doc-empty">This workbook has no visible sheets.</div>
  const hasCites = rows.size > 0
  const citedIn = (k: number) => [...rows.keys()].some((r) => r.startsWith(`${k}:`))
  return (
    <div className="sheet">
      {p.sheets.length > 1 && (
        <div className="sheet-tabs" role="tablist">
          {p.sheets.map((s, k) => (
            <button key={k} role="tab" aria-selected={k === i} className={k === i ? 'active' : ''} onClick={() => setI(k)}>
              {s.name}{citedIn(k) && <span className="tab-dot" aria-label="has cited cells" />}
            </button>
          ))}
        </div>
      )}
      {sheet.rows.length === 0 ? <div className="doc-empty">This sheet is empty.</div> : (
        <div className="grid-scroll doc-scroll" ref={boxRef} tabIndex={0} aria-label={`Sheet ${sheet.name}`}>
          <table className="grid">
            <thead>
              <tr>
                <th className="corner" />
                {Array.from({ length: sheet.n_cols }, (_, c) => <th key={c}>{colLetter(c)}</th>)}
              </tr>
            </thead>
            <tbody>
              {sheet.rows.map((row) => {
                const rc = rows.get(`${i}:${row.r}`) ?? []
                const rt = [...new Set(rc.map((x) => x.t))]
                const rs = state(rt.filter((t) => !t.startsWith('h:')), p.active, p.hover)
                const cls = [rc.some((x) => !x.t.startsWith('h:')) && 'cited-row', rs.on && 'on', rs.hover && 'hover'].filter(Boolean).join(' ')
                return (
                  <tr key={row.r} className={cls}>
                    <th>{row.r}</th>
                    {row.cells.map((v, k) => {
                      const cc = cells.get(`${i}:${row.r}:${k}`)
                      if (!cc) return <td key={k} title={v.length > 40 ? v : undefined}>{v}</td>
                      const ts = [...new Set(cc.map((x) => x.t))]
                      const s = state(ts, p.active, p.hover)
                      const ccls = ['cited', s.on && 'on', s.muted && 'muted', s.hover && 'hover'].filter(Boolean).join(' ')
                      return (
                        <td
                          key={s.on ? `${k}-${p.nonce}` : k}
                          className={ccls}
                          onMouseEnter={(e) => { p.onHover(ts); tip.show(e, tipBody(cc, p.lines)) }}
                          onMouseMove={(e) => tip.show(e, tipBody(cc, p.lines))}
                          onMouseLeave={() => { p.onHover(null); tip.hide() }}
                          onClick={() => p.onPick(ts.includes(p.active ?? '') ? p.active! : ts[0])}
                        >{v}</td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="doc-foot">
        {hasCites && <span><span className="swatch cell" aria-hidden /> cells the order was read from</span>}
        {p.preview?.source === 'text' && <span>Values as they were read from the file{p.preview.note ? ` (the original file couldn't be opened: ${p.preview.note})` : ''}.</span>}
        {sheet.truncated && <span>Showing the first {sheet.rows.length} rows and {sheet.n_cols} columns.</span>}
      </div>
      {tip.el}
    </div>
  )
}

// =============================================================================================== text
function TextView(p: DocPaneProps & { text: string; cited: Cited[] }) {
  const boxRef = useRef<HTMLDivElement>(null)
  const tip = useTip()
  const text = p.text || ''
  // split the text at every span boundary; each piece knows which spans cover it
  const pieces = useMemo(() => {
    const spans = p.cited.filter((x) => x.c.source_kind === 'text' && x.c.char_start != null && x.c.char_stop != null
      && x.c.char_start < text.length && x.c.char_stop! > x.c.char_start!)
    if (!spans.length) return [{ a: 0, b: text.length, cov: [] as Cited[] }]
    const cut = new Set([0, text.length])
    for (const x of spans) { cut.add(x.c.char_start!); cut.add(Math.min(x.c.char_stop!, text.length)) }
    const pts = [...cut].sort((a, b) => a - b)
    return pts.slice(0, -1).map((a, k) => ({
      a, b: pts[k + 1], cov: spans.filter((x) => x.c.char_start! <= a && Math.min(x.c.char_stop!, text.length) >= pts[k + 1]),
    }))
  }, [p.cited, text])

  useEffect(() => {
    if (!p.active || !boxRef.current) return
    scrollIntoBox(boxRef.current, boxRef.current.querySelector('mark.on'))
  }, [p.active, p.nonce])

  const anyCite = pieces.some((x) => x.cov.length)
  return (
    <>
      <div className="doc-scroll text-scroll" ref={boxRef}>
        <pre className="doc-text">{pieces.map((x, k) => {
          const s = text.slice(x.a, x.b)
          if (!x.cov.length) return <span key={k}>{s}</span>
          const ts = [...new Set(x.cov.map((y) => y.t))]
          const st = state(ts, p.active, p.hover)
          return (
            <mark
              key={st.on ? `${k}-${p.nonce}` : k}
              className={['cited', st.on && 'on', st.muted && 'muted', st.hover && 'hover'].filter(Boolean).join(' ')}
              onMouseEnter={(e) => { p.onHover(ts); tip.show(e, tipBody(x.cov, p.lines)) }}
              onMouseMove={(e) => tip.show(e, tipBody(x.cov, p.lines))}
              onMouseLeave={() => { p.onHover(null); tip.hide() }}
              onClick={() => p.onPick(ts.includes(p.active ?? '') ? p.active! : ts[0])}
            >{s}</mark>
          )
        })}{!text && <span className="muted">No text available for this document.</span>}</pre>
      </div>
      {(anyCite || p.preview?.truncated) && (
        <div className="doc-foot">
          {anyCite && <span><span className="swatch cell" aria-hidden /> text the order was read from</span>}
          {p.preview?.truncated && <span>Showing the beginning of a long document.</span>}
        </div>
      )}
      {tip.el}
    </>
  )
}
