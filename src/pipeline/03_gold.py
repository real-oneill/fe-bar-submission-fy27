# ============================================================
# Order Intake — Lakeflow Declarative Pipeline · Phase 3: GOLD (registry-driven)
# The extraction prompt + response schema are LOADED FROM the MLflow Prompt Registry
# at pipeline runtime (prompts:/<catalog>.<schema>.order_extraction@production) — NOT hardcoded.
# Promoting a new prompt version in the registry flows through automatically on the next run.
# catalog/schema/serving endpoint are injected from the pipeline `configuration` (bundle variables).
# ============================================================
import json
import re
import unicodedata
import dlt
import mlflow
from pyspark.sql import functions as F

CAT = spark.conf.get("order_intake.catalog")
SCH = spark.conf.get("order_intake.schema")
ENDPOINT = spark.conf.get("order_intake.serving_endpoint", "databricks-claude-haiku-4-5")
S = f"{CAT}.{SCH}"
# Override order_intake.prompt_uri to A/B a candidate version (e.g. ".../order_extraction/3") in a dev run.
PROMPT_URI = spark.conf.get("order_intake.prompt_uri", f"prompts:/{S}.order_extraction@production")
MAX_OUTPUT_TOKENS = 32000
# Master data: 'demo' = the template tables (customer_master / retailer_sku_map / product_master);
# 'sap' = the real SAP masters, via the oi_sap_* working tables refreshed by src/setup/01b_sap_masters.py.
MASTER_SOURCE = spark.conf.get("order_intake.master_source", "demo")
if MASTER_SOURCE not in ("demo", "sap"):
    raise ValueError(f"order_intake.master_source must be 'demo' or 'sap', got {MASTER_SOURCE!r}")
# Extraction: 'hybrid' (default) = ai_extract v2.1 precision first (the ai_parse_document layout for PDFs/images/Word,
# the cell-addressed / plain text otherwise), ai_query (the registry prompt below) as the fallback for documents
# ai_extract can't handle; 'ai_query' = ai_query for every document (the previous behaviour, unchanged).
EXTRACTION_MODE = spark.conf.get("order_intake.extraction_mode", "hybrid")
if EXTRACTION_MODE not in ("hybrid", "ai_query"):
    raise ValueError(f"order_intake.extraction_mode must be 'hybrid' or 'ai_query', got {EXTRACTION_MODE!r}")
HYBRID = EXTRACTION_MODE == "hybrid"
# Shared code (src/lib) is the order-intake-lib wheel installed in the pipeline environment (resources/
# medallion_pipeline.yml): plain top-level imports, available on the driver and in UDFs on the workers.
if MASTER_SOURCE == "sap":
    import sap_masters as _sm
    import customer_hints as _ch
    SAP_ORGS = _sm.parse_sales_orgs(spark.conf.get("order_intake.sap_sales_orgs", ""))
    PREFIX_LEN = _sm.parse_prefix_len(spark.conf.get("order_intake.material_prefix_len", "6"))
    # orders whose document names no SAP customer: try the sender / subject / file name (oi_customer_hints)
    CUSTOMER_HINTS = spark.conf.get("order_intake.customer_hints", "true").lower() == "true"
if HYBRID:
    import extract_adapter as _xa
    import extract_citations as _xc
    import extract_select as _xsel
    import extract_spec as _xs
    HYBRID_CFG = _xsel.config({
        "max_chars": spark.conf.get("order_intake.hybrid_max_chars", ""),
        "max_rows": spark.conf.get("order_intake.hybrid_max_rows", ""),
        "min_completeness": spark.conf.get("order_intake.hybrid_min_completeness", ""),
        "min_code_coverage": spark.conf.get("order_intake.hybrid_min_code_coverage", ""),
        "min_verified": spark.conf.get("order_intake.hybrid_min_verified", ""),
    })

# ---- load the governed prompt from the UC Prompt Registry (runs at graph-eval time) ----
mlflow.set_registry_uri("databricks-uc")
_pv = mlflow.genai.load_prompt(PROMPT_URI)
_prefix, _suffix = (_pv.template.split("{{document}}") + [""])[:2]
_resp_fmt = json.dumps(_pv.response_format)

if HYBRID:
    # ai_extract schema + instructions, governed next to order_extraction: prompts:/<cat>.<sch>.order_extract_schema
    # (template = instructions, response_format = the ai_extract schema). 'builtin' = the copy in src/lib/extract_spec.py
    # with instructions derived from the order_extraction template above (used by the offline harness).
    SCHEMA_URI = spark.conf.get("order_intake.extract_schema_uri", f"prompts:/{S}.order_extract_schema@production")
    _sv = None
    if SCHEMA_URI != "builtin":
        try:
            _sv = mlflow.genai.load_prompt(SCHEMA_URI)
        except Exception as _e:  # noqa — not registered yet (setup not re-run after the upgrade): use the builtin spec
            print(f"WARNING: {SCHEMA_URI} not loadable ({_e}); using the builtin ai_extract spec")
    if _sv is None:
        _x_instructions, _x_schema = _xs.instructions_from_prompt(_pv.template), _xs.SCHEMA
        _x_version = "builtin" if SCHEMA_URI == "builtin" else "builtin (registry prompt not found)"
    else:
        _x_instructions = _sv.template
        _x_schema = _sv.response_format if isinstance(_sv.response_format, dict) else json.loads(_sv.response_format)
        _x_version = str(_sv.version)


def _sql_lit(s: str) -> str:
    return s.replace("'", "''")


_ORDERS_DDL = (
    "STRUCT<orders:ARRAY<STRUCT<po_number:STRING,po_number_label:STRING,customer_name:STRING,customer_number:STRING,"
    "order_date:STRING,currency:STRING,sales_org:STRING,ship_to:STRING,quantity_column:STRING,"
    "quantity_column_letter:STRING,header_confidence:DOUBLE,"
    "line_items:ARRAY<STRUCT<line_no:INT,source_row:STRING,material_or_sku:STRING,ean:STRING,description:STRING,quantity:DOUBLE,"
    "uom:STRING,unit_price:DOUBLE,line_confidence:DOUBLE>>>>>"
)




# =====================================================================
# Deterministic extraction checks (pure Python; no model self-rating).
# Every extracted value is verified against the parsed source text:
#   - line:  is the SKU in the source row, and is the quantity in the stated ordered-qty column?
#   - order: does the PO number look like a PO and appear in the document? is the customer the supplier?
#   - doc:   completeness — how many rows of the form have a filled ordered-quantity cell vs. extracted lines?
# Spreadsheets are checked on the cell-addressed grid from Silver ("S1R35: A=.. | E=3"); PDFs on the HTML
# tables ai_parse_document emits; plain text (email bodies) on a same-line match.
# =====================================================================
# BEGIN_CHECKS
_ROW_RE = re.compile(r"^(S\d+R\d+): (.*)$", re.M)
_CELL_RE = re.compile(r"^([A-Z]{1,3})=(.*)$")
_TOTAL_RE = re.compile(r"(?i)\b(sub)?total|summe|gesamt|somme|totaal|importe total|zwischensumme\b")
_MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|janv|févr|fevr|mars|avr|mai|juin|juil|août|aout|"
           "sept|okt|dez|märz|marz|mrz|ene|abr|ago|dic|gen|mag|giu|lug|ott")
_DATE_RES = [
    re.compile(r"^\d{1,4}[./-]\d{1,2}[./-]\d{1,4}$"),                       # 26.2.2026, 2026-09-28, 28/09/26
    re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$"),     # 20260226
    re.compile(rf"(?i)^(\d{{1,2}}\.?\s*)?({_MONTHS})[a-zé]*\.?\s+(19|20)\d{{2}}$"),  # Sept 2026 / 21 sept. 2026
]
# month + year inside a longer string ("BDC JUIN 2026") = a title, not a PO. "SEP-2026-1000" (no space) is a PO.
_MONTH_YEAR_RE = re.compile(rf"(?i)\b({_MONTHS})[a-zé]*\.?\s+(19|20)\d{{2}}\b")
_SUPPLIER_RE = re.compile(r"(?i)(maison\s*solenne|\bmaisonsolenne\b|@maisonsolenne\.)")
_SUPPLIER_BRANDS = {
    "solenne", "solenne paris", "kori botanicals", "kori", "atelier noor", "velour cosmetics", "velour",
    "thornfield grooming", "thornfield", "mistral hair", "lune rouge", "ember oak", "ember and oak",
}
_LEGAL_SUFFIX_RE = re.compile(r"\b(gmbh|ag|sas|s a s|sa|ltd|limited|bv|b v|spa|s p a|sl|s l|inc|llc|cosmetics?|beauty|paris|london)\b")


def _norm_code(s):
    return re.sub(r"[\s\-_.]", "", str(s or "")).upper()


