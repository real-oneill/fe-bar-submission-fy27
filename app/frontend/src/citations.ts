import type { Citation, LineItem } from './api'

/** What a citation backs in the review form: a header field (`h:<field>`) or a line (`l:<order_idx>:<li_idx>`). */
export type TargetKey = string

export const HEADER_LABELS: Record<string, string> = {
  // exactly the labels of the review form's fields (Detail.tsx HEADER_FIELDS), so a tooltip names the field it backs
  po_number: 'Customer PO',
  customer_name: 'Customer Name',
  customer_number: 'Customer Number',
  order_date: 'Order Date',
  currency: 'Currency',
  ship_to: 'Ship To',
}
/** citation field -> the form field it supports (the PO label sits next to the PO number) */
const HEADER_ALIAS: Record<string, string> = { po_number_label: 'po_number' }

const LINE_FIELD_LABELS: Record<string, string> = {
  material_or_sku: 'code', quantity: 'quantity', description: 'description', unit_price: 'price', uom: 'unit',
  line_no: 'line no.', source_row: 'row',
}

export const headerKey = (field: string): TargetKey => `h:${field}`
export const lineKey = (l: Pick<LineItem, 'order_idx' | 'li_idx'>, i: number): TargetKey =>
  `l:${l.order_idx ?? 0}:${l.li_idx ?? i}`

/** The target a citation backs, or null if the form doesn't show that field. */
export function targetOf(c: Citation, headerOrderIdx: number): TargetKey | null {
  if (c.li_idx == null) {
    if ((c.order_idx ?? 0) !== headerOrderIdx) return null
    const f = HEADER_ALIAS[c.field] ?? c.field
    return HEADER_LABELS[f] ? headerKey(f) : null
  }
  return `l:${c.order_idx ?? 0}:${c.li_idx}`
}

/** Human label of a target, e.g. "PO number" or "Line 3 · SKU-922615". */
export function targetLabel(key: TargetKey, lines: LineItem[]): string {
  if (key.startsWith('h:')) return HEADER_LABELS[key.slice(2)] ?? key.slice(2)
  const i = lines.findIndex((l, k) => lineKey(l, k) === key)
  if (i < 0) return 'Line'
  const code = lines[i].material_or_sku
  return `Line ${i + 1}${code ? ` · ${code}` : ''}`
}

export const lineFieldLabel = (f: string) => LINE_FIELD_LABELS[f] ?? f.replace(/_/g, ' ')

/** "D10" -> { col: 3, row: 10 } */
export function parseCellRef(ref: string | null | undefined): { col: number; row: number } | null {
  const m = /^([A-Z]{1,3})(\d+)$/.exec((ref ?? '').toUpperCase())
  if (!m) return null
  let n = 0
  for (const ch of m[1]) n = n * 26 + (ch.charCodeAt(0) - 64)
  return { col: n - 1, row: Number(m[2]) }
}

/** 0-based column index -> spreadsheet letter (0 -> A, 26 -> AA). */
export function colLetter(i: number): string {
  let out = ''
  let n = i + 1
  while (n) {
    const r = (n - 1) % 26
    out = String.fromCharCode(65 + r) + out
    n = Math.floor((n - 1) / 26)
  }
  return out
}

/** The pipeline's fallback reasons name the two readers; say it in plain words. */
export function plainReason(reason: string): string {
  return reason
    .replace(/\s*\(silent failure\)/gi, '')
    .replace(/read with the fallback extractor/gi, 'read with a second method')
    .replace(/\bai_extract lines\b/gi, 'lines from the first reading')
    .replace(/\bai_extract\b/gi, 'the first reading')
    .replace(/\bai_query\b/gi, 'the second method')
    .replace(/^the first/, 'The first')
}

export function extractorNote(extractor: string | null | undefined, reason: string | null | undefined): string | null {
  if (!extractor) return null
  if (extractor === 'ai_query' && reason) return `Checked with a second method: ${plainReason(reason)}`
  if (extractor === 'ai_extract' && reason) return `Read automatically, also checked with a second method (${plainReason(reason)})`
  return 'Read automatically'
}

export const pct = (v: number) => `${Math.round(v * 100)}%`
