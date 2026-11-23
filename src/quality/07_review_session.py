# Databricks notebook source
# MAGIC %md
# MAGIC ## Quality 07 — Start a human review (labeling) session
# MAGIC Run on demand (`bundle run quality_review_session`). Creates the label questions (first run only) and a labeling session
# MAGIC assigned to `reviewers`, filled with the lowest-confidence traces that haven't been in a session yet.
# MAGIC Reviewers answer in MLflow's review UI; their labels are stored on the traces as **HUMAN** feedback, next to
# MAGIC the code checks and the LLM judges.

# COMMAND ----------
# MAGIC %pip install "mlflow[databricks]>=3.16"
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import datetime
import os

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("experiment", ""), ("warehouse_id", ""),
             ("reviewers", ""), ("sample_size", "20")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
experiment, warehouse_id = dbutils.widgets.get("experiment"), dbutils.widgets.get("warehouse_id")
reviewers = [r.strip() for r in dbutils.widgets.get("reviewers").split(",") if r.strip()]
sample_size = int(dbutils.widgets.get("sample_size"))
S = f"{catalog}.{schema}"
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = warehouse_id

import mlflow
from mlflow.entities.trace_location import UnityCatalog
from mlflow.genai import label_schemas as ls
from mlflow.genai.labeling import create_labeling_session

mlflow.set_tracking_uri("databricks")
exp = mlflow.set_experiment(experiment_name=experiment, trace_location=UnityCatalog(catalog, schema))

# COMMAND ----------
# ---- label questions: created once, then reused (a schema used by a session can't be overwritten) ----
def _schema(name, title, input_):
    try:
        return ls.get_label_schema(name)
    except Exception:
        return ls.create_label_schema(name=name, type="feedback", title=title, input=input_)


schemas = [
    _schema("extraction_correct", "Is this extraction correct?",
            ls.InputCategorical(options=["Correct", "Minor fixes needed", "Wrong"])),
    _schema("extraction_issues", "What is wrong? (select all that apply)",
            ls.InputCategoricalList(options=["Missed lines", "Extra lines", "Wrong quantity", "Wrong product code",
                                             "Wrong PO number", "Wrong customer", "Not an order", "Other"])),
    _schema("reviewer_comments", "Comments", ls.InputText()),
]

# ---- pick traces: lowest order_confidence first, not yet sent to a session ----
spark.sql(f"""CREATE TABLE IF NOT EXISTS {S}.quality_review_sessions (
  trace_id STRING, session_name STRING, added_at TIMESTAMP)""")
picked = [r["trace_id"] for r in spark.sql(f"""
  SELECT t.trace_id FROM {S}.quality_trace_index t
  LEFT ANTI JOIN {S}.quality_review_sessions s ON s.trace_id = t.trace_id
  ORDER BY t.logged_at DESC LIMIT 500""").collect()]
traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], max_results=5000)
traces = traces[traces["trace_id"].isin(set(picked))]

def _conf(assessments):
    """order_confidence from search_traces' assessments column (dicts on Databricks; objects elsewhere)."""
    for a in assessments or []:
        if isinstance(a, dict):
            name, v = a.get("assessment_name") or a.get("name"), (a.get("feedback") or {}).get("value")
        else:
            name, v = getattr(a, "name", None), getattr(getattr(a, "feedback", None), "value", None)
        if name == "order_confidence":
            return float(v) if v is not None else 1.0
    return 1.0
traces = traces.assign(_c=traces["assessments"].apply(_conf)).sort_values("_c").head(sample_size)
if traces.empty:
    dbutils.notebook.exit("no new traces to review")

# COMMAND ----------
# Sessions work on COPIES of the traces; reviewers' labels are mirrored back onto the originals by
# 06_score_traces.py (copies carry the creation-time tag source_trace_id, set in 05_log_traces.py).
name = f"order-review-{datetime.datetime.utcnow():%Y%m%d-%H%M}"
session = create_labeling_session(name=name, assigned_users=reviewers, label_schemas=[s.name for s in schemas])
session.add_traces(traces.drop(columns=["_c"]))   # search_traces rows (plain strings are parsed as trace JSON, not IDs)
spark.createDataFrame([(t, name) for t in traces["trace_id"]], "trace_id string, session_name string") \
    .selectExpr("*", "current_timestamp() added_at").write.mode("append").saveAsTable(f"{S}.quality_review_sessions")
print(f"labeling session {name}: {len(traces)} trace(s), reviewers {reviewers or '(none assigned)'}")
print("review URL:", getattr(session, "url", None))
dbutils.notebook.exit(str(getattr(session, "url", name)))
