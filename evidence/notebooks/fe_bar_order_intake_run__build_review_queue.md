# [dev <deployer>] fe_bar_order_intake_run / build_review_queue (run 203254553454054, as executed, with outputs)

Notebook `5a66c712-7cc0-4d1c-ae34-14424bd38101`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 03 — Build the Review-App queue table
Materializes `review_orders` (order grain) from the Gold `purchase_orders` (line grain)
that the pipeline produced. **Run AFTER the pipeline.** The Review App reads/updates this
table (status, corrections) and writes approvals to `sap_outbound`.
Re-run to refresh the queue after a new pipeline run (resets any in-flight status).
Duplicates (same parsed content, or same valid PO for the same customer) are kept with
`status='duplicate'` + `duplicate_of`, never silently dropped. `review_reasons` says why an order needs a look.
`region`: the customer's country (customer_master, by resolved sold-to, else by name variant) mapped through
`region_map`; a country not in the map -> `Other`; customer not found -> `Unassigned`.
`master_source=sap`: `customer_number` = the resolved SAP sold-to, `sales_org` / `currency` from its KNVV sales
view; region = `region_map` for the sold-to's SAP country, else the SAP affiliate (`oi_sap_region_map`).

```python
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
dbutils.widgets.text("master_source", "demo")
dbutils.widgets.text("lib_path", "")
master_source = dbutils.widgets.get("master_source").strip() or "demo"
if master_source not in ("demo", "sap"):
    raise ValueError(f"master_source must be 'demo' or 'sap', got {master_source!r}")
S = f"{catalog}.{schema}"

# master_source=sap: SAP columns of purchase_orders (03_gold) are carried into the queue; demo: nothing changes.
SAP = master_source == "sap"
sap_agg = ("""
    any_value(sap_sales_org) sap_sales_org, any_value(sap_currency) sap_currency, any_value(sap_country) sap_country,
    any_value(sap_ship_to) sap_ship_to, any_value(ship_to_check) ship_to_check,
    any_value(customer_match_method) customer_match_method,""" if SAP else "")
sap_line = ("""
      'sku_resolve_method',sku_resolve_method,'material_candidates',material_candidates,
      'sap_material_text',sap_material_text,'material_issue',material_issue,""" if SAP else "")
q_customer_number = "resolved_sap_sold_to" if SAP else "CAST(NULL AS STRING)"
# sap: a customer inferred from the sender / subject / file name (03_gold oi_customer_hints) shows its SAP name
# when the document printed none (or printed the supplier); the reason says where it came from
q_agg_customer_name = ("""any_value(CASE WHEN customer_source <> 'document' AND resolved_sap_sold_to IS NOT NULL
                                 AND (customer_name IS NULL OR customer_is_supplier)
                            THEN resolved_retailer ELSE customer_name END) customer_name""" if SAP
                       else "any_value(customer_name) customer_name")
q_currency = "coalesce(sap_currency, currency) currency" if SAP else "currency"
q_sales_org = "sap_sales_org" if SAP else "CAST(NULL AS STRING)"
q_sap_tail = (",\n  sap_ship_to, ship_to_check, customer_match_method, sap_country" if SAP else "")
q_sap_null_tail = (",\n  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING)"
                   if SAP else "")
if SAP:
    import os, sys
    sys.path.insert(0, dbutils.widgets.get("lib_path") or os.path.abspath(os.path.join(os.getcwd(), "..", "lib")))
    import sap_masters as _sm
    _rj, _rexpr = _sm.region_join_sql("q", "queue.sales_org", "queue.sap_country", f"{S}.{_sm.T_REGIONS}", f"{S}.region_map")

region_tail = f"""-- one country per sold-to and per normalized name variant (a sold-to is a single customer)
cm AS (
  SELECT sap_sold_to, lower(regexp_replace(name_variant, '[^A-Za-z0-9]', '')) name_key, country
  FROM {S}.customer_master WHERE country IS NOT NULL
),
by_sold_to AS (SELECT sap_sold_to, any_value(country) country FROM cm GROUP BY sap_sold_to),
by_name AS (SELECT name_key, any_value(country) country FROM cm GROUP BY name_key)
SELECT queue.*,
  CASE WHEN coalesce(s.country, n.country) IS NULL THEN 'Unassigned'
       ELSE coalesce(rm.region, 'Other') END region
FROM queue
LEFT JOIN by_sold_to s ON queue.resolved_sap_sold_to = s.sap_sold_to
LEFT JOIN by_name n ON lower(regexp_replace(queue.customer_name, '[^A-Za-z0-9]', '')) = n.name_key
LEFT JOIN (SELECT upper(country) country, any_value(region) region FROM {S}.region_map GROUP BY 1) rm
  ON upper(coalesce(s.country, n.country)) = rm.country
"""
if SAP:
    region_tail = f"""sap_region AS (SELECT 1 x)     -- (keeps the WITH list well-formed)
SELECT queue.*,
  {_rexpr} region
FROM queue{_rj}
"""

# Hybrid extraction (03_gold extraction_mode=hybrid): which extractor produced the order, why the fallback ran, and
# ai_extract's per-field confidence. Older Gold tables don't have these columns -> NULL.
_ep_cols = set(spark.table(f"{S}.extracted_parsed").columns)
x_extractor = "x.extractor" if "extractor" in _ep_cols else "CAST(NULL AS STRING)"
x_reason = "x.fallback_reason" if "fallback_reason" in _ep_cols else "CAST(NULL AS STRING)"
x_conf = "x.field_confidence" if "field_confidence" in _ep_cols else "CAST(NULL AS STRING)"
e_extractor = x_extractor.replace("x.", "e.")
e_reason = x_reason.replace("x.", "e.")

spark.sql(f"""
CREATE OR REPLACE TABLE {S}.review_orders AS
WITH queue AS (
WITH po AS (
  -- one review row per (document, PO): orders with the same VALID PO inside one document are merged;
  -- orders without a valid PO stay separate (keyed by their position)
  SELECT *, CASE WHEN po_ok THEN upper(regexp_replace(po_number, '[^A-Za-z0-9]', ''))
                 ELSE concat('#', order_idx) END order_key
  FROM {S}.purchase_orders
),
agg AS (
  SELECT doc_id, order_key, min(order_idx) order_idx,
    any_value(attachment_filename) attachment_filename, any_value(source_path) source_path,
    any_value(received_at) received_at, any_value(po_number) po_number, any_value(po_ok) po_ok,
    any_value(order_date) order_date, {q_agg_customer_name},
    any_value(ship_to) ship_to, any_value(currency) currency,
    any_value(resolved_sap_sold_to) resolved_sap_sold_to,{sap_agg}
    round(any_value(parse_confidence),3) parse_confidence,
    round(any_value(header_confidence),3) header_confidence,
    count(*) n_lines, round(avg(line_confidence),3) avg_line_confidence,
    min(order_confidence) overall_confidence,                -- deterministic (verification-based), not self-rated
    array_join(array_distinct(filter(collect_list(review_reasons), x -> x <> '')), '; ') review_reasons,
    any_value(parse_truncated) parse_truncated,
    array_sort(collect_set(order_idx)) order_idxs,           -- the extracted orders behind this review row
    -- sorted by (order_idx, li_idx): the keys extraction_citations / review_citations use for each line
    to_json(array_sort(collect_list(named_struct(
      'order_idx',order_idx,'li_idx',li_idx,
      'line_no',line_no,'source_row',source_row,'material_or_sku',printed_sku,'description',description,
      'quantity',quantity,'uom',uom,'unit_price',unit_price,'line_confidence',line_confidence,
      'verified',line_verified,'resolved_material_no',resolved_material_no,'sku_resolved',sku_resolved,{sap_line}
      'needs_review',line_needs_review)))) line_items_json
  FROM po
  GROUP BY doc_id, order_key
),
q AS (
  -- order_id goes in app URLs, which can't contain '/': non-manifest docs (doc_id = file path) get a short hash,
  -- and '/' or whitespace in PO numbers is replaced
  SELECT a.*,
    regexp_replace(concat(coalesce(m.doc_id, concat('doc-', substr(sha2(a.doc_id, 256), 1, 12))), '#',
                          CASE WHEN a.po_ok THEN a.po_number
                               ELSE concat(coalesce(a.po_number, 'order'), '-', a.order_idx + 1) END),
                   '[/\\\\s]', '-') order_id,
    coalesce(m.doc_id, a.attachment_filename) doc_name,
    x.extractor, x.fallback_reason,
    get_json_object(x.field_confidence, concat('$.orders[', a.order_idx, '].fields')) field_confidence_json,
    CASE WHEN p.parse_method = 'ai_parse_document' THEN 'pdf'
         WHEN p.parse_method = 'text' THEN 'email/text' ELSE 'spreadsheet' END orig_format,
    substr(p.parsed_content, 1, 20000) parsed_content,
    -- the app serves the source as a PDF, so only link real PDFs that sit directly in the Volume (not .msg/.eml parts)
    coalesce(m.volume_path,
      CASE WHEN p.attachment_mime_type = 'application/pdf' AND lower(a.source_path) NOT LIKE '%.msg' AND lower(a.source_path) NOT LIKE '%.eml'
           THEN regexp_replace(a.source_path, '^dbfs:', '') END) volume_path,
    upper(regexp_replace(a.po_number, '[^A-Za-z0-9]', '')) po_norm,
    coalesce(a.resolved_sap_sold_to, nullif(lower(regexp_replace(a.customer_name, '[^A-Za-z0-9]', '')), '')) cust_key
  FROM agg a
  LEFT JOIN {S}.parsed_attachments p
    ON a.source_path = p.source_path AND a.attachment_filename = p.attachment_filename
  LEFT JOIN (SELECT source_path sp_x, attachment_filename af_x, {x_extractor} extractor, {x_reason} fallback_reason,
                    {x_conf} field_confidence FROM {S}.extracted_parsed x) x
    ON a.source_path = x.sp_x AND a.attachment_filename = x.af_x
  LEFT JOIN {S}.email_manifest m ON a.attachment_filename = m.attachment_filename
),
k AS (
  -- Order-level dedup key: same (valid) PO number for the same customer. An email body and its attachment
  -- share the source .msg, so the body inherits the attachment's customer before keying.
  SELECT q.*,
    CASE WHEN po_ok THEN concat(po_norm, '|',
      coalesce(max(cust_key) OVER (PARTITION BY source_path, po_norm), source_path)) END dedup_key
  FROM q
),
d AS (
  SELECT k.*,
    ROW_NUMBER() OVER (PARTITION BY coalesce(dedup_key, order_id) ORDER BY
      CASE WHEN attachment_filename LIKE '%body.txt' THEN 1 ELSE 0 END, n_lines DESC, received_at NULLS LAST, order_id) dup_rank,
    FIRST_VALUE(order_id) OVER (PARTITION BY coalesce(dedup_key, order_id) ORDER BY
      CASE WHEN attachment_filename LIKE '%body.txt' THEN 1 ELSE 0 END, n_lines DESC, received_at NULLS LAST, order_id) first_order
  FROM k
)
SELECT order_id, doc_name, orig_format, po_number, customer_name, {q_customer_number} customer_number, order_date,
  {q_currency}, {q_sales_org} sales_org, ship_to, resolved_sap_sold_to,
  header_confidence, n_lines, line_items_json, avg_line_confidence, parse_confidence, parsed_content, volume_path,
  overall_confidence,
  CASE WHEN dup_rank > 1 THEN 'duplicate' ELSE 'pending' END status,
  'ok' extraction_status, parse_truncated,
  CASE WHEN dup_rank > 1 THEN concat_ws('; ', concat('Duplicate of order ', first_order), nullif(review_reasons, ''))
       ELSE nullif(review_reasons, '') END review_reasons,
  CASE WHEN dup_rank > 1 THEN first_order END duplicate_of,
  source_path, attachment_filename{q_sap_tail},                         -- source document (links the order to its trace)
  extractor, fallback_reason, field_confidence_json, order_idxs
FROM d

UNION ALL

-- Documents with nothing to review line-by-line are queued anyway (0 lines, confidence 0 -> top of the queue)
-- so a person handles them instead of losing them: extraction failed, or no ordered (quantity > 0) lines found.
-- Email bodies with no order ("see attached") are skipped.
SELECT concat('doc-', substr(sha2(concat(e.source_path, ' :: ', e.attachment_filename), 256), 1, 12), '#',
              CASE WHEN e.extraction_status = 'ok' THEN 'no-lines' ELSE 'failed' END),
  e.attachment_filename,
  CASE WHEN p.parse_method = 'ai_parse_document' THEN 'pdf'
       WHEN p.parse_method = 'text' THEN 'email/text' ELSE 'spreadsheet' END,
  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS DOUBLE), CAST(0 AS BIGINT), '[]', CAST(NULL AS DOUBLE), round(e.parse_confidence,3),
  substr(p.parsed_content,1,20000),
  CASE WHEN p.attachment_mime_type = 'application/pdf' AND lower(e.source_path) NOT LIKE '%.msg' AND lower(e.source_path) NOT LIKE '%.eml'
       THEN regexp_replace(e.source_path, '^dbfs:', '') END,
  CAST(0.0 AS DOUBLE), 'pending',
  e.extraction_status, p.parse_truncated,
  CASE e.extraction_status
    WHEN 'ai_error' THEN concat('Extraction failed: ', substr(e.ai_error, 1, 200))
    WHEN 'unparseable' THEN 'Extraction returned unreadable output (often: document too long for one call)'
    ELSE 'No ordered lines (quantity > 0) found — check whether this is an order' END,
  CAST(NULL AS STRING),
  e.source_path, e.attachment_filename{q_sap_null_tail},
  {e_extractor}, {e_reason}, CAST(NULL AS STRING), CAST(NULL AS ARRAY<INT>)
FROM {S}.extracted_parsed e
LEFT JOIN {S}.parsed_attachments p
  ON e.source_path = p.source_path AND e.attachment_filename = p.attachment_filename
WHERE (e.extraction_status IN ('ai_error', 'unparseable')
       OR (e.extraction_status IN ('ok', 'no_orders')
           AND NOT EXISTS (SELECT 1 FROM {S}.purchase_orders po
                           WHERE po.source_path = e.source_path AND po.attachment_filename = e.attachment_filename)))
  AND NOT (e.attachment_filename LIKE '%body.txt' AND e.extraction_status IN ('ok', 'no_orders'))

UNION ALL

-- Documents whose parsed content duplicates an earlier file were not re-extracted; show them, marked.
SELECT concat('doc-', substr(sha2(concat(e.source_path, ' :: ', e.attachment_filename), 256), 1, 12), '#duplicate'),
  e.attachment_filename,
  CASE WHEN p.parse_method = 'ai_parse_document' THEN 'pdf'
       WHEN p.parse_method = 'text' THEN 'email/text' ELSE 'spreadsheet' END,
  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING),
  CAST(NULL AS DOUBLE), CAST(0 AS BIGINT), '[]', CAST(NULL AS DOUBLE), round(e.parse_confidence,3),
  substr(p.parsed_content,1,20000),
  CASE WHEN p.attachment_mime_type = 'application/pdf' AND lower(e.source_path) NOT LIKE '%.msg' AND lower(e.source_path) NOT LIKE '%.eml'
       THEN regexp_replace(e.source_path, '^dbfs:', '') END,
  CAST(NULL AS DOUBLE), 'duplicate',
  e.extraction_status, p.parse_truncated,
  concat('Same content as ', e.duplicate_of, ' (not extracted again)'),
  e.duplicate_of,
  e.source_path, e.attachment_filename{q_sap_null_tail},
  {e_extractor}, {e_reason}, CAST(NULL AS STRING), CAST(NULL AS ARRAY<INT>)
FROM {S}.extracted_parsed e
LEFT JOIN {S}.parsed_attachments p
  ON e.source_path = p.source_path AND e.attachment_filename = p.attachment_filename
WHERE e.extraction_status = 'duplicate'
),
{region_tail}""")
print("review_orders rows:", spark.table(f"{S}.review_orders").count())
```

