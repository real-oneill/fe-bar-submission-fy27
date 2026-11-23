"""Attached-email view (app/server/mailview.py): parsing, part paths, and the HTML sanitizer."""
import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))
from server import mailview  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def _inner() -> bytes:
    m = EmailMessage()
    m["Subject"], m["From"] = "Original order", "buyer@shop.example"
    m.set_content("see the sheet")
    m.add_attachment(b"col1,col2\n1,2\n", maintype="text", subtype="csv", filename="order.csv")
    return bytes(m)


def _outer() -> bytes:
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = "FW: Bestellung", "cs@maisonsolenne.example", "orders@maisonsolenne.example"
    m["Date"] = "Tue, 22 Sep 2026 10:00:00 +0200"
    m.set_content("plain body")
    m.add_alternative('<html><head><style>p{color:red}</style><script>alert(1)</script></head><body>'
                      '<p onclick="steal()">Hello <b>there</b></p><img src="cid:logo1"><img src="https://track.example/x.png">'
                      '<a href="javascript:alert(1)">bad</a><a href="https://maisonsolenne.example">ok</a>'
                      '<iframe src="https://evil.example"></iframe><form action="x"><input name="q"></form></body></html>',
                      subtype="html")
    m.get_payload()[1].add_related(PNG, maintype="image", subtype="png", cid="<logo1>")
    m.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="PO 123.pdf")
    from email import message_from_bytes, policy
    m.add_attachment(message_from_bytes(_inner(), policy=policy.default))
    return bytes(m)


def test_eml_headers_attachments_and_nested_email():
    mail = mailview.open_mail(_outer(), ".eml")
    assert mail.subject == "FW: Bestellung" and mail.sender == "cs@maisonsolenne.example" and mail.to == "orders@maisonsolenne.example"
    kinds = [(a.name, a.kind) for a in mail.attachments]
    assert kinds[0] == ("PO 123.pdf", "pdf") and kinds[1][1] == "email"
    nested = mailview.resolve(mail, "1")
    assert nested.mail.subject == "Original order"
    csv = mailview.resolve(mail, "1.0")
    assert csv.name == "order.csv" and csv.kind == "sheet" and csv.data.startswith(b"col1")
    j = mailview.email_json(mail)
    assert [a["path"] for a in j["email"]["attachments"]] == ["0", "1"]
    assert mailview.email_json(nested.mail, "1")["email"]["attachments"][0]["path"] == "1.0"


def test_find_part_follows_silver_part_names():
    mail = mailview.open_mail(_outer(), ".eml")
    assert mailview.find_part(mail, "fw.eml / PO 123.pdf") == "0"
    nested_name = mail.attachments[1].name
    assert mailview.find_part(mail, f"fw.eml / {nested_name} / order.csv") == "1.0"
    assert mailview.find_part(mail, "PO 123.pdf") == "0"
    assert mailview.find_part(mail, "fw.eml / missing.pdf") is None


def test_unknown_part_path():
    mail = mailview.open_mail(_outer(), ".eml")
    for bad in ("9", "0.0", "x"):
        try:
            mailview.resolve(mail, bad)
            raise AssertionError(bad)
        except LookupError:
            pass


def test_sanitizer_strips_active_content_and_inlines_cid_images():
    mail = mailview.open_mail(_outer(), ".eml")
    doc = mailview.email_json(mail)["email"]["html"]
    assert "Content-Security-Policy" in doc and "default-src 'none'" in doc
    low = doc.lower()
    for bad in ("<script", "alert(1)", "onclick", "javascript:", "<iframe", "<form", "<input", "track.example"):
        assert bad not in low, bad
    assert "<b>there</b>" in doc and "p{color:red}" in doc
    assert 'src="data:image/png;base64,' in doc                    # the cid: logo, inlined
    assert 'href="https://maisonsolenne.example" target="_blank" rel="noopener noreferrer"' in doc


def test_plain_text_fallback_and_bad_input():
    m = EmailMessage()
    m["Subject"] = "text only"
    m.set_content("just text")
    j = mailview.email_json(mailview.open_mail(bytes(m), ".eml"))["email"]
    assert j["html"] is None and j["text"].strip() == "just text"
    try:
        mailview.open_mail(b"\x00\x01 not an outlook file", ".msg")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_css_with_remote_urls_is_dropped():
    doc = mailview.sanitize_html('<style>body{background:url(https://x.example/a.png)}</style>'
                                 '<p style="background:url(http://x.example/b)">t</p>')
    assert "x.example" not in doc and "<p>t</p>" in doc
