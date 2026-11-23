# [dev <deployer>] fe_bar_order_intake_bootstrap / evaluate (run 179023887435266, as executed, with outputs)

Notebook `da983beb-edb4-4a8f-b0a8-b4cd4bab3f16`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## FE Bar 10: Score the run against the answer key and compute time and $ saved
Reads what the accelerator produced (`purchase_orders` lines, `review_orders` queue) and the corpus answer key
(`gt_*`, loaded by `00_load_corpus.py`). Writes the tables the Genie space and the evidence report use:

| table | grain | what |
|---|---|---|
| `eval_line_results` | answer-key line | found? material right? quantity right? |
| `eval_order_results` | answer-key PO | PO number found, customer resolved to the right sold-to, line recall, routed to review? |
| `eval_doc_results` | document | the above rolled up, plus the time, FTE and labour-$ model |
| `roi_assumptions` | one row per parameter | the editable time, volume, FTE and labour-cost assumptions (illustrative, not measured) |

**Matching rules.** A corpus document is identified by `DOC-xxxxx` in the source path, and an email's parts belong
to the email. A PO matches when the normalized PO numbers are equal (upper case, alphanumerics only, letter `O`
read as `0`). A line matches when the same document and PO has an extracted line whose **resolved material**
equals the answer key's `material_id`. Its quantity is right when it equals the quantity as written or the quantity
in eaches. Cancelled lines and lines whose answer is `UNRESOLVABLE` are reported separately; a correct
pipeline must route those to a person.

```python
dbutils.widgets.text("catalog", "evan_aws_01_catalog")
dbutils.widgets.text("schema", "fe_bar_fy27")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
S = f"{catalog}.{schema}"
spark.sql(f"USE {S}")
```

**Output:**

```
{"text/plain": "DataFrame[]"}
```

### ROI assumptions (editable; seeded only when the table is empty)

```python
spark.sql("""CREATE TABLE IF NOT EXISTS roi_assumptions (parameter STRING, value DOUBLE, unit STRING, rationale STRING)
COMMENT 'Assumptions behind the time, FTE and $ saved metrics. Illustrative planning values, not measurements: edit them and re-run 10_evaluate.'""")
if spark.table("roi_assumptions").count() == 0:
    spark.createDataFrame([
        ("manual_min_per_order", 3.0, "minutes", "Open the email or file, find PO, customer and ship-to, create the order header in the ERP"),
        ("manual_min_per_line", 0.75, "minutes", "Key one line: look up the material (retailer item, GTIN or name), quantity, UOM, price"),
        ("complexity_mult_1", 1.0, "x", "Complexity 1 (EDI, portal export): manual effort multiplier"),
        ("complexity_mult_2", 1.2, "x", "Complexity 2 (Excel, price list, email body)"),
        ("complexity_mult_3", 1.5, "x", "Complexity 3 (fax, phone, handwritten, amended scans)"),
        ("complexity_mult_4", 2.0, "x", "Complexity 4 (multi-PO, 90+ lines, phone photos, multimodal)"),
        ("review_min_clean_order", 0.5, "minutes", "Glance and approve an order with no review reasons"),
        ("review_min_flagged_order", 2.0, "minutes", "Open a flagged order in the Review App and check the header"),
        ("review_min_flagged_line", 0.25, "minutes", "Check one line next to the source document"),
        ("rework_min_per_missed_line", 0.75, "minutes", "Key a line the pipeline missed or got wrong (same as manual)"),
        ("loaded_cost_per_hour_usd", 40.0, "USD/hour", "Fully loaded cost of a customer-service order-entry rep"),
    ], "parameter string, value double, unit string, rationale string").write.mode("append").saveAsTable("roi_assumptions")
# parameters added later: inserted when missing, existing values kept
spark.createDataFrame([
    ("annual_documents", 40000.0, "documents/year", "Inbound order documents a year (about 160 per working day) with the corpus' channel mix"),
    ("fte_productive_hours_per_year", 1680.0, "hours/FTE/year", "Productive hours of one full-time rep (after leave, training, meetings)"),
], "parameter string, value double, unit string, rationale string").createOrReplaceTempView("_new_assumptions")
spark.sql("""MERGE INTO roi_assumptions t USING _new_assumptions s ON t.parameter = s.parameter
             WHEN NOT MATCHED THEN INSERT *""")
A = {r.parameter: r.value for r in spark.table("roi_assumptions").collect()}
display(spark.table("roi_assumptions"))
```

