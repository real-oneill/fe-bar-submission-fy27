# FE Bar FY27 submission: AI Purchase-Order Intake on Databricks

An end-to-end **purchase-order intake** system on Databricks: retailer orders arrive as EDI, emailed PDFs, faxes,
handwritten photos, Excel buy sheets, portal exports, phone transcripts and image-heavy promo forms. The system
**parses** them (`ai_parse_document`), **extracts** orders with confidence (`ai_extract` v2.1, falling back to `ai_query`),
**resolves** customers and materials against master data, **routes** low-confidence orders to a human Review App
(React + FastAPI on Lakebase), and emits SAP ORDERS05 payloads for approved orders.

This repository combines two things:

| | Source | What it is |
|---|---|---|
| **The code** | the Order Intake Accelerator (production code built for a customer deployment) | `src/pipeline`, `src/setup`, `src/lib`, `src/quality`, `app/`, `resources/`, `databricks.yml`: one Declarative Automation Bundle |
| **The documents** | the Brick-by-Brick @ NYU use-case corpus | `corpus/`: **184 fictional documents** (220 POs, 2,719 lines, 11 channels) for the fictional supplier **Maison Solenne**, with master data and a full **answer key** |

Everything in this repository is fictional or generic. Customer names, workspaces, mailboxes and SAP identifiers from
the original deployment were removed. The supplier the prompt protects against ("never return the supplier as the
customer") is now Maison Solenne and its eight brands.

## Execution evidence (text, committed)

The build was **deployed and run** on the FE demo workspace (`fevm-evan-aws-01`, catalog `evan_aws_01_catalog`,
schema `fe_bar_fy27`). The evidence files are plain text, so they can be read without access to the workspace:

| File | What it shows |
|---|---|
| [`evidence/run_report.md`](evidence/run_report.md) | Headline accuracy, review routing and FTE saved, read back live from the result tables, plus row counts bronze → silver → gold → queue, breakdowns by document type, region, complexity and problem type, real review-queue rows and extracted lines vs the answer key |
| [`evidence/results/*.csv`](evidence/results) | The same query results as CSV |
| [`evidence/notebooks/`](evidence/notebooks) | **The job-run notebooks as executed, with their cell outputs** (`.ipynb` + readable `.md`), decoded from the Jobs export-run API: corpus load, review-queue build, publish to Lakebase, tracing, LLM judges, evaluation |
| [`evidence/job_runs.md`](evidence/job_runs.md) | Every job run: task-by-task result state, start time, duration, run URL |
| [`evidence/pipeline_updates.md`](evidence/pipeline_updates.md) | The medallion pipeline's updates and per-flow output row counts from its event log |
| [`genie/genie_answers.md`](genie/genie_answers.md) | Questions asked to the Genie space through the Conversation API: Genie's answer, the SQL it generated and the rows it returned |

See [`evidence/README.md`](evidence/README.md) for how each file was produced.

## Architecture

```
corpus/documents/<channel>/*   ──00_load_corpus──►  UC Volume  landing/inbound_docs/      (+ email_manifest, master data, answer key)
                                                        │
                       Lakeflow Declarative Pipeline (serverless) `fe_bar_order_intake_medallion`
   Bronze  email_attachments     Auto Loader (binaryFile) + arrival metadata
   Silver  parsed_attachments    .eml unpacked into body + attachments; PDF/image → ai_parse_document;
                                 xlsx/csv/EDI/JSON/txt parsed locally
   Gold    extracted_parsed      ai_extract v2.1 (precision) on the layout → ai_query (Claude Haiku 4.5, prompt from
                                 the MLflow Prompt Registry) as fallback, per document the better-grounded result
           purchase_orders       deterministic checks (PO in source, quantities grounded in the source row, completeness),
                                 customer → sold-to (name variants, fuzzy), retailer item / GTIN → material, confidence
                                                        │
   review_orders (Delta) ──04_publish──► Lakebase Postgres ──► Review App `fe-bar-fy27-review` (approve / edit / flag → SAP ORDERS05)
   MLflow traces per document + code checks + LLM judges (quality experiment)
                                                        │
   10_evaluate ──► eval_line_results / eval_order_results / eval_doc_results (FTE model) / roi_assumptions
                                                        │
   Genie space "PO Intake Queue Evaluation": FTE saved, accuracy, review rate by document type, region, complexity, problem type
```

The only code added for this submission is glue: `src/fe_bar/00_load_corpus.py` (corpus → Volume, master data in
the accelerator's demo shape, answer key), `src/fe_bar/10_evaluate.py` (scoring + FTE savings model),
`genie/` (space definition and Q&A capture) and `scripts/collect_evidence.py`. Three small changes to the accelerator
itself: `.edi` and `.json` files are read as text (the corpus's X12 850/860 and portal/ASR exports); demo-mode Gold
also resolves a line by the supplier's own material number and by a GTIN given in its own field (SAP mode already did
both; this lifted line accuracy from 0.61 to 0.78 on the corpus); and `scramp>=1.4.6` is pinned next to `pg8000`
(newer pg8000 needs it on serverless).

## FTE saved: how it is computed

`roi_assumptions` (editable table; **illustrative planning values, not measurements**):

- **Manual keying** per document = (3 min per order + 0.75 min per line) × a complexity multiplier (1.0 / 1.2 / 1.5 / 2.0),
  using the **answer key's** true PO and line counts.
- **With the pipeline** = 0.5 min to approve a clean order, 2 min per flagged order + 0.25 min per flagged line, and every
  line the pipeline missed or got wrong re-keyed by hand (0.75 min). A pipeline that misses lines gets no credit for them.
- **Annualised**: 40,000 inbound documents a year with the corpus' channel mix, and 1,680 productive hours per FTE.
  `fte_saved` is additive per document, so any slice (document type, region, complexity, problem type) sums to its
  FTE saved. Labour $ = hours × $40/h loaded cost. Platform cost is not modelled in this demo.

## Deploy it yourself

```bash
databricks auth login --host <workspace-url> --profile <p>
# one-time: the schema and the (pre-existing) inbound Volume
databricks schemas create fe_bar_fy27 <catalog> -p <p>
databricks volumes create <catalog> fe_bar_fy27 landing MANAGED -p <p>
# edit the fevm target in databricks.yml (catalog, warehouse_id, app/lakebase names), then:
databricks bundle deploy -t fevm -p <p>          # first deploy runs `bootstrap`: load corpus → pipeline → queue → app → evaluate
uv run --with databricks-sdk python genie/create_genie_space.py --profile <p> --catalog <catalog>
uv run --with databricks-sdk python genie/ask_genie.py --profile <p>
uv run --with databricks-sdk python scripts/collect_evidence.py --profile <p> --catalog <catalog>
```

Requirements: Unity Catalog, serverless compute, Foundation Model APIs (Claude Haiku 4.5 and Sonnet 5), AI Functions,
Lakebase, Databricks CLI ≥ 1.19. Details: [`docs/ACCELERATOR_README.md`](docs/ACCELERATOR_README.md),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/PREREQUISITES.md`](docs/PREREQUISITES.md); corpus:
[`corpus/README.md`](corpus/README.md); the use case: [`docs/USE_CASE_REQUIREMENTS.md`](docs/USE_CASE_REQUIREMENTS.md).

## Repository layout

```
databricks.yml, resources/   the bundle: pipeline, jobs (bootstrap, run, load_corpus, evaluate, ...), Review App, Lakebase
src/pipeline/                bronze / silver / gold (Lakeflow Declarative Pipeline)
src/setup/, src/quality/     schema, masters, prompt registry, review queue, Lakebase publish, MLflow traces + judges
src/lib/                     extraction checks, routing, citations, customer hints, SAP matching (wheel)
src/fe_bar/                  FE Bar glue: corpus loader + evaluation
app/                         Review App (FastAPI + React, Lakebase backend)
corpus/                      fictional Maison Solenne documents, master data, answer key
genie/                       Genie space definition + captured answers
evidence/                    execution evidence (text)
tests/, app/tests/           pytest
```
