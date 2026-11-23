# Prerequisites: deploying to a workspace

Everything the deploy needs from the workspace, from you and from other people, in the order it matters. Run the
preflight first: it checks the items marked **auto** and lists the rest to confirm by hand.

```bash
cp deploy/variable-overrides.example.json .databricks/bundle/custom/variable-overrides.json   # fill it in
python3 scripts/preflight.py -t custom -p <profile>          # custom_outlook for the Outlook connector
databricks bundle deploy   -t custom -p <profile>
```

`custom` takes mail from files in the volume (or from an Outlook table that already exists); `custom_outlook` also
creates the Outlook ingestion pipeline and runs it first. Both are generic: host and login come from the CLI profile
and every value from the variables file, nothing is baked in. (`fevm` is the pre-filled FE Bar demo deployment.)

## 1. Features the workspace must have

| Feature | Why | Needed when | Preflight |
|---|---|---|---|
| Unity Catalog with a catalog you can use | all tables, the volume, the prompt registry | always | auto |
| Serverless compute for jobs and pipelines | the Lakeflow pipeline and every job run serverless | always | manual |
| Databricks Apps | the review app | always | auto |
| Lakebase (Autoscaling) projects | the review app's database. CLI >= 1.19.0 | always | auto |
| SQL warehouse | the app resource, MLflow trace storage in Unity Catalog | always | auto |
| Foundation Model endpoint for extraction | `ai_query` (`serving_endpoint`, default `databricks-claude-haiku-4-5`): the fallback in `hybrid` mode, every document in `ai_query` mode | always | auto |
| Foundation Model endpoint for the judges | LLM judges (`judge_endpoint`, default `databricks-claude-sonnet-5`) | always | auto |
| AI Functions in the region | `ai_parse_document` (Silver), `ai_extract` v2.1 precision mode (Gold, `extraction_mode=hybrid`), `ai_query` | always | manual (`ai_query` is probed) |
| MLflow: prompt registry in Unity Catalog, tracing to Unity Catalog, labeling sessions | the extraction prompt and the `ai_extract` schema are loaded from the registry; quality traces and review sessions | always | manual |
| `uv` on your machine | builds the `src/lib` wheel (`order-intake-lib`) that the pipeline installs | always | auto |
| Databricks CLI >= 1.19.0 on your machine | direct deployment engine (`job_runs`, apps started on deploy), `postgres_projects` | always | auto |
| Files API on the volume | the jobs read and write the volume only through it | always | auto |
| PyPI reachable from serverless | `openpyxl`, `xlrd`, `extract-msg`, `mlflow` install at pipeline start (a mirror works) | always | manual |
| Lakeflow Connect **Outlook** connector (Beta, account preview) | ingests the order mailbox | `mail_source=outlook` or `both` | manual |
| UC **HTTP connection** to Microsoft Graph | reads attached emails and sender names the connector does not store | `mail_source=outlook` or `both` | auto |
| SAP customer and material views in Unity Catalog | customer and material resolution (KNA1, ADRC, KNVV, KNVP, MARA, MARM, MAKT, MVKE, sales-org geography) | `master_source=sap` | auto |
| Groups for the regions, and the `postgres` app scope | row-level security: each reviewer sees their regions | `rls_enforced=true` | manual |

## 2. Access you need before you deploy

The jobs, the pipeline and the Outlook ingestion run **as the user who deploys**. For a shared deployment deploy as a
service principal and give it the same grants.

| Object | You need | Notes |
|---|---|---|
| Catalog | `USE CATALOG`; `CREATE SCHEMA` if the schema is new | or ownership |
| Schema (`catalog.schema`) | `USE SCHEMA`, `CREATE TABLE`, `CREATE MATERIALIZED VIEW`, `CREATE FUNCTION`, `EXECUTE`, `MANAGE` | the last three are what the Unity Catalog **prompt registry** needs (without `MANAGE`, loading and registering a prompt fail with "Permission denied ... prompt in schema"). The owner has all of them |
| Volume | `READ VOLUME` + `WRITE VOLUME` | it **must already exist**: the bundle never creates it. If it is in another catalog, the app's service principal is granted `READ VOLUME` on it at deploy time, which needs `USE CATALOG` on that catalog for the principal: grant it, or deploy as someone with `MANAGE` on that catalog |
| SQL warehouse | `CAN USE` | |
| Both model endpoints | `CAN QUERY` | |
| MLflow experiment folder (`quality_experiment`, default under your user folder) | write | its parent folder must exist |
| Outlook and Graph connections | `USE CONNECTION` on each | created by an admin: `CREATE CONNECTION` on the metastore |
| SAP objects in `sap_catalog.db_fnd_proc` | `SELECT` on `v_customer_master`, `v_address_master_customer`, `v_customer_sales_org_master`, `v_customer_master_partner_functions`, `v_material_master`, `v_material_master_sales`, `v_material_master_unit_of_measures`, `v_material_text`, `t_sales_org_geography_look_up` | for the identity the jobs run as |
| Lakebase | permission to create a project, or `lakebase_projects: {}` plus the name of an existing one | see "Use an existing Lakebase project" in the README |
| Workspace | permission to create Apps | `app_name` must be unused (or already owned by this bundle) |

