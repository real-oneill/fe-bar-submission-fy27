"""Citation-backed grounding for ai_extract v2.1 output (pure Python; unit-tested).

ai_extract returns `metadata.citations` and per-field `citation_ids`:
  - text input   -> chunk_type "span":  {"id", "start", "stop"}  (character offsets into the input text)
  - layout input -> chunk_type "bbox":  {"id", "bbox": [{"coord": [x1, y1, x2, y2], "page_id"}]}  (page boxes of the
                    ai_parse_document VARIANT; mapped here to the parse elements whose box matches)
A line is CITATION-VERIFIED when the text its material/quantity cite contains the code and, in the same table row
(or the same line for plain text), the quantity. That is the citation counterpart of Gold's line_verified.
"""
import json
import re

from extract_adapter import to_number


def _norm(s):
    return re.sub(r"[\s\-_.]", "", str(s or "")).upper()


def _num_candidates(tok):
    t = re.sub(r"[^\d,.\-]", "", str(tok or ""))
    if not re.search(r"\d", t):
        return set()
    out = set()
    for dec, thou in ((".", ","), (",", ".")):
        try:
            out.add(float(t.replace(thou, "").replace(dec, ".")))
        except ValueError:
            pass
    n = to_number(t)
    if n is not None:
        out.add(n)
    return out


def _has_qty(text, qty):
    if qty is None:
        return False
    return any(abs(c - float(qty)) < 1e-6 for tok in re.findall(r"[\d][\d.,]*", str(text or ""))
               for c in _num_candidates(tok))


def _rows(text):
    """Units in which code and quantity must co-occur: HTML table rows, else lines."""
    t = str(text or "")
    if "<tr" in t.lower():
        rows = re.split(r"(?i)</tr\s*>", t)
        return [re.sub(r"<[^>]+>", " | ", r) for r in rows if r.strip()]
    return t.splitlines() or [t]


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _contains(outer, inner, tol=2):
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1] and
            outer[2] + tol >= inner[2] and outer[3] + tol >= inner[3])


def element_index(elements):
    """ai_parse_document elements (list of dicts with bbox [{coord, page_id}] and content) -> [(page, coord, text)]."""
    out = []
    for e in elements or []:
        txt = e.get("content") or ""
        for bb in e.get("bbox") or []:
            c = bb.get("coord")
            if c and len(c) == 4:
                out.append((bb.get("page_id"), [float(x) for x in c], txt))
    return out


def cited_text(cit, text=None, elements_idx=None):
    """Text a single citation points at: the span, or the parse elements whose box matches the cited box."""
    if cit is None:
        return None, None
    if "start" in cit and text is not None:
        return text[int(cit["start"]):int(cit["stop"])], "span"
    if cit.get("bbox") and elements_idx is not None:
        parts = []
        for bb in cit["bbox"]:
            c, p = bb.get("coord"), bb.get("page_id")
            if not c:
                continue
            c = [float(x) for x in c]
            hits = [t for (pg, ec, t) in elements_idx if pg == p and (_iou(c, ec) >= 0.5 or _contains(c, ec))]
            if not hits:   # cited box smaller than its element (e.g. a cell): the element that contains it
                hits = [t for (pg, ec, t) in elements_idx if pg == p and _contains(ec, c)]
            parts += hits
        return ("\n".join(parts) if parts else None), "bbox"
    return None, None


def _is_wrapped(x):
    return isinstance(x, dict) and "value" in x and set(x) <= {"value", "citation_ids", "confidence_score"}


