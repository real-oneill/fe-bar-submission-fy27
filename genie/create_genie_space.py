"""Create (or update) the Genie space "PO Intake Queue Evaluation (Maison Solenne, FE Bar FY27)".

Usage: uv run --with databricks-sdk python genie/create_genie_space.py --profile fevm-evan-aws-01 \
         [--catalog evan_aws_01_catalog --schema fe_bar_fy27 --warehouse 4a29d0ae256f1d92] [--space-id <id to update>]
Writes the space id to genie/space_id.txt.
"""
import argparse, json, pathlib, uuid
from databricks.sdk import WorkspaceClient

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True)
ap.add_argument("--catalog", default="evan_aws_01_catalog")
ap.add_argument("--schema", default="fe_bar_fy27")
ap.add_argument("--warehouse", default="4a29d0ae256f1d92")
ap.add_argument("--space-id", default="")
a = ap.parse_args()
S = f"{a.catalog}.{a.schema}"
_n = iter(range(1, 1000))
def sid(prefix):  # deterministic, sortable 32-hex ids
    return f"{prefix}{next(_n):0{32 - len(prefix)}x}"

TABLES = {
 "eval_doc_results": "One row per corpus document. Accuracy vs the answer key, review routing, and the savings model: manual_minutes (keying by hand), assisted_minutes (Review App + re-keying misses), minutes_saved, annualised annual_hours_saved, fte_manual / fte_assisted / fte_saved (additive), annual_usd_saved (labour), line_accuracy.",
 "eval_order_results": "One row per answer-key purchase order: po_found, customer_correct, needs_review (routed to a person), order_fully_correct, line counts.",
 "eval_line_results": "One row per answer-key order line: material_found, qty_correct, line_correct, line_class (orderable / unresolvable / cancel_line).",
 "review_orders": "The live review queue the accelerator produced (one row per extracted document + PO): overall_confidence, review_reasons, status (pending/approved/duplicate), region.",
 "gt_issues": "Every injected problem per document (issue_type, detail) - join on doc_id to see accuracy by problem type.",
 "roi_assumptions": "The editable assumptions behind the savings metrics (minutes per order/line, complexity multipliers, review minutes, annual document volume, productive hours per FTE, loaded cost per hour).",
}
tables = [{"identifier": f"{S}.{t}", "description": [d]} for t, d in sorted(TABLES.items())]