**Output:**

```
review_orders rows: 217
```

```python
# Citations for the app: Gold extraction_citations (hybrid; ai_extract documents only) keyed to the review row.
# One row per (order_id, order_idx, li_idx, field, citation, location); li_idx NULL = a header field. See
# docs/ARCHITECTURE.md "Citations".
CIT_COLS = ("order_idx, li_idx, field, value, confidence, citation_id, source_kind, page_index, x1, y1, x2, y2, "
            "element_id, element_type, table_row_index, table_row_count, sheet_index, sheet_name, row_number, "
            "cell_ref, char_start, char_stop, snippet, b_input")
# Use citations only when the current Gold run is hybrid: after switching to extraction_mode=ai_query the pipeline no
# longer refreshes extraction_citations, but a table left from an earlier hybrid run can remain and must not be shown.
_ep_props = {r["key"]: r["value"] for r in spark.sql(f"SHOW TBLPROPERTIES {S}.extracted_parsed").collect()}
_hybrid_run = _ep_props.get("extraction_mode", "ai_query") == "hybrid"   # older Gold has no property: no citations
print("extraction_mode (Gold):", _ep_props.get("extraction_mode"), "-> citations", "on" if _hybrid_run else "off")
if _hybrid_run and spark.catalog.tableExists(f"{S}.extraction_citations"):
    cit_src = f"{S}.extraction_citations"
else:   # ai_query mode / older Gold: an empty table with the same columns
    cit_src = ("(SELECT * FROM VALUES (CAST(NULL AS STRING), CAST(NULL AS STRING)) t(source_path, attachment_filename) "
               "LATERAL VIEW inline(CAST(array() AS ARRAY<STRUCT<order_idx:INT,li_idx:INT,field:STRING,value:STRING,"
               "confidence:DOUBLE,citation_id:INT,source_kind:STRING,page_index:INT,x1:DOUBLE,y1:DOUBLE,x2:DOUBLE,"
               "y2:DOUBLE,element_id:INT,element_type:STRING,table_row_index:INT,table_row_count:INT,sheet_index:INT,"
               "sheet_name:STRING,row_number:INT,cell_ref:STRING,char_start:INT,char_stop:INT,snippet:STRING,"
               "b_input:STRING>>)) c)")
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.review_citations AS
SELECT sha2(concat_ws('|', r.order_id, c.order_idx, coalesce(c.li_idx, -1), c.field, c.citation_id,
                      coalesce(c.page_index, c.sheet_index, -1), coalesce(c.row_number, -1),
                      coalesce(c.x1, c.char_start, -1)), 256) citation_key,
  r.order_id, c.source_path, c.attachment_filename, {', '.join('c.' + x.strip() for x in CIT_COLS.split(','))}
FROM {cit_src} c
JOIN (SELECT order_id, source_path, attachment_filename, explode(order_idxs) order_idx
      FROM {S}.review_orders WHERE order_idxs IS NOT NULL AND status <> 'duplicate') r
  ON r.source_path = c.source_path AND r.attachment_filename = c.attachment_filename AND r.order_idx = c.order_idx
""")
print("review_citations rows:", spark.table(f"{S}.review_citations").count())
```

**Output:**

```
extraction_mode (Gold): hybrid -> citations on
review_citations rows: 12018
```

