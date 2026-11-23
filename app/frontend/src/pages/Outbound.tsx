import { useEffect, useState } from 'react'
import { api, type OutboundRow } from '../api'

export default function Outbound() {
  const [rows, setRows] = useState<OutboundRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listOutbound().then(setRows).catch((e) => setError(String(e))).finally(() => setLoading(false))
  }, [])

  return (
    <div className="container">
      <h1 className="page-title">SAP Outbound</h1>
      <p className="page-sub">Approved orders written as ORDERS05 IDoc payloads to Unity Catalog (sap_outbound).</p>

      <div className="card">
        {loading ? (
          <div className="loading">Loading…</div>
        ) : error ? (
          <div className="loading" style={{ color: 'var(--red)' }}>{error}</div>
        ) : rows.length === 0 ? (
          <div className="empty">No approved orders yet. Approve one from the Review Queue.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Order ID</th><th>Customer PO</th><th>Sold-To</th><th>Customer</th>
                <th>Currency</th><th>IDoc</th><th>Approved By</th><th>Approved At</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.order_id} style={{ cursor: 'default' }}>
                  <td className="mono">{r.order_id}</td>
                  <td className="mono">{r.po_number || '—'}</td>
                  <td className="mono">{r.sap_sold_to || '—'}</td>
                  <td>{r.customer_name || '—'}</td>
                  <td>{r.currency || '—'}</td>
                  <td><span className="pill approved">{r.idoc_type}</span></td>
                  <td>{r.approved_by || '—'}</td>
                  <td style={{ color: 'var(--muted)' }}>{r.approved_at ? new Date(r.approved_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
