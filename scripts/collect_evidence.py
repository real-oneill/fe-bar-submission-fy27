"""Collect text evidence that the build ran, into evidence/ (committed).

  uv run --with databricks-sdk python scripts/collect_evidence.py --profile fevm-evan-aws-01

Writes
  evidence/job_runs.md              every run of this deployment's jobs: task states, durations, run URLs
  evidence/pipeline_updates.md      the medallion pipeline's updates and per-table row counts from its event log
  evidence/run_report.md            headline results + breakdowns, queried live from the result tables
  evidence/results/*.csv            the same query results as CSV
  evidence/notebooks/<job>__<task>.ipynb + .md
                                    the job-run notebooks exactly as executed, WITH their cell outputs
                                    (decoded from the Jobs export-run API)
"""
import argparse, base64, csv, datetime as dt, html, io, json, pathlib, re, time, urllib.parse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import ViewsToExport
from databricks.sdk.service.sql import StatementState

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True)
ap.add_argument("--catalog", default="evan_aws_01_catalog")
ap.add_argument("--schema", default="fe_bar_fy27")
ap.add_argument("--warehouse", default="4a29d0ae256f1d92")
ap.add_argument("--job-filter", default="fe_bar_")
a = ap.parse_args()
S = f"{a.catalog}.{a.schema}"
ROOT = pathlib.Path(__file__).resolve().parents[1] / "evidence"
(ROOT / "results").mkdir(parents=True, exist_ok=True)
(ROOT / "notebooks").mkdir(parents=True, exist_ok=True)
w = WorkspaceClient(profile=a.profile)
HOST = w.config.host.rstrip("/")
me = w.current_user.me().user_name
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def ts(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ms else ""


def md_table(cols, rows, limit=None):
    rows = rows[:limit] if limit else rows
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v).replace("|", "\\|").replace("\n", " ")[:160] for v in r) + " |")
    return "\n".join(out)