**Output:**

| parameter | value | unit | rationale |
|---|---|---|---|
| manual_min_per_order | 3.0 | minutes | Open the email or file, find PO, customer and ship-to, create the order header in the ERP |
| manual_min_per_line | 0.75 | minutes | Key one line: look up the material (retailer item, GTIN or name), quantity, UOM, price |
| complexity_mult_1 | 1.0 | x | Complexity 1 (EDI, portal export): manual effort multiplier |
| complexity_mult_2 | 1.2 | x | Complexity 2 (Excel, price list, email body) |
| complexity_mult_3 | 1.5 | x | Complexity 3 (fax, phone, handwritten, amended scans) |
| complexity_mult_4 | 2.0 | x | Complexity 4 (multi-PO, 90+ lines, phone photos, multimodal) |
| review_min_clean_order | 0.5 | minutes | Glance and approve an order with no review reasons |
| review_min_flagged_order | 2.0 | minutes | Open a flagged order in the Review App and check the header |
| review_min_flagged_line | 0.25 | minutes | Check one line next to the source document |
| rework_min_per_missed_line | 0.75 | minutes | Key a line the pipeline missed or got wrong (same as manual) |
| loaded_cost_per_hour_usd | 40.0 | USD/hour | Fully loaded cost of a customer-service order-entry rep |
| annual_documents | 40000.0 | documents/year | Inbound order documents a year (about 160 per working day) with the corpus' channel mix |
| fte_productive_hours_per_year | 1680.0 | hours/FTE/year | Productive hours of one full-time rep (after leave, training, meetings) |

### Line-level scoring

```python
spark.sql("""
CREATE OR REPLACE TEMP VIEW _pred_lines AS
SELECT regexp_extract(source_path, '(DOC-[0-9]{5})', 1) doc_id,
       translate(upper(regexp_replace(coalesce(po_number, ''), '[^A-Za-z0-9]', '')), 'O', '0') po_norm,
       po_number, resolved_sap_sold_to, resolved_material_no, printed_sku, description, quantity, uom,
       line_needs_review, order_confidence, review_reasons
FROM purchase_orders
""")
spark.sql("""
CREATE OR REPLACE TABLE eval_line_results COMMENT 'One row per answer-key order line: was it extracted with the right material and quantity?' AS
WITH gt AS (
  SELECT l.* EXCEPT (po_number), coalesce(l.po_number, '') po_number, translate(upper(regexp_replace(coalesce(l.po_number, ''), '[^A-Za-z0-9]', '')), 'O', '0') po_norm,
         CAST(l.qty_as_written AS DOUBLE) qw, CAST(l.qty_each AS DOUBLE) qe
  FROM gt_lines l
),
po_has AS (SELECT DISTINCT doc_id, po_norm FROM _pred_lines),
m AS (
  SELECT g.doc_id, g.po_number, g.line_no, any_value(g.line_action) line_action, any_value(g.raw_item_text) raw_item_text,
         any_value(g.material_id) material_id, any_value(g.qw) qty_as_written, any_value(g.qe) qty_each,
         any_value(g.uom_as_written) uom_as_written, any_value(g.is_free_goods) is_free_goods,
         count(p.resolved_material_no) > 0 material_found,
         max(CASE WHEN p.quantity = g.qw OR p.quantity = g.qe THEN 1 ELSE 0 END) = 1 qty_correct,
         max(CASE WHEN p.quantity = g.qe THEN 1 ELSE 0 END) = 1 qty_in_eaches,
         max(CAST(p.line_needs_review AS INT)) = 1 flagged
  FROM gt g
  LEFT JOIN po_has ph ON ph.doc_id = g.doc_id AND ph.po_norm = g.po_norm
  LEFT JOIN _pred_lines p
    ON p.doc_id = g.doc_id AND p.resolved_material_no = g.material_id
   AND (p.po_norm = g.po_norm OR ph.po_norm IS NULL)          -- PO not extracted: match within the document
  GROUP BY g.doc_id, g.po_number, g.line_no
)
SELECT m.*, man.channel, man.retailer, man.doc_type, CAST(man.complexity AS INT) complexity,
  CASE WHEN line_action = 'CANCEL' THEN 'cancel_line'
       WHEN material_id = 'UNRESOLVABLE' THEN 'unresolvable'
       ELSE 'orderable' END line_class,
  (material_found AND qty_correct) line_correct
FROM m JOIN gt_manifest man USING (doc_id)
""")
display(spark.sql("""SELECT line_class, count(*) lines, round(avg(CAST(material_found AS INT)),3) material_recall,
  round(avg(CAST(line_correct AS INT)),3) material_and_qty_correct FROM eval_line_results GROUP BY 1 ORDER BY 1"""))
```

