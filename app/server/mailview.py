"""Attached emails (.eml / .msg) for the review page: headers, a sanitized HTML body, and the attachments, which open
in the same viewers as the order's document (PDF, spreadsheet, image, text) — emails inside emails included.

  * open_mail()      bytes + extension -> Mail (stdlib email parser for .eml / message/rfc822, extract-msg for .msg)
  * resolve()        Mail + part path ("0", "1.0" = attachment 1 of the email attached as attachment 1) -> Mail | Part
  * find_part()      Mail + Silver's part name ("order.msg / inner.eml / order.pdf") -> part path, or None
  * email_json()     Mail -> the JSON the frontend renders
  * sanitize_html()  an email's HTML -> a self-contained document for a sandboxed iframe: no scripts, event handlers,
                     forms, frames or remote loads (Content-Security-Policy: data: images only); cid: images inlined.
"""
from __future__ import annotations

import base64
import email
import email.policy
import html as _html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import PurePosixPath

MAX_DEPTH = 5
MIME_BY_EXT = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12", ".xls": "application/vnd.ms-excel", ".csv": "text/csv",
    ".txt": "text/plain", ".eml": "message/rfc822", ".msg": "application/vnd.ms-outlook",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SHEET_EXT = {".xlsx", ".xlsm", ".xls", ".csv"}
MAIL_EXT = {".eml", ".msg"}
TEXT_EXT = {".txt", ".csv", ".json", ".xml", ".edi"}
# served inline by the raw endpoint; everything else is a download (never rendered by the browser)
INLINE_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}


@dataclass
class Part:
    name: str
    mime: str
    data: bytes | None
    mail: "Mail | None" = None          # an email attached to the email

    @property
    def kind(self) -> str:
        ext = PurePosixPath(self.name).suffix.lower()
        if self.mail is not None or ext in MAIL_EXT:
            return "email"
        if self.mime == "application/pdf" or ext == ".pdf":
            return "pdf"
        if ext in SHEET_EXT:
            return "sheet"
        if self.mime.startswith("image/"):
            return "image"
        if self.mime.startswith("text/") or ext in TEXT_EXT:
            return "text"
        return "file"


@dataclass
class Mail:
    subject: str | None = None
    sender: str | None = None
    to: str | None = None
    cc: str | None = None
    sent_at: str | None = None
    html: str | None = None
    text: str | None = None
    attachments: list[Part] = field(default_factory=list)
    inline: dict[str, tuple[str, bytes]] = field(default_factory=dict)   # content id -> (mime, bytes)


def mime_of(name: str, declared: str | None = None) -> str:
    return MIME_BY_EXT.get(PurePosixPath(name or "").suffix.lower()) or (declared or "application/octet-stream")


# ------------------------------------------------------------------------------------------------ parsing
def open_mail(data: bytes, ext: str) -> Mail:
    """Raises ValueError when the bytes can't be read as an email."""
    try:
        if ext == ".msg":
            import extract_msg                      # only needed for Outlook .msg files
            m = extract_msg.openMsg(bytes(data))
            try:
                return _from_msg(m, 1)
            finally:
                m.close()
        return _from_eml(email.message_from_bytes(bytes(data), policy=email.policy.default), 1)
    except ValueError:
        raise
    except Exception as e:  # noqa  (extract-msg / email raise many types on bad input)
        raise ValueError(f"could not read the email: {str(e)[:160]}") from e


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return v.decode(enc)
            except UnicodeDecodeError:
                continue
    s = str(v).strip()
    return s or None


