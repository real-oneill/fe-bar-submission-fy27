# ============================================================
# Order Intake — Lakeflow Declarative Pipeline · Phase 2: SILVER
# parsed_attachments: unified parsed text + confidence.
#   .msg (Outlook)          -> extract-msg: split into email body + each attachment, then routed below
#   .eml / message/rfc822   -> email stdlib: same (attached Outlook items fetched from Graph arrive as .eml);
#                              emails attached to emails are unpacked recursively (depth <= 3)
#   PDF/image/Word          -> ai_parse_document (SQL AI function)
#   xlsx/xlsm               -> openpyxl  \
#   xls (legacy Excel)      -> xlrd       } rendered CELL-ADDRESSED: "S1R35: A=... | D=3 | F=29.7"
#   csv                     -> csv module /  (empty cells omitted, so values can never shift columns)
#   txt                     -> decoded as text
#   anything else           -> kept as parse_method='unsupported' (never silently dropped)
# (openpyxl / xlrd / extract-msg supplied via pipeline environment deps)
# ============================================================
import dlt
import io
import os
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.functions import pandas_udf

_ELEMS = "cast(pv:document:elements AS ARRAY<VARIANT>)"
# Cap for locally parsed text (~40K tokens, well within the extraction model's context). Order forms /
# price lists can be long; anything cut is marked with TRUNCATED_MARK so it's visible downstream.
MAX_CHARS = 150_000
TRUNCATED_MARK = "[TRUNCATED: document exceeded parser limit]"

# Keep in sync with the CASE in 01_bronze.sql and MIME_BY_EXT in 01_bronze_outlook.py.
MIME_BY_EXT = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "txt": "text/plain",
    "edi": "text/plain",     # X12 EDI (850/860) interchanges are plain text
    "json": "text/plain",    # portal exports / ASR transcripts: read as text
    "msg": "application/vnd.ms-outlook",
    "eml": "message/rfc822",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
}
MSG_MIME = MIME_BY_EXT["msg"]
AI_PARSE_MIMES = [MIME_BY_EXT[e] for e in ("pdf", "png", "jpg", "docx", "doc")]
XLSX_MIMES = [MIME_BY_EXT["xlsx"], MIME_BY_EXT["xlsm"]]
XLS_MIME = MIME_BY_EXT["xls"]
TEXT_MIMES = [MIME_BY_EXT["csv"], MIME_BY_EXT["txt"]]


EML_MIME = "message/rfc822"
MAIL_MIMES = [MSG_MIME, EML_MIME]
MAX_MAIL_DEPTH = 3   # an email inside an email inside an email; deeper ones are kept as unparsed parts


def _strip_html(h):
    import html as _html
    import re
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"[ \t\xa0]+", " ", _html.unescape(h)).strip()


def unpack_mail_parts(content, mime):
    """Split an email (.msg = Outlook, .eml / message/rfc822 = MIME, e.g. an attached Outlook item fetched from
    Graph) into its body (as "<prefix>body.txt") plus each real attachment; attached emails are unpacked the same
    way, recursively (depth <= MAX_MAIL_DEPTH), named "<outer part> / <inner part>". Inline images are skipped.
    Returns [(name, mime, bytes)]."""
    parts = []

    def body_part(prefix, sender, subject, body):
        text = f"From: {sender}\nSubject: {subject}\n\n{body or ''}"
        parts.append((f"{prefix}body.txt", MIME_BY_EXT["txt"], text.encode("utf-8")))

    def child(name, data, declared, prefix, depth):
        mime_ = MIME_BY_EXT.get(os.path.splitext(name)[1].lower().lstrip(".")) or declared or "application/octet-stream"
        if mime_ in MAIL_MIMES and depth < MAX_MAIL_DEPTH:
            walk_bytes(data, mime_, f"{prefix}{name} / ", depth + 1)
        else:
            parts.append((f"{prefix}{name}", mime_, data))

    def walk_msg(msg, prefix, depth):
        body_part(prefix, msg.sender, msg.subject, msg.body)
        for a in msg.attachments:
            name = a.longFilename or a.shortFilename or "attachment"
            if isinstance(a.data, bytes):
                mime_ = MIME_BY_EXT.get(os.path.splitext(name)[1].lower().lstrip("."), "application/octet-stream")
                # skip inline images (logos, signatures) embedded in the email body
                if mime_.startswith("image/") and (getattr(a, "hidden", False) or getattr(a, "cid", None)):
                    continue
                child(name, a.data, None, prefix, depth)
            elif a.data is not None and depth < MAX_MAIL_DEPTH:  # an email attached to the email
                walk_msg(a.data, f"{prefix}{name} / ", depth + 1)

    def walk_eml(m, prefix, depth):
        body = m.get_body(preferencelist=("plain", "html"))
        text = ""
        if body is not None:
            try:
                text = body.get_content()
            except Exception:  # noqa  (unknown charset)
                text = (body.get_payload(decode=True) or b"").decode("latin-1")
            if body.get_content_type() == "text/html":
                text = _strip_html(text)
        body_part(prefix, m.get("From", ""), m.get("Subject", ""), text)
        for i, a in enumerate(m.iter_attachments(), 1):
            ctype = a.get_content_type()
            if ctype == EML_MIME:                         # an email attached to the email
                inner = a.get_payload(0) if a.is_multipart() else None
                name = a.get_filename() or f"{(inner.get('Subject', '') if inner is not None else '') or 'attached-message'}.eml"
                if inner is not None and depth < MAX_MAIL_DEPTH:
                    walk_eml(inner, f"{prefix}{name} / ", depth + 1)
                else:
                    parts.append((f"{prefix}{name}", EML_MIME, inner.as_bytes() if inner is not None else None))
                continue
            if ctype.startswith("image/") and (a.get("Content-ID") or a.get_content_disposition() == "inline"):
                continue                                  # inline images (logos, signatures)
            name = a.get_filename() or f"attachment-{i}"
            child(name, a.get_payload(decode=True), ctype, prefix, depth)

    def walk_bytes(b, mime_, prefix, depth):
        if b is None:
            return
        if mime_ == MSG_MIME:
            import extract_msg
            msg = extract_msg.openMsg(bytes(b))
            try:
                walk_msg(msg, prefix, depth)
            finally:
                msg.close()
        else:
            import email
            from email import policy
            walk_eml(email.message_from_bytes(bytes(b), policy=policy.default), prefix, depth)

    if content is None:
        return []
    try:
        walk_bytes(content, mime, "", 1)
    except Exception as e:  # noqa
        return [(f"[mail parse error: {e}]", "application/octet-stream", None)]
    return parts