**Output:**

| line_class | lines | material_recall | material_and_qty_correct |
|---|---|---|---|
| cancel_line | 17 | 0.471 | 0.471 |
| orderable | 2605 | 0.778 | 0.778 |
| unresolvable | 97 | 0.0 | 0.0 |

### Order-level scoring (per answer-key PO) and the review queue

```python
spark.sql("""
CREATE OR REPLACE TEMP VIEW _queue AS
SELECT regexp_extract(source_path, '(DOC-[0-9]{5})', 1) doc_id,
       translate(upper(regexp_replace(coalesce(po_number, ''), '[^A-Za-z0-9]', '')), 'O', '0') po_norm,
       order_id, status, region, overall_confidence, n_lines, resolved_sap_sold_to, customer_name, review_reasons,
       (review_reasons IS NOT NULL AND review_reasons <> '') needs_review
FROM review_orders
""")
spark.sql("""
CREATE OR REPLACE TABLE eval_order_results COMMENT 'One row per answer-key purchase order: PO found, customer resolved correctly, line recall, routed to review.' AS
WITH h AS (
  SELECT h.* EXCEPT (po_number), coalesce(h.po_number, '') po_number,
         translate(upper(regexp_replace(coalesce(h.po_number, ''), '[^A-Za-z0-9]', '')), 'O', '0') po_norm FROM gt_headers h
),
q AS (
  SELECT h.doc_id, h.po_number, h.po_norm,
    max(CASE WHEN q.po_norm = h.po_norm AND h.po_norm <> '' THEN 1 ELSE 0 END) = 1 po_found,
    max(CASE WHEN q.resolved_sap_sold_to = h.sold_to_id THEN 1 ELSE 0 END) = 1 customer_correct,
    max(CAST(q.needs_review AS INT)) = 1 needs_review,
    max(CASE WHEN q.status = 'duplicate' THEN 1 ELSE 0 END) = 1 flagged_duplicate,
    min(q.overall_confidence) min_confidence,
    any_value(q.region) queue_region
  FROM h LEFT JOIN _queue q
    ON q.doc_id = h.doc_id AND (q.po_norm = h.po_norm OR h.po_norm = '' OR q.po_norm = '')
  GROUP BY h.doc_id, h.po_number, h.po_norm
),
l AS (
  SELECT doc_id, po_number,
    count_if(line_class = 'orderable') lines_orderable,
    count_if(line_class = 'orderable' AND line_correct) lines_correct,
    count_if(line_class <> 'orderable') lines_exception,
    count_if(flagged) lines_flagged
  FROM eval_line_results GROUP BY doc_id, po_number
)
SELECT h.doc_id, h.po_number, h.sold_to_id, h.order_type, h.is_duplicate_of, h.currency,
  q.po_found, q.customer_correct, coalesce(q.needs_review, true) needs_review, q.flagged_duplicate, q.min_confidence, q.queue_region,
  coalesce(l.lines_orderable, 0) lines_orderable, coalesce(l.lines_correct, 0) lines_correct,
  coalesce(l.lines_exception, 0) lines_exception, coalesce(l.lines_flagged, 0) lines_flagged,
  (h.po_number = '' OR q.po_found) AND q.customer_correct
    AND coalesce(l.lines_correct, 0) = coalesce(l.lines_orderable, 0) order_fully_correct
FROM h JOIN q USING (doc_id, po_number) LEFT JOIN l USING (doc_id, po_number)
""")
display(spark.sql("""SELECT count(*) pos, round(avg(CAST(po_found AS INT)),3) po_found, round(avg(CAST(customer_correct AS INT)),3) customer_correct,
  round(avg(CAST(order_fully_correct AS INT)),3) fully_correct, round(avg(CAST(needs_review AS INT)),3) routed_to_review,
  count_if(NOT needs_review AND NOT order_fully_correct) false_confidence FROM eval_order_results"""))
```