def _from_eml(m, depth: int) -> Mail:
    out = Mail(subject=_text(m.get("Subject")), sender=_text(m.get("From")), to=_text(m.get("To")),
               cc=_text(m.get("Cc")), sent_at=_text(m.get("Date")))
    for kind in ("html", "plain"):
        b = m.get_body(preferencelist=(kind,))
        if b is None:
            continue
        try:
            body = b.get_content()
        except Exception:  # noqa  (unknown charset)
            body = (b.get_payload(decode=True) or b"").decode("latin-1")
        if kind == "html":
            out.html = body
        else:
            out.text = body
    for p in m.walk():                              # inline images the HTML refers to (cid:)
        cid = p.get("Content-ID")
        if cid and p.get_content_maintype() == "image":
            out.inline[cid.strip("<> ")] = (p.get_content_type(), p.get_payload(decode=True) or b"")
    for i, a in enumerate(m.iter_attachments(), 1):
        ctype = a.get_content_type()
        if ctype == "message/rfc822":
            inner = a.get_payload(0) if a.is_multipart() else None
            name = a.get_filename() or f"{(_text(inner.get('Subject')) if inner is not None else None) or 'attached message'}.eml"
            out.attachments.append(Part(name, "message/rfc822", inner.as_bytes() if inner is not None else None,
                                        _from_eml(inner, depth + 1) if inner is not None and depth < MAX_DEPTH else None))
            continue
        if ctype.startswith("image/") and a.get("Content-ID") and a.get_content_disposition() != "attachment":
            continue                                # shown in the body
        name = a.get_filename() or f"attachment-{i}"
        data = a.get_payload(decode=True)
        part = Part(name, mime_of(name, ctype), data)
        if part.kind == "email" and data and depth < MAX_DEPTH:
            try:
                part.mail = open_mail(data, PurePosixPath(name).suffix.lower() or ".eml")
            except ValueError:
                pass
        out.attachments.append(part)
    return out


def _from_msg(m, depth: int) -> Mail:
    html = m.htmlBody if getattr(m, "htmlBody", None) else None
    date = getattr(m, "date", None)
    out = Mail(subject=_text(m.subject), sender=_text(m.sender), to=_text(m.to), cc=_text(m.cc),
               sent_at=date.isoformat() if hasattr(date, "isoformat") else _text(date),
               html=_text(html), text=_text(m.body))
    for i, a in enumerate(m.attachments, 1):
        name = a.longFilename or a.shortFilename or getattr(a, "displayName", None) or f"attachment-{i}"
        data = a.data
        if isinstance(data, bytes):
            mime = mime_of(name, getattr(a, "mimetype", None))
            cid = getattr(a, "cid", None) or getattr(a, "contentId", None)
            if cid and mime.startswith("image/"):
                out.inline[str(cid).strip("<> ")] = (mime, data)
                if getattr(a, "hidden", False) or (out.html and f"cid:{str(cid).strip('<> ')}" in out.html):
                    continue                        # shown in the body
            part = Part(name, mime, data)
            if part.kind == "email" and depth < MAX_DEPTH:
                try:
                    part.mail = open_mail(data, PurePosixPath(name).suffix.lower())
                except ValueError:
                    pass
            out.attachments.append(part)
        elif data is not None:                      # an Outlook item attached to the email
            subject = _text(getattr(data, "subject", None)) or "attached message"
            nm = name if PurePosixPath(name).suffix.lower() in MAIL_EXT else f"{subject}.msg"
            out.attachments.append(Part(nm, "application/vnd.ms-outlook", None,
                                        _from_msg(data, depth + 1) if depth < MAX_DEPTH else None))
    return out


def resolve(mail: Mail, path: str) -> Mail | Part:
    """'' -> the email; '2' -> its attachment 2 (0-based); '2.0' -> attachment 0 of the email attached as 2.
    Raises LookupError for an unknown path."""
    cur: Mail | Part = mail
    for step in [s for s in (path or "").split(".") if s != ""]:
        m = cur.mail if isinstance(cur, Part) else cur
        if m is None or not step.isdigit() or int(step) >= len(m.attachments):
            raise LookupError("no such attachment")
        cur = m.attachments[int(step)]
    return cur


def find_part(mail: Mail, name: str | None) -> str | None:
    """Silver names a part of an email "<email file> / <attachment> / <attachment of an attached email>" (the first
    element is the email file itself). -> the part path for resolve(), or None."""
    names = [n.strip() for n in (name or "").split(" / ") if n.strip()]

    def walk(chain):
        path, cur = [], mail
        for n in chain:
            if cur is None:
                return None
            idx = next((i for i, a in enumerate(cur.attachments) if a.name == n), None)
            if idx is None:
                return None
            path.append(str(idx))
            cur = cur.attachments[idx].mail
        return ".".join(path) if path else None

    return (walk(names[1:]) if len(names) > 1 else None) or walk(names)


