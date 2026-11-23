export interface OrderSummary {
  order_id: string
  doc_name: string
  orig_format: string
  po_number: string | null
  customer_name: string | null
  customer_number: string | null
  currency: string | null
  sales_org: string | null
  n_lines: number | null
  status: string
  parse_confidence: number | null
  header_confidence: number | null
  avg_line_confidence: number | null
  overall_confidence: number | null
  review_reasons: string | null
  duplicate_of: string | null
  has_pdf: boolean
  region: string | null
}

export interface LineItem {
  order_idx?: number | null
  li_idx?: number | null
  line_no?: number | string | null
  material_or_sku: string | null
  description: string | null
  quantity: number | null
  unit_price: number | null
  line_confidence: number | null
  sku_resolved?: boolean | null
  resolved_material_no?: string | null
}

export interface OrderDetail extends OrderSummary {
  order_date: string | null
  ship_to: string | null
  parsed_content: string | null
  volume_path: string | null
  line_items_json: string | null
  line_items: LineItem[]
  extractor?: string | null
  fallback_reason?: string | null
  field_confidence?: Record<string, number | null>
  related_orders?: { order_id: string; doc_name: string; status: string }[]
}

/** One row of review_citations (see .superpowers/citations-contract.md). Layout boxes are in pixels of the page
 * rendered at 200 DPI, origin top-left. */
export interface Citation {
  order_idx: number | null
  li_idx: number | null
  field: string
  value: string | null
  confidence: number | null
  citation_id: number | null
  source_kind: 'layout' | 'sheet' | 'text' | string
  page_index: number | null
  x1: number | null
  y1: number | null
  x2: number | null
  y2: number | null
  element_id: number | null
  element_type: string | null
  table_row_index: number | null
  table_row_count: number | null
  sheet_index: number | null
  sheet_name: string | null
  row_number: number | null
  cell_ref: string | null
  char_start: number | null
  char_stop: number | null
  snippet: string | null
}

export interface CitationData {
  order_id: string
  extractor: string | null
  fallback_reason: string | null
  field_confidence: Record<string, number | null>
  citations: Citation[]
}

export interface SheetRow { r: number; cells: string[] }
export interface Sheet { index: number; name: string; rows: SheetRow[]; n_cols: number; truncated: boolean }

export interface EmailAttachment {
  path: string
  name: string
  kind: 'pdf' | 'sheet' | 'image' | 'email' | 'text' | 'file'
  mime: string
  size: number | null
}

export interface EmailData {
  subject: string | null
  from: string | null
  to: string | null
  cc: string | null
  sent_at: string | null
  /** sanitized, self-contained HTML document (shown in a sandboxed iframe) */
  html: string | null
  text: string | null
  attachments: EmailAttachment[]
}

export interface Preview {
  kind: 'pdf' | 'sheet' | 'text' | 'image' | 'email' | 'file'
  url?: string
  sheets?: Sheet[]
  truncated?: boolean
  source?: 'file' | 'text'
  text?: string
  note?: string | null
  /** the order came from an attached email: this endpoint returns it (and, with ?path=, its attachments) */
  email_url?: string
  email?: EmailData
  name?: string
  path?: string
}

export interface OutboundRow {
  order_id: string
  po_number: string | null
  sap_sold_to: string | null
  customer_name: string | null
  order_date: string | null
  currency: string | null
  approved_by: string | null
  approved_at: string | null
  idoc_type: string | null
  line_items_json: string | null
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  listOrders: (status?: string, region?: string) => {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (region) q.set('region', region)
    const qs = q.toString()
    return fetch(`/api/orders${qs ? `?${qs}` : ''}`).then(j<OrderSummary[]>)
  },
  listRegions: () => fetch('/api/regions').then(j<string[]>),
  getOrder: (id: string) => fetch(`/api/orders/${encodeURIComponent(id)}`).then(j<OrderDetail>),
  getCitations: (id: string) => fetch(`/api/orders/${encodeURIComponent(id)}/citations`).then(j<CitationData>),
  getPreview: (id: string) => fetch(`/api/orders/${encodeURIComponent(id)}/preview`).then(j<Preview>),
  updateOrder: (id: string, body: any) =>
    fetch(`/api/orders/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j<any>),
  approveOrder: (id: string, body: any = {}) =>
    fetch(`/api/orders/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(j<any>),
  flagManual: (id: string) =>
    fetch(`/api/orders/${encodeURIComponent(id)}/flag`, { method: 'POST' }).then(j<any>),
  listOutbound: () => fetch('/api/outbound').then(j<OutboundRow[]>),
  documentUrl: (id: string) => `/api/orders/${encodeURIComponent(id)}/document`,
  /** emailUrl = Preview.email_url; path '' = the email itself, '0' = its first attachment, '1.0' = nested */
  getEmailPart: (emailUrl: string, path: string) =>
    fetch(`${emailUrl}?path=${encodeURIComponent(path)}`).then(j<Preview>),
}