def sql(q):
    r = w.statement_execution.execute_statement(statement=q, warehouse_id=a.warehouse, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{r.status.state}: {r.status.error.message if r.status.error else ''}\n{q}")
    cols = [c.name for c in r.manifest.schema.columns]
    rows = list(r.result.data_array or [])
    chunk = r.result
    while chunk.next_chunk_index:
        chunk = w.statement_execution.get_statement_result_chunk_n(r.statement_id, chunk.next_chunk_index)
        rows += chunk.data_array or []
    return cols, rows


# ---------------------------------------------------------------- jobs + notebook outputs
jobs = [j for j in w.jobs.list() if a.job_filter in (j.settings.name or "") and j.creator_user_name == me]
lines = [f"# Job runs (collected {now})", "",
         f"Workspace `{HOST}`. Jobs of this bundle (name contains `{a.job_filter}`), every run, newest first.", ""]
exported = []
for j in sorted(jobs, key=lambda j: j.settings.name):
    runs = list(w.jobs.list_runs(job_id=j.job_id, expand_tasks=True, limit=25))
    lines += [f"## {j.settings.name} (job {j.job_id})", ""]
    if not runs:
        lines += ["_no runs_", ""]
        continue
    for r in runs:
        st = r.state
        lines += [f"### run {r.run_id}: {st.life_cycle_state.value if st.life_cycle_state else ''} / "
                  f"{st.result_state.value if st.result_state else ''}",
                  f"started {ts(r.start_time)} UTC, ended {ts(r.end_time)} UTC, run page {r.run_page_url}", ""]
        trow = []
        for t in sorted(r.tasks or [], key=lambda t: t.start_time or 0):
            dur = round(((t.end_time or 0) - (t.start_time or 0)) / 60000, 1) if t.end_time else ""
            trow.append([t.task_key, t.state.result_state.value if t.state and t.state.result_state else
                         (t.state.life_cycle_state.value if t.state and t.state.life_cycle_state else ""),
                         ts(t.start_time), dur, (t.state.state_message or "")[:120] if t.state else ""])
        lines += [md_table(["task", "result", "start (UTC)", "minutes", "message"], trow), ""]
    # export the notebooks of the newest successful-ish run with outputs
    for r in runs[:1]:
        for t in r.tasks or []:
            if not t.notebook_task:
                continue
            exported.append((j.settings.name, t))
(ROOT / "job_runs.md").write_text("\n".join(lines) + "\n")
print("job_runs.md:", len(jobs), "jobs")


def model_from_html(page):
    m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", page)
    if not m:
        return None
    raw = base64.b64decode(m.group(1)).decode("utf-8")
    return json.loads(urllib.parse.unquote(raw))


def result_text(res):
    """Databricks command result -> plain text."""
    if not res:
        return ""
    typ, data = res.get("type"), res.get("data")
    if isinstance(data, list) and data and all(isinstance(x, dict) and "type" in x for x in data):
        parts = [s for s in (result_text(x) for x in data) if s.strip()]   # listResults: several outputs
        return "\n\n".join(s if s.startswith(("|", "```")) else "```\n" + s.strip() + "\n```" for s in parts)
    if typ == "table" and isinstance(data, list):
        cols = [c.get("name") for c in res.get("schema", [])]
        return md_table(cols, data, limit=50) + (f"\n\n(first 50 of {len(data)} rows)" if len(data) > 50 else "")
    if typ in ("text", "ansi") or isinstance(data, str):
        txt = data if isinstance(data, str) else json.dumps(data)
        return re.sub(r"\x1b\[[0-9;]*m", "", html.unescape(re.sub(r"<[^>]+>", "", txt)))
    if typ == "error":
        return "ERROR: " + str(res.get("summary") or data)[:4000]
    return json.dumps(data)[:4000] if data else ""


for job_name, t in exported:
    try:
        ex = w.jobs.export_run(t.run_id, views_to_export=ViewsToExport.CODE)
    except Exception as e:
        print("export failed", t.task_key, e)
        continue
    for v in ex.views or []:
        model = model_from_html(v.content or "")
        if not model:
            continue
        cells, md = [], [f"# {job_name} / {t.task_key} (run {t.run_id}, as executed, with outputs)", "",
                         f"Notebook `{model.get('name')}`, exported {now} from {HOST} via the Jobs export-run API.", ""]
        for c in sorted(model.get("commands", []), key=lambda c: c.get("position", 0)):
            src = c.get("command", "")
            out = result_text(c.get("results"))
            if c.get("errorSummary") or c.get("error"):
                out = (out + "\nERROR: " + re.sub(r"<[^>]+>", "", str(c.get("errorSummary") or c.get("error")))[:4000]).strip()
            is_md = src.lstrip().startswith("%md")
            if is_md:
                cells.append({"cell_type": "markdown", "metadata": {}, "source": src.lstrip()[3:].lstrip("\n")})
                md += [src.lstrip()[3:].strip(), ""]
            else:
                cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "source": src,
                              "outputs": [{"output_type": "stream", "name": "stdout", "text": out}] if out else []})
                md += ["```python", src.strip(), "```", ""]
                if out:
                    md += ["**Output:**", "", out if out.startswith(("|", "```")) else "```\n" + out.strip() + "\n```", ""]
        nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"databricks_run": {"job": job_name, "task": t.task_key,
              "run_id": t.run_id, "exported_at": now}}, "cells": cells}
        stem = re.sub(r"[^A-Za-z0-9_]+", "_", f"{job_name.split('] ')[-1]}__{t.task_key}")
        (ROOT / "notebooks" / f"{stem}.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False))
        (ROOT / "notebooks" / f"{stem}.md").write_text("\n".join(md) + "\n")
        print("notebook:", stem, len(cells), "cells")

# ---------------------------------------------------------------- pipeline updates
pls = [p for p in w.pipelines.list_pipelines() if "fe_bar_order_intake_medallion" in (p.name or "")]
pl_lines = [f"# Medallion pipeline updates (collected {now})", ""]
for p in pls:
    pl_lines += [f"## {p.name} (`{p.pipeline_id}`)", ""]
    ups = w.pipelines.list_updates(p.pipeline_id, max_results=10).updates or []
    pl_lines += [md_table(["update_id", "state", "created (UTC)", "full_refresh"],
                          [[u.update_id, u.state.value if u.state else "", ts(u.creation_time), u.full_refresh] for u in ups]), ""]
    flows, token = {}, None
    for _ in range(10):   # REST: the SDK's PipelineEvent drops `details`
        q = {"max_results": 250, "order_by": "timestamp desc"} | ({"page_token": token} if token else {})
        page = w.api_client.do("GET", f"/api/2.0/pipelines/{p.pipeline_id}/events", query=q)
        for ev in page.get("events", []):
            fp = (ev.get("details") or {}).get("flow_progress")
            name = (ev.get("origin") or {}).get("flow_name") or ""
            if ev.get("event_type") == "flow_progress" and fp and fp.get("status") == "COMPLETED" and name not in flows:
                flows[name] = [name, (fp.get("metrics") or {}).get("num_output_rows"), ev.get("timestamp")]
        token = page.get("next_page_token")
        if not token:
            break
    if flows:
        pl_lines += ["Latest completed flow per table (event log `flow_progress`):", "",
                     md_table(["flow", "num_output_rows", "completed"], sorted(flows.values())), ""]
(ROOT / "pipeline_updates.md").write_text("\n".join(pl_lines) + "\n")

# ---------------------------------------------------------------- result tables
Q = {
 "table_row_counts": f"""SELECT 'email_attachments (bronze)' t, count(*) n FROM {S}.email_attachments UNION ALL
   SELECT 'parsed_attachments (silver)', count(*) FROM {S}.parsed_attachments UNION ALL
   SELECT 'extracted_parsed (gold)', count(*) FROM {S}.extracted_parsed UNION ALL
   SELECT 'purchase_orders (gold lines)', count(*) FROM {S}.purchase_orders UNION ALL
   SELECT 'review_orders (queue)', count(*) FROM {S}.review_orders UNION ALL
   SELECT 'gt_manifest (answer key docs)', count(*) FROM {S}.gt_manifest UNION ALL
   SELECT 'gt_lines (answer key lines)', count(*) FROM {S}.gt_lines""",
 "headline": f"""SELECT count(*) documents, sum(n_pos) purchase_orders, sum(gt_lines) answer_key_lines,
   round(sum(pos_found)/sum(n_pos_with_number),3) po_found_rate, round(sum(customers_correct)/sum(n_pos),3) customer_correct_rate,
   round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy, round(sum(pos_needs_review)/sum(n_pos),3) review_rate,
   sum(pos_false_confidence) false_confidence_pos, round(sum(manual_minutes)/60,1) corpus_manual_hours,
   round(sum(assisted_minutes)/60,1) corpus_assisted_hours, round(sum(minutes_saved)/sum(manual_minutes),3) time_saved_share,
   round(sum(annual_hours_saved),0) annual_hours_saved, round(sum(fte_manual),1) fte_manual,
   round(sum(fte_assisted),1) fte_assisted, round(sum(fte_saved),1) fte_saved, round(sum(annual_usd_saved),0) annual_usd_saved
   FROM {S}.eval_doc_results""",
 "by_document_type": f"""SELECT channel, count(*) docs, sum(gt_lines) lines, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy,
   round(sum(customers_correct)/sum(n_pos),3) customer_acc, round(sum(pos_needs_review)/sum(n_pos),3) review_rate,
   sum(pos_false_confidence) false_conf, round(sum(fte_saved),2) fte_saved, round(sum(annual_usd_saved),0) annual_usd_saved
   FROM {S}.eval_doc_results GROUP BY channel ORDER BY fte_saved DESC""",
 "by_region": f"""SELECT region, count(*) docs, sum(n_pos) pos, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy,
   round(sum(pos_needs_review)/sum(n_pos),3) review_rate, round(sum(fte_saved),2) fte_saved, round(sum(annual_usd_saved),0) annual_usd_saved
   FROM {S}.eval_doc_results GROUP BY region ORDER BY docs DESC""",
 "by_complexity": f"""SELECT complexity, count(*) docs, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy,
   round(sum(pos_needs_review)/sum(n_pos),3) review_rate, sum(pos_false_confidence) false_conf, round(sum(fte_saved),2) fte_saved
   FROM {S}.eval_doc_results GROUP BY complexity ORDER BY complexity""",
 "by_issue_type": f"""SELECT i.issue_type, count(DISTINCT i.doc_id) docs, round(sum(d.lines_correct)/sum(d.lines_orderable),3) line_accuracy,
   round(sum(d.pos_needs_review)/sum(d.n_pos),3) review_rate FROM (SELECT DISTINCT doc_id, issue_type FROM {S}.gt_issues) i
   JOIN {S}.eval_doc_results d USING (doc_id) GROUP BY i.issue_type ORDER BY docs DESC""",
 "line_classes": f"""SELECT line_class, count(*) lines, round(avg(CAST(material_found AS INT)),3) material_found,
   round(avg(CAST(line_correct AS INT)),3) material_and_qty_correct, round(avg(CAST(flagged AS INT)),3) flagged
   FROM {S}.eval_line_results GROUP BY line_class ORDER BY lines DESC""",
 "roi_assumptions": f"SELECT * FROM {S}.roi_assumptions",
 "review_queue_lowest_confidence": f"""SELECT order_id, orig_format, po_number, customer_name, resolved_sap_sold_to, region, n_lines,
   overall_confidence, status, review_reasons FROM {S}.review_orders ORDER BY overall_confidence ASC NULLS FIRST, order_id LIMIT 25""",
 "review_queue_highest_confidence": f"""SELECT order_id, orig_format, po_number, customer_name, resolved_sap_sold_to, region, n_lines,
   overall_confidence, status, review_reasons FROM {S}.review_orders ORDER BY overall_confidence DESC NULLS LAST, order_id LIMIT 15""",
 "sample_extracted_vs_truth": f"""SELECT e.doc_id, e.channel, e.po_number, e.line_no, e.raw_item_text, e.material_id truth_material,
   e.qty_as_written, e.qty_each, e.material_found, e.qty_correct, e.line_correct FROM {S}.eval_line_results e
   WHERE e.doc_id IN ('DOC-00001','DOC-00040','DOC-00100','DOC-00150','DOC-00170') ORDER BY e.doc_id, e.po_number, CAST(e.line_no AS INT) LIMIT 60""",
 "sample_extracted_lines": f"""SELECT regexp_extract(source_path,'(DOC-[0-9]{{5}})',1) doc_id, attachment_filename, po_number, customer_name,
   resolved_sap_sold_to, printed_sku, description, quantity, uom, resolved_material_no, sku_resolve_method, order_confidence
   FROM {S}.purchase_orders ORDER BY doc_id, po_number, line_no LIMIT 40""",
}
results = {}
for name, q in Q.items():
    try:
        cols, rows = sql(q)
    except Exception as e:
        print("query failed", name, str(e)[:200])
        cols, rows = ["error"], [[str(e)[:300]]]
    results[name] = (cols, rows)
    with open(ROOT / "results" / f"{name}.csv", "w", newline="") as f:
        cw = csv.writer(f); cw.writerow(cols); cw.writerows(rows)

h = dict(zip(*[results["headline"][0], results["headline"][1][0]])) if results["headline"][1] else {}
rep = [f"# FE Bar FY27: run report (collected {now})", "",
       f"Live query results from `{S}` on `{HOST}` (SQL warehouse `{a.warehouse}`), produced by the accelerator's",
       "medallion pipeline, the review-queue jobs and `src/fe_bar/10_evaluate.py` on the 184 fictional Maison Solenne documents.",
       "Every number below was read back from the tables when this file was generated; the CSVs are in `evidence/results/`.", ""]
if h:
    rep += ["## Headline", "",
            f"- **{h['documents']} documents / {h['purchase_orders']} purchase orders / {h['answer_key_lines']} answer-key lines** processed end to end.",
            f"- Line accuracy (right material AND quantity): **{h['line_accuracy']}**; PO number found: **{h['po_found_rate']}**; customer resolved to the right sold-to: **{h['customer_correct_rate']}**.",
            f"- Orders routed to human review: **{h['review_rate']}**; orders NOT routed but wrong (false confidence): **{h['false_confidence_pos']}**.",
            f"- Effort on these 184 documents: **{h['corpus_manual_hours']} h** keyed by hand vs **{h['corpus_assisted_hours']} h** with the pipeline (review + re-keying misses): **{h['time_saved_share']} of the effort saved**.",
            f"- Annualised at the assumed volume (`roi_assumptions`): **{h['fte_manual']} FTE today -> {h['fte_assisted']} FTE with the pipeline = {h['fte_saved']} FTE saved** ({h['annual_hours_saved']} hours, about ${h['annual_usd_saved']} labour a year).", ""]
titles = {"table_row_counts": "Table row counts (bronze -> silver -> gold -> queue)", "headline": "Headline metrics (raw)",
          "by_document_type": "By document type (channel)", "by_region": "By region", "by_complexity": "By complexity",
          "by_issue_type": "By injected problem type", "line_classes": "Answer-key lines by class",
          "roi_assumptions": "Savings assumptions (illustrative, editable)",
          "review_queue_lowest_confidence": "Review queue: 25 lowest-confidence orders (what a reviewer sees first)",
          "review_queue_highest_confidence": "Review queue: 15 highest-confidence orders",
          "sample_extracted_vs_truth": "Sample: answer-key lines vs what was extracted (5 documents)",
          "sample_extracted_lines": "Sample: extracted, resolved lines (gold `purchase_orders`)"}
for name, (cols, rows) in results.items():
    rep += [f"## {titles.get(name, name)}", "", md_table(cols, rows), ""]
(ROOT / "run_report.md").write_text("\n".join(rep) + "\n")
print("run_report.md written")


# ---------------------------------------------------------------- redact the deployer's identity (public repo)
short = me.split("@")[0].replace(".", "_")
for f in ROOT.rglob("*"):
    if f.is_file() and f.suffix in {".md", ".ipynb", ".csv"}:
        s = f.read_text()
        r = s.replace(me, "<deployer>").replace(short, "<deployer>")
        if r != s:
            f.write_text(r)
print("redacted", me)
