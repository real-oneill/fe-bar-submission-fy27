# Databricks notebook source
# MAGIC %md
# MAGIC ## Quality 05 — Log one MLflow trace per extracted document
# MAGIC Writes each newly extracted document to the quality experiment as a trace (root span = the document and its
# MAGIC extracted orders; child span = the `ai_query` call), attaches the deterministic extraction checks as **CODE**
# MAGIC feedback, records the trace in `quality_trace_index` (so a document is traced once per prompt version), and
# MAGIC stamps `trace_id` onto `review_orders` so the Review App can log reviewer feedback to the right trace.
# MAGIC
# MAGIC Traces are stored in Unity Catalog (`<catalog>.<schema>`), which requires a SQL warehouse for reads/writes.
# MAGIC Also grants the app's service principal what it needs to log feedback (experiment edit + trace tables).

# COMMAND ----------
# MAGIC %pip install "mlflow[databricks]>=3.16"
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import json
import os

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("experiment", ""), ("warehouse_id", ""),
             ("serving_endpoint", "databricks-claude-haiku-4-5"), ("app_name", "order-intake-review"),
             ("max_text_chars", "30000")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
experiment, warehouse_id = dbutils.widgets.get("experiment"), dbutils.widgets.get("warehouse_id")
endpoint, app_name = dbutils.widgets.get("serving_endpoint"), dbutils.widgets.get("app_name")
max_chars = int(dbutils.widgets.get("max_text_chars"))
S = f"{catalog}.{schema}"
if not experiment or not warehouse_id:
    raise ValueError("experiment and warehouse_id are required (traces live in UC and need a SQL warehouse)")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = warehouse_id

import mlflow
from mlflow.entities import AssessmentSource
from mlflow.entities.trace_location import UnityCatalog

mlflow.set_tracking_uri("databricks")
exp = mlflow.set_experiment(experiment_name=experiment, trace_location=UnityCatalog(catalog, schema))
print(f"experiment {experiment} ({exp.experiment_id}); traces in {S}")

# COMMAND ----------
# ---- which documents still need a trace (new docs, or re-extracted with a new prompt version) ----
spark.sql(f"""CREATE TABLE IF NOT EXISTS {S}.quality_trace_index (
  doc_key STRING, content_hash STRING, prompt_version STRING, trace_id STRING,
  logged_at TIMESTAMP, scored BOOLEAN)
  COMMENT 'One row per document traced to the quality experiment (written by src/quality/05_log_traces.py)'""")

props = {r["key"]: r["value"] for r in spark.sql(f"SHOW TBLPROPERTIES {S}.extracted_parsed").collect()}
# hybrid extraction (03_gold): extractor + fallback_reason per document; older Gold tables -> NULL
_ep_cols = set(spark.table(f"{S}.extracted_parsed").columns)
_x = (", e.extractor, e.fallback_reason" if {"extractor", "fallback_reason"} <= _ep_cols
      else ", CAST(NULL AS STRING) extractor, CAST(NULL AS STRING) fallback_reason")
prompt_uri, prompt_version = props.get("prompt_uri", ""), props.get("prompt_version", "")

docs = spark.sql(f"""
  WITH o AS (   -- order-level checks + reasons per document
    SELECT source_path, attachment_filename,
      min(order_confidence) order_confidence,
      avg(CASE WHEN line_verified THEN 1.0 ELSE 0.0 END) lines_verified_share,
      min(completeness) completeness, bool_and(po_ok) po_valid, bool_or(customer_is_supplier) customer_is_supplier,
      count(*) n_lines,
      array_join(array_distinct(filter(collect_list(review_reasons), x -> x <> '')), '; ') review_reasons
    FROM {S}.purchase_orders GROUP BY 1, 2)
  SELECT concat(e.source_path, ' :: ', e.attachment_filename) doc_key, e.source_path, e.attachment_filename,
    e.content_hash, e.extraction_status, e.ai_error, e.raw_response, to_json(e.po) po_json{_x},
    p.parse_method, p.parse_confidence, substr(p.parsed_content, 1, {max_chars}) parsed_text,
    o.order_confidence, o.lines_verified_share, o.completeness, o.po_valid, o.customer_is_supplier, o.n_lines,
    o.review_reasons,
    (SELECT concat_ws(',', collect_list(r.order_id)) FROM {S}.review_orders r
      WHERE r.source_path = e.source_path AND r.attachment_filename = e.attachment_filename) order_ids
  FROM {S}.extracted_parsed e
  LEFT JOIN {S}.parsed_attachments p ON e.source_path = p.source_path AND e.attachment_filename = p.attachment_filename
  LEFT JOIN o ON e.source_path = o.source_path AND e.attachment_filename = o.attachment_filename
  LEFT ANTI JOIN {S}.quality_trace_index t
    ON t.doc_key = concat(e.source_path, ' :: ', e.attachment_filename)
   AND t.content_hash <=> e.content_hash AND t.prompt_version = '{prompt_version}'
  WHERE e.extraction_status <> 'duplicate'
""").toPandas()
print(f"{len(docs)} document(s) to trace (prompt v{prompt_version})")

# COMMAND ----------
def _clean(v):
    """NaN/NumPy -> plain JSON-able Python."""
    if v is None:
        return None
    try:
        if v != v:  # NaN
            return None
    except Exception:
        pass
    return v.item() if hasattr(v, "item") else v