def check(b_raw, text=None, elements=None):
    """b_raw: ai_extract result (dict / JSON). text: the input text (span citations). elements: parse elements
    (bbox citations). Returns a per-document summary dict (None if no usable response)."""
    if isinstance(b_raw, str):
        try:
            b_raw = json.loads(b_raw)
        except ValueError:
            return None
    if not isinstance(b_raw, dict) or not isinstance(b_raw.get("response"), dict):
        return None
    meta = b_raw.get("metadata") or {}
    cits = {c.get("id"): c for c in (meta.get("citations") or []) if isinstance(c, dict)}
    eidx = element_index(elements) if elements is not None else None
    orders = b_raw["response"].get("orders")
    if _is_wrapped(orders):
        orders = orders["value"]
    if not isinstance(orders, list):
        return None
    n_cits = len(cits)
    s = {"chunk_type": meta.get("chunk_type"), "n_citations": n_cits,
         "pages_cited": len({bb.get("page_id") for c in cits.values() for bb in (c.get("bbox") or [])}),
         "n_lines": 0, "lines_with_cite": 0, "lines_cite_mapped": 0, "sku_cite_ok": 0, "qty_cite_ok": 0,
         "line_cite_verified": 0, "n_po": 0, "po_cite_ok": 0, "cited_chars": 0, "n_cited": 0}
    cache = {}

    def txt(ids):
        out = []
        for i in ids or []:
            if i not in cache:
                cache[i] = cited_text(cits.get(i), text, eidx)[0]
            if cache[i]:
                out.append(cache[i])
        return "\n".join(out) if out else None

    for o in orders:
        if not isinstance(o, dict):
            continue
        po = o.get("po_number")
        if _is_wrapped(po) and po.get("value"):
            s["n_po"] += 1
            t = txt(po.get("citation_ids"))
            s["po_cite_ok"] += bool(t) and _norm(po["value"]) in _norm(t)
        lines = o.get("line_items")
        if _is_wrapped(lines):
            lines = lines["value"]
        for l in lines or []:
            if not isinstance(l, dict):
                continue
            m, q = l.get("material_or_sku"), l.get("quantity")
            mv = m.get("value") if _is_wrapped(m) else m
            qv = to_number(q.get("value") if _is_wrapped(q) else q)
            if qv is None or qv <= 0:
                continue
            s["n_lines"] += 1
            ids = list(dict.fromkeys((m.get("citation_ids") if _is_wrapped(m) else []) +
                                     (q.get("citation_ids") if _is_wrapped(q) else [])))
            if not ids:
                continue
            s["lines_with_cite"] += 1
            t = txt(ids)
            if not t:
                continue
            s["lines_cite_mapped"] += 1
            s["cited_chars"] += len(t)
            s["n_cited"] += 1
            code = _norm(mv)
            sku_ok = bool(code) and code in _norm(t)
            s["sku_cite_ok"] += sku_ok
            qty_ok = _has_qty(t, qv)
            s["qty_cite_ok"] += qty_ok
            row_ok = bool(code) and any(code in _norm(r) and _has_qty(r, qv) for r in _rows(t))
            s["line_cite_verified"] += row_ok
    return s


# =====================================================================================================================
# Citation rows for the app (Gold `extraction_citations`): one row per (order, line, field, citation, location)
# =====================================================================================================================
# Layout input: ai_parse_document 2.0 boxes are PIXELS of the page rendered at 200 DPI, origin top-left, y down
# (verified on an A4 page: 1654 x 2339 px image for a 595.3 x 841.9 pt page). PDF points = px * 72 / 200.
LAYOUT_DPI = 200
CITATION_FIELDS = ("order_idx", "li_idx", "field", "value", "confidence", "citation_id", "source_kind",
                   "page_index", "x1", "y1", "x2", "y2", "element_id", "element_type", "table_row_index",
                   "table_row_count", "sheet_index", "sheet_name", "row_number", "cell_ref", "char_start",
                   "char_stop", "snippet")
CITATION_DDL = (
    "array<struct<order_idx:int,li_idx:int,field:string,value:string,confidence:double,citation_id:int,"
    "source_kind:string,page_index:int,x1:double,y1:double,x2:double,y2:double,element_id:int,element_type:string,"
    "table_row_index:int,table_row_count:int,sheet_index:int,sheet_name:string,row_number:int,cell_ref:string,"
    "char_start:int,char_stop:int,snippet:string>>")
_SHEET_RE = re.compile(r"^=== Sheet S(\d+): (.*?) ===", re.M)
_ROW_LINE_RE = re.compile(r"^S(\d+)R(\d+): (.*)$", re.M)
_CELL_RE = re.compile(r"^([A-Z]{1,3})=(.*)$")
SNIPPET_MAX = 300


def _elements_full(elements):
    """[(element_id, type, page, coord, content)] for every bbox of every parse element."""
    out = []
    for i, e in enumerate(elements or []):
        for bb in e.get("bbox") or []:
            c = bb.get("coord")
            if c and len(c) == 4:
                out.append((e.get("id", i), e.get("type"), bb.get("page_id"), [float(x) for x in c],
                            e.get("content") or ""))
    return out


def _best_element(eidx, page, coord):
    best, score = None, 0.0
    for el in eidx:
        if el[2] != page:
            continue
        s = _iou(coord, el[3])
        if s == 0 and (_contains(el[3], coord) or _contains(coord, el[3])):
            s = 0.01
        if s > score:
            best, score = el, s
    return best


def _table_rows(html):
    rows = [r for r in re.split(r"(?i)</tr\s*>", html or "") if "<t" in r.lower()]
    return [re.sub(r"<[^>]+>", " | ", r) for r in rows]


def _value_in(value, text, numeric):
    if value is None or text is None:
        return False
    if numeric:
        return _has_qty(text, value)
    v = _norm(value)
    return bool(v) and v in _norm(text)


def _sheet_names(text):
    return {int(m.group(1)): m.group(2) for m in _SHEET_RE.finditer(text or "")}


def _grid_rows_in_span(text, start, stop):
    """Cell-addressed rows ("S1R35: A=.. | E=3") overlapping [start, stop) -> [(sheet, row, {letter: value})]."""
    out = []
    for m in _ROW_LINE_RE.finditer(text):
        if m.end() <= start or m.start() >= stop:
            continue
        cells = {}
        for part in m.group(3).split(" | "):
            c = _CELL_RE.match(part)
            if c:
                cells[c.group(1)] = c.group(2)
        out.append((int(m.group(1)), int(m.group(2)), cells))
    return out