**Output:**

| pos | po_found | customer_correct | fully_correct | routed_to_review | false_confidence |
|---|---|---|---|---|---|
| 220 | 0.873 | 0.905 | 0.359 | 0.782 | 0 |

### Document-level results with the time, FTE and $ model
Manual minutes come from the answer key's true PO and line counts: (minutes per order + minutes per line × lines)
× the complexity multiplier. Assisted minutes are the reviewer's time in the Review App, plus re-keying every line
the pipeline missed or got wrong. **Annualised:** each document stands for `annual_documents / 184` documents a
year (the corpus mix is taken as the yearly mix); FTE = annual hours / `fte_productive_hours_per_year`. The FTE
columns are additive, so `sum(fte_saved)` over any slice (document type, region, ...) is that slice's FTE saved.
$ = labour only (hours × loaded cost per hour); platform cost is not modelled in this demo.

```python
n_docs = spark.table("gt_manifest").count()
scale = A["annual_documents"] / n_docs            # yearly documents represented by one corpus document
spark.sql(f"""
CREATE OR REPLACE TABLE eval_doc_results COMMENT 'One row per corpus document: accuracy, review routing, manual vs assisted minutes, annualised hours and FTE saved, labour $ saved.' AS
WITH o AS (
  SELECT doc_id, count(*) n_pos, count_if(po_number <> '') n_pos_with_number, count_if(po_found) pos_found, count_if(customer_correct) customers_correct,
    count_if(order_fully_correct) pos_fully_correct, count_if(needs_review) pos_needs_review,
    count_if(NOT needs_review) pos_clean, count_if(NOT needs_review AND NOT order_fully_correct) pos_false_confidence,
    sum(lines_orderable) lines_orderable, sum(lines_correct) lines_correct, sum(lines_exception) lines_exception,
    sum(lines_flagged) lines_flagged, min(min_confidence) min_confidence, any_value(queue_region) queue_region
  FROM eval_order_results GROUP BY doc_id
),
d AS (
  SELECT m.doc_id, m.channel, m.retailer, m.file_format, m.doc_type, CAST(m.complexity AS INT) complexity,
    CAST(m.line_count AS INT) gt_lines, CAST(m.received_at AS TIMESTAMP) received_at,
    c.sold_to_id, c.country, coalesce(rm.region, 'Other') region, c.region corpus_region, c.currency,
    o.* EXCEPT (doc_id)
  FROM gt_manifest m
  JOIN o USING (doc_id)
  LEFT JOIN md_customers c ON c.customer_name = m.retailer
  LEFT JOIN region_map rm ON upper(rm.country) = upper(c.country)
),
t AS (
  SELECT d.*,
    ({A['manual_min_per_order']} * n_pos + {A['manual_min_per_line']} * gt_lines)
      * CASE complexity WHEN 1 THEN {A['complexity_mult_1']} WHEN 2 THEN {A['complexity_mult_2']}
                        WHEN 3 THEN {A['complexity_mult_3']} ELSE {A['complexity_mult_4']} END manual_minutes,
    {A['review_min_clean_order']} * pos_clean + {A['review_min_flagged_order']} * pos_needs_review
      + {A['review_min_flagged_line']} * lines_flagged
      + {A['rework_min_per_missed_line']} * (gt_lines - lines_correct) assisted_minutes
  FROM d
)
SELECT *, manual_minutes - assisted_minutes minutes_saved,
  round(manual_minutes / 60 * {scale}, 2) annual_manual_hours,
  round(assisted_minutes / 60 * {scale}, 2) annual_assisted_hours,
  round((manual_minutes - assisted_minutes) / 60 * {scale}, 2) annual_hours_saved,
  round(manual_minutes / 60 * {scale} / {A['fte_productive_hours_per_year']}, 4) fte_manual,
  round(assisted_minutes / 60 * {scale} / {A['fte_productive_hours_per_year']}, 4) fte_assisted,
  round((manual_minutes - assisted_minutes) / 60 * {scale} / {A['fte_productive_hours_per_year']}, 4) fte_saved,
  round((manual_minutes - assisted_minutes) / 60 * {scale} * {A['loaded_cost_per_hour_usd']}, 2) annual_usd_saved,
  CASE WHEN lines_orderable > 0 THEN round(lines_correct / lines_orderable, 3) END line_accuracy,
  (pos_fully_correct = n_pos) doc_fully_correct
FROM t
""")
display(spark.table("eval_doc_results").limit(10))
```