@F.udf("array<struct<name:string,mime:string,content:binary>>")
def unpack_mail(content, mime):
    return unpack_mail_parts(content, mime)


def _cap(text):
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n" + TRUNCATED_MARK


def _fmt_cell(v):
    """Render one cell value; None/'' -> None (omitted). Floats lose binary noise (29.700000000000003 -> 29.7)."""
    import datetime as _dt
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        if v.is_integer():
            return str(int(v))  # also keeps EAN-like floats (18084067994.0) intact
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()[:10] if isinstance(v, _dt.datetime) and v.time() == _dt.time(0) else v.isoformat()
    # multi-line cells (bilingual headers like "order quantity /\nBestellmenge") -> one line
    parts = [" ".join(p.split()).rstrip("/").strip() for p in str(v).replace("\r", "\n").split("\n")]
    t = " / ".join(p for p in parts if p)
    return t if t and t.lower() != "nan" else None


def _col_letter(i):
    """0-based column index -> spreadsheet letter (0 -> A, 26 -> AA)."""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _rows_to_text(sheet_no, rows):
    """rows: iterable of (row_number, values). One line per non-empty row, every value tagged with its
    column letter. Blank cells are omitted but can no longer shift other values into their column."""
    out = []
    for r, vals in rows:
        cells = []
        for i, v in enumerate(vals):
            t = _fmt_cell(v)
            if t is not None:
                cells.append(f"{_col_letter(i)}={t}")
        if cells:
            out.append(f"S{sheet_no}R{r}: " + " | ".join(cells))
    return "\n".join(out)


def _sheets_to_text(sheets):
    """sheets: iterable of (sheet_name, rows-with-numbers). Every non-empty sheet under a header line."""
    parts = []
    for n, (name, rows) in enumerate(sheets, 1):
        text = _rows_to_text(n, rows)
        if text:
            parts.append(f"=== Sheet S{n}: {name} === (cells shown as COLUMN=value; empty cells omitted)\n{text}")
    return _cap("\n\n".join(parts))


def _xlsx_sheets(b):
    import openpyxl
    # read_only=True streams rows. (read_only=False loads every *styled* cell into memory, and order forms are
    # often formatted far beyond their data, which crashed the Python worker.)
    wb = openpyxl.load_workbook(io.BytesIO(b), data_only=True, read_only=True)
    for ws in wb.worksheets:
        if getattr(ws, "sheet_state", "visible") != "visible":
            continue
        yield ws.title, _bounded_rows(ws.iter_rows(min_row=1, min_col=1, values_only=True))


def _bounded_rows(it, max_blank_run=2000):
    """Number rows from 1 (min_row/min_col=1 so labels never shift), trim trailing empty cells, and stop
    after a long run of empty rows — styled-but-empty ranges can extend to row 1,048,576."""
    blank = 0
    for r, vals in enumerate(it, 1):
        vals = list(vals)
        while vals and (vals[-1] is None or (isinstance(vals[-1], str) and not vals[-1].strip())):
            vals.pop()
        if not vals:
            blank += 1
            if blank >= max_blank_run:
                return
            continue
        blank = 0
        yield r, vals


