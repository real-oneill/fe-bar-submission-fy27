# Databricks notebook source
# MAGIC %md
# MAGIC ## Quality 06 — LLM judges on new traces
# MAGIC Scores every trace in `quality_trace_index` that hasn't been scored yet with three judges (run on a stronger
# MAGIC model than the extractor). Each judge sees the parsed document (`inputs`) and the extracted orders
# MAGIC (`outputs`); results are attached to the traces as **LLM_JUDGE** feedback and summarized in an MLflow
# MAGIC evaluation run in the quality experiment.

# COMMAND ----------
# MAGIC %pip install "mlflow[databricks]>=3.16"
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import os

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("experiment", ""), ("warehouse_id", ""),
             ("judge_endpoint", "databricks-claude-sonnet-5")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
experiment, warehouse_id = dbutils.widgets.get("experiment"), dbutils.widgets.get("warehouse_id")
judge_model = f"databricks:/{dbutils.widgets.get('judge_endpoint')}"
S = f"{catalog}.{schema}"
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = warehouse_id

import mlflow
from mlflow.entities.trace_location import UnityCatalog
from mlflow.genai.judges import make_judge

mlflow.set_tracking_uri("databricks")
exp = mlflow.set_experiment(experiment_name=experiment, trace_location=UnityCatalog(catalog, schema))

pending = [r["trace_id"] for r in spark.sql(
    f"SELECT trace_id FROM {S}.quality_trace_index WHERE NOT scored").collect()]
print(f"{len(pending)} trace(s) to score")

# COMMAND ----------
SUPPLIER = ("Maison Solenne or any of its entities or brands (Solenne Paris, Kōri Botanicals, Atelier Noor, "
            "Velour Cosmetics, Thornfield Grooming, Mistral Hair, Lune Rouge, Ember & Oak)")
judges = [
    make_judge(
        name="customer_is_buyer",
        instructions=(
            "You review purchase orders extracted from a retailer's document. The parsed source document is in "
            "{{ inputs }} and the extraction is in {{ outputs }}. Is every order's customer_name the retailer, store, "
            f"salon or distributor that PLACED the order (not the supplier: {SUPPLIER})? A store whose name merely "
            "contains a brand counts as a customer. If customer_name is missing, answer true only if the document "
            "truly names no customer. Answer true or false."),
        feedback_value_type=bool, model=judge_model),
    make_judge(
        name="po_number_valid",
        instructions=(
            "The parsed source document is in {{ inputs }} and the extraction is in {{ outputs }}. For each order, is "
            "po_number the buyer's own order reference as printed in the document (not a date, document title, "
            "product code, customer/account number, invoice or page number)? If po_number is missing, answer true "
            "only if the document has no order reference. Answer true or false."),
        feedback_value_type=bool, model=judge_model),
    make_judge(
        name="lines_correct_and_complete",
        instructions=(
            "The parsed source document is in {{ inputs }} (spreadsheets appear cell by cell as 'S1R35: A=.. | E=3'; "
            "a missing column letter is an empty cell) and the extraction is in {{ outputs }}. Did the extraction "
            "capture every ORDERED line (rows where the customer entered a quantity greater than 0) with the right "
            "product code and quantity, and nothing else (no unordered catalog rows, no prices or pack sizes read as "
            "quantities)? Answer true or false and name any missed, extra or wrong lines in the rationale."),
        feedback_value_type=bool, model=judge_model),
]

# COMMAND ----------
if pending:
    traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=5000)
    traces = traces[traces["trace_id"].isin(set(pending))]
    print(f"scoring {len(traces)} trace(s) with {judge_model}")
    result = mlflow.genai.evaluate(data=traces, scorers=judges)
    print("evaluation run:", result.run_id, "| metrics:", result.metrics)
    ids = ",".join(f"'{t}'" for t in traces["trace_id"])
    if ids:
        spark.sql(f"UPDATE {S}.quality_trace_index SET scored = true WHERE trace_id IN ({ids})")

# COMMAND ----------
# ---- mirror expert labels from labeling-session copies onto the original traces ----
# A labeling session works on COPIES of the traces. A copy keeps the creation-time tags (source_trace_id, set in
# 05_log_traces.py) and the original's request_time; older traces without the tag are matched on
# (document, request_time). Copy every HUMAN label onto the original once, so one trace per document holds the
# code checks, the judge scores, the Review App feedback and the expert labels.
from mlflow.entities import AssessmentSource

has_sessions = spark.catalog.tableExists(f"{S}.quality_review_sessions")
names = [r["session_name"] for r in spark.sql(
    f"SELECT DISTINCT session_name FROM {S}.quality_review_sessions").collect()] if has_sessions else []
mirrored = 0
if names:
    from mlflow.genai.labeling import get_labeling_sessions
    sessions = {x.name: x for x in get_labeling_sessions()}
    originals = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=5000)
    indexed = {r["trace_id"] for r in spark.sql(f"SELECT trace_id FROM {S}.quality_trace_index").collect()}
    by_doc_time = {((r["tags"] or {}).get("document"), r["request_time"]): r["trace_id"]
                   for _, r in originals.iterrows() if r["trace_id"] in indexed}
    for name in names:
        sess = sessions.get(name)
        if sess is None:
            continue
        copies = mlflow.search_traces(run_id=sess.mlflow_run_id, max_results=5000)
        for _, c in copies.iterrows():
            original = (c["tags"] or {}).get("source_trace_id") or \
                by_doc_time.get(((c["tags"] or {}).get("document"), c["request_time"]))
            labels = [a for a in (c["assessments"] or []) if (a.get("source") or {}).get("source_type") == "HUMAN"]
            if not original or not labels:
                continue
            have = {(a.name, a.source.source_id) for a in (mlflow.get_trace(original).info.assessments or [])}
            for a in labels:
                key = (a.get("assessment_name"), (a.get("source") or {}).get("source_id"))
                value = (a.get("feedback") or {}).get("value")
                if key in have or value is None:
                    continue
                mlflow.log_feedback(trace_id=original, name=key[0], value=value,
                                    source=AssessmentSource(source_type="HUMAN", source_id=key[1]),
                                    rationale=a.get("rationale"), metadata={"labeling_session": name})
                mirrored += 1
print(f"mirrored {mirrored} expert label(s) onto original traces")
