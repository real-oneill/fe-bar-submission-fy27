# Databricks notebook source
# MAGIC %md
# MAGIC ## FE Bar 10: Score the run against the answer key and compute time and $ saved
# MAGIC Reads what the accelerator produced (`purchase_orders` lines, `review_orders` queue) and the corpus answer key
# MAGIC (`gt_*`, loaded by `00_load_corpus.py`). Writes the tables the Genie space and the evidence report use:
# MAGIC
# MAGIC | table | grain | what |
# MAGIC |---|---|---|
# MAGIC | `eval_line_results` | answer-key line | found? material right? quantity right? |
# MAGIC | `eval_order_results` | answer-key PO | PO number found, customer resolved to the right sold-to, line recall, routed to review? |
# MAGIC | `eval_doc_results` | document | the above rolled up, plus the time, FTE and labour-$ model |
# MAGIC | `roi_assumptions` | one row per parameter | the editable time, volume, FTE and labour-cost assumptions (illustrative, not measured) |
# MAGIC
# MAGIC **Matching rules.** A corpus document is identified by `DOC-xxxxx` in the source path, and an email's parts belong
# MAGIC to the email. A PO matches when the normalized PO numbers are equal (upper case, alphanumerics only, letter `O`
# MAGIC read as `0`). A line matches when the same document and PO has an extracted line whose **resolved material**
# MAGIC equals the answer key's `material_id`. Its quantity is right when it equals the quantity as written or the quantity
# MAGIC in eaches. Cancelled lines and lines whose answer is `UNRESOLVABLE` are reported separately; a correct
# MAGIC pipeline must route those to a person.

# COMMAND ----------
dbutils.widgets.text("catalog", "evan_aws_01_catalog")
dbutils.widgets.text("schema", "fe_bar_fy27")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
S = f"{catalog}.{schema}"
spark.sql(f"USE {S}")

# COMMAND ----------
# MAGIC %md ### ROI assumptions (editable; seeded only when the table is empty)

# COMMAND ----------
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

# COMMAND ----------
# MAGIC %md ### Line-level scoring

# COMMAND ----------
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

# COMMAND ----------
# MAGIC %md ### Order-level scoring (per answer-key PO) and the review queue

# COMMAND ----------
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

# COMMAND ----------
# MAGIC %md ### Document-level results with the time, FTE and $ model
# MAGIC Manual minutes come from the answer key's true PO and line counts: (minutes per order + minutes per line × lines)
# MAGIC × the complexity multiplier. Assisted minutes are the reviewer's time in the Review App, plus re-keying every line
# MAGIC the pipeline missed or got wrong. **Annualised:** each document stands for `annual_documents / 184` documents a
# MAGIC year (the corpus mix is taken as the yearly mix); FTE = annual hours / `fte_productive_hours_per_year`. The FTE
# MAGIC columns are additive, so `sum(fte_saved)` over any slice (document type, region, ...) is that slice's FTE saved.
# MAGIC $ = labour only (hours × loaded cost per hour); platform cost is not modelled in this demo.

# COMMAND ----------
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

# COMMAND ----------
# MAGIC %md ### Headline results

# COMMAND ----------
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