def _ascii(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def _num_candidates(s):
    """'1.000' -> {1.0, 1000.0}; '3,5' -> {3.5, 35.0}; 'x' -> set(). Both locales, compared to the model's number."""
    t = re.sub(r"[^\d,.\-]", "", str(s or ""))
    if not re.search(r"\d", t):
        return set()
    out = set()
    for dec, thou in ((".", ","), (",", ".")):
        try:
            out.add(float(t.replace(thou, "").replace(dec, ".")))
        except ValueError:
            pass
    return out


def _qty_matches(cell, qty):
    return qty is not None and any(abs(c - float(qty)) < 1e-6 for c in _num_candidates(cell))


def _positive(cell):
    c = _num_candidates(cell)
    return bool(c) and max(c) > 0


def is_supplier(name):
    """True if `name` is a supplier (Maison Solenne) entity or a bare supplier brand. A salon/store that merely contains a brand is NOT."""
    if not name:
        return False
    if _SUPPLIER_RE.search(_ascii(name)) or _SUPPLIER_RE.search(str(name)):
        return True
    n = re.sub(r"[^a-z0-9 ]", " ", _ascii(name).replace("+", " "))
    n = " ".join(_LEGAL_SUFFIX_RE.sub(" ", n).split())
    return n in _SUPPLIER_BRANDS


def po_issue(po, line_skus):
    """None if `po` looks like a PO number, else a short human-readable problem."""
    if po is None or not str(po).strip():
        return "missing"
    p = str(po).strip()
    if any(r.search(p) for r in _DATE_RES):
        return "looks like a date"
    if not re.search(r"\d", p):
        return "has no digits (looks like a title)"
    if _MONTH_YEAR_RE.search(p):
        return "looks like a title or heading"
    if len(p.split()) > 3 or len(p) > 30:
        return "looks like a title or heading"
    if _norm_code(p) in {_norm_code(s) for s in line_skus if s}:
        return "equals a product code"
    return None


def _grid(text):
    """Cell-addressed text -> {row_label: {letter: value}} preserving order."""
    rows = {}
    for label, body in _ROW_RE.findall(text):
        cells = {}
        for part in body.split(" | "):
            m = _CELL_RE.match(part)
            if m:
                cells[m.group(1)] = m.group(2)
        rows[label] = cells
    return rows


def _html_tables(text):
    """HTML tables from ai_parse_document -> list of (header_cells, [row_cells, ...])."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tables, self.row, self.cell, self.in_cell = [], None, [], False

        def handle_starttag(self, tag, attrs):
            if tag == "table":
                self.tables.append([])
            elif tag == "tr" and self.tables:
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.in_cell, self.cell = True, []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.row is not None and self.in_cell:
                self.row.append(" ".join("".join(self.cell).split()))
                self.in_cell = False
            elif tag == "tr" and self.row is not None and self.tables:
                if any(self.row):
                    self.tables[-1].append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.in_cell:
                self.cell.append(data)

    p = P()
    p.feed(text)
    return [(t[0], t[1:]) for t in p.tables if t]


def _hdr_match(header_cell, qty_header):
    a, b = _ascii(header_cell).strip(), _ascii(qty_header).strip()
    return bool(a) and bool(b) and (a == b or (len(b) >= 3 and b in a) or (len(a) >= 3 and a in b))


def _product_like(cells, skip_key):
    others = [v for k, v in cells.items() if k != skip_key and str(v).strip()]
    return len(others) >= 2 and not any(_TOTAL_RE.search(str(v)) for v in others)


def _filled_rows(grid, letter, qhdr):
    """Labels of rows below the column's header whose `letter` cell holds a positive number on a product-like row.
    With no header text, counting starts at the first non-numeric cell in the column (or row 1)."""
    rows, started = set(), {}
    for label, cells in grid.items():
        sheet = label.split("R")[0]
        v = cells.get(letter)
        if not started.get(sheet):
            if v is None:
                continue
            if qhdr and _hdr_match(v, qhdr) or not _positive(v):
                started[sheet] = True
                continue
            started[sheet] = True          # no header row: this first value is data
        if _positive(v) and _product_like(cells, letter):
            rows.add(label)
    return rows


def _derive_letter(grid, lines, min_share=0.8):
    """The single column whose cell equals the extracted quantity on >= min_share of the lines."""
    from collections import Counter
    votes, n = Counter(), 0
    for l in lines:
        qty, sr = l.get("quantity"), l.get("source_row")
        if qty is None or qty <= 0 or sr not in grid:
            continue
        n += 1
        for k, v in grid[sr].items():
            if _qty_matches(v, qty):
                votes[k] += 1
    if not n or not votes:
        return None
    letter, c = votes.most_common(1)[0]
    return letter if c / n >= min_share else None


def check_document(text, po_json):
    """Return JSON: {"method", "expected_lines", "extracted_lines", "orders":[{idx, po_issue, po_in_source,
    customer_is_supplier, qty_col_resolved, lines:[{idx, sku_in_source, qty_grounded}]}]}"""
    text = text or ""
    po = json.loads(po_json) if po_json else {}
    orders = (po or {}).get("orders") or []
    norm_text = _norm_code(text)
    grid = _grid(text)
    tables = [] if grid else _html_tables(text)
    method = "grid" if grid else ("html" if tables else "text")
    text_lines = text.splitlines()

    expected_rows = set() if method in ("grid", "html") else None
    any_col_resolved = False
    extracted = 0
    out_orders = []
    for oi, o in enumerate(orders):
        lines = o.get("line_items") or []
        skus = [l.get("material_or_sku") for l in lines]
        issue = po_issue(o.get("po_number"), skus)
        po_in_src = bool(o.get("po_number")) and _norm_code(o["po_number"]) in norm_text
        qhdr, qletter = o.get("quantity_column"), (o.get("quantity_column_letter") or "").strip().upper() or None

        # --- resolve the ordered-quantity column and count filled rows (completeness) ---
        col_resolved = False
        letter_derived = False
        html_cols = {}  # table index -> qty column index
        if method == "grid":
            if not qletter and qhdr:  # infer the letter from the header text
                for cells in grid.values():
                    hit = [k for k, v in cells.items() if _hdr_match(v, qhdr)]
                    if hit:
                        qletter = hit[0]
                        break
            rows_l = _filled_rows(grid, qletter, qhdr) if qletter else set()
            if not rows_l:
                # Stated column is empty on every row (header label offset / merged header cell) or no column was
                # given: use the column the model's quantities actually come from, if one column explains them.
                derived = _derive_letter(grid, lines)
                if derived and derived != qletter:
                    qletter, letter_derived = derived, True
                    rows_l = _filled_rows(grid, qletter, None)
            col_resolved = bool(qletter) and bool(rows_l)
            if col_resolved:
                expected_rows |= rows_l
        elif method == "html" and qhdr:
            for ti, (hdr, rows) in enumerate(tables):
                idx = next((i for i, h in enumerate(hdr) if _hdr_match(h, qhdr)), None)
                if idx is None:
                    continue
                html_cols[ti] = idx
                col_resolved = True
                for ri, r in enumerate(rows):
                    cells = {i: v for i, v in enumerate(r)}
                    if idx < len(r) and _positive(r[idx]) and _product_like(cells, idx):
                        expected_rows.add((ti, ri))
        any_col_resolved = any_col_resolved or col_resolved

        # --- per-line grounding ---
        out_lines = []
        for li, l in enumerate(lines):
            sku, qty = l.get("material_or_sku"), l.get("quantity")
            if qty is None or qty <= 0:
                out_lines.append({"idx": li, "sku_in_source": None, "qty_grounded": None, "drop": False})
                continue
            nsku = _norm_code(sku)
            sku_ok = bool(nsku) and (nsku in norm_text or nsku.lstrip("0") in norm_text)
            qty_ok = False
            if method == "grid":
                cand = []
                if l.get("source_row") in grid:
                    cand.append(grid[l["source_row"]])
                cand += [c for c in grid.values() if nsku and any(_norm_code(v) == nsku for v in c.values())]
                row = next((c for c in cand if nsku and any(nsku in _norm_code(v) for v in c.values())), None)
                sku_ok = row is not None
                qty_ok = bool(row) and bool(qletter) and _qty_matches(row.get(qletter), qty)
                if row is not None and col_resolved and not str(row.get(qletter) or "").strip():
                    # the ordered-quantity column has data, but this row's cell is empty -> not an ordered row
                    out_lines.append({"idx": li, "sku_in_source": True, "qty_grounded": False, "drop": True})
                    continue
            elif method == "html":
                for ti, (hdr, rows) in enumerate(tables):
                    for r in rows:
                        if nsku and any(_norm_code(v) == nsku or nsku in _norm_code(v) for v in r):
                            idx = html_cols.get(ti)
                            if (idx is not None and idx < len(r) and _qty_matches(r[idx], qty)) or \
                               (idx is None and any(_qty_matches(v, qty) for v in r)):
                                qty_ok = True
                if not qty_ok and sku_ok:  # SKU found outside a table: same-line match
                    qty_ok = any(nsku in _norm_code(t) and any(_qty_matches(tok, qty) for tok in t.split())
                                 for t in text_lines)
            else:
                qty_ok = any(nsku and nsku in _norm_code(t) and any(_qty_matches(tok, qty) for tok in re.split(r"[\s|;:,]+", t))
                             for t in text_lines)
            out_lines.append({"idx": li, "sku_in_source": bool(sku_ok), "qty_grounded": bool(qty_ok), "drop": False})

        extracted += sum(1 for x in out_lines if x["qty_grounded"] is not None and not x["drop"])
        out_orders.append({
            "idx": oi, "po_issue": issue, "po_in_source": po_in_src,
            "customer_is_supplier": is_supplier(o.get("customer_name")),
            "qty_col_resolved": col_resolved, "qty_letter": qletter if method == "grid" else None,
            "qty_letter_derived": letter_derived, "lines": out_lines,
        })

    expected = len(expected_rows) if (expected_rows is not None and any_col_resolved) else None
    return json.dumps({"method": method, "expected_lines": expected, "extracted_lines": extracted,
                       "orders": out_orders})
# END_CHECKS

_CHECKS_DDL = (
    "STRUCT<method:STRING,expected_lines:INT,extracted_lines:INT,orders:ARRAY<STRUCT<idx:INT,po_issue:STRING,"
    "po_in_source:BOOLEAN,customer_is_supplier:BOOLEAN,qty_col_resolved:BOOLEAN,qty_letter:STRING,"
    "qty_letter_derived:BOOLEAN,lines:ARRAY<STRUCT<idx:INT,sku_in_source:BOOLEAN,qty_grounded:BOOLEAN,drop:BOOLEAN>>>>>"
)


@F.udf("string")
def _check_document_udf(text, po_json):
    try:
        return check_document(text, po_json)
    except Exception as e:  # noqa — a checker bug must never fail the pipeline; it just routes to review
        return json.dumps({"method": f"error: {e}"[:200], "expected_lines": None, "extracted_lines": None, "orders": []})


# =====================================================================
# Tables
# =====================================================================
def _ai_query_sql(view):
    """Gold's ai_query extraction (unchanged): dedup + ai_query with the registry prompt over the rows of `view`."""
    # failOnError => false: one bad document no longer fails the whole run; its error is kept instead.
    # max_tokens: large order forms produce long JSON; a cut-off answer can't be parsed.
    # Dedup: identical parsed content (re-sent files, "(1)/(3)" downloads, same file in two emails) is
    # extracted once; later copies point at the first via duplicate_of.
    return f"""
        WITH pa AS (
          SELECT *,
            sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256) AS content_hash,
            ROW_NUMBER() OVER (PARTITION BY sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256)
                               ORDER BY received_at NULLS LAST, source_path, attachment_filename) AS dup_rank,
            FIRST_VALUE(attachment_filename) OVER (
              PARTITION BY sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256)
              ORDER BY received_at NULLS LAST, source_path, attachment_filename) AS first_copy
          FROM {view}
          WHERE parse_method <> 'unsupported'
        ),
        r AS (
          SELECT email_id, attachment_filename, source_path, received_at, parse_confidence, parse_truncated,
            content_hash, CAST(NULL AS STRING) AS duplicate_of,
            ai_query(
              '{ENDPOINT}',
              concat('{_sql_lit(_prefix)}', parsed_content, '{_sql_lit(_suffix)}'),
              responseFormat => '{_sql_lit(_resp_fmt)}',
              modelParameters => named_struct('max_tokens', {MAX_OUTPUT_TOKENS}, 'temperature', 0.0),
              failOnError => false
            ) AS resp
          FROM pa
          WHERE dup_rank = 1 OR length(trim(parsed_content)) < 20
        ),
        p AS (
          SELECT *, from_json(resp.result, '{_ORDERS_DDL}') AS po FROM r
        )
        SELECT email_id, attachment_filename, source_path, received_at, parse_confidence, parse_truncated,
          content_hash, duplicate_of, po,
          CASE WHEN resp.errorMessage IS NOT NULL THEN 'ai_error'
               WHEN po.orders IS NULL THEN 'unparseable'
               WHEN size(po.orders) = 0 THEN 'no_orders'
               ELSE 'ok' END AS extraction_status,
          resp.errorMessage AS ai_error,
          resp.result AS raw_response
        FROM p
        UNION ALL
        SELECT email_id, attachment_filename, source_path, received_at, parse_confidence, parse_truncated,
          content_hash, first_copy AS duplicate_of, CAST(NULL AS {_ORDERS_DDL}) AS po,
          'duplicate' AS extraction_status, CAST(NULL AS STRING) AS ai_error, CAST(NULL AS STRING) AS raw_response
        FROM pa
        WHERE dup_rank > 1 AND length(trim(parsed_content)) >= 20
    """


_EXTRACTOR_NOTE = ("Extraction: hybrid = ai_extract v2.1 precision first, ai_query fallback (see extractor / "
                   "fallback_reason)" if HYBRID else "Extraction: ai_query for every document")


@dlt.table(
    name="extracted_parsed",
    comment=f"Gold: ai_query ({ENDPOINT}) using prompt+schema loaded from registry {PROMPT_URI} (v{_pv.version}). "
            "Documents whose parsed content duplicates an earlier one are not re-extracted (extraction_status='duplicate'). "
            + _EXTRACTOR_NOTE,
    table_properties={"quality": "gold", "prompt_uri": PROMPT_URI, "prompt_version": str(_pv.version),
                      "extraction_mode": EXTRACTION_MODE,
                      **({"extract_schema_uri": SCHEMA_URI, "extract_schema_version": _x_version} if HYBRID else {})},
)
def extracted_parsed():
    dlt.read("parsed_attachments").createOrReplaceTempView("_pa")
    if HYBRID:
        return _hybrid_extracted()
    return (spark.sql(_ai_query_sql("_pa"))
            .withColumn("extractor", F.when(F.col("extraction_status") != "duplicate", F.lit("ai_query")))
            .withColumn("fallback_reason", F.lit(None).cast("string"))
            .withColumn("field_confidence", F.lit(None).cast("string")))


# =====================================================================
# extraction_mode = hybrid: ai_extract v2.1 precision first, ai_query fallback (src/lib/extract_select.py).
#   oi_extract_route           per document to extract: ai_extract, or straight to ai_query (size guard)
#   oi_extract_primary         ai_extract (one statement): layout VARIANT for PDFs/images/Word, text otherwise
#   oi_extract_primary_checked unwrapped to the ai_query shape + Gold's own checks -> fallback_reason (or none)
#   oi_extract_fallback        ai_query (the same SQL as ai_query mode) on the pre-routed + fallback documents only
#   extracted_parsed           per document: ai_extract, or — where the fallback ran — whichever passes Gold's
#                              checks better (completeness, then verified lines; tie -> ai_extract)
#   extraction_citations       where to find each extracted field in the source (page + box / sheet + cell / text)
# =====================================================================
_PA_COLS = "email_id, attachment_filename, source_path, received_at, parse_confidence, parse_truncated"


def _dedup_sql(view):
    return f"""
      SELECT *,
        sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256) AS content_hash,
        ROW_NUMBER() OVER (PARTITION BY sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256)
                           ORDER BY received_at NULLS LAST, source_path, attachment_filename) AS dup_rank,
        FIRST_VALUE(attachment_filename) OVER (
          PARTITION BY sha2(regexp_replace(lower(parsed_content), '\\\\s+', ' '), 256)
          ORDER BY received_at NULLS LAST, source_path, attachment_filename) AS first_copy
      FROM {view}
      WHERE parse_method <> 'unsupported'"""


if HYBRID:
    @F.udf("string")
    def _pre_route_udf(text):
        return _xsel.pre_route(text, HYBRID_CFG)

    @dlt.table(name="oi_extract_route", table_properties={"quality": "gold"},
               comment="Gold (hybrid): documents to extract and their route — ai_extract, or straight to ai_query "
                       "(route_reason) when they exceed the size guard (hybrid_max_chars / hybrid_max_rows).")
    def oi_extract_route():
        dlt.read("parsed_attachments").createOrReplaceTempView("_pa")
        d = spark.sql(f"""SELECT {_PA_COLS}, content_hash, parse_method, parsed_layout IS NOT NULL has_layout,
                                 parsed_content
                          FROM ({_dedup_sql('_pa')}) WHERE dup_rank = 1 OR length(trim(parsed_content)) < 20""")
        return (d.withColumn("route_reason", _pre_route_udf("parsed_content"))
                 .withColumn("route", F.when(F.col("route_reason").isNull(), "ai_extract").otherwise("ai_query"))
                 .drop("parsed_content"))

    @dlt.table(name="oi_extract_primary", table_properties={"quality": "gold"},
               comment="Gold (hybrid): raw ai_extract v2.1 output (mode=precision, citations + confidence scores). "
                       "b_input = layout (ai_parse_document VARIANT) or text.")
    def oi_extract_primary():
        dlt.read("oi_extract_route").where("route = 'ai_extract'").createOrReplaceTempView("_route")
        dlt.read("parsed_attachments").select("source_path", "attachment_filename", "parsed_content",
                                              "parsed_layout").createOrReplaceTempView("_pa_x")
        cols = ", ".join(f"r.{c.strip()}" for c in _PA_COLS.split(",")) + ", r.content_hash"
        join = "_route r JOIN _pa_x p ON p.source_path = r.source_path AND p.attachment_filename = r.attachment_filename"
        return spark.sql(f"""
          SELECT {cols}, 'layout' AS b_input,
            to_json({_xs.ai_extract_sql('p.parsed_layout', _x_instructions, 'precision', _x_schema)}) AS b_raw
          FROM {join} WHERE p.parsed_layout IS NOT NULL
          UNION ALL
          SELECT {cols}, 'text' AS b_input,
            to_json({_xs.ai_extract_sql('p.parsed_content', _x_instructions, 'precision', _x_schema)}) AS b_raw
          FROM {join} WHERE p.parsed_layout IS NULL""")

    _EVAL_DDL = ("struct<a_json:string,conf_json:string,err:string,status:string,checks_json:string,"
                 "fallback_reason:string,completeness:double,verified:double>")

    @F.udf(_EVAL_DDL)
    def _eval_primary_udf(b_raw, text):
        try:
            a_json, conf_json, err = _xa.adapt_json(b_raw)
            if a_json:
                _a, _n = _xa.drop_unprinted_headers(json.loads(a_json), text)
                if _n:
                    a_json = json.dumps(_a, ensure_ascii=False)
            if err:
                status = "unparseable" if (err.startswith(("unparseable", "orders is not", "adapter error"))) else "ai_error"
            else:
                status = "ok" if (json.loads(a_json).get("orders") or []) else "no_orders"
            checks = check_document(text, a_json) if a_json else None
            reason = _xsel.fallback_reason("ok" if status == "no_orders" else status, err,
                                           json.loads(a_json) if a_json else None, checks, text, HYBRID_CFG)
            comp, ver = _xsel.doc_score(checks, None) if checks else (0.0, 0.0)
            return (a_json, conf_json, err, status, checks, reason, float(comp), float(ver))
        except Exception as e:  # noqa — never fail the pipeline on one document: fall back instead
            return (None, "{}", f"hybrid evaluation error: {e}"[:300], "ai_error", None,
                    "ai_extract output could not be checked", 0.0, 0.0)

    @dlt.table(name="oi_extract_primary_checked", table_properties={"quality": "gold"},
               comment="Gold (hybrid): ai_extract output unwrapped to the ai_query shape (a_json, per-field confidence "
                       "+ citation ids in conf_json), Gold's deterministic checks, and why it needs the fallback (or NULL).")
    def oi_extract_primary_checked():
        b = dlt.read("oi_extract_primary")
        p = dlt.read("parsed_attachments").select("source_path", "attachment_filename", "parsed_content")
        return (b.join(p, ["source_path", "attachment_filename"], "left")
                 .withColumn("ev", _eval_primary_udf("b_raw", "parsed_content"))
                 .select(*[c.strip() for c in _PA_COLS.split(",")], "content_hash", "b_input", "b_raw",
                         "ev.a_json", "ev.conf_json", F.col("ev.err").alias("ai_error"),
                         F.col("ev.status").alias("extraction_status"), "ev.checks_json", "ev.fallback_reason",
                         "ev.completeness", "ev.verified"))

    @dlt.table(name="oi_extract_fallback", table_properties={"quality": "gold"},
               comment=f"Gold (hybrid): ai_query ({ENDPOINT}, {PROMPT_URI} v{_pv.version}) on the documents routed to "
                       "it or whose ai_extract result needs the fallback — the same SQL as extraction_mode=ai_query.")
    def oi_extract_fallback():
        dlt.read("parsed_attachments").createOrReplaceTempView("_pa")
        dlt.read("oi_extract_route").createOrReplaceTempView("_route")
        dlt.read("oi_extract_primary_checked").createOrReplaceTempView("_chk")
        spark.sql("""
          SELECT p.* FROM _pa p
          WHERE EXISTS (SELECT 1 FROM _route r WHERE r.route = 'ai_query'
                          AND r.source_path = p.source_path AND r.attachment_filename = p.attachment_filename)
             OR EXISTS (SELECT 1 FROM _chk c WHERE c.fallback_reason IS NOT NULL
                          AND c.source_path = p.source_path AND c.attachment_filename = p.attachment_filename)
        """).createOrReplaceTempView("_pa_fb")
        return _repaired(spark.sql(_ai_query_sql("_pa_fb")).where("extraction_status <> 'duplicate'"))

    def _repaired(a):
        """Repair one ai_query answer shape seen on the largest documents: {"orders": "<the array as a JSON string>"}
        (otherwise 'unparseable'). Only in the fallback; extraction_mode=ai_query is left exactly as it was."""
        a = a.withColumn("_fix", F.when(F.col("extraction_status") == "unparseable", _repair_orders_udf("raw_response")))
        return (a.withColumn("po", F.when(F.col("_fix").isNotNull(), F.from_json("_fix", _ORDERS_DDL)).otherwise(F.col("po")))
                 .withColumn("extraction_status",
                             F.when(F.col("_fix").isNotNull() & F.col("po.orders").isNotNull(),
                                    F.when(F.size("po.orders") == 0, "no_orders").otherwise("ok"))
                              .otherwise(F.col("extraction_status")))
                 .withColumn("raw_response", F.coalesce("_fix", "raw_response"))
                 .drop("_fix"))

    @dlt.table(name="oi_extract_fallback_retry", table_properties={"quality": "gold"},
               comment="Gold (hybrid): one more ai_query attempt for fallback documents whose first ai_query answer "
                       "failed or could not be read (seen on the largest documents; the answer varies between calls).")
    def oi_extract_fallback_retry():
        dlt.read("parsed_attachments").createOrReplaceTempView("_pa")
        dlt.read("oi_extract_fallback").where("extraction_status IN ('ai_error', 'unparseable')") \
            .select("source_path", "attachment_filename").createOrReplaceTempView("_fb_bad")
        spark.sql("""SELECT p.* FROM _pa p WHERE EXISTS (SELECT 1 FROM _fb_bad b WHERE b.source_path = p.source_path
                     AND b.attachment_filename = p.attachment_filename)""").createOrReplaceTempView("_pa_retry")
        return _repaired(spark.sql(_ai_query_sql("_pa_retry")).where("extraction_status <> 'duplicate'"))

    @F.udf("string")
    def _repair_orders_udf(raw):
        try:
            d = json.loads(raw)
            if isinstance(d, dict) and isinstance(d.get("orders"), str):
                d["orders"] = json.loads(d["orders"])
                return json.dumps(d, ensure_ascii=False)
        except Exception:  # noqa
            pass
        return None

    @F.udf("struct<completeness:double,verified:double>")
    def _score_udf(text, po_json):
        try:
            if not po_json:
                return (0.0, 0.0)
            c, v = _xsel.doc_score(check_document(text, po_json), None)
            return (float(c), float(v))
        except Exception:  # noqa
            return (0.0, 0.0)

    @F.udf("string")
    def _pick_udf(b_status, b_c, b_v, a_status, a_c, a_v):
        return _xsel.pick(b_status in ("ok", "no_orders"), (b_c or 0.0, b_v or 0.0),
                          a_status in ("ok", "no_orders"), (a_c or 0.0, a_v or 0.0))

    def _hybrid_extracted():
        r = dlt.read("oi_extract_route").alias("r")
        c = dlt.read("oi_extract_primary_checked").alias("c")
        rt = (dlt.read("oi_extract_fallback_retry").where("extraction_status IN ('ok', 'no_orders')")
              .select("source_path", "attachment_filename", F.col("po").alias("r_po"),
                      F.col("extraction_status").alias("r_status"), F.col("raw_response").alias("r_raw")))
        f = (dlt.read("oi_extract_fallback").join(rt, ["source_path", "attachment_filename"], "left")
             .withColumn("po", F.coalesce("r_po", "po"))
             .withColumn("ai_error", F.when(F.col("r_status").isNotNull(), F.lit(None)).otherwise(F.col("ai_error")))
             .withColumn("raw_response", F.coalesce("r_raw", "raw_response"))
             .withColumn("extraction_status", F.coalesce("r_status", "extraction_status"))).alias("f")
        p = dlt.read("parsed_attachments").select("source_path", "attachment_filename", "parsed_content").alias("p")
        k = ["source_path", "attachment_filename"]
        j = (r.join(c.select(*k, "c.a_json", "c.conf_json", "c.ai_error", "c.extraction_status", "c.fallback_reason",
                             "c.completeness", "c.verified"), k, "left")
              .withColumnRenamed("ai_error", "b_err").withColumnRenamed("extraction_status", "b_status")
              .withColumnRenamed("completeness", "b_c").withColumnRenamed("verified", "b_v")
              .join(f.select(*k, F.col("po").alias("a_po"), F.col("extraction_status").alias("a_status"),
                             F.col("ai_error").alias("a_err"), F.col("raw_response").alias("a_raw")), k, "left")
              .join(p, k, "left")
              .withColumn("a_sc", F.when(F.col("a_status").isNotNull(), _score_udf("parsed_content", F.to_json("a_po")))))
        chosen = (F.when(F.col("route") == "ai_query", F.lit("ai_query"))
                   .when(F.col("fallback_reason").isNull(), F.lit("ai_extract"))
                   .when(F.col("a_status").isNull(), F.lit("ai_extract"))
                   .otherwise(_pick_udf("b_status", "b_c", "b_v", "a_status", "a_sc.completeness", "a_sc.verified")))
        j = j.withColumn("extractor", chosen)
        is_b = F.col("extractor") == "ai_extract"
        reason = (F.when(F.col("route") == "ai_query", F.col("route_reason"))
                   .when(F.col("fallback_reason").isNotNull() & is_b,
                         F.concat(F.col("fallback_reason"), F.lit("; the fallback was not better, ai_extract kept")))
                   .otherwise(F.col("fallback_reason")))
        out = j.select(
            *[c_.strip() for c_ in _PA_COLS.split(",")], "content_hash",
            F.lit(None).cast("string").alias("duplicate_of"),
            F.when(is_b, F.from_json("a_json", _ORDERS_DDL)).otherwise(F.col("a_po")).alias("po"),
            F.when(is_b, F.col("b_status")).otherwise(F.col("a_status")).alias("extraction_status"),
            F.when(is_b, F.col("b_err")).otherwise(F.col("a_err")).alias("ai_error"),
            F.when(is_b, F.col("a_json")).otherwise(F.col("a_raw")).alias("raw_response"),
            "extractor", reason.alias("fallback_reason"),
            F.when(is_b, F.col("conf_json")).alias("field_confidence"))
        dups = spark.sql(f"""
          SELECT {_PA_COLS}, content_hash, first_copy AS duplicate_of, CAST(NULL AS {_ORDERS_DDL}) AS po,
            'duplicate' AS extraction_status, CAST(NULL AS STRING) AS ai_error, CAST(NULL AS STRING) AS raw_response,
            CAST(NULL AS STRING) AS extractor, CAST(NULL AS STRING) AS fallback_reason,
            CAST(NULL AS STRING) AS field_confidence
          FROM ({_dedup_sql('_pa')}) WHERE dup_rank > 1 AND length(trim(parsed_content)) >= 20""")
        return out.unionByName(dups)

    @F.udf(_xc.CITATION_DDL)
    def _citations_udf(b_raw, a_json, conf_json, b_input, text, elements_json):
        try:
            lay = b_input == "layout"
            rows = _xc.citation_rows(b_raw, a_json, conf_json, None if lay else text,
                                     json.loads(elements_json) if (lay and elements_json) else None)
            return [tuple(r.get(k) for k in _xc.CITATION_FIELDS) for r in rows]
        except Exception:  # noqa — citations are an aid; a mapping bug must not fail the run
            return []

    @dlt.table(name="extraction_citations", table_properties={"quality": "gold"},
               comment="Gold (hybrid): where each field ai_extract returned sits in the source — one row per (document, "
                       "order_idx, li_idx, field, citation, location). source_kind = layout (page_index + box x1,y1,x2,y2 "
                       "in pixels of the page at 200 DPI, origin top-left; element_id/type, table row) | sheet "
                       "(sheet_index/sheet_name, row_number, cell_ref like E35) | text (char_start/char_stop + snippet). "
                       "Only for documents whose extractor is ai_extract. See docs/ARCHITECTURE.md.")
    def extraction_citations():
        e = dlt.read("extracted_parsed").where("extractor = 'ai_extract' AND extraction_status = 'ok'") \
            .select("email_id", "source_path", "attachment_filename")
        c = dlt.read("oi_extract_primary_checked").select("source_path", "attachment_filename", "b_raw", "a_json",
                                                          "conf_json", "b_input")
        p = (dlt.read("parsed_attachments")
             .select("source_path", "attachment_filename", "parsed_content",
                     F.expr("to_json(parsed_layout:document:elements)").alias("elements_json")))
        k = ["source_path", "attachment_filename"]
        return (e.join(c, k).join(p, k, "left")
                 .withColumn("cit", F.explode(_citations_udf("b_raw", "a_json", "conf_json", "b_input",
                                                            "parsed_content", "elements_json")))
                 .select("email_id", "source_path", "attachment_filename", "b_input", "cit.*"))


@dlt.table(
    name="extraction_checks",
    comment="Gold: deterministic verification of each extraction against its parsed source "
            "(SKU/quantity grounding, ordered-qty completeness, PO-number sanity, supplier-as-customer).",
    table_properties={"quality": "gold"},
)
def extraction_checks():
    e = dlt.read("extracted_parsed").where("extraction_status = 'ok'")
    p = dlt.read("parsed_attachments").select("source_path", "attachment_filename", "parsed_content")
    return (
        e.join(p, ["source_path", "attachment_filename"], "left")
        .withColumn("checks", F.from_json(_check_document_udf(F.col("parsed_content"), F.to_json("po")), _CHECKS_DDL))
        .select("email_id", "attachment_filename", "source_path", "checks")
    )


@dlt.table(
    name="purchase_orders",
    comment="Gold: line-grain PO (ordered lines only, quantity > 0) with tribal-knowledge resolution, "
            "deterministic order_confidence and plain-language review_reasons",
    table_properties={"quality": "gold"},
)
def purchase_orders():
    dlt.read("extracted_parsed").where("extraction_status = 'ok'").createOrReplaceTempView("_ep")
    dlt.read("extraction_checks").createOrReplaceTempView("_ck")
    if MASTER_SOURCE == "sap":
        return _purchase_orders_sap()
    return spark.sql(f"""
      WITH ord AS (
        SELECT e.email_id, e.attachment_filename, e.source_path, e.received_at, e.parse_confidence,
               e.parse_truncated, c.checks, oi AS order_idx, o AS os
        FROM _ep e
        LEFT JOIN _ck c ON e.source_path = c.source_path AND e.attachment_filename = c.attachment_filename
        LATERAL VIEW posexplode(e.po.orders) t AS oi, o
      ),
      hdr AS (
        -- LEFT JOIN: files not in email_manifest (real examples / connector mail) are kept;
        -- their doc_id falls back to source file + part name (unique even for .msg parts).
        SELECT ord.email_id, ord.attachment_filename, ord.source_path, ord.received_at, ord.order_idx,
               coalesce(m.doc_id, concat(ord.source_path, ' :: ', ord.attachment_filename)) doc_id,
               ord.parse_confidence, ord.parse_truncated,
               ord.os.po_number, ord.os.po_number_label, ord.os.quantity_column,
               ord.os.order_date, ord.os.customer_name, ord.os.ship_to, ord.os.currency,
               ord.os.header_confidence, ord.os.line_items,
               element_at(ord.checks.orders, ord.order_idx + 1) oc,
               ord.checks.method check_method, ord.checks.expected_lines, ord.checks.extracted_lines,
               size(filter(ord.os.line_items, x -> coalesce(x.quantity, 0) <= 0)) n_zero_qty_dropped,
               size(filter(element_at(ord.checks.orders, ord.order_idx + 1).lines, x -> coalesce(x.drop, false)))
                 n_blank_qty_dropped,
               lower(regexp_replace(ord.os.customer_name, '[^A-Za-z0-9 ]','')) cn_norm
        FROM ord LEFT JOIN {S}.email_manifest m ON ord.attachment_filename = m.attachment_filename
      ),
      cust AS (
        SELECT sap_sold_to, retailer_canonical,
               lower(regexp_replace(name_variant, '[^A-Za-z0-9 ]','')) nv_norm
        FROM {S}.customer_master
      ),
      cm AS (
        SELECT h.doc_id, h.order_idx, c.sap_sold_to, c.retailer_canonical,
          CASE WHEN h.cn_norm=c.nv_norm THEN 1.0
               ELSE 1.0-(levenshtein(h.cn_norm,c.nv_norm)/greatest(length(h.cn_norm),length(c.nv_norm),1)) END AS score,
          -- per order, not per document: a multi-PO spreadsheet can hold orders for different customers
          ROW_NUMBER() OVER (PARTITION BY h.doc_id, h.order_idx ORDER BY
            CASE WHEN h.cn_norm=c.nv_norm THEN 1.0
                 ELSE 1.0-(levenshtein(h.cn_norm,c.nv_norm)/greatest(length(h.cn_norm),length(c.nv_norm),1)) END DESC) rn
        FROM hdr h CROSS JOIN cust c
        WHERE NOT coalesce(h.oc.customer_is_supplier, false)   -- never resolve the supplier to a sold-to
      ),
      cust_best AS (
        SELECT doc_id, order_idx, sap_sold_to resolved_sap_sold_to, retailer_canonical resolved_retailer,
               score customer_match_score,
               CASE WHEN score>=0.999 THEN 'exact' WHEN score>=0.85 THEN 'fuzzy' ELSE 'none' END customer_match_method
        FROM cm WHERE rn=1
      ),
      lines AS (
        SELECT h.* EXCEPT (line_items, cn_norm), li_idx,
               li.line_no, li.source_row, li.material_or_sku printed_sku, li.ean printed_ean, li.description, li.quantity,
               li.uom, li.unit_price, li.line_confidence,
               element_at(h.oc.lines, li_idx + 1) lc
        FROM hdr h LATERAL VIEW posexplode(h.line_items) t AS li_idx, li
        WHERE coalesce(li.quantity, 0) > 0          -- ordered lines only; dropped counts kept on the order
          AND NOT coalesce(element_at(h.oc.lines, li_idx + 1).drop, false)
      ),
      scored AS (
        SELECT l.*,
          cb.resolved_sap_sold_to, cb.resolved_retailer, cb.customer_match_score,
          coalesce(cb.customer_match_method, 'none') customer_match_method,
          coalesce(rs.material_no, pe.material_no, pn.material_no, pf.material_no) AS resolved_material_no,
          CASE WHEN rs.material_no IS NOT NULL THEN 'retailer_sku'
               WHEN pe.material_no IS NOT NULL THEN 'ean'
               WHEN pn.material_no IS NOT NULL THEN 'material_no'
               WHEN pf.material_no IS NOT NULL THEN 'ean_field' ELSE 'none' END AS sku_resolve_method,
          (coalesce(rs.material_no, pe.material_no, pn.material_no, pf.material_no) IS NOT NULL) AS sku_resolved,
          coalesce(l.lc.sku_in_source, false) AND coalesce(l.lc.qty_grounded, false) AS line_verified,
          (l.oc.po_issue IS NULL AND coalesce(l.oc.po_in_source, false)) AS po_ok,
          coalesce(l.oc.customer_is_supplier, false) AS customer_is_supplier
        FROM lines l
        LEFT JOIN cust_best cb ON l.doc_id = cb.doc_id AND l.order_idx = cb.order_idx
        LEFT JOIN {S}.retailer_sku_map rs ON trim(rs.retailer_sku) = trim(l.printed_sku)
        LEFT JOIN {S}.product_master   pe ON CAST(pe.ean AS STRING) = trim(l.printed_sku)
        -- the supplier's own material number printed as the code (e.g. portal exports, returned price lists)
        LEFT JOIN {S}.product_master   pn ON upper(pn.material_no) = upper(trim(l.printed_sku))
        -- GTIN given in its own field (e.g. EDI EN qualifier) when the printed code is a retailer item
        LEFT JOIN {S}.product_master   pf ON CAST(pf.ean AS STRING) = trim(l.printed_ean)
      ),
      ordered AS (
        SELECT s.*,
          avg(CASE WHEN line_verified THEN 1.0 ELSE 0.0 END) OVER w AS line_score,
          sum(CASE WHEN line_verified THEN 0 ELSE 1 END) OVER w AS n_unverified,
          sum(CASE WHEN sku_resolved THEN 0 ELSE 1 END) OVER w AS n_sku_unresolved,
          CASE WHEN po_ok THEN 1.0 ELSE 0.0 END AS po_score,
          CASE WHEN customer_is_supplier OR customer_name IS NULL THEN 0.0
               WHEN customer_match_method = 'exact' THEN 1.0
               WHEN customer_match_method = 'fuzzy' THEN 0.9
               ELSE 0.75 END AS customer_score,            -- unresolved != wrong: masters may be incomplete
          CASE WHEN expected_lines IS NULL THEN 1.0         -- not verifiable (e.g. email text)
               WHEN greatest(expected_lines, extracted_lines) = 0 THEN 1.0
               ELSE least(expected_lines, extracted_lines) / greatest(expected_lines, extracted_lines) END
            AS completeness
        FROM scored s
        WINDOW w AS (PARTITION BY doc_id, order_idx)
      )
      SELECT o.* EXCEPT (oc, lc, line_score, po_score, customer_score),
        round(coalesce(parse_confidence, 1.0)
              * (0.35 * (po_score + customer_score) / 2 + 0.45 * line_score + 0.20 * completeness), 3)
          AS order_confidence,
        concat_ws('; ', array_compact(array(
          CASE WHEN po_number IS NULL THEN 'No customer PO number found in the document'
               WHEN oc.po_issue IS NOT NULL THEN concat('Customer PO number ', oc.po_issue, ': ', po_number)
               WHEN NOT coalesce(oc.po_in_source, false) THEN concat('Customer PO number not found in the document: ', po_number) END,
          CASE WHEN customer_is_supplier THEN concat('Customer is the supplier (supplier entity/brand): ', customer_name)
               WHEN customer_name IS NULL THEN 'No customer identified'
               WHEN customer_match_method = 'none' THEN 'Customer not in customer master' END,
          CASE WHEN n_unverified > 0 THEN concat(n_unverified, ' line(s) not verified against the source row') END,
          CASE WHEN n_blank_qty_dropped > 0 THEN concat(n_blank_qty_dropped, ' extracted line(s) dropped: their ',
               'ordered-quantity cell (column ', oc.qty_letter, ') is empty') END,
          CASE WHEN oc.qty_letter_derived THEN concat('Quantities read from column ', oc.qty_letter,
               ' (the quantity header label sits on another column)') END,
          CASE WHEN expected_lines > extracted_lines
               THEN concat('Form has ', expected_lines, ' filled quantity rows but ', extracted_lines, ' were extracted')
               WHEN expected_lines < extracted_lines
               THEN concat('Extracted ', extracted_lines, ' lines but form has ', expected_lines, ' filled quantity rows') END,
          CASE WHEN n_sku_unresolved > 0 THEN concat(n_sku_unresolved, ' SKU(s) not in material master') END,
          CASE WHEN parse_truncated THEN 'Document was truncated by the parser' END
        ))) AS review_reasons,
        (NOT line_verified OR NOT sku_resolved OR NOT po_ok OR customer_is_supplier
           OR customer_match_method = 'none' OR completeness < 1.0) AS line_needs_review
      FROM ordered o
    """)


# =====================================================================
# master_source = sap: same order/line grain, checks and confidence structure as above, but customers and
# materials are resolved against the SAP working tables (oi_sap_*, refreshed by src/setup/01b_sap_masters.py)
# with the shared SQL in src/lib/sap_masters.py (the same SQL the read-only validation runs).
# The two resolution steps are their own tables (oi_order_customers, oi_line_materials): it keeps each query
# plan small (the resolution SQL is large) and shows why an order/line resolved the way it did.
# =====================================================================
def _sap_views():
    """Temp views _sap_hdr (one row per extracted order) and _sap_lines (ordered lines) from the Gold inputs."""
    dlt.read("extracted_parsed").where("extraction_status = 'ok'").createOrReplaceTempView("_ep")
    dlt.read("extraction_checks").createOrReplaceTempView("_ck")
    spark.sql(f"""
      WITH ord AS (
        SELECT e.email_id, e.attachment_filename, e.source_path, e.received_at, e.parse_confidence,
               e.parse_truncated, c.checks, oi AS order_idx, o AS os
        FROM _ep e
        LEFT JOIN _ck c ON e.source_path = c.source_path AND e.attachment_filename = c.attachment_filename
        LATERAL VIEW posexplode(e.po.orders) t AS oi, o
      )
      SELECT ord.email_id, ord.attachment_filename, ord.source_path, ord.received_at, ord.order_idx,
             coalesce(m.doc_id, concat(ord.source_path, ' :: ', ord.attachment_filename)) doc_id,
             ord.parse_confidence, ord.parse_truncated,
             ord.os.po_number, ord.os.po_number_label, ord.os.quantity_column,
             ord.os.order_date, ord.os.customer_name, ord.os.customer_number, ord.os.ship_to, ord.os.currency,
             ord.os.header_confidence, ord.os.line_items,
             element_at(ord.checks.orders, ord.order_idx + 1) oc,
             ord.checks.method check_method, ord.checks.expected_lines, ord.checks.extracted_lines,
             size(filter(ord.os.line_items, x -> coalesce(x.quantity, 0) <= 0)) n_zero_qty_dropped,
             size(filter(element_at(ord.checks.orders, ord.order_idx + 1).lines, x -> coalesce(x.drop, false)))
               n_blank_qty_dropped
      FROM ord LEFT JOIN {S}.email_manifest m ON ord.attachment_filename = m.attachment_filename
    """).createOrReplaceTempView("_sap_hdr")
    spark.sql("""
      SELECT h.* EXCEPT (line_items), li_idx,
             li.line_no, li.source_row, li.material_or_sku printed_sku, li.ean printed_ean, li.description,
             li.quantity, li.uom,
             li.unit_price, li.line_confidence,
             element_at(h.oc.lines, li_idx + 1) lc
      FROM _sap_hdr h LATERAL VIEW posexplode(h.line_items) t AS li_idx, li
      WHERE coalesce(li.quantity, 0) > 0          -- ordered lines only; dropped counts kept on the order
        AND NOT coalesce(element_at(h.oc.lines, li_idx + 1).drop, false)
    """).createOrReplaceTempView("_sap_lines")


if MASTER_SOURCE == "sap":
    @dlt.table(
        name="oi_order_customers_doc",
        comment="Gold (master_source=sap): each extracted order's customer AS PRINTED ON THE DOCUMENT resolved to an "
                "SAP sold-to (+ sales org, currency, ship-to and KNVP pair check) against oi_sap_customers / "
                "oi_sap_partner_links. oi_order_customers adds the email / file-name hints on top.",
        table_properties={"quality": "gold"},
    )
    def oi_order_customers_doc():
        _sap_views()
        return spark.sql(_sm.customer_resolution_sql(
            "(SELECT doc_id, order_idx, customer_name, customer_number, ship_to, "
            "coalesce(oc.customer_is_supplier, false) customer_is_supplier FROM _sap_hdr)",
            # SAP only: no business-maintained name pins (customer_master is a demo-mode table)
            f"{S}.{_sm.T_CUSTOMERS}", f"{S}.{_sm.T_LINKS}", SAP_ORGS))

    @dlt.table(
        name="oi_order_customers",
        comment="Gold (master_source=sap): the order's SAP customer — from the document (oi_order_customers_doc), "
                "else inferred from the sender / subject / file name (oi_customer_hints). customer_source says which, "
                "customer_hint holds the evidence.",
        table_properties={"quality": "gold"},
    )
    def oi_order_customers():
        # separate tables per resolution step: one resolution per query keeps the plan small
        dlt.read("oi_order_customers_doc").createOrReplaceTempView("_cres_doc")
        if not CUSTOMER_HINTS:
            return spark.sql("SELECT *, 'document' customer_source, CAST(NULL AS STRING) customer_hint FROM _cres_doc")
        _sap_views()
        dlt.read("oi_customer_hints").createOrReplaceTempView("_hints_doc")
        # hints only for the orders the document left unresolved (no customer, the supplier as customer, or not in SAP)
        spark.sql("""
          SELECT h.doc_id, h.order_idx, pos hint_rank, hh.source hint_source, hh.hint hint, hh.evidence hint_evidence,
                 h.customer_number, h.ship_to
          FROM _sap_hdr h
          JOIN _cres_doc c ON c.doc_id = h.doc_id AND c.order_idx = h.order_idx AND c.customer_match_method = 'none'
          JOIN _hints_doc d ON d.source_path = h.source_path AND d.attachment_filename = h.attachment_filename
          LATERAL VIEW posexplode(d.hints) x AS pos, hh
        """).createOrReplaceTempView("_hint_rows")
        return spark.sql(_sm.customer_hint_resolution_sql(
            "_cres_doc", "_hint_rows", f"{S}.{_sm.T_CUSTOMERS}", f"{S}.{_sm.T_LINKS}", SAP_ORGS))

    @F.udf("array<struct<source:string,hint:string,evidence:string>>")
    def _hints_udf(senders, subjects, file_name):
        try:
            return _ch.customer_hints([x for x in senders or [] if x], [x for x in subjects or [] if x], file_name,
                                      is_supplier=is_supplier)
        except Exception:  # noqa — a hint is an aid; a parsing bug must not fail the run
            return []

    @dlt.table(
        name="oi_customer_hints",
        comment="Gold (master_source=sap): customer-like texts around each extracted document, best first — the "
                "sender's email domain and name (the From: of an unpacked email before the mailbox sender), the "
                "subject and the file name. Supplier domains/brands, free-mail domains and order words are never hints. "
                "Used by oi_order_customers only for orders the document leaves unresolved.",
        table_properties={"quality": "gold"},
    )
    def oi_customer_hints():
        dlt.read("extracted_parsed").select("source_path", "attachment_filename").distinct() \
            .createOrReplaceTempView("_hint_docs")
        dlt.read("email_attachments").select("source_path", "from_name", "from_email", "subject") \
            .createOrReplaceTempView("_hint_mail")
        dlt.read("parsed_attachments").where("attachment_filename LIKE '%body.txt'") \
            .select("source_path", "attachment_filename", F.substring("parsed_content", 1, 2000).alias("head")) \
            .createOrReplaceTempView("_hint_bodies")
        # an unpacked part ('X.msg / order.pdf') takes the headers of its own email's body ('X.msg / body.txt')
        df = spark.sql("""
          WITH d AS (
            SELECT source_path, attachment_filename,
              CASE WHEN attachment_filename LIKE '%body.txt' THEN attachment_filename
                   WHEN instr(attachment_filename, ' / ') > 0
                   THEN concat(regexp_extract(attachment_filename, '^(.*) / [^/]*$', 1), ' / body.txt') END body_name
            FROM _hint_docs
          ),
          m AS (SELECT source_path, first(from_name, true) from_name, first(from_email, true) from_email,
                       first(subject, true) subject FROM _hint_mail GROUP BY source_path)
          SELECT d.source_path, d.attachment_filename,
            array(regexp_extract(b.head, '(?m)^From: *(.*)$', 1),
                  CASE WHEN m.from_email IS NOT NULL
                       THEN concat_ws(' ', m.from_name, concat('<', m.from_email, '>')) ELSE m.from_name END) senders,
            array(regexp_extract(b.head, '(?m)^Subject: *(.*)$', 1), m.subject) subjects
          FROM d
          LEFT JOIN _hint_bodies b ON b.source_path = d.source_path AND b.attachment_filename = d.body_name
          LEFT JOIN m ON m.source_path = d.source_path
        """)
        return df.select("source_path", "attachment_filename",
                         _hints_udf("senders", "subjects", "attachment_filename").alias("hints"))

    @dlt.table(
        name="oi_line_materials",
        comment="Gold (master_source=sap): each ordered line's code validated against oi_sap_materials for the "
                "order's sales org (exact / EAN / prefix; ambiguous EANs flagged, never picked).",
        table_properties={"quality": "gold"},
    )
    def oi_line_materials():
        _sap_views()
        dlt.read("oi_order_customers").createOrReplaceTempView("_sap_cres")
        return spark.sql(_sm.material_resolution_sql(
            "(SELECT l.doc_id, l.order_idx, l.li_idx, l.printed_sku, l.printed_ean, c.sap_sales_org sales_org "
            "FROM _sap_lines l LEFT JOIN _sap_cres c ON c.doc_id = l.doc_id AND c.order_idx = l.order_idx)",
            # SAP only: material number, EAN, prefix — no retailer_sku_map (a demo-mode table)
            f"{S}.{_sm.T_MATERIALS}", SAP_ORGS, PREFIX_LEN, with_ean=True))


def _purchase_orders_sap():
    orgs_txt = ", ".join(SAP_ORGS)
    # Review reasons stay short with many affiliates configured (EMEA = 31 sales orgs).
    orgs_phrase = f"sales org {orgs_txt}" if len(SAP_ORGS) <= 4 else f"any of the {len(SAP_ORGS)} configured sales orgs"
    _sap_views()
    dlt.read("oi_order_customers").createOrReplaceTempView("_sap_cres")
    dlt.read("oi_line_materials").createOrReplaceTempView("_sap_mres")
    return spark.sql(f"""
      WITH scored AS (
        SELECT l.*,
          c.sap_sold_to resolved_sap_sold_to, c.sap_sold_to_name resolved_retailer, c.customer_match_score,
          c.customer_match_method, c.sap_sales_org, c.sap_currency, c.sap_n_currencies, c.sap_country,
          c.sap_customer_deleted, c.sap_customer_blocked, c.sap_n_sales_orgs, c.sold_to_via_partner,
          c.candidate_sold_tos, c.n_customer_candidates, c.pinned_sold_to, c.pinned_in_sap,
          c.sap_ship_to, c.ship_to_check, c.customer_source, c.customer_hint,
          m.resolved_material_no, m.sku_resolve_method, m.sku_resolved, m.sku_from_retailer_map,
          m.material_candidates, m.material_issue, m.sap_material_text, m.sap_material_deleted, m.material_sales_org,
          coalesce(l.lc.sku_in_source, false) AND coalesce(l.lc.qty_grounded, false) AS line_verified,
          (l.oc.po_issue IS NULL AND coalesce(l.oc.po_in_source, false)) AS po_ok_document,
          coalesce(l.oc.customer_is_supplier, false) AS customer_is_supplier,
          pr.rule po_rule, pr.pattern po_rule_pattern
        FROM _sap_lines l
        LEFT JOIN _sap_cres c ON c.doc_id = l.doc_id AND c.order_idx = l.order_idx
        LEFT JOIN _sap_mres m ON m.doc_id = l.doc_id AND m.order_idx = l.order_idx AND m.li_idx = l.li_idx
        LEFT JOIN (SELECT lpad(trim(sold_to), 10, '0') sold_to, lower(trim(any_value(rule))) rule,
                          nullif(trim(any_value(pattern)), '') pattern
                   FROM {S}.{_sm.T_PO_RULES} GROUP BY 1) pr ON pr.sold_to = c.sap_sold_to
      ),
      po AS (     -- missing PO: flagged ('require', the default) unless the customer's rule says 'generate'
        SELECT s.* EXCEPT (po_number),
          (po_rule = 'generate' AND coalesce(trim(po_number), '') = '') AS po_generated,
          (coalesce(po_rule, 'require') = 'require' AND po_rule_pattern IS NOT NULL AND coalesce(trim(po_number), '') <> ''
             AND NOT trim(po_number) RLIKE po_rule_pattern) AS po_pattern_mismatch,
          CASE WHEN po_rule = 'generate' AND coalesce(trim(po_number), '') = ''
               THEN replace(replace(coalesce(po_rule_pattern, 'AUTO-{{date}}-{{doc}}'),
                                    '{{date}}', date_format(coalesce(received_at, current_timestamp()), 'yyyyMMdd')),
                            '{{doc}}', substr(sha2(doc_id, 256), 1, 6))
               ELSE po_number END AS po_number
        FROM scored s
      ),
      po2 AS (
        SELECT *, CASE WHEN po_generated THEN true WHEN po_pattern_mismatch THEN false ELSE po_ok_document END AS po_ok
        FROM po
      ),
      ordered AS (
        SELECT s.*,
          avg(CASE WHEN line_verified THEN 1.0 ELSE 0.0 END) OVER w AS line_score,
          sum(CASE WHEN line_verified THEN 0 ELSE 1 END) OVER w AS n_unverified,
          sum(CASE WHEN sku_resolved THEN 0 ELSE 1 END) OVER w AS n_sku_unresolved,
          sum(CASE WHEN material_issue = 'not_found' THEN 1 ELSE 0 END) OVER w AS n_mat_not_found,
          sum(CASE WHEN material_issue = 'not_listed' THEN 1 ELSE 0 END) OVER w AS n_mat_not_listed,
          sum(CASE WHEN material_issue = 'ean_ambiguous' THEN 1 ELSE 0 END) OVER w AS n_ean_ambiguous,
          sum(CASE WHEN sku_resolve_method = 'prefix' AND material_candidates > 1 THEN 1 ELSE 0 END) OVER w
            AS n_prefix_multi,
          sum(CASE WHEN sap_material_deleted THEN 1 ELSE 0 END) OVER w AS n_mat_deleted,
          CASE WHEN po_ok THEN 1.0 ELSE 0.0 END AS po_score,
          CASE WHEN customer_source <> 'document' AND customer_match_method = 'ambiguous' THEN 0.5
               WHEN customer_source <> 'document' AND resolved_sap_sold_to IS NOT NULL THEN 0.7   -- inferred: check
               WHEN customer_is_supplier OR customer_name IS NULL THEN 0.0
               WHEN customer_match_method IN ('customer_number', 'name_address', 'name_variant') THEN 1.0
               WHEN customer_match_method IN ('name', 'address') THEN 0.9
               WHEN customer_match_method = 'ambiguous' THEN 0.6
               ELSE 0.5 END AS customer_score,           -- SAP is the full master: not found weighs more than in demo
          CASE WHEN expected_lines IS NULL THEN 1.0
               WHEN greatest(expected_lines, extracted_lines) = 0 THEN 1.0
               ELSE least(expected_lines, extracted_lines) / greatest(expected_lines, extracted_lines) END
            AS completeness
        FROM po2 s
        WINDOW w AS (PARTITION BY doc_id, order_idx)
      )
      SELECT o.* EXCEPT (oc, lc, line_score, po_score, customer_score, n_mat_not_found, n_mat_not_listed,
                         n_ean_ambiguous, n_prefix_multi, n_mat_deleted),
        round(coalesce(parse_confidence, 1.0)
              * (0.35 * (po_score + customer_score) / 2 + 0.45 * line_score + 0.20 * completeness), 3)
          AS order_confidence,
        concat_ws('; ', array_compact(array(
          CASE WHEN po_generated THEN concat('Customer PO number generated by the PO rule for this customer: ', po_number)
               WHEN po_number IS NULL THEN 'No customer PO number found in the document'
               WHEN po_pattern_mismatch THEN concat('Customer PO number does not match the PO format of this customer: ', po_number)
               WHEN oc.po_issue IS NOT NULL THEN concat('Customer PO number ', oc.po_issue, ': ', po_number)
               WHEN NOT coalesce(oc.po_in_source, false) THEN concat('Customer PO number not found in the document: ', po_number) END,
          CASE WHEN customer_source <> 'document' AND customer_match_method = 'ambiguous'
               THEN concat('Customer inferred from the ', element_at(map('sender_domain', 'sender\\'s email domain', 'sender_name', 'sender\\'s name', 'subject', 'email subject', 'file_name', 'file name'), customer_source), ' (',
                           customer_hint, ') matches ', n_customer_candidates, ' SAP customers (',
                           array_join(candidate_sold_tos, ', '), CASE WHEN n_customer_candidates > 5 THEN ', ...' ELSE '' END,
                           ') — choose the sold-to')
               WHEN customer_source <> 'document'
               THEN concat('Customer inferred from the ', element_at(map('sender_domain', 'sender\\'s email domain', 'sender_name', 'sender\\'s name', 'subject', 'email subject', 'file_name', 'file name'), customer_source), ' (',
                           customer_hint, '): ', resolved_retailer, ' ', resolved_sap_sold_to,
                           CASE WHEN customer_is_supplier THEN ' (the document names the supplier as the customer)'
                                WHEN customer_name IS NOT NULL THEN concat(' (the document says ', customer_name, ')')
                                ELSE '' END, ' — check')
               WHEN customer_is_supplier THEN concat('Customer is the supplier (supplier entity/brand): ', customer_name)
               WHEN customer_name IS NULL AND resolved_sap_sold_to IS NULL THEN 'No customer identified'
               WHEN customer_match_method = 'none' THEN 'Customer not found in SAP for {orgs_phrase}'
               WHEN customer_match_method = 'ambiguous'
               THEN concat('Customer matches ', n_customer_candidates, ' SAP customers (',
                           array_join(candidate_sold_tos, ', '), CASE WHEN n_customer_candidates > 5 THEN ', ...' ELSE '' END,
                           ') — choose the sold-to') END,
          CASE WHEN pinned_sold_to IS NOT NULL AND NOT pinned_in_sap
               THEN concat('Pinned sold-to ', pinned_sold_to, ' (customer_master) is not a sold-to in SAP for {orgs_phrase}') END,
          CASE WHEN sold_to_via_partner IS NOT NULL
               THEN concat('Sold-to ', resolved_sap_sold_to, ' found through its SAP ',
                           element_at(map('WE', 'ship-to', 'RE', 'bill-to', 'RG', 'payer'), split(sold_to_via_partner, ':')[0]),
                           ' ', split(sold_to_via_partner, ':')[1]) END,
          CASE WHEN sap_customer_deleted THEN concat('SAP customer ', resolved_sap_sold_to, ' is flagged for deletion') END,
          CASE WHEN sap_customer_blocked THEN concat('SAP customer ', resolved_sap_sold_to, ' has an order block') END,
          CASE WHEN sap_n_sales_orgs > 1 THEN concat('Customer has sales views in ', sap_n_sales_orgs,
               ' of the sales orgs; using ', sap_sales_org) END,
          CASE WHEN sap_currency IS NOT NULL AND nullif(trim(currency), '') IS NOT NULL AND upper(trim(currency)) <> sap_currency
               THEN concat('Order currency ', currency, ' differs from SAP (', sap_currency, '); the SAP currency is used') END,
          CASE WHEN ship_to_check = 'not_linked' THEN concat('Ship-to ', sap_ship_to, ' is not linked to sold-to ',
                    resolved_sap_sold_to, ' in sales org ', sap_sales_org, ' (SAP partner functions)')
               WHEN ship_to_check = 'not_found' THEN 'Ship-to address not found among the SAP ship-tos' END,
          CASE WHEN n_unverified > 0 THEN concat(n_unverified, ' line(s) not verified against the source row') END,
          CASE WHEN n_blank_qty_dropped > 0 THEN concat(n_blank_qty_dropped, ' extracted line(s) dropped: their ',
               'ordered-quantity cell (column ', oc.qty_letter, ') is empty') END,
          CASE WHEN oc.qty_letter_derived THEN concat('Quantities read from column ', oc.qty_letter,
               ' (the quantity header label sits on another column)') END,
          CASE WHEN expected_lines > extracted_lines
               THEN concat('Form has ', expected_lines, ' filled quantity rows but ', extracted_lines, ' were extracted')
               WHEN expected_lines < extracted_lines
               THEN concat('Extracted ', extracted_lines, ' lines but form has ', expected_lines, ' filled quantity rows') END,
          CASE WHEN n_mat_not_found > 0 THEN concat(n_mat_not_found, ' material(s) not found in SAP') END,
          CASE WHEN n_mat_not_listed > 0 THEN concat(n_mat_not_listed, ' material(s) not listed for ',
               coalesce(concat('sales org ', sap_sales_org), '{orgs_phrase}')) END,
          CASE WHEN n_ean_ambiguous > 0 THEN concat(n_ean_ambiguous, ' EAN(s) match several materials — choose the material') END,
          CASE WHEN n_prefix_multi > 0 THEN concat(n_prefix_multi,
               ' material prefix(es) match several materials — SAP will resolve') END,
          CASE WHEN n_mat_deleted > 0 THEN concat(n_mat_deleted, ' material(s) flagged for deletion in SAP') END,
          CASE WHEN parse_truncated THEN 'Document was truncated by the parser' END
        ))) AS review_reasons,
        (NOT line_verified OR NOT sku_resolved OR NOT po_ok OR customer_is_supplier
           OR customer_match_method IN ('none', 'ambiguous') OR completeness < 1.0
           OR ship_to_check = 'not_linked' OR coalesce(sap_customer_deleted, false)
           OR coalesce(sap_customer_blocked, false) OR sap_material_deleted
           OR (pinned_sold_to IS NOT NULL AND NOT pinned_in_sap)) AS line_needs_review
      FROM ordered o
    """)