def _cell_for(cells, value, numeric):
    for letter, v in cells.items():
        if numeric and value is not None and any(abs(c - float(value)) < 1e-6 for c in _num_candidates(v)):
            return letter
        if not numeric and value is not None and _norm(v) == _norm(value) and _norm(v):
            return letter
    for letter, v in cells.items():          # containment (e.g. code inside a longer cell)
        if not numeric and value is not None and _norm(value) and _norm(value) in _norm(v):
            return letter
    return None


def citation_rows(b_raw, a_json, conf_json, text=None, elements=None):
    """ai_extract output + the adapter's output (A shape, conf with citation ids) -> list of citation dicts
    (CITATION_FIELDS). `text` = the input text (span citations: spreadsheets map to sheet/row/cell, other text to a
    snippet); `elements` = ai_parse_document elements (bbox citations: page + box + element + table row)."""
    raw = json.loads(b_raw) if isinstance(b_raw, str) else (b_raw or {})
    a = json.loads(a_json) if isinstance(a_json, str) else (a_json or {})
    conf = json.loads(conf_json) if isinstance(conf_json, str) else (conf_json or {})
    cits = {c.get("id"): c for c in ((raw.get("metadata") or {}).get("citations") or []) if isinstance(c, dict)}
    if not cits:
        return []
    eidx = _elements_full(elements) if elements else []
    grid = bool(text) and bool(_ROW_LINE_RE.search(text or ""))
    sheets = _sheet_names(text) if grid else {}
    out = []

    def emit(oi, li, field, value, confv, ids, anchor_code=None):
        numeric = field in ("quantity", "unit_price", "line_no")
        for cid in ids or []:
            c = cits.get(cid)
            if not c:
                continue
            base = dict.fromkeys(CITATION_FIELDS)
            base.update(order_idx=oi, li_idx=li, field=field, value=None if value is None else str(value),
                        confidence=confv, citation_id=int(cid))
            if c.get("bbox"):
                for bb in c["bbox"]:
                    co = bb.get("coord")
                    if not co or len(co) != 4:
                        continue
                    co = [float(x) for x in co]
                    r = dict(base, source_kind="layout", page_index=bb.get("page_id"),
                             x1=co[0], y1=co[1], x2=co[2], y2=co[3])
                    el = _best_element(eidx, bb.get("page_id"), co) if eidx else None
                    if el is not None:
                        r.update(element_id=el[0], element_type=el[1], snippet=(el[4] or "")[:SNIPPET_MAX])
                        if "<tr" in (el[4] or "").lower():
                            rows = _table_rows(el[4])
                            key = anchor_code if anchor_code else value
                            hit = next((i for i, row in enumerate(rows)
                                        if _value_in(key, row, numeric and not anchor_code)), None)
                            r.update(table_row_count=len(rows), table_row_index=hit)
                            if hit is not None:
                                r["snippet"] = rows[hit].strip(" |")[:SNIPPET_MAX]
                    out.append(r)
            elif "start" in c and text is not None:
                st, sp = int(c["start"]), int(c["stop"])
                if grid:
                    rows = _grid_rows_in_span(text, st, sp)
                    if anchor_code:                   # the line's own row: where its code is
                        own = [x for x in rows if any(_norm(anchor_code) and _norm(anchor_code) in _norm(v)
                                                      for v in x[2].values())]
                        rows = own or rows
                    else:
                        own = [x for x in rows if _cell_for(x[2], value, numeric)]
                        rows = own or rows
                    for sh, rn, cells in rows[:5] or [(None, None, {})]:
                        letter = _cell_for(cells, value, numeric) if cells else None
                        out.append(dict(base, source_kind="sheet", sheet_index=sh, sheet_name=sheets.get(sh),
                                        row_number=rn, cell_ref=f"{letter}{rn}" if letter and rn else None,
                                        char_start=st, char_stop=sp,
                                        snippet=" | ".join(f"{k}={v}" for k, v in cells.items())[:SNIPPET_MAX]))
                else:
                    out.append(dict(base, source_kind="text", char_start=st, char_stop=sp,
                                    snippet=text[st:sp][:SNIPPET_MAX]))
    for oi, o in enumerate(a.get("orders") or []):
        oc = (conf.get("orders") or [{}] * (oi + 1))[oi] if oi < len(conf.get("orders") or []) else {}
        for f, ids in (oc.get("cites") or {}).items():
            emit(oi, None, f, o.get(f), (oc.get("fields") or {}).get(f), ids)
        for li, l in enumerate(o.get("line_items") or []):
            lcits = (oc.get("line_cites") or [])[li] if li < len(oc.get("line_cites") or []) else {}
            lconf = (oc.get("lines") or [])[li] if li < len(oc.get("lines") or []) else {}
            code = l.get("material_or_sku")
            for f, ids in lcits.items():
                emit(oi, li, f, l.get(f), lconf.get(f), ids, anchor_code=code if f != "material_or_sku" else None)
    return out
