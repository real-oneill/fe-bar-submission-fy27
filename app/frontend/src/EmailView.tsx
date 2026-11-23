import { useEffect, useState, type ReactNode } from 'react'
import { api, type EmailAttachment, type Preview } from './api'

const KIND_ICON: Record<EmailAttachment['kind'], string> = {
  pdf: 'PDF', sheet: 'XLS', image: 'IMG', email: 'MAIL', text: 'TXT', file: 'FILE',
}

const fmtSize = (n: number | null) =>
  n == null ? '' : n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`

/** An email (the one an order came from, or one attached to it): headers, the body in a sandboxed frame (no
 *  scripts, no remote loads — the server sanitizes it too), and its attachments, which open in the document
 *  viewers (`renderDoc`); an attached email opens as another EmailView. */
export default function EmailView(p: {
  emailUrl: string
  /** the email's own preview (kind 'email'); fetched from emailUrl when absent */
  data?: Preview
  renderDoc: (preview: Preview) => ReactNode
  onBack?: () => void
}) {
  const [mail, setMail] = useState<Preview | null>(p.data ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState<{ a: EmailAttachment; preview: Preview | null; err: string | null } | null>(null)

  useEffect(() => {
    if (p.data) { setMail(p.data); return }
    let dead = false
    api.getEmailPart(p.emailUrl, '').then((m) => { if (!dead) setMail(m) })
      .catch((e) => { if (!dead) setErr(String(e).replace(/^Error: /, '').slice(0, 160)) })
    return () => { dead = true }
  }, [p.emailUrl, p.data])

  const openPart = (a: EmailAttachment) => {
    setOpen({ a, preview: null, err: null })
    api.getEmailPart(p.emailUrl, a.path).then((pv) => setOpen({ a, preview: pv, err: null }))
      .catch((e) => setOpen({ a, preview: null, err: String(e).replace(/^Error: /, '').slice(0, 160) }))
  }

  if (err) return <div className="doc-empty">The email can't be shown here ({err}).</div>
  if (!mail?.email) return <div className="doc-empty">Opening the email…</div>

  if (open) {
    const back = <button className="btn-link" onClick={() => setOpen(null)}>← Back to the email</button>
    if (open.err) return <div className="email-part">{back}<div className="doc-empty">This attachment can't be shown ({open.err}).</div></div>
    if (!open.preview) return <div className="email-part">{back}<div className="doc-empty">Opening {open.a.name}…</div></div>
    if (open.preview.kind === 'email') {
      return <EmailView emailUrl={p.emailUrl} data={open.preview} renderDoc={p.renderDoc} onBack={() => setOpen(null)} />
    }
    return (
      <div className="email-part">
        <div className="email-part-head">{back}<span className="email-part-name">{open.a.name}</span></div>
        {p.renderDoc(open.preview)}
      </div>
    )
  }

  const e = mail.email
  return (
    <div className="email-view">
      {p.onBack && <div className="email-part-head"><button className="btn-link" onClick={p.onBack}>← Back</button></div>}
      <div className="email-head">
        <div className="email-subject">{e.subject || '(no subject)'}</div>
        {e.from && <div><span className="muted">From</span> {e.from}</div>}
        {e.to && <div><span className="muted">To</span> {e.to}</div>}
        {e.cc && <div><span className="muted">Cc</span> {e.cc}</div>}
        {e.sent_at && <div><span className="muted">Sent</span> {e.sent_at}</div>}
        {e.attachments.length > 0 && (
          <div className="email-atts">
            {e.attachments.map((a) => (
              <button key={a.path} className="email-att" onClick={() => openPart(a)} title={`Open ${a.name}`}>
                <span className={`email-att-kind k-${a.kind}`}>{KIND_ICON[a.kind]}</span>
                <span className="email-att-name">{a.name}</span>
                {a.size != null && <span className="muted">{fmtSize(a.size)}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
      {e.html ? (
        // sandbox without allow-scripts / allow-same-origin: the body can't run code or reach the app;
        // links open in a new tab
        <iframe className="email-body" title="Email body" srcDoc={e.html}
                sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" />
      ) : (
        <div className="doc-scroll text-scroll"><pre className="doc-text">{e.text || '(no text)'}</pre></div>
      )}
    </div>
  )
}
