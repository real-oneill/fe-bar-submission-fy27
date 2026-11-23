# Execution evidence

Everything here is plain text produced by the deployed system on the FE demo workspace `fevm-evan-aws-01`
(catalog `evan_aws_01_catalog`, schema `fe_bar_fy27`). Nothing in this folder was typed by hand.

| File | Produced by | How |
|---|---|---|
| `notebooks/*.ipynb`, `notebooks/*.md` | `scripts/collect_evidence.py` | Jobs `export-run` API on the latest bootstrap run, then decoded: every notebook cell as executed, **with its output** (printed lines, tables, `dbutils.notebook.exit` values, errors) |
| `job_runs.md` | `scripts/collect_evidence.py` | Jobs API `list_runs`: every run of the bundle's jobs, task by task (result, start, minutes, message) |
| `pipeline_updates.md` | `scripts/collect_evidence.py` | Pipelines API: updates of `fe_bar_order_intake_medallion` and `flow_progress` output row counts from its event log |
| `run_report.md`, `results/*.csv` | `scripts/collect_evidence.py` | SQL Statement Execution API on the result tables: row counts bronze→silver→gold→queue, accuracy vs the answer key, FTE model, review-queue rows, extracted lines |
| `../genie/genie_answers.md` | `genie/ask_genie.py` | Genie Conversation API: each question's answer text, generated SQL and result rows |

Regenerate: `uv run --with databricks-sdk python scripts/collect_evidence.py --profile <p>` and
`uv run --with databricks-sdk python genie/ask_genie.py --profile <p>`.