**Reviewers** (not the deployer): `CAN USE` on the app, `CAN READ` on the MLflow experiment to see scores, their email
in `reviewers` for labeling sessions, and, with `rls_enforced=true`, membership of the Databricks group of each region
they review (listed in `region_access`).

**Outlook / Entra** (an admin, once): an Entra app with the `Mail.Read` **application** permission on the mailboxes
(admin consent). The Outlook connection and the Graph connection use the same app. The Graph connection is an HTTP
connection to `https://graph.microsoft.com`, base path `/v1.0`, OAuth machine-to-machine.

## 3. Values you decide

Set in `.databricks/bundle/<target>/variable-overrides.json` (see `deploy/variable-overrides.example.json`) or `--var`.

| Variable | Required | Meaning |
|---|---|---|
| `catalog`, `schema`, `volume`, `warehouse_id` | yes | where it lives; the volume exists already |
| `volume_catalog`, `volume_schema`, `inbound_via_table` | no | when the volume is elsewhere; `inbound_via_table=true` when serverless cannot read the volume's storage directly |
| `app_name`, `lakebase_project` | no | change them if the defaults are taken |
| `rls_enforced`, `reviewers` | no | row-level security by region; emails for labeling sessions |
| `master_source`, `sap_catalog`, `sap_sales_orgs` | for SAP | `demo` (default) or `sap`; with `sap`, the sales orgs (VKORG) of the affiliates you serve |
| `mail_source`, `outlook_mailbox` | for Outlook | `volume`, `outlook` or `both`; the mailbox(es) this deployment reads (comma-separated) |
| `outlook_connection`, `outlook_mailboxes`, `outlook_start_date`, `outlook_table_name` | `custom_outlook` | the ingestion the bundle creates; `outlook_mailboxes` is a list and must include `outlook_mailbox` |
| `outlook_table` | `custom` with `outlook`/`both` | an existing message table (`catalog.schema.table`) another pipeline writes |
| `graph_connection` | for attachments | the Graph HTTP connection; without it attached emails are not read |
| `serving_endpoint`, `judge_endpoint`, `extraction_mode` | no | model endpoints that exist in the workspace; `hybrid` or `ai_query` |
| `fetch_table_prefix` | no | when another accelerator in the schema already uses the Graph fetch table names |

## 4. Known failures, and what causes them

| You see | Cause | Fix |
|---|---|---|
| `Permission denied to create/update prompt in schema` | missing `CREATE FUNCTION`, `EXECUTE` or `MANAGE` on the schema | grant the three (or deploy as the schema owner) |
| `Cannot add volume ... lack USE CATALOG permission` on the app update | the volume is in another catalog | grant the app's service principal `USE CATALOG` there, or deploy as a `MANAGE` holder |
| 403 reading `/Volumes/...` in Bronze | the volume's storage is not directly readable from serverless | set `inbound_via_table=true`: a job copies new `inbound_docs/` files into a table through the Files API |
| `owner of one of the underlying resources failed an authorization check` on the message table | the table was created by a pipeline owned by someone else | read your own: `custom_outlook` creates the ingestion pipeline |
| bootstrap fails reading the Outlook table on a new workspace | the table does not exist before the first ingestion | `custom_outlook` runs the ingestion first |
| deploy fails after an admin restricted app scopes | with `rls_enforced=true` the app requests the `postgres` user-authorization scope | allow it (Settings -> Development) |
| everyone sees "not in any region group" | `rls_enforced=true` and no group in `region_access` matches the user | create the groups and replace the placeholder rows of `region_access` |
| Lakebase project `already exists` / not found | the name is taken, or `lakebase_projects: {}` points at a project that does not exist | change `lakebase_project`, or fix the existing one |
| `refresh token is invalid` | the CLI login expired | `databricks auth login --profile <name>` |

## 5. After the deploy

1. The first deploy fires `bootstrap` (schema, masters, prompts, ingestion, pipeline, review queue, traces, publish).
   Check it succeeded in Jobs.
2. Open the app from the **Apps** page. Later refreshes: `databricks bundle run run_medallion -t <target>`.
3. Neither the ingestion nor `run_medallion` is scheduled: add a schedule when you go beyond a trial.
4. Give reviewers the access above. Start a labeling session with
   `databricks bundle run quality_review_session -t <target> --var reviewers="a@x.com,b@x.com"`.