def _xls_sheets(b):
    dfs = pd.read_excel(io.BytesIO(b), sheet_name=None, header=None, engine="xlrd")
    for name, df in dfs.items():
        yield name, _bounded_rows(df.itertuples(index=False))


def _decode(b):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("latin-1")


def _csv_sheets(text):
    import csv
    try:
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    yield "csv", _bounded_rows(csv.reader(io.StringIO(text), dialect))


@pandas_udf("string")
def parse_non_ai(content: pd.Series, mime: pd.Series) -> pd.Series:
    """Parse spreadsheets (all visible sheets) and text files locally; '' for types it doesn't handle."""
    def one(b, m):
        if b is None:
            return ""
        b = bytes(b)
        try:
            if m in XLSX_MIMES:
                return _sheets_to_text(_xlsx_sheets(b))
            if m == XLS_MIME:
                return _sheets_to_text(_xls_sheets(b))
            if m == MIME_BY_EXT["csv"]:
                return _sheets_to_text(_csv_sheets(_decode(b)))
            if m in TEXT_MIMES:
                return _cap(_decode(b))
        except Exception as e:  # noqa
            return f"[{m} parse error: {e}]"
        return ""

    return pd.Series([one(b, m) for b, m in zip(content, mime)])


@dlt.table(
    name="parsed_attachments",
    comment="Silver: .msg/.eml unpacked; PDF/image/Word via ai_parse_document; xlsx/xls/csv/txt parsed locally; "
            "unified parsed_content + parse_confidence. source_path traces every row to its Bronze file.",
    table_properties={"quality": "silver"},
)
def parsed_attachments():
    common = ["email_id", "attachment_filename", "attachment_mime_type",
              "from_email", "subject", "received_at", "source_path"]
    b = (
        dlt.read("email_attachments")
        .withColumn("attachment_mime_type",
                    F.coalesce(F.col("attachment_mime_type"), F.lit("application/octet-stream")))
        .select(*common, "content")
    )

    # Emails (.msg, .eml / attached Outlook items) -> one row per part (body + each attachment, attached emails
    # recursively), named "<email>.msg / <part>"; they keep the outer email's email_id + source_path.
    msg_parts = (
        b.filter(F.col("attachment_mime_type").isin(MAIL_MIMES))
        .withColumn("part", F.explode(unpack_mail("content", "attachment_mime_type")))
        .withColumn("attachment_filename", F.concat_ws(" / ", "attachment_filename", "part.name"))
        .withColumn("attachment_mime_type", F.col("part.mime"))
        .withColumn("content", F.col("part.content"))
        .select(*common, "content")
    )
    docs = b.filter(~F.col("attachment_mime_type").isin(MAIL_MIMES)).unionByName(msg_parts)

    ai = (
        docs.filter(F.col("attachment_mime_type").isin(AI_PARSE_MIMES))
        .withColumn("pv", F.expr("ai_parse_document(content)"))
        .withColumn("parse_method", F.lit("ai_parse_document"))
        .withColumn("parsed_layout", F.col("pv"))  # Keep the VARIANT for hybrid extraction (Gold)
        .withColumn("parsed_content",
                    F.expr(f"array_join(transform({_ELEMS}, x -> cast(x:content AS STRING)), '\\n')"))
        .withColumn("parse_confidence",
                    F.expr(f"aggregate(transform({_ELEMS}, x -> cast(x:confidence AS DOUBLE)), "
                           f"CAST(0.0 AS DOUBLE), (a,x)->a+coalesce(x,CAST(1.0 AS DOUBLE)))"
                           f"/greatest(size({_ELEMS}),1)"))
        .withColumn("parse_truncated", F.lit(False))
        .select(*common, "parse_method", "parsed_content", "parsed_layout", "parse_confidence", "parse_truncated")
    )

    mime = F.col("attachment_mime_type")
    local = (
        docs.filter(~mime.isin(AI_PARSE_MIMES))
        .withColumn("parse_method",
                    F.when(mime.isin(XLSX_MIMES), "openpyxl_xlsx")
                     .when(mime == XLS_MIME, "xlrd_xls")
                     .when(mime == MIME_BY_EXT["csv"], "csv")
                     .when(mime.isin(TEXT_MIMES), "text")
                     .otherwise("unsupported"))
        .withColumn("parsed_content", parse_non_ai(F.col("content"), mime))
        .withColumn("parsed_layout", F.lit(None).cast("VARIANT"))  # No VARIANT for locally-parsed docs
        .withColumn("parse_confidence",
                    F.when(F.col("parse_method") == "unsupported", 0.0).otherwise(1.0))
        .withColumn("parse_truncated", F.col("parsed_content").contains(TRUNCATED_MARK))
        .select(*common, "parse_method", "parsed_content", "parsed_layout", "parse_confidence", "parse_truncated")
    )

    return ai.unionByName(local)
