"""Source-document previews for the review page, and where the extracted fields sit in them (citations).

  * allowed_path()      the ONLY files the app reads: /Volumes/<catalog>/<schema>/<volume>/{inbound_docs,
                        outlook_attachments}/... (no '..'). Every document endpoint checks it before downloading.
  * sheet_preview()     .xlsx/.xlsm/.xls/.csv -> sheets of display strings, bounded (MAX_ROWS x MAX_COLS per sheet,
                        `truncated` flag). Sheets, row numbers and cell values follow Silver's cell-addressed text
                        (src/pipeline/02_silver.py: visible sheets numbered from 1, rows numbered like Excel, blank rows
                        skipped, the same cell formatting), so a citation `S<sheet_index>R<row_number>` / `D10` lands on
                        the cell the extraction read.
  * sheets_from_text()  the same grid rebuilt from Silver's cell-addressed text (`S1R10: A=1 | B=SKU-1 ...`), used when
                        the original workbook isn't reachable (e.g. fallback orders, which have no citations to name it).
  * eml_attachment()    a document that came inside an .eml: the attachment bytes (stdlib email parser).
  * citation_rows()     review_citations rows -> JSON-safe dicts for the frontend.
"""
from __future__ import annotations

import csv
import datetime as _dt
import email
import email.policy
import io
import re
from itertools import islice
from pathlib import PurePosixPath
from typing import Any, Iterable, Iterator

MAX_ROWS = 500
MAX_COLS = 40
MAX_SHEETS = 20
MAX_TEXT_CHARS = 50_000
SHEET_EXT = {".xlsx", ".xlsm", ".xls", ".csv"}
MAIL_EXT = {".eml", ".msg"}
# the only Volume folders documents are served from: files dropped for the pipeline, Outlook-connector exports
SERVED_DIRS = ("inbound_docs", "outlook_attachments")


# ------------------------------------------------------------------------------------------------ allow-list
def volume_path(source_path: str) -> str:
    """dbfs:/Volumes/... (Spark file paths) -> /Volumes/... (Files API)."""
    return source_path[len("dbfs:"):] if source_path.startswith("dbfs:") else source_path


def allowed_path(source_path: str | None, catalog: str, schema: str, volume: str) -> bool:
    """True only for a file under /Volumes/<catalog>/<schema>/<volume>/{inbound_docs,outlook_attachments}/ (no '..')."""
    if not source_path or not (catalog and schema and volume):
        return False
    parts = volume_path(source_path).split("/")
    root = ["", "Volumes", catalog, schema, volume]
    return (len(parts) > len(root) + 1 and parts[: len(root)] == root and parts[len(root)] in SERVED_DIRS
            and all(p not in ("", ".", "..") for p in parts[len(root):]))


def ext_of(name: str | None) -> str:
    return PurePosixPath(name or "").suffix.lower()


# ------------------------------------------------------------------------------------------------ cells (= Silver)
def fmt_cell(v: Any) -> str | None:
    """One cell as Silver renders it (02_silver._fmt_cell); None/'' -> None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        if v.is_integer():
            return str(int(v))
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()[:10] if isinstance(v, _dt.datetime) and v.time() == _dt.time(0) else v.isoformat()
    parts = [" ".join(p.split()).rstrip("/").strip() for p in str(v).replace("\r", "\n").split("\n")]
    t = " / ".join(p for p in parts if p)
    return t if t and t.lower() != "nan" else None


def col_letter(i: int) -> str:
    """0-based column index -> spreadsheet letter (0 -> A, 26 -> AA)."""
    out, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def col_index(letters: str) -> int:
    """'A' -> 0, 'AA' -> 26."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def bounded_rows(it: Iterable, max_blank_run: int = 2000) -> Iterator[tuple[int, list]]:
    """(row_number from 1, values) with trailing empty cells trimmed; blank rows skipped (02_silver._bounded_rows)."""
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