# ------------------------------------------------------------------------------------------------ JSON
def email_json(mail: Mail, path: str = "") -> dict:
    pre = f"{path}." if path else ""
    return {
        "kind": "email",
        "path": path,
        "email": {
            "subject": mail.subject, "from": mail.sender, "to": mail.to, "cc": mail.cc, "sent_at": mail.sent_at,
            "html": sanitize_html(mail.html, mail.inline) if mail.html else None,
            "text": mail.text if mail.text else (html_to_text(mail.html) if mail.html else None),
            "attachments": [{"path": f"{pre}{i}", "name": a.name, "kind": a.kind, "mime": a.mime,
                             "size": len(a.data) if a.data is not None else None}
                            for i, a in enumerate(mail.attachments)],
        },
    }


def html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"[ \t\xa0]+", " ", _html.unescape(h)).strip()


# ------------------------------------------------------------------------------------------------ sanitizing
ALLOWED_TAGS = {
    "a", "abbr", "address", "b", "bdi", "bdo", "big", "blockquote", "br", "caption", "center", "cite", "code", "col",
    "colgroup", "dd", "del", "dfn", "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i",
    "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "s", "samp", "small", "span", "strike", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "tt", "u", "ul", "var", "wbr", "style",
}
DROP_WITH_CONTENT = {"script", "noscript", "iframe", "frame", "frameset", "object", "embed", "applet", "template",
                     "svg", "math", "select", "textarea", "button", "title"}
VOID = {"br", "col", "hr", "img", "wbr"}
URL_ATTRS = {"href", "src", "background"}
ALLOWED_ATTRS = {"align", "alt", "bgcolor", "border", "cellpadding", "cellspacing", "class", "color", "colspan",
                 "dir", "face", "height", "href", "lang", "rowspan", "size", "span", "src", "style", "title",
                 "valign", "width", "background", "start", "type", "headers", "scope", "nowrap"}
CSP = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; "
       "form-action 'none'; base-uri 'none'")
_BAD_CSS = re.compile(r"(?i)expression\s*\(|javascript:|vbscript:|@import|behavior\s*:|-moz-binding|url\s*\(\s*['\"]?\s*(?!data:image/)")


class _Sanitizer(HTMLParser):
    def __init__(self, inline):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip = 0                  # inside a dropped element
        self.in_style = False
        self.inline = inline

    def _url(self, name, value):
        v = (value or "").strip()
        low = re.sub(r"[\s\x00-\x1f]", "", v).lower()
        if low.startswith("cid:"):
            hit = self.inline.get(v[4:].strip("<> "))
            return f"data:{hit[0]};base64,{base64.b64encode(hit[1]).decode()}" if hit else None
        if name == "href":
            return v if low.startswith(("http://", "https://", "mailto:", "#")) else None
        return v if low.startswith("data:image/") else None      # remote images are never loaded

    def _attrs(self, tag, attrs):
        out = []
        for k, v in attrs:
            k = (k or "").lower()
            if k.startswith("on") or k not in ALLOWED_ATTRS:
                continue
            if k in URL_ATTRS:
                v = self._url(k, v)
                if v is None:
                    continue
            if k == "style" and v and _BAD_CSS.search(v):
                continue
            out.append(f' {k}="{_html.escape(v or "", quote=True)}"')
        if tag == "a":
            out.append(' target="_blank" rel="noopener noreferrer"')
        return "".join(out)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if tag not in VOID:
                self.skip += 1
            return
        if self.skip or tag not in ALLOWED_TAGS:
            return
        if tag == "style":
            self.in_style = True
        self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in ALLOWED_TAGS or tag in VOID:
            return
        if tag == "style":
            self.in_style = False
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_style:
            self.out.append("" if _BAD_CSS.search(data) else data.replace("</", ""))
        else:
            self.out.append(_html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(f"&#{name};")


def sanitize_html(html: str, inline: dict | None = None) -> str:
    """A complete HTML document safe for <iframe sandbox srcdoc> (the frame also gets no allow-scripts)."""
    body = re.sub(r"(?is)<!--.*?-->|<!doctype[^>]*>|<\?xml[^>]*>", "", html or "")
    s = _Sanitizer(inline or {})
    s.feed(body)
    s.close()
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
            '<style>body{font:14px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:12px;color:#1f2328;'
            'word-wrap:break-word}img{max-width:100%;height:auto}table{border-collapse:collapse}</style>'
            f'</head><body>{"".join(s.out)}</body></html>')