code = AssessmentSource(source_type="CODE", source_id="extraction_checks")


def _checks(trace_id, r):
    """Deterministic checks as CODE feedback — one scalar per assessment (the server rejects dict values)."""
    if r["order_confidence"] is None:
        return
    items = [
        ("order_confidence", float(r["order_confidence"]), r["review_reasons"] or "all checks passed"),
        ("po_valid", bool(r["po_valid"]), None),
        ("customer_not_supplier", not bool(r["customer_is_supplier"]), None),
        ("lines_verified_share", round(float(r["lines_verified_share"] or 0), 3), None),
        ("completeness", round(float(r["completeness"] or 0), 3), None),
    ]
    for name, value, rationale in items:
        mlflow.log_feedback(trace_id=trace_id, name=name, value=value, source=code, rationale=rationale)


from concurrent.futures import ThreadPoolExecutor

index_rows, futures, errors = [], [], []
pool = ThreadPoolExecutor(max_workers=8)
try:
    for r in docs.to_dict("records"):
        r = {k: _clean(v) for k, v in r.items()}
        orders = (json.loads(r["po_json"]) or {}).get("orders") if r.get("po_json") else None
        with mlflow.start_span(name="extract_order", span_type="CHAIN") as root:
            root.set_inputs({"document": r["attachment_filename"], "source_path": r["source_path"],
                             "parse_method": r["parse_method"], "parsed_text": r["parsed_text"]})
            with mlflow.start_span(name=r.get("extractor") or "ai_query", span_type="LLM") as llm:
                llm.set_inputs({"endpoint": endpoint if (r.get("extractor") or "ai_query") == "ai_query" else "ai_extract",
                                "prompt_uri": prompt_uri, "prompt_version": prompt_version,
                                "extractor": r.get("extractor"), "fallback_reason": r.get("fallback_reason")})
                llm.set_outputs({"raw_response": (r["raw_response"] or "")[:max_chars], "ai_error": r["ai_error"]})
            root.set_outputs({"orders": orders, "extraction_status": r["extraction_status"]})
            mlflow.update_current_trace(tags={
                # source_trace_id is set at creation so labeling-session copies inherit it (tags added later aren't copied)
                "source_trace_id": root.trace_id,
                "document": r["attachment_filename"], "prompt_version": prompt_version,
                "extraction_status": r["extraction_status"], "order_ids": r["order_ids"] or "",
                "parse_method": r["parse_method"] or "",
                "extractor": r.get("extractor") or "ai_query", "fallback_reason": (r.get("fallback_reason") or "")[:250]})
            trace_id = root.trace_id
        index_rows.append((r["doc_key"], r["content_hash"], prompt_version, trace_id))
        futures.append(pool.submit(_checks, trace_id, r))
    for f in futures:
        try:
            f.result()
        except Exception as e:  # noqa — a failed check annotation shouldn't lose the trace
            errors.append(str(e).splitlines()[0][:200])
finally:
    pool.shutdown(wait=True)
    # record whatever was traced, even on failure, so a re-run doesn't trace the same documents twice
    if index_rows:
        (spark.createDataFrame(index_rows, "doc_key string, content_hash string, prompt_version string, trace_id string")
         .selectExpr("*", "current_timestamp() logged_at", "false scored")
         .write.mode("append").saveAsTable(f"{S}.quality_trace_index"))
print(f"logged {len(index_rows)} trace(s); {len(errors)} check-annotation error(s)" + (f": {errors[:3]}" if errors else ""))

# COMMAND ----------
# ---- stamp trace_id onto the review queue ----

if "trace_id" not in [f.name for f in spark.table(f"{S}.review_orders").schema.fields]:
    spark.sql(f"ALTER TABLE {S}.review_orders ADD COLUMNS (trace_id STRING)")
spark.sql(f"""
  MERGE INTO {S}.review_orders r
  USING (SELECT doc_key, max_by(trace_id, logged_at) trace_id FROM {S}.quality_trace_index GROUP BY doc_key) t
  ON concat(r.source_path, ' :: ', r.attachment_filename) = t.doc_key
  WHEN MATCHED THEN UPDATE SET r.trace_id = t.trace_id""")

# COMMAND ----------
# ---- let the Review App log human feedback: experiment edit + the UC trace tables ----
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.ml import ExperimentAccessControlRequest, ExperimentPermissionLevel

w = WorkspaceClient()
app_sp = w.apps.get(name=app_name).service_principal_client_id
w.experiments.update_permissions(exp.experiment_id, access_control_list=[ExperimentAccessControlRequest(
    service_principal_name=app_sp, permission_level=ExperimentPermissionLevel.CAN_EDIT)])
prefix = exp.experiment_id
for t in spark.sql(f"SHOW TABLES IN {S}").collect():
    name = t["tableName"]
    if name.startswith(prefix) or name.startswith("mlflow_experiment_trace"):
        for privs in ("SELECT, MODIFY", "SELECT"):      # views can't take MODIFY
            try:
                spark.sql(f"GRANT {privs} ON TABLE {S}.`{name}` TO `{app_sp}`")
                break
            except Exception as e:  # noqa — best effort; reported, never fatal
                err = str(e).splitlines()[0][:120]
        else:
            print(f"could not grant on {name}: {err}")
print(f"app {app_name} ({app_sp}): CAN_EDIT on experiment + trace-table grants")