**Output:**

| doc_id | channel | retailer | file_format | doc_type | complexity | gt_lines | received_at | sold_to_id | country | region | corpus_region | currency | n_pos | n_pos_with_number | pos_found | customers_correct | pos_fully_correct | pos_needs_review | pos_clean | pos_false_confidence | lines_orderable | lines_correct | lines_exception | lines_flagged | min_confidence | queue_region | manual_minutes | assisted_minutes | minutes_saved | annual_manual_hours | annual_assisted_hours | annual_hours_saved | fte_manual | fte_assisted | fte_saved | annual_usd_saved | line_accuracy | doc_fully_correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DOC-00038 | fax | Pharmacie Lumen | pdf | fax | 3 | 12 | 2026-09-21T16:32:45.000Z | 200300 | FR | France | EMEA | EUR | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 12 | 12 | 0 | 0 | 0.96 | France | 18.000 | 0.50 | 17.500 | 65.22 | 1.81 | 63.41 | 0.0388 | 0.0011 | 0.0377 | 2536.23 | 1.0 | True |
| DOC-00104 | phone | Kensington Salon Supply | txt | phone | 3 | 5 | 2026-09-08T11:25:42.000Z | 400800 | GB | UK & Ireland | EMEA | GBP | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 5 | 0 | 0 | 0 | 0.375 | UK & Ireland | 10.125 | 5.75 | 4.375 | 36.68 | 20.83 | 15.85 | 0.0218 | 0.0124 | 0.0094 | 634.06 | 0.0 | False |
| DOC-00090 | portal_export | BeautyHaus Online | json | portal_export | 1 | 30 | 2026-09-28T13:12:03.000Z | 200600 | DE | DACH | EMEA | EUR | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 30 | 30 | 0 | 30 | 0.55 | DACH | 25.500 | 9.50 | 16.000 | 92.39 | 34.42 | 57.97 | 0.0550 | 0.0205 | 0.0345 | 2318.84 | 1.0 | True |
| DOC-00154 | multimodal | Parfümerie Lindqvist | pdf | promo_form | 2 | 4 | 2026-09-08T11:55:11.000Z | 200652 | DE | DACH | EMEA | EUR | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 4 | 4 | 0 | 4 | 0.781 | DACH | 7.200 | 3.00 | 4.200 | 26.09 | 10.87 | 15.22 | 0.0155 | 0.0065 | 0.0091 | 608.70 | 1.0 | True |
| DOC-00181 | email_body | Al Noor Trading | eml | email_body | 3 | 3 | 2026-09-22T14:05:44.000Z | 300700 | AE | Middle East | MEA | AED | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 0.55 | Middle East | 7.875 | 4.25 | 3.625 | 28.53 | 15.40 | 13.13 | 0.0170 | 0.0092 | 0.0078 | 525.37 | 0.0 | False |
| DOC-00171 | multimodal | Al Noor Trading | eml | email_inline | 2 | 4 | 2026-09-11T08:55:50.000Z | 300700 | AE | Middle East | MEA | AED | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 0 | 0 | 0 |  |  | 7.200 | 5.00 | 2.200 | 26.09 | 18.12 | 7.97 | 0.0155 | 0.0108 | 0.0047 | 318.84 | 0.0 | False |
| DOC-00064 | excel_buysheet | Meridian Travel Retail | xlsx | excel_buysheet | 3 | 56 | 2026-09-01T19:32:26.000Z | 300500 | AE | Middle East | Travel Retail | USD\|EUR | 4 | 4 | 4 | 4 | 2 | 3 | 1 | 0 | 53 | 50 | 3 | 0 | 1.0 | Middle East | 81.000 | 11.00 | 70.000 | 293.48 | 39.86 | 253.62 | 0.1747 | 0.0237 | 0.1510 | 10144.93 | 0.943 | False |
| DOC-00008 | erp_edi | Halcyon & Finch | edi | erp_edi | 1 | 18 | 2026-09-06T17:18:27.000Z | 100100 | US | North America | NA | USD | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 17 | 4 | 1 | 4 | 0.55 | North America | 16.500 | 13.50 | 3.000 | 59.78 | 48.91 | 10.87 | 0.0356 | 0.0291 | 0.0065 | 434.78 | 0.235 | False |
| DOC-00167 | multimodal | Kensington Salon Supply | png | chat_screenshot | 3 | 5 | 2026-09-28T17:01:26.000Z | 400800 | GB | UK & Ireland | EMEA | GBP | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 5 | 0 | 0 | 0 | 0.32 | DACH | 10.125 | 5.75 | 4.375 | 36.68 | 20.83 | 15.85 | 0.0218 | 0.0124 | 0.0094 | 634.06 | 0.0 | False |
| DOC-00140 | amended_scan | Harlow & Vale | pdf | amended_scan | 3 | 25 | 2026-09-18T06:43:24.000Z | 401000 | GB | UK & Ireland | EMEA | GBP | 1 | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 24 | 22 | 1 | 0 | 0.96 | UK & Ireland | 32.625 | 4.25 | 28.375 | 118.21 | 15.40 | 102.81 | 0.0704 | 0.0092 | 0.0612 | 4112.32 | 0.917 | False |

