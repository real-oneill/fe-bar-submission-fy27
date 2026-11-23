import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type OrderSummary } from '../api'
import { ConfBadge, StatusPill } from '../components'

const FILTERS = ['all', 'needs_manual', 'pending', 'approved', 'duplicate']

export default function Queue() {
  const [orders, setOrders] = useState<OrderSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [region, setRegion] = useState('')
  const [regions, setRegions] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const nav = useNavigate()

  useEffect(() => {
    api.listRegions().then(setRegions).catch(() => setRegions([]))
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    api
      .listOrders(filter === 'all' ? undefined : filter, region || undefined)
      .then(setOrders)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [filter, region])

  return (
    <div className="container">
      <h1 className="page-title">Review Queue</h1>
      <p className="page-sub">
        Extracted purchase orders sorted by confidence (lowest first). Confidence comes from checking each value
        against the source document, not from the model's self-rating. Review, correct, and approve to SAP.
      </p>

      <div className="filters">
        {FILTERS.map((f) => (
          <button key={f} className={`chip ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>
            {f === 'all' ? 'All' : f === 'needs_manual' ? 'Needs manual' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <select
          className="region-select"
          aria-label="Region"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        >
          <option value="">All my regions</option>
          {regions.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      <div className="card">
        {loading ? (
          <div className="loading">Loading orders…</div>
        ) : error ? (
          <div className="loading" style={{ color: 'var(--red)' }}>{error}</div>
        ) : orders.length === 0 ? (
          <div className="empty">No orders match this filter.</div>
        ) : (
          <div className="table-scroll">
          <table className="queue-table">
            <thead>
              <tr>
                <th className="col-doc">Document</th>
                <th>Customer PO</th>
                <th>Customer</th>
                <th>Region</th>
                <th>Currency</th>
                <th style={{ textAlign: 'right' }}>Lines</th>
                <th style={{ textAlign: 'center' }}>Confidence</th>
                <th className="col-status">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr
                  key={o.order_id}
                  className={o.status === 'needs_manual' ? 'manual' : ''}
                  onClick={() => nav(`/orders/${encodeURIComponent(o.order_id)}`)}
                >
                  <td className="col-doc">
                    <div style={{ fontWeight: 600 }}>{o.doc_name}</div>
                    <div style={{ color: 'var(--muted)', fontSize: 12 }}>
                      {o.orig_format}{o.has_pdf ? ' · PDF' : ''}
                    </div>
                  </td>
                  <td className="mono">{o.po_number || '—'}</td>
                  <td>{o.customer_name || <span style={{ color: 'var(--red)' }}>Needs manual entry</span>}</td>
                  <td>{o.region || '—'}</td>
                  <td>{o.currency || '—'}</td>
                  <td style={{ textAlign: 'right' }}>{o.n_lines ?? '—'}</td>
                  <td style={{ textAlign: 'center' }}><ConfBadge value={o.overall_confidence} /></td>
                  <td className="col-status">
                    <StatusPill status={o.status} />
                    {o.review_reasons && <div className="reason-hint">{o.review_reasons}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  )
}
