"""Hybrid extraction: routing, fallback and per-document pick (pure Python; unit-tested; used by Gold + harness).

Primary = ai_extract v2.1 precision (layout VARIANT for PDFs/images/Word, text otherwise). Fallback = ai_query (the
registry prompt, as before). SAP master-data matching is deliberately NOT an input here.
  pre_route()       documents sent straight to ai_query (size guard; plain-words reason)
  fallback_reason() why an ai_extract result can't be trusted (silent failure, no lines, cut off, codes missing)
  doc_score()       Gold's deterministic checks -> (completeness, verified share) used to pick when both ran
  pick()            'ai_extract' | 'ai_query' for a document where both ran (tie -> ai_extract)
"""
import json
import re

DEFAULTS = {
    "max_chars": 400_000,        # pre-route: parsed text longer than this
    "max_rows": 3_000,           # pre-route: spreadsheet rows / PDF table rows above this
    "min_completeness": 0.8,     # fallback: extracted < 80% of the filled quantity rows Gold counts ...
    "min_missing_rows": 3,       # ... and at least this many rows missing
    "min_code_coverage": 0.5,    # fallback: fewer than half the lines have a code while the text has codes
    "min_verified": 0.5,         # fallback: fewer than half the lines pass Gold's code + quantity grounding check
}
_GRID_ROW_RE = re.compile(r"(?m)^S\d+R\d+:")
_CODE_TOKEN_RE = re.compile(r"\b(?=[A-Z0-9\-]*\d)(?=[A-Z0-9\-]*[A-Z0-9]{5})[A-Z0-9][A-Z0-9\-]{4,19}\b")


def config(overrides=None):
    c = dict(DEFAULTS)
    for k, v in (overrides or {}).items():
        if v is None or str(v).strip() == "":
            continue
        c[k] = type(DEFAULTS[k])(float(v)) if isinstance(DEFAULTS[k], int) else float(v)
    return c


def est_rows(text):
    """Rough size of a document's tables: spreadsheet rows, else HTML table rows, else text lines."""
    t = text or ""
    n = len(_GRID_ROW_RE.findall(t))
    if n:
        return n
    n = t.lower().count("<tr")
    return n if n else t.count("\n") + 1


def pre_route(text, cfg=None):
    """Plain-words reason to skip ai_extract and read the document with ai_query, or None."""
    cfg = cfg or DEFAULTS
    n = len(text or "")
    if n > cfg["max_chars"]:
        return f"Very large document ({n:,} characters): read with the fallback extractor"
    r = est_rows(text)
    if r > cfg["max_rows"]:
        return f"Very large table ({r:,} rows): read with the fallback extractor"
    return None


def _ordered_lines(po):
    out = []
    for o in (po or {}).get("orders") or []:
        for l in o.get("line_items") or []:
            try:
                if l.get("quantity") is not None and float(l["quantity"]) > 0:
                    out.append(l)
            except (TypeError, ValueError):
                pass
    return out


def _kept_lines(checks):
    """Gold check lines with a positive quantity that Gold does not drop."""
    return [x for o in (checks or {}).get("orders") or [] for x in o.get("lines") or []
            if x.get("qty_grounded") is not None and not x.get("drop")]


def doc_score(checks, po):
    """(completeness, verified share) from Gold's deterministic checks of one extraction."""
    ck = json.loads(checks) if isinstance(checks, str) else (checks or {})
    exp, ext = ck.get("expected_lines"), ck.get("extracted_lines")
    if exp is None or max(exp or 0, ext or 0) == 0:
        comp = 1.0
    else:
        comp = min(exp, ext or 0) / max(exp, ext or 0)
    kept = _kept_lines(ck)
    ver = (sum(1 for x in kept if x.get("sku_in_source") and x.get("qty_grounded")) / len(kept)) if kept else 0.0
    return comp, ver


def fallback_reason(status, error, po, checks, text, cfg=None):
    """Why the ai_extract result needs the fallback (plain words), or None if it can be used as is."""
    cfg = cfg or DEFAULTS
    if status != "ok":
        if error and str(error).startswith("empty response"):
            return "ai_extract returned no result (silent failure)"
        if status == "unparseable":
            return "ai_extract output could not be read"
        return f"ai_extract failed: {str(error or status)[:160]}"
    lines = _ordered_lines(po)
    if not lines:
        return "ai_extract found no order lines"
    ck = json.loads(checks) if isinstance(checks, str) else (checks or {})
    exp, ext = ck.get("expected_lines"), ck.get("extracted_lines")
    if exp and (ext or 0) < cfg["min_completeness"] * exp and exp - (ext or 0) >= cfg["min_missing_rows"]:
        return f"ai_extract returned {ext or 0} of {exp} filled quantity rows (looks cut off)"
    with_code = sum(1 for l in lines if str(l.get("material_or_sku") or "").strip())
    if with_code < cfg["min_code_coverage"] * len(lines):
        codes_in_text = len(set(_CODE_TOKEN_RE.findall((text or "").upper())))
        if codes_in_text >= len(lines):
            return (f"ai_extract left the product code empty on {len(lines) - with_code} of {len(lines)} lines "
                    "although the document has codes")
    kept = _kept_lines(ck)
    if kept:
        ok = sum(1 for x in kept if x.get("sku_in_source") and x.get("qty_grounded"))
        if ok < cfg["min_verified"] * len(kept):
            return f"only {ok} of {len(kept)} ai_extract lines could be checked against the document"
    return None


def pick(b_usable, b_score, a_ok, a_score):
    """Both ran: the one that passes Gold's checks better (completeness, then verified share); tie -> ai_extract."""
    if not b_usable:
        return "ai_query"
    if not a_ok:
        return "ai_extract"
    a = tuple(round(x, 3) for x in a_score)
    b = tuple(round(x, 3) for x in b_score)
    return "ai_query" if a > b else "ai_extract"