### Headline results

```python
summary = spark.sql("""
SELECT count(*) documents, sum(n_pos) purchase_orders, sum(gt_lines) answer_key_lines,
  round(sum(pos_found) / sum(n_pos_with_number), 3) po_found_rate,
  round(sum(customers_correct) / sum(n_pos), 3) customer_correct_rate,
  round(sum(lines_correct) / sum(lines_orderable), 3) line_accuracy,
  round(sum(pos_needs_review) / sum(n_pos), 3) review_rate,
  sum(pos_false_confidence) false_confidence_pos,
  round(sum(manual_minutes) / 60, 1) corpus_manual_hours, round(sum(assisted_minutes) / 60, 1) corpus_assisted_hours,
  round(sum(minutes_saved) / sum(manual_minutes), 3) time_saved_share,
  round(sum(annual_manual_hours), 0) annual_manual_hours, round(sum(annual_hours_saved), 0) annual_hours_saved,
  round(sum(fte_manual), 1) fte_manual, round(sum(fte_assisted), 1) fte_assisted, round(sum(fte_saved), 1) fte_saved,
  round(sum(annual_usd_saved), 0) annual_usd_saved
FROM eval_doc_results
""")
display(summary)
display(spark.sql("""SELECT channel, count(*) docs, sum(gt_lines) lines, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy,
  round(sum(pos_needs_review)/sum(n_pos),3) review_rate, round(sum(fte_saved),2) fte_saved, round(sum(annual_usd_saved),0) annual_usd_saved
  FROM eval_doc_results GROUP BY channel ORDER BY fte_saved DESC"""))
spark.sql("DROP TABLE IF EXISTS run_cost")   # earlier versions billed cost; not part of the FTE demo
import json
dbutils.notebook.exit(json.dumps(summary.first().asDict(), default=str))
```

**Output:**

```
{"documents": 184, "purchase_orders": 220, "answer_key_lines": 2719, "po_found_rate": 0.941, "customer_correct_rate": 0.905, "line_accuracy": 0.778, "review_rate": 0.782, "false_confidence_pos": 0, "corpus_manual_hours": "62.6", "corpus_assisted_hours": "17.4", "time_saved_share": "0.723", "annual_manual_hours": "13604", "annual_hours_saved": "9832", "fte_manual": "8.1", "fte_assisted": "2.2", "fte_saved": "5.9", "annual_usd_saved": "393294"}
```

