import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, type OrderDetail, type LineItem, type CitationData, type Preview } from '../api'
import { StatusPill, Toast } from '../components'
import DocPane from '../DocPane'
import { extractorNote, headerKey, lineKey, pct, targetOf, type TargetKey } from '../citations'

const HEADER_FIELDS: { key: keyof OrderDetail; label: string }[] = [
  { key: 'po_number', label: 'Customer PO' },
  { key: 'customer_name', label: 'Customer Name' },
  { key: 'customer_number', label: 'Customer Number' },
  { key: 'order_date', label: 'Order Date' },
  { key: 'currency', label: 'Currency' },
  { key: 'ship_to', label: 'Ship To' },
]

const LOW = 0.85

export default function Detail() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const [order, setOrder] = useState<OrderDetail | null>(null)
  const [header, setHeader] = useState<Record<string, string>>({})
  const [lines, setLines] = useState<LineItem[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<{ msg: string; err?: boolean } | null>(null)
  const [cites, setCites] = useState<CitationData | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  // click-to-locate: the selected field/line (+ a counter so a repeated click re-scrolls and flashes)
  const [active, setActive] = useState<TargetKey | null>(null)
  const [nonce, setNonce] = useState(0)
  // hover in the document -> the field(s)/line(s) that box backs
  const [docHover, setDocHover] = useState<TargetKey[] | null>(null)
  const formRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setPreview(null); setPreviewError(null); setCites(null); setActive(null)
    api.getOrder(id).then((o) => {
      setOrder(o)
      const h: Record<string, string> = {}
      HEADER_FIELDS.forEach((f) => (h[f.key as string] = (o[f.key] as string) || ''))
      setHeader(h)
      setLines(o.line_items || [])
    }).catch((e) => flash(String(e), true)).finally(() => setLoading(false))
    // the document and the citations load independently: an order without either still reviews fine
    api.getPreview(id).then(setPreview).catch((e) => setPreviewError(String(e).replace(/^Error: /, '').slice(0, 160)))
    api.getCitations(id).then(setCites).catch(() => setCites(null))
  }, [id])

  function flash(msg: string, err = false) {
    setToast({ msg, err })
    setTimeout(() => setToast(null), 2600)
  }

  function updateLine(i: number, key: keyof LineItem, val: string) {
    setLines((prev) => prev.map((l, idx) => (idx === i ? { ...l, [key]: key === 'quantity' || key === 'unit_price' ? (val === '' ? null : Number(val)) : val } : l)))
  }

  async function save() {
    if (!id) return
    setBusy(true)
    try {
      await api.updateOrder(id, { ...header, line_items: lines })
      flash('Corrections saved')
    } catch (e) { flash(String(e), true) } finally { setBusy(false) }
  }

  async function approve() {
    if (!id) return
    setBusy(true)
    try {
      await api.updateOrder(id, { ...header, line_items: lines })
      const res = await api.approveOrder(id)
      flash(`Approved & sent to SAP as ${res.idoc_type}`)
      setTimeout(() => nav('/outbound'), 1200)
    } catch (e) { flash(String(e), true) } finally { setBusy(false) }
  }

  async function flag() {
    if (!id) return
    setBusy(true)
    try { await api.flagManual(id); flash('Flagged for manual entry'); setOrder((o) => o && { ...o, status: 'needs_manual' }) }
    catch (e) { flash(String(e), true) } finally { setBusy(false) }
  }

  const citations = useMemo(() => cites?.citations ?? [], [cites])
  // header fields belong to the order of the review row's lines (a row can merge several extracted orders)
  const headerOrderIdx = useMemo(() => {
    const idx = (order?.line_items ?? []).map((l) => l.order_idx).filter((v): v is number => v != null)
    if (idx.length) return Math.min(...idx)
    const h = citations.filter((c) => c.li_idx == null).map((c) => c.order_idx ?? 0)
    return h.length ? Math.min(...h) : 0
  }, [order, citations])
  const citedTargets = useMemo(() => new Set(citations.map((c) => targetOf(c, headerOrderIdx)).filter(Boolean)),
    [citations, headerOrderIdx])

  function select(key: TargetKey) {
    setActive(key)
    setNonce((n) => n + 1)
  }
  /** a box/cell/snippet clicked in the document: select what it backs and bring it into view in the form */
  function pick(key: TargetKey) {
    select(key)
    const el = formRef.current?.querySelector(`[data-key="${CSS.escape(key)}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  /** What the reviewer still has to fill in or look at, each with the field it points to (click = go there). */
  const todo = useMemo(() => {
    const out: { key: string; label: string; why: string }[] = []
    const h = (k: string, label: string, why: string) => out.push({ key: headerKey(k), label, why })
    if (!(header.po_number ?? '').trim()) h('po_number', 'Customer PO', 'not found in the document')
    if (!(header.customer_name ?? '').trim() && !(header.customer_number ?? '').trim()) h('customer_name', 'Customer Name', 'no customer identified')
    else if (!(header.customer_number ?? '').trim()) h('customer_number', 'Customer Number', 'customer not matched to a SAP number')
    if (!(header.order_date ?? '').trim()) h('order_date', 'Order Date', 'not found')
    if (!(header.ship_to ?? '').trim()) h('ship_to', 'Ship To', 'not found')
    lines.forEach((l, i) => {
      const k = lineKey(l, i), n = `Line ${i + 1}`
      if (!(l.material_or_sku ?? '').toString().trim()) out.push({ key: k, label: n, why: 'no material / SKU' })
      else if (l.sku_resolved === false) out.push({ key: k, label: `${n} · ${l.material_or_sku}`, why: 'material not found in SAP' })
      if (!l.quantity) out.push({ key: k, label: n, why: 'no quantity' })
      else if ((l.line_confidence ?? 1) < LOW) out.push({ key: k, label: n, why: 'read with low confidence' })
    })
    return out
  }, [header, lines])
  function goTo(key: TargetKey) {
    const el = formRef.current?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    el?.querySelector<HTMLInputElement>('input')?.focus()
  }

  if (loading) return <div className="container"><div className="loading">Loading…</div></div>
  if (!order) return <div className="container"><div className="loading">Not found.</div></div>

  const fieldConf = { ...(order.field_confidence ?? {}), ...(cites?.field_confidence ?? {}) }
  const note = extractorNote(cites?.extractor ?? order.extractor, cites?.fallback_reason ?? order.fallback_reason)
  const hasCites = citedTargets.size > 0
  const linked = (k: TargetKey) => docHover?.includes(k) ?? false

  return (
    <div className="container wide">
      <div className="detail-header">
        <a className="back" onClick={() => nav('/')} style={{ cursor: 'pointer' }}>← Queue</a>
        <h1>{order.doc_name}</h1>
        <StatusPill status={order.status} />
      </div>

      {(order.related_orders?.length ?? 0) > 0 && (
        <div className="related-banner">
          Same email also produced:{' '}
          {order.related_orders!.map((r, i) => (
            <a key={r.order_id} onClick={() => nav(`/orders/${encodeURIComponent(r.order_id)}`)} style={{ cursor: 'pointer' }}>
              {i > 0 && ', '}{r.doc_name}
            </a>
          ))}
          . The email text may add to or change what the attachment says — check both.
        </div>
      )}

      {order.review_reasons && (
        <div className="exception-banner">⚠ {order.review_reasons}</div>
      )}

      <div className="two-pane review">
        {/* LEFT: source document */}
        <div className="pane doc-pane">
          <div className="pane-head">
            <span>Source Document <span className="muted-normal">{order.orig_format}</span></span>
            <a className="open-original" href={`/api/orders/${encodeURIComponent(order.order_id)}/original`} target="_blank"
               rel="noreferrer" title="Open the file exactly as received (Excel, PDF, …) in a new tab">Open original ↗</a>
          </div>
          {note && <div className="doc-hint doc-note">{note}</div>}
          <div className="doc-hint">
            {hasCites ? 'Click a field or a line to see where it was read. Hover a highlight to see what it supports.'
              : 'Locations in the document aren’t available for this order.'}
          </div>
          <div className="doc-body">
            <DocPane
              preview={preview}
              previewError={previewError}
              citations={citations}
              lines={lines}
              headerOrderIdx={headerOrderIdx}
              active={active}
              nonce={nonce}
              hover={docHover?.[0] ?? null}
              onHover={setDocHover}
              onPick={pick}
              fallbackText={order.parsed_content || ''}
            />
          </div>
        </div>

        {/* RIGHT: editable extraction */}
        <div className="pane form-pane">
          <div className="pane-head">Extracted Fields
            {order.overall_confidence != null && (
              <span className={`conf-chip ${order.overall_confidence < LOW ? 'low' : ''}`} style={{ marginLeft: 8 }}
                    title="One score for the order: each value checked against the source document">
                Confidence {pct(order.overall_confidence)}
              </span>
            )}
          </div>
          <div className="pane-body form-body" ref={formRef}>
            {todo.length > 0 && (
              <div className="todo" role="list" aria-label="To complete">
                <b>To complete ({todo.length})</b>
                {todo.map((t, i) => (
                  <button key={i} type="button" role="listitem" onClick={() => goTo(t.key)}>
                    {t.label} <span className="why">— {t.why}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="field-grid">
              {HEADER_FIELDS.map((f) => {
                const k = headerKey(f.key as string)
                const conf = fieldConf[f.key as string]
                const low = conf != null ? conf < LOW
                  : (f.key === 'customer_name' || f.key === 'po_number') && (order.header_confidence ?? 1) < LOW
                const cited = citedTargets.has(k)
                const cls = ['field', low && 'low', cited && 'cited', active === k && 'selected', linked(k) && 'linked'].filter(Boolean).join(' ')
                return (
                  <div key={f.key as string} className={cls} data-key={k}
                       onClick={cited ? () => select(k) : undefined} onFocusCapture={cited ? () => { if (active !== k) select(k) } : undefined}>
                    <label>
                      {f.label}
                      {cited && <span className="locate" title="Show in the document" aria-hidden>◎</span>}
                      {low && <span className="conf-chip low" title="Read with low confidence — check it against the document">check</span>}
                    </label>
                    <input
                      value={header[f.key as string] ?? ''}
                      onChange={(e) => setHeader((h) => ({ ...h, [f.key]: e.target.value }))}
                    />
                  </div>
                )
              })}
            </div>

            <div className="lines-table">
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>Line Items ({lines.length})</div>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>#</th>
                    <th>Material / SKU</th><th>Description</th>
                    <th style={{ width: 70 }}>Qty</th><th style={{ width: 90 }}>Unit Price</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.length === 0 && (
                    <tr><td colSpan={5} style={{ color: 'var(--muted)', padding: 12 }}>No line items extracted.</td></tr>
                  )}
                  {lines.map((l, i) => {
                    const low = (l.line_confidence ?? 1) < LOW
                    const k = lineKey(l, i)
                    const cited = citedTargets.has(k)
                    const cls = [low && 'low', cited && 'cited', active === k && 'selected', linked(k) && 'linked'].filter(Boolean).join(' ')
                    return (
                      <tr key={i} className={cls} data-key={k}
                          onClick={cited ? () => select(k) : undefined}
                          onFocusCapture={cited ? () => { if (active !== k) select(k) } : undefined}>
                        <td className="line-no">{i + 1}</td>
                        <td><input className="mono" value={l.material_or_sku ?? ''} onChange={(e) => updateLine(i, 'material_or_sku', e.target.value)} /></td>
                        <td><input value={l.description ?? ''} onChange={(e) => updateLine(i, 'description', e.target.value)} /></td>
                        <td><input value={l.quantity ?? ''} onChange={(e) => updateLine(i, 'quantity', e.target.value)} /></td>
                        <td><input value={l.unit_price ?? ''} onChange={(e) => updateLine(i, 'unit_price', e.target.value)} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="actions">
              <button className="btn" onClick={save} disabled={busy}>Save corrections</button>
              <button className="btn primary" onClick={approve} disabled={busy}>Approve → SAP</button>
              <button className="btn" onClick={flag} disabled={busy}>Flag manual</button>
            </div>
          </div>
        </div>
      </div>

      {toast && <Toast msg={toast.msg} err={toast.err} />}
    </div>
  )
}
