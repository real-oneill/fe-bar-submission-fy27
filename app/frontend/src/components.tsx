export function confClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'none'
  if (v >= 0.9) return 'green'
  if (v >= 0.75) return 'amber'
  return 'red'
}

export function ConfBadge({ value }: { value: number | null | undefined }) {
  const cls = confClass(value)
  return <span className={`badge ${cls}`}>{value === null || value === undefined ? '—' : value.toFixed(2)}</span>
}

export function StatusPill({ status }: { status: string }) {
  const label = status === 'needs_manual' ? 'Needs manual' : status.charAt(0).toUpperCase() + status.slice(1)
  return <span className={`pill ${status}`}>{label}</span>
}

export function Toast({ msg, err }: { msg: string; err?: boolean }) {
  return <div className={`toast ${err ? 'err' : ''}`}>{msg}</div>
}