text = [
 "This space evaluates an AI purchase-order intake pipeline run on 184 fictional documents from the supplier Maison Solenne (11 inbound channels, 14 retailers).",
 "Savings are expressed in FTE: use eval_doc_results. FTE saved = sum(fte_saved); FTE needed today = sum(fte_manual); FTE needed with the pipeline = sum(fte_assisted). These are annualised: every corpus document stands for annual_documents/184 documents a year. Annual hours saved = sum(annual_hours_saved); labour $ saved per year = sum(annual_usd_saved). Always say these come from the assumptions in roi_assumptions (illustrative planning values, not measurements); platform cost is not modelled.",
 "Accuracy: line accuracy = sum(lines_correct)/sum(lines_orderable) from eval_doc_results (or avg of line_correct over line_class='orderable' in eval_line_results). Review rate = sum(pos_needs_review)/sum(n_pos). False confidence = orders NOT routed to review that are not fully correct (pos_false_confidence).",
 "Document type = channel (erp_edi, email_pdf, fax, handwritten, excel_buysheet, portal_export, email_body, phone, email_pricelist, amended_scan, multimodal); doc_type is a finer type for multimodal documents (promo_form, catalog_markup, chat_screenshot, email_inline). complexity is 1 (simple) to 4 (extreme).",
 "Region = eval_doc_results.region (North America, France, Italy, DACH, UK & Ireland, Middle East); country is the retailer's country.",
 "Problem types: join gt_issues to eval_doc_results on doc_id. Count distinct documents per issue_type.",
]
examples = [
 ("How many FTE does the pipeline save?",
  f"SELECT round(sum(fte_manual),1) fte_today, round(sum(fte_assisted),1) fte_with_pipeline, round(sum(fte_saved),1) fte_saved, round(100*sum(minutes_saved)/sum(manual_minutes),1) pct_effort_saved, round(sum(annual_hours_saved),0) annual_hours_saved, round(sum(annual_usd_saved),0) annual_labour_usd_saved FROM {S}.eval_doc_results"),
 ("FTE saved by document type",
  f"SELECT channel, count(*) docs, sum(gt_lines) lines, round(sum(fte_saved),2) fte_saved, round(sum(annual_usd_saved),0) annual_usd_saved, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy, round(sum(pos_needs_review)/sum(n_pos),3) review_rate FROM {S}.eval_doc_results GROUP BY channel ORDER BY fte_saved DESC"),
 ("Accuracy and review rate by region",
  f"SELECT region, count(*) docs, sum(n_pos) pos, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy, round(sum(customers_correct)/sum(n_pos),3) customer_accuracy, round(sum(pos_needs_review)/sum(n_pos),3) review_rate, round(sum(fte_saved),2) fte_saved FROM {S}.eval_doc_results GROUP BY region ORDER BY docs DESC"),
 ("Line accuracy by complexity level",
  f"SELECT complexity, count(*) docs, round(sum(lines_correct)/sum(lines_orderable),3) line_accuracy, round(avg(min_confidence),3) avg_min_confidence, sum(pos_false_confidence) false_confidence_pos FROM {S}.eval_doc_results GROUP BY complexity ORDER BY complexity"),
 ("Which problem types hurt accuracy most?",
  f"SELECT i.issue_type, count(DISTINCT i.doc_id) docs, round(sum(d.lines_correct)/sum(d.lines_orderable),3) line_accuracy, round(sum(d.pos_needs_review)/sum(d.n_pos),3) review_rate FROM {S}.gt_issues i JOIN {S}.eval_doc_results d ON d.doc_id = i.doc_id GROUP BY i.issue_type ORDER BY line_accuracy ASC"),
 ("What is in the review queue right now?",
  f"SELECT status, region, count(*) orders, round(avg(overall_confidence),3) avg_confidence, count_if(review_reasons IS NOT NULL) with_review_reasons FROM {S}.review_orders GROUP BY status, region ORDER BY orders DESC"),
]
samples = ["How many FTE does the pipeline save?", "FTE saved by document type",
           "Accuracy and review rate by region", "Which problem types hurt accuracy most?",
           "Which documents were wrong but not routed to review?", "FTE saved by region and complexity"]
space = {
 "version": 2,
 "config": {"sample_questions": [{"id": sid("1"), "question": [q]} for q in samples]},
 "data_sources": {"tables": tables},
 "instructions": {
   "text_instructions": [{"id": sid("3"), "content": [t + "\n" for t in text]}],
   "example_question_sqls": [{"id": sid("2"), "question": [q], "sql": [s]} for q, s in examples],
 },
}
for k in ("example_question_sqls", "text_instructions"):
    space["instructions"][k].sort(key=lambda x: x["id"])
space["config"]["sample_questions"].sort(key=lambda x: x["id"])

w = WorkspaceClient(profile=a.profile)
body = {"title": "PO Intake Queue Evaluation (Maison Solenne, FE Bar FY27)",
        "description": "Accuracy, review routing and FTE saved of the Order Intake accelerator on the fictional Maison Solenne corpus, by document type, region, complexity and problem type.",
        "warehouse_id": a.warehouse, "serialized_space": json.dumps(space)}
if a.space_id:
    r = w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{a.space_id}", body=body)
else:
    r = w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)
space_id = r.get("space_id") or a.space_id
pathlib.Path(__file__).with_name("space_id.txt").write_text(space_id + "\n")
print("space_id", space_id, f"{w.config.host}/genie/rooms/{space_id}")
