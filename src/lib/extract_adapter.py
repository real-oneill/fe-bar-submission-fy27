"""Unwrap adapter: ai_extract v2.1 output -> arm A's JSON shape (+ per-field confidence).

ai_extract v2.1 wraps every scalar (including scalar array items) as {"value", "citation_ids", "confidence_score"};
arrays and objects are returned as plain arrays/objects of wrapped leaves. Arm A's shape is the registered prompt's
response schema: {"orders": [{po_number, ..., header_confidence, line_items: [{..., line_confidence}]}]}.
The output goes through the SAME downstream code as A (Gold extraction_checks, SAP resolution, purchase_orders).
Plain Python: used as a Spark UDF in the notebooks and unit-tested locally.
"""
import json
import re
import unicodedata

from extract_spec import HEADER_FIELDS, LINE_FIELDS   # same field lists as the schema sent to ai_extract

# header fields whose confidence makes up header_confidence (the ones a reviewer cares about)
HEADER_CONF_FIELDS = ("po_number", "customer_name", "order_date", "currency")
LINE_CONF_FIELDS = ("material_or_sku", "quantity")
NUMERIC_LINE = ("quantity", "unit_price")
_PLACEHOLDERS = {"", "null", "none", "n/a", "na", "unknown", "-", "--"}


def _is_wrapped(x):
    return isinstance(x, dict) and "value" in x and set(x) <= {"value", "citation_ids", "confidence_score"}


def unwrap(x):
    """Recursively strip {value, citation_ids, confidence_score} wrappers."""
    if _is_wrapped(x):
        return unwrap(x["value"])
    if isinstance(x, dict):
        return {k: unwrap(v) for k, v in x.items()}
    if isinstance(x, list):
        return [unwrap(v) for v in x]
    return x


def _conf(x):
    if _is_wrapped(x):
        c = x.get("confidence_score")
        return float(c) if isinstance(c, (int, float)) else None
    return None


def _cites(x):
    return list(x.get("citation_ids") or []) if _is_wrapped(x) else []


def to_number(v):
    """Model number -> float. Strings are read in either locale ('1.000' -> 1000, '3,5' -> 3.5, '1.234,50' ->
    1234.5, '920.000' -> 920000); None/'' -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:            # the later one is the decimal separator
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        # '3,5' / '12,50' decimal; '1,000' / '12,000,000' thousands
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")           # '1.000' / '1.000.000' thousands (European order forms)
    try:
        return float(s)
    except ValueError:
        return None


def _clean_str(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return None if s.lower() in _PLACEHOLDERS else s


def _min(vals):
    vals = [v for v in vals if v is not None]
    return min(vals) if vals else None


def adapt(b):
    """ai_extract result (dict or JSON string: {"response", "error_message", "metadata"}) ->
    (a_json_dict | None, conf_dict, error | None).

    conf_dict = {"orders": [{"fields": {field: conf}, "cites": {field: [citation ids]}, "lines": [{field: conf}],
                             "line_cites": [{field: [citation ids]}]}], "n_citations": int}
    (indices align with the A-shaped output: empty items are dropped from both)
    header_confidence / line_confidence in the A-shaped output are the MIN confidence over HEADER_CONF_FIELDS /
    LINE_CONF_FIELDS that have a value (None when ai_extract gave no scores)."""
    if b is None:
        return None, {}, "null result"
    if isinstance(b, str):
        try:
            b = json.loads(b)
        except ValueError as e:
            return None, {}, f"unparseable: {e}"
    if b.get("error_message"):
        return None, {}, str(b["error_message"])
    resp = b.get("response")
    if not isinstance(resp, dict):
        return None, {}, "no response"
    raw_orders = resp.get("orders")
    if _is_wrapped(raw_orders):
        raw_orders = raw_orders["value"]
    if raw_orders is None:
        # seen on the largest documents: {"orders": {"value": null, "confidence_score": null}} and no error —
        # a silent failure, not "no orders in the document"
        return None, {}, "empty response (orders = null, no error message)"
    if not isinstance(raw_orders, list):
        return None, {}, "orders is not an array"
    orders, confs = [], []
    for ro in raw_orders:
        if not isinstance(ro, dict):
            continue
        o, oc = {}, {"fields": {}, "cites": {}, "lines": [], "line_cites": []}
        for f in HEADER_FIELDS:
            if f in ro:
                v = _clean_str(unwrap(ro[f]))
                if v is not None:
                    o[f] = v
                    oc["fields"][f] = _conf(ro[f])
                    if _cites(ro[f]):
                        oc["cites"][f] = _cites(ro[f])
        lines = []
        raw_lines = ro.get("line_items")
        if _is_wrapped(raw_lines):
            raw_lines = raw_lines["value"]
        for rl in raw_lines or []:
            if not isinstance(rl, dict):
                continue
            l, lc, lcit = {}, {}, {}
            for f in LINE_FIELDS:
                if f not in rl:
                    continue
                raw = unwrap(rl[f])
                if f in NUMERIC_LINE:
                    v = to_number(raw)
                elif f == "line_no":
                    n = to_number(raw)
                    v = int(n) if n is not None and float(n).is_integer() else None
                else:
                    v = _clean_str(raw)
                if v is not None:
                    l[f] = v
                    lc[f] = _conf(rl[f])
                    if _cites(rl[f]):
                        lcit[f] = _cites(rl[f])
            if not l:                         # all-empty item
                continue
            l["line_confidence"] = _min(lc.get(f) for f in LINE_CONF_FIELDS if f in l)
            lines.append(l)
            oc["lines"].append(lc)
            oc["line_cites"].append(lcit)
        o["header_confidence"] = _min(oc["fields"].get(f) for f in HEADER_CONF_FIELDS if f in o)
        o["line_items"] = lines
        orders.append(o)
        confs.append(oc)
    n_cit = len(((b.get("metadata") or {}).get("citations")) or [])
    return {"orders": orders}, {"orders": confs, "n_citations": n_cit}, None


def adapt_json(b_json):
    """String in, (a_json_string | None, conf_json_string, error | None) out — the Spark UDF body."""
    try:
        a, c, err = adapt(b_json)
    except Exception as e:  # noqa — an adapter bug must surface as a per-document failure, not a job failure
        return None, "{}", f"adapter error: {e}"[:300]
    return (json.dumps(a, ensure_ascii=False) if a is not None else None), json.dumps(c), err


def _ntext(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower())


def drop_unprinted_headers(a, text):
    """ai_extract sometimes names an ordered-quantity column that is not in the document (e.g. 'ordered_amount'):
    Gold's checks would then look for quantities under the wrong header. A header text the document doesn't contain
    is not a header — drop it (same rule the ai_query prompt states: copy labels as printed, otherwise omit).
    Returns (a, n_dropped)."""
    if not a or not text:
        return a, 0
    nt = _ntext(text)
    n = 0
    for o in a.get("orders") or []:
        qc = o.get("quantity_column")
        if qc and _ntext(qc) and _ntext(qc) not in nt:
            o.pop("quantity_column", None)
            n += 1
    return a, n