def _xlsx_sheets(data: bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            yield ws.title, bounded_rows(ws.iter_rows(min_row=1, min_col=1, values_only=True))
    finally:
        wb.close()


def _xls_sheets(data: bytes):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data, on_demand=True)
    for sh in wb.sheets():
        rows = ([sh.cell_value(r, c) if sh.cell_type(r, c) not in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) else None
                 for c in range(sh.ncols)] for r in range(sh.nrows))
        yield sh.name, bounded_rows(rows)


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def _csv_sheets(text: str):
    try:
        dialect = csv.Sniffer().sniff(text[:20000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    yield "csv", bounded_rows(csv.reader(io.StringIO(text), dialect))


def _sheet(index: int, name: str, rows: Iterable[tuple[int, list]], formatted: bool = False) -> dict:
    out, n_cols, truncated = [], 0, False
    for r, vals in islice(rows, MAX_ROWS + 1):
        if len(out) == MAX_ROWS:
            truncated = True
            break
        if len(vals) > MAX_COLS:
            truncated = True
        cells = [(v if formatted else fmt_cell(v)) or "" for v in vals[:MAX_COLS]]
        n_cols = max(n_cols, len(cells))
        out.append({"r": r, "cells": cells})
    for row in out:                                       # rectangular grid
        row["cells"] += [""] * (n_cols - len(row["cells"]))
    return {"index": index, "name": name, "rows": out, "n_cols": n_cols, "truncated": truncated}


def sheet_preview(data: bytes, ext: str) -> dict:
    """Workbook/csv bytes -> {"kind": "sheet", "sheets": [...], "truncated": bool}. Raises ValueError if unreadable."""
    try:
        if ext in (".xlsx", ".xlsm"):
            sheets = _xlsx_sheets(data)
        elif ext == ".xls":
            sheets = _xls_sheets(data)
        elif ext == ".csv":
            sheets = _csv_sheets(decode(data))
        else:
            raise ValueError(f"not a spreadsheet: {ext or '(no extension)'}")
        # numbered like Silver: every yielded sheet counts (empty ones too), from 1
        out = [_sheet(n, name, rows) for n, (name, rows) in islice(enumerate(sheets, 1), MAX_SHEETS)]
    except ValueError:
        raise
    except Exception as e:  # corrupt / not really a workbook
        raise ValueError(f"could not read the spreadsheet: {e}") from e
    return {"kind": "sheet", "sheets": out, "truncated": any(s["truncated"] for s in out)}


_SHEET_HEAD = re.compile(r"^=== Sheet S(\d+): (.*?) ===")
_ROW = re.compile(r"^S(\d+)R(\d+): (.*)$")
_CELL_SPLIT = re.compile(r" \| (?=[A-Z]{1,3}=)")


def sheets_from_text(text: str) -> dict | None:
    """Silver's cell-addressed text -> the same grid shape as sheet_preview, or None if the text isn't in that format.
    Only non-empty cells are known (the text omits blanks), which is all a reviewer needs."""
    if not text or not _SHEET_HEAD.match(text.lstrip()):
        return None
    sheets: dict[int, dict] = {}
    for line in text.splitlines():
        m = _SHEET_HEAD.match(line)
        if m:
            sheets.setdefault(int(m.group(1)), {"name": m.group(2), "rows": []})
            continue
        m = _ROW.match(line)
        if not m:
            continue
        s = sheets.setdefault(int(m.group(1)), {"name": f"Sheet {m.group(1)}", "rows": []})
        vals: list = []
        for part in _CELL_SPLIT.split(m.group(3)):
            col, _, val = part.partition("=")
            if not re.fullmatch(r"[A-Z]{1,3}", col):
                continue
            i = col_index(col)
            vals += [None] * (i + 1 - len(vals))
            vals[i] = val
        s["rows"].append((int(m.group(2)), vals))
    if not sheets:
        return None
    out = [_sheet(n, s["name"], s["rows"], formatted=True) for n, s in sorted(sheets.items())[:MAX_SHEETS]]
    return {"kind": "sheet", "sheets": out, "truncated": any(s["truncated"] for s in out)}


# ------------------------------------------------------------------------------------------------ mail containers
def eml_attachment(data: bytes, filename: str) -> bytes:
    """The attachment `filename` of an .eml (also inside attached messages). Raises LookupError if absent."""
    msg = email.message_from_bytes(data, policy=email.policy.default)
    for part in msg.walk():
        if part.get_filename() == filename:
            payload = part.get_payload(decode=True)
            if payload is not None:
                return payload
    raise LookupError(f"attachment {filename!r} not found in the message")


# ------------------------------------------------------------------------------------------------ citations
CITATION_COLS = [
    "order_idx", "li_idx", "field", "value", "confidence", "citation_id", "source_kind", "page_index",
    "x1", "y1", "x2", "y2", "element_id", "element_type", "table_row_index", "table_row_count",
    "sheet_index", "sheet_name", "row_number", "cell_ref", "char_start", "char_stop", "snippet",
]


def citation_rows(rows: list[dict]) -> list[dict]:
    """review_citations rows -> the columns the frontend uses (JSON-safe; ints/floats as numbers)."""
    out = []
    for r in rows:
        c = {k: r.get(k) for k in CITATION_COLS}
        for k in ("confidence", "x1", "y1", "x2", "y2"):
            if c[k] is not None:
                c[k] = float(c[k])
        out.append(c)
    out.sort(key=lambda c: (c["order_idx"] or 0, -1 if c["li_idx"] is None else c["li_idx"], c["field"] or ""))
    return out


def source_of(rows: list[dict]) -> tuple[str | None, str | None]:
    """(source_path, attachment_filename) the citations of one order point at (they all share one document)."""
    for r in rows:
        if r.get("source_path"):
            return r["source_path"], r.get("attachment_filename")
    return None, None
