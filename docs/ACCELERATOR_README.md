# Order Intake Accelerator (original README)

> This is the accelerator's own README, kept for reference. For the FE Bar FY27 submission see the [top-level README](../README.md). The offline A/B harness (`src/eval/`) and the customer-specific deployment targets and guide are not part of this repository.

AI-powered retailer **purchase-order intake** on Databricks. Retailer orders arrive as email attachments in many formats (PDF, scanned, faxed, handwritten, Excel, multi-PO spreadsheets, multiple languages). This accelerator ingests them, extracts structured orders with confidence scores, resolves them against your master data, routes low-confidence items to a human review app, and emits SAP-ready orders — replacing manual line-by-line re-keying.

## Architecture

```
Email/attachments ─► Bronze (email_attachments, streaming)
   Outlook connector table       │  (mail_source=outlook)
   or Volume + Auto Loader       ▼  (mail_source=volume, demo)
                        Silver (parsed_attachments)
                        · PDF/scanned  → ai_parse_document (layout + per-element confidence)
                        · Excel/CSV    → openpyxl
                                 │
                                 ▼
                        Gold (extracted_parsed → purchase_orders)
                        · ai_extract v2.1 precision (hybrid, default) → ai_query fallback
                        · ai_query (Foundation Model API, Haiku 4.5) with a
                          prompt+schema LOADED FROM the MLflow Prompt Registry (@production)
                        (see "AI Functions used")
                        · tribal-knowledge joins: customer name → SAP sold-to,
                          retailer SKU/EAN → material; composite confidence + needs_review
                                 │
                                 ▼
                        Review App (React/FastAPI) — confidence-sorted queue,
                        source-doc vs editable extraction, correct/approve
                                 │
                                 ▼
                        sap_outbound — approved orders as ORDERS05 IDoc payloads
```

All stages run in **one Lakeflow Declarative Pipeline** (serverless). The Gold prompt is **governed in the MLflow Prompt Registry** — promote a new version and the pipeline picks it up automatically.

## Prerequisites
> **Deploying to your own workspace?** [docs/PREREQUISITES.md](docs/PREREQUISITES.md) is the full checklist (features, access, values, known failures); `python3 scripts/preflight.py -t custom -p <profile>` checks it before you deploy. Targets `custom` and `custom_outlook` are generic (`deploy/variable-overrides.example.json`); `fevm` is the pre-filled FE Bar demo deployment.

- Unity Catalog; **serverless** compute enabled in-region; **Foundation Model API** access.
- An **existing catalog** you can create schemas in.
- An **existing UC Volume** for inbound documents — the bundle reads from its `inbound_docs/` subfolder and does **not** create the Volume. Note its name for the `volume` variable.
- **Lakebase** (Autoscaling Postgres) available in your workspace/region, and permission to create a project — the bundle creates one per target and the Review App reads/writes it (OLTP: low latency, real concurrency).
- **Databricks CLI ≥ 1.19** (direct deployment engine: `job_runs`, apps started on deploy), authenticated, authenticated to your workspace (`databricks auth login`).
- For the production Outlook connector: the **Previews** toggle enabled (it is Beta) + an Entra ID app registration (see *Ingestion*).

## Configure
Set your targets/vars in `databricks.yml` (or override on the CLI):

| Variable | Meaning | Default |
|---|---|---|
| `catalog` | target UC catalog (must exist) | `main` |
| `schema` | target schema (created for you) | `order_intake` |
| `volume` | **existing** UC Volume holding inbound docs (NOT created; docs read from its `inbound_docs/` folder) | `landing` |
| `volume_catalog` / `volume_schema` | where that Volume lives, when not next to the tables | `catalog` / `schema` |
| `inbound_via_table` | `true` when the pipeline's compute can reach the Volume only through the Files API: a job task copies new `inbound_docs/` files into `<fetch_table_prefix>inbound_files` and Bronze streams that table (needs `mail_source: both`) | `false` |
| `serving_endpoint` | FM endpoint for extraction | `databricks-claude-haiku-4-5` |
| `app_name` | Review App name — must be unique in the workspace | `order-intake-review` |
| `lakebase_project` | Lakebase project id (`*_lakebase` targets; unique in the workspace) | `order-intake` |
| `lakebase_branch` / `lakebase_database` / `lakebase_schema` | Branch, Postgres DB and schema the app uses | `production` / `databricks_postgres` / `public` |
| `lakebase_projects` / `lakebase_branch_path` | Create a project (default) or use an existing one — see *Use an existing Lakebase project* | create |
| `promote_prompt` | `true` = move the prompt's `@production` alias to the version this deploy registers | `false` |
| `quality_experiment` | MLflow experiment for traces, judge scores and human feedback (created if missing) | `/Users/<deployer>/order-intake-quality` |
| `judge_endpoint` | Model for the LLM judges | `databricks-claude-sonnet-5` |
| `reviewers` | Emails assigned to human review sessions | *(empty)* |
| `warehouse_id` | SQL warehouse — required: UC-stored traces are read/written through it | *(set this)* |
| `mail_source` | Bronze mail source: `volume` (files in `inbound_docs/`) or `outlook` (the Outlook connector's table) — see *Ingestion* | `volume` |
| `outlook_table` / `outlook_mailbox` | `mail_source=outlook`: the connector's messages table and the one mailbox to read | *(empty)* |
| `rls_enforced` | `true` = the app works on Lakebase **as the signed-in user** and Postgres row-level security limits each user to their regions; `false` = no RLS, the app's service principal sees every row — see *Region filter and row-level security* | `false` |
| `graph_connection` | `mail_source=outlook`: UC HTTP connection to Microsoft Graph used to fetch **attached emails** (and sender names) the connector stores without content — see *Attached emails* | *(empty = not fetched)* |
| `master_source` | Master data for customer/material resolution: `demo` (template tables) or `sap` (the real SAP masters) — see *Master data* | `demo` |
| `sap_catalog` / `sap_sales_orgs` / `material_prefix_len` | `master_source=sap`: catalog with the SAP views (`db_fnd_proc.v_*`), the affiliate's sales orgs (comma list; first = preferred), material prefix length | *(empty)* / *(empty)* / `6` |


## Deploy — one command
```bash
cd app/frontend && npm install && npm run build && cd ../..   # the UI is shipped pre-built

databricks bundle deploy -t dev     # (or -t prod)
```
On the **first** deploy this creates everything, starts the app, and runs the `bootstrap` job (`job_runs.bootstrap_on_first_deploy`):
schema + `inbound_docs` folder → master templates → register the prompt → medallion pipeline → review queue → **publish**
(Lakebase upsert, preserving approved rows) and the **app grants**. The deploy waits for it.

Afterwards:
```bash
databricks bundle run run_medallion -t dev   # process new documents (pipeline → queue → publish)
databricks bundle deploy -t dev              # code/config changes; does not re-run the bootstrap
```
**Grants are automatic.** The app's resources grant its service principal `READ VOLUME` on the inbound Volume and a Postgres role on the Lakebase branch. The publish step adds `USE CATALOG`/`USE SCHEMA` (best effort) and the Postgres access to `review_orders`/`sap_outbound` (they don't exist until the bootstrap creates them): with `rls_enforced=true` (default) each **user** in a region group gets a Postgres role and region-filtered access, and the app's service principal gets none; with `rls_enforced=false` the service principal gets read/write on both tables. **Who sees which region is set up in Databricks groups** — see *Region filter and row-level security*.

**Notes**
- If another deployment in the workspace already uses the app name (e.g. a colleague's dev deploy), pass `--var app_name=order-intake-review-<you>`. After `bundle destroy`, wait for the app to finish deleting before redeploying the same name.
- `bundle destroy` soft-deletes the Lakebase project; its id stays reserved for ~7 days, so redeploy with a new `lakebase_project` in that window.
- **Demo data:** `databricks bundle run demo_corpus -t dev` writes synthetic POs into `inbound_docs/` — sandbox only, never with a Volume that receives real orders. Then `bundle run run_medallion`.

## Quality: traces, LLM judges and human feedback
Every processing run (`run_medallion`, and the first-deploy bootstrap) also feeds an MLflow experiment
(`quality_experiment`, default `/Users/<deployer>/order-intake-quality`; traces stored in UC `<catalog>.<schema>`):
- **One trace per extracted document** (`log_traces`): the parsed document plus the extracted orders, with an
  `ai_query` child span. The deterministic checks are attached as **CODE** feedback: `order_confidence`,
  `po_valid`, `customer_not_supplier`, `lines_verified_share`, `completeness`. Each document is traced once per
  prompt version (`quality_trace_index`), and every order in the queue carries its `trace_id`.
- **LLM judges** (`score_traces`, model `judge_endpoint`, default `databricks-claude-sonnet-5`):
  `customer_is_buyer`, `po_number_valid`, `lines_correct_and_complete` → **LLM_JUDGE** feedback + an evaluation run.
- **Human feedback from the Review App, automatically**: *Approve* logs `human_review=approved` plus the reviewed
  order as the `expected_order` **expectation** (ground truth); *Flag manual* logs `human_review=needs_manual`;
  saving changes logs `human_corrected=true` with the changed fields. This is best effort and asynchronous, so a
  review never waits on MLflow.
- **Expert review sessions**: `databricks bundle run quality_review_session -t dev --var reviewers=a@x.com,b@x.com`
  creates a labeling session with the lowest-confidence new traces. Questions: correct? / what's wrong? / comments.
  The job prints the review URL. Sessions work on *copies* of the traces (the experiment lists them too); every
  processing run mirrors reviewers' labels back onto the original trace, so each document has one trace with
  everything: code checks, judge scores, Review App feedback and expert labels.

Tracing never blocks the queue: publishing runs even if `log_traces` fails. UC-stored traces need a SQL warehouse
(`warehouse_id`); the app gets `CAN USE` on it, plus edit access on the experiment, automatically.

## Region filter and row-level security
Every order has a **region**, and each reviewer sees (and can edit/approve) only the orders of their regions.
The queue has a **region dropdown** (the user's regions, plus a *Region* column) to narrow further.

**Where the region comes from.** With `master_source = sap`: the resolved sold-to's SAP country mapped
through **`region_map(country, region)`**, else the SAP affiliate; customer not found → `Unassigned`. Demo mode: the
customer's `country` in `customer_master` (by sold-to, else by name variant) through `region_map`; a country not in
the map → `Other`. `region_map` is seeded with an editable default (DE/AT/CH →
DACH, ES/PT → Iberia, AE/SA/KW/QA/IL → Middle East, GB/UK/IE → UK & Ireland) while it is empty — edit it freely.

**Who sees what — defined once, in Databricks groups.** **`region_access(group_name, region)`** (Delta) maps a
Databricks group (exact display name; account groups must be assigned to the workspace) to a region; `region = '*'`
means all regions (admins, GSM leads). Membership is managed in the groups, not in the app. It is seeded with
placeholder groups (`oi-region-dach`, `oi-region-iberia`, `oi-region-middle-east`, `oi-region-uk-ireland`,
`oi-region-other`, `oi-all-regions` = `*`) — create those groups or replace the rows with yours. `Unassigned` orders
are visible to `*` groups only, unless you add a group for region `Unassigned`.

**How it's enforced (`rls_enforced=true`; opt-in, default `false`).**
- Each publish (`04_publish_review_queue.py`, every `run_medallion`) expands `region_access` with the groups'
  current members (SCIM API; nested groups followed) into Lakebase **`user_regions(principal, region, via_group)`**,
  creates a Postgres login role for each member (`databricks_create_role`; users = email, service principals =
  application id), and grants it the NOLOGIN role `oi_reviewer_<pg schema>`. Members removed from every group lose
  it. **Group changes take effect at the next publish.**
- **Postgres row-level security** (ENABLE + FORCE) on `review_orders`: only rows whose region is one of the user's
  regions (or the user has `*`); `sap_outbound`: only rows whose order is visible; `user_regions`: only the user's
  own rows. The reviewer role may only update the editable columns (not `region`).
- The app has the **`postgres` user-authorization scope** (`user_api_scopes` in `resources/review_app.yml`). Per
  request it takes the signed-in user's forwarded token (`X-Forwarded-Access-Token`), mints the user's own Lakebase
  credential with it (`POST /api/2.0/postgres/credentials`), logs in as the user's role, and runs
  `SET ROLE oi_reviewer_<schema>`. The policies key on `session_user` (the user who logged in — SET ROLE can't change
  it), the privileges are the reviewer role's (no BYPASSRLS), so even the project owner is filtered in the app.
- The app's service principal has **no** access to the tables. A request without a forwarded user token is refused
  (401); a user in no region group gets a 403 explaining why. `GET /api/whoami-db` shows the Postgres identity a
  request gets.
- Users consent to the app's `postgres` scope the first time they open it. A workspace admin setting can restrict
  app scopes (Settings → Development → *Restrict OAuth scopes for apps*); it must allow `postgres`.
- Not covered by RLS: Postgres roles with BYPASSRLS that connect **directly** (e.g. the project owner in psql) still
  see everything — RLS here protects the app path. The PDF viewer checks the order (RLS) before streaming its file.

**Turning it off / reverting.** Deploy without `--var rls_enforced=true` (the default is `false`), then run the publish (`bundle run run_medallion`):
RLS is disabled on both tables and the app's service principal gets read/write on every row again, as before. (The
`user_regions` table and the `oi_*` roles stay, unused.) Re-enable the same way with `true`.

**Local dev.** Running the app locally has no forwarded user token; set `RLS_ENFORCED=false` (and a sandbox
publish with `rls_enforced=false`) to use your own identity for everything.

## Use an existing Lakebase project (optional)
By default the bundle creates (and owns) a Lakebase project. To point the app at a project that already exists, set
these in the target's `variables` in `databricks.yml` (commented template under `dev`), or in
`.databricks/bundle/<target>/variable-overrides.json`. Complex variables can't be passed with `--var`.
```yaml
lakebase_project: my-existing-project          # its project id
lakebase_projects: {}                          # don't create a project
lakebase_branch_path: projects/${var.lakebase_project}/branches/${var.lakebase_branch}
lakebase_schema: order_intake                  # recommended in a shared project (default: public)
```
- The bundle then never creates, changes or deletes the project. `bundle destroy` leaves it alone.
- The project needs the branch (`lakebase_branch`, default `production`) and its `databricks_postgres` database.
  The deployer needs a Postgres role there that can create a schema/tables and grant on them. The app's own role
  is created by its `postgres` resource.
- Moving an existing deployment from a bundle-created project to "existing" without deleting it: run
  `databricks bundle deployment unbind order_intake -t <target>` first, then set the variables above.

## Ingestion: demo vs production
Bronze `email_attachments` (one row per attachment, same columns either way) is fed by ONE of two sources, picked
by the `mail_source` variable. Silver, Gold, the queue and the app are the same for both.

- **`mail_source: volume` (default) — files in the Volume.** `src/pipeline/01_bronze.sql` reads the `inbound_docs/`
  folder of `volume` with Auto Loader. Use it for the demo, or for a production feed that drops attachments there
  (Power Automate / Logic Apps). The `demo_corpus` job (`src/demo/generate_synthetic_corpus.py`, sandbox only)
  writes synthetic PO files there and populates the masters + `email_manifest`. Runs with no connector and no real data.
- **`mail_source: outlook` — the Lakeflow Connect Outlook connector (Beta, Previews-gated).** Create the connector
  (Microsoft Graph + Entra ID app registration) so it lands its `email_messages` table, then set
  ```yaml
  mail_source: outlook
  outlook_table: <catalog>.<schema>.email_messages   # the deployer needs SELECT on it
  outlook_mailbox: orders@yourcompany.com            # only this mailbox is read; the table may hold others
  ```
  `src/pipeline/01_bronze_outlook.py` then builds `email_attachments` from that table: the mailbox filter is applied
  first; one row per **non-inline** attachment (inline images are signature logos); messages without one produce
  no rows; the table is read through its **change feed** (`insert` changes only), because the connector updates
  rows in place (read state, folder moves) — updates are ignored, every new message is processed exactly once.
  **Change data feed must stay enabled on the connector table** (`delta.enableChangeDataFeed = true`; the
  connector sets it). After the pipeline, the
  `export_attachments` task writes each attachment to `<volume>/outlook_attachments/...` (its Bronze
  `source_path`, never inside `inbound_docs/`) so the Review App can show the PDF. In this mode the `demo_corpus`
  job does nothing. **Validate shared-mailbox support** for your tenant before committing — it is Beta.
- **Attached emails (`mail_source: outlook`).** When someone drags an email into the order email (or forwards it
  "as attachment"), the connector stores it as an `itemAttachment` (`message/rfc822`) **without its content**, and
  it stores no sender display names. The `fetch_outlook_items` job task (`src/setup/06_fetch_outlook_items.py`,
  first task of `run_medallion` / before the pipeline in `bootstrap`) fetches them through a Unity Catalog **HTTP
  connection to Microsoft Graph** named by `graph_connection`:
  - the connection: host `https://graph.microsoft.com`, base path `/v1.0`, OAuth machine-to-machine with the
    **same Entra app registration as the Outlook connector** (it needs the `Mail.Read` application permission — verify the connector's app has it);
    the job's run-as user needs `USE CONNECTION` on it. Only read-only `GET`s are made:
    `/users/{mailbox}/messages/{id}/attachments/{attachment_id}/$value` (the attached email as MIME/.eml),
    `/users/{mailbox}/messages/{id}/attachments/{attachment_id}` (a file attachment the connector left empty), and
    `/users/{mailbox}/messages/{id}?$select=from,sender` (sender display name), for `outlook_mailbox` only;
  - results go to `<schema>.outlook_item_attachments` / `<schema>.outlook_message_senders`; each attachment and
    message is fetched once, failures are recorded (`http_status`, `error`) and retried on the next runs (3
    attempts in total). Only counts are printed;
  - Bronze streams the fetched emails into `email_attachments` (`<subject>.eml`, `message/rfc822`) and Silver
    unpacks them like `.msg` files: the attached email's body and every attachment (PDF/Excel/CSV orders, emails
    attached to it, up to 3 levels) become documents of the outer email, extracted like any other.
    `from_name` comes from Graph when fetched;
  - **without `graph_connection`** the task prints how many attached emails were skipped and does nothing else;
    everything else works, attached emails just aren't extracted (before this change they were empty Bronze rows
    that Gold ignored). `.eml` files dropped into `inbound_docs/` (`mail_source: volume`) are unpacked the same way.
    The app shows parts of an attached email as parsed text (no PDF viewer), as for `.msg` parts.
- **Switching an existing deployment** between the two changes the streaming source of `email_attachments`, which
  then needs a **full refresh** (re-reads every message/file; Silver/Gold recompute, the queue is rebuilt and
  republished — approvals in Lakebase are kept):
  ```bash
  databricks bundle deploy -t <target>
  databricks bundle run medallion -t <target> --full-refresh email_attachments   # Bronze only
  databricks bundle run run_medallion -t <target>                                # Silver/Gold, queue, publish
  ```
  Without the full refresh the next pipeline update fails with `DIFFERENT_DELTA_TABLE_READ_BY_STREAMING_SOURCE`
  (the stream's checkpoint belongs to the old source); nothing is written, so you can still run the full refresh.
  A deployment that stays on `volume` needs nothing: its Bronze definition is unchanged.
- **Attached emails in the Review App.** An order read from an `.eml` / `.msg` (or an Outlook item fetched from
  Graph) shows the document it was read from (the PDF or workbook inside the email, else the extracted text) and an
  **Email** tab: headers, the HTML body (sanitized server-side; shown in a sandboxed frame with no scripts and no
  remote loads), and the attachments, which open in the same viewers — attached emails included.

See `docs/ARCHITECTURE.md`; `docs/SAP_FIELD_MAPPING.md` lists every extracted field, the SAP table and field it maps to, and the customer / material matching rules.

## Master data: demo templates or SAP (`master_source`)
Gold resolves each order's customer and each line's material against ONE of two master sources. Extraction,
checks, confidence structure, the queue and the app are the same for both.

- **`master_source: demo` (default)** — the template tables below (*Load your master data*). The sandbox demo.
- **`master_source: sap`** — the real SAP masters, read-only, from the views in `sap_catalog` (schema `db_fnd_proc`,
  `v_*` views = one row per key; client `100`): KNA1 `v_customer_master`, ADRC `v_address_master_customer`, KNVV
  `v_customer_sales_org_master`, KNVP `v_customer_master_partner_functions`, MARA `v_material_master`, MARM
  `v_material_master_unit_of_measures`, MAKT `v_material_text`, MVKE `v_material_master_sales`, plus
  `t_sales_org_geography_look_up`. The deployer (the jobs and pipeline run as them) needs `SELECT` on these.
  ```yaml
  master_source: sap
  sap_catalog: <catalog with db_fnd_proc>
  sap_sales_orgs: "4160,4020,4025,4390"   # the affiliate's sales orgs (VKORG); the first wins on ties
  material_prefix_len: "6"                 # default
  ```
  The `sap_masters` job task (`src/setup/01b_sap_masters.py`; before the pipeline in `bootstrap` and `run_medallion`;
  no-op in demo mode) refreshes **small working tables** in the accelerator's schema, restricted to those sales
  orgs and to saleable materials — never full copies of SAP: `oi_sap_customers` (customers with a KNVV sales view
  in the orgs: name, address incl. ADRC street line 2, country, currency, deletion/block flags, sold-to/ship-to
  role), `oi_sap_partner_links` (KNVP AG/WE/RE/RG), `oi_sap_materials` (MARA FERT/HAWA listed in MVKE: prefix,
  EANs from MARA + MARM, German/English text, sales orgs + sales status), `oi_sap_region_map` (sales org + country
  → SAP affiliate). It also creates the empty `po_rules` table once.

  **Customer** (`oi_order_customers`, one row per order). The extracted customer name, the printed customer
  number and the ship-to text are matched against `oi_sap_customers` of the configured sales orgs: normalized name
  (umlauts, accents, legal forms such as GmbH/AG/SAS removed; Levenshtein, containment and word overlap),
  postcode / city / street found in the text, and the printed customer number (= KUNNR, only with some name or
  address evidence). The best **sold-to** wins unless another sold-to scores within 0.05 — then the order is
  **ambiguous** and lists the candidates (never picked arbitrarily). If only a ship-to / bill-to / payer matches,
  its sold-to is taken through KNVP. The **sales org and currency come from the sold-to's KNVV** (not the
  document); a different currency on the document is reported. **SAP only — no business-maintained tables**: there are
  no name pins (`customer_master` is a demo-mode table and is neither created nor read with `master_source = sap`). **Ship-to**: if the document names one, it is looked up among the sold-to's KNVP ship-tos (`WE`,
  same sales org) and then among all SAP ship-tos; a ship-to that isn't linked to the sold-to is **flagged for
  review** (extraction is not blocked). Account group (KTOKD) is not used yet.
  **Customer from the email or file name**: when the document's customer isn't found (no name printed, the supplier printed
  as the customer, or no SAP match), the sender's email domain, the sender's name, the subject and the file name
  are tried in that order, with the same matching (for an email unpacked from a `.msg`, that email's own sender
  first). Supplier domains and brands, free-mail domains and order words are skipped. A match is never trusted
  blindly: the order is reviewed with *Customer inferred from the sender's email domain (orders@…): … — check*.
  Turn it off with the pipeline setting `order_intake.customer_hints: false`.
  **Material** (`oi_line_materials`, one row per line), against materials listed in MVKE for the order's sales
  org (any configured org while the customer is unresolved): exact 10-character number (kept in full) → EAN/UPC
  (MARA + MARM, leading zeros ignored) → the first `material_prefix_len` characters (**valid**, SAP resolves the
  full number; the prefix is passed on). An EAN on several materials is **ambiguous** unless exactly one is
  listed for the sales org. Sales status (VMSTA) is never filtered on. MAKT text is shown for confirmation only.
  No retailer-code mapping table (`retailer_sku_map` is demo-mode only). **Quantities are never changed; availability is not checked** (SAP does that).
  **Customer PO**: always the number printed on the customer's document (extracted, checked against the document
  text, never looked up in SAP). The IDoc carries it in `E1EDK02` qualifier `001` (customer purchase order →
  sales order customer PO, VBAK-BSTNK).
  **PO rules** (`po_rules(sold_to, rule, pattern)`, empty until the business fills it): no row = `require` (a
  missing PO is flagged, as today); `require` + `pattern` (Java regex) also flags a PO that doesn't match;
  `generate` gives a missing PO a reference from `pattern` (`{date}` = received yyyyMMdd, `{doc}` = 6-char
  document hash; default `AUTO-{date}-{doc}`). Nothing is generated without a rule.
  **Review reasons** in plain words, e.g. *Customer not found in SAP for sales org 4160, 4020, 4025, 4390*,
  *Customer matches 2 SAP customers (…) — choose the sold-to*, *Ship-to … is not linked to sold-to … in sales org
  4160*, *3 material prefix(es) match several materials — SAP will resolve*, *1 EAN(s) match several materials*.
  **Queue**: `customer_number` = the SAP sold-to (it becomes the IDoc's AG partner), `sales_org` and `currency`
  from SAP; region = `region_map` for the sold-to's SAP country if listed, else the SAP affiliate code of the
  sales org + country (e.g. `DAC`), else `Other`; unresolved → `Unassigned`. Use those region names in
  `region_access`.
- Switching an existing deployment between the two needs no full refresh: the next `run_medallion` recomputes
  Gold and the queue (approvals in Lakebase are kept).

## Load your master data
The setup creates empty typed templates. Load your own **in demo mode only** — with `master_source = sap` customers
and materials come from SAP, and `customer_master` / `retailer_sku_map` are not created:
- `customer_master` — every retailer **name variant** → one SAP sold-to.
- `retailer_sku_map` — retailer article number → your material number.
- `product_master` — material + EAN + list prices (EAN resolves EAN-ordered lines).
- `retailer_rules` — optional per-retailer parsing hints.
- `region_map` — country → region (seeded default; in demo mode `customer_master.country` must be filled).
- `region_access` — Databricks group → region (`*` = all) for the Review App's row-level security.
(See comments in `src/setup/01_masters.py`.)

## Prompt governance (instead of a hardcoded prompt)
The extraction prompt lives in the **MLflow Prompt Registry** as `<catalog>.<schema>.order_extraction`, alias `production`. To change extraction behaviour:
1. Edit the template/schema and `register_prompt` → creates a new version.
2. Compare eval runs in the MLflow experiment.
3. `set_prompt_alias(name, "production", <new version>)` to promote (or roll back).
The pipeline loads `@production` at runtime and stamps `prompt_version` on `extracted_parsed` — verify with `SHOW TBLPROPERTIES <catalog>.<schema>.extracted_parsed`.

## Extraction mode: hybrid or ai_query (`extraction_mode`)
One bundle variable picks the extraction architecture for every target:

| `extraction_mode` | What runs |
|---|---|
| `hybrid` (default) | `ai_extract` v2.1 precision mode first (page layout for PDFs/images/Word, text otherwise), `ai_query` with the `order_extraction` prompt as the fallback for documents it can't handle; citations shown in the app |
| `ai_query` | `ai_query` with the `order_extraction` prompt for every document — the original architecture, same SQL; no `ai_extract` calls, no citations |

Switch with a deploy and a pipeline run (no full refresh — Gold is recomputed):
```bash
databricks bundle deploy -t dev --var extraction_mode=ai_query   # or hybrid
databricks bundle run run_medallion -t dev
```
To make it permanent for a target, set `extraction_mode` under that target's `variables` in `databricks.yml`. Gold
records the mode it ran with (`SHOW TBLPROPERTIES <catalog>.<schema>.extracted_parsed` → `extraction_mode`), and the
review queue only shows citations when that mode is `hybrid`. The `ai_extract` schema prompt
(`order_extract_schema`) stays registered either way. See docs/ARCHITECTURE.md *Hybrid extraction*.

## AI Functions used
The pipeline calls three Databricks SQL [AI Functions](https://learn.microsoft.com/en-us/azure/databricks/large-language-models/ai-functions),
all from the serverless Lakeflow pipeline (`resources/medallion_pipeline.yml`). Facts below are from the Azure
Databricks docs (October 2026). Not every Azure region offers them: check
[AI function availability](https://learn.microsoft.com/en-us/azure/databricks/resources/feature-region-support#ai-functions-azure)
before you deploy.

| Function | Where | Input | What it does here | Runs when |
|---|---|---|---|---|
| [`ai_parse_document`](https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/functions/ai_parse_document) | Silver, `src/pipeline/02_silver.py` | PDF / PNG / JPG / DOC / DOCX bytes | layout, text, per-element confidence | always |
| [`ai_extract`](https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/functions/ai_extract) | Gold, `src/pipeline/03_gold.py` (spec: `src/lib/extract_spec.py`) | `ai_parse_document` VARIANT, or text | schema-driven order extraction with per-field confidence + citations | `extraction_mode=hybrid` (primary) |
| [`ai_query`](https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/functions/ai_query) | Gold, `src/pipeline/03_gold.py` (`_ai_query_sql`) | parsed text in the registry prompt | LLM extraction on a Foundation Model endpoint | `extraction_mode=ai_query`; hybrid fallback + retry |

### `ai_parse_document` (Silver)
```python
.withColumn("pv", F.expr("ai_parse_document(content)"))
```
- **Input:** a `BINARY` column (the attachment bytes). Silver sends PDF, PNG, JPG, DOC and DOCX here (`AI_PARSE_MIMES`).
  The function also accepts TIFF and PPT/PPTX, but Silver doesn't route those to it today. Spreadsheets, CSV and
  emails are parsed locally (openpyxl / mail unpacking).
- **Options:** none are set, so the default output schema (`"2.0"`) and default figure descriptions (`'*'`) apply.
  Optional settings: `version` (pins the schema), `imageOutputPath` (saves rendered page images to a UC Volume,
  needed to *render* bounding boxes), `descriptionElementTypes` (`''` turns off figure descriptions to save compute)
  and `pageRange` (e.g. `'1,3,5-10'`).
- **Output (`VARIANT`):** `document.pages[]` (`id`, `image_uri`), `document.elements[]` (`id`, `type`, `content`,
  `confidence` 0–1, `bbox[{coord, page_id}]`, `description`), `error_status[]` and `metadata` (`id`, `version`).
  Element types: `text`, `table` (content is **HTML**), `figure`, `signature`, `title`, `caption`, `section_header`,
  `page_header`, `page_footer`, `page_number`, `footnote`.
- **What Silver keeps:** `parsed_layout` = the whole VARIANT (the layout input for `ai_extract` and the source of
  citation boxes); `parsed_content` = the element `content` values joined with newlines (input to `ai_query`, the
  dedup hash and Gold's checks); `parse_confidence` = mean element `confidence` (an element without a score counts
  as 1.0).
- **Limits:** 500 pages per document (without `pageRange`, a longer document fails before any page is parsed);
  100 MB per file. Accuracy can drop on images with non-Latin text (e.g. Japanese, Korean) and on digitally signed
  documents. You can't swap in your own model.
- **Requirements / billing:** Databricks Runtime 17.3+, or serverless environment version 3+. Usage is billed under the
  `AI_FUNCTIONS` product in `system.billing.usage`. It's the main cost driver (per page, see *Cost*).

### `ai_extract` v2.1 (Gold, `extraction_mode=hybrid`)
`extract_spec.ai_extract_sql()` builds the call, and `oi_extract_primary` runs it:
```sql
ai_extract(p.parsed_layout,            -- or p.parsed_content when there is no layout
           '<order_extract_schema JSON>',
           map('version', '2.1', 'enableConfidenceScores', 'true', 'enableCitations', 'true',
               'instructions', '<rules from the order_extraction prompt + ADDENDUM>', 'mode', 'precision'))
```
- **Input:** the `ai_parse_document` VARIANT for PDFs/images/Word (`b_input='layout'`), or the parsed `STRING` for
  spreadsheets, CSV and email bodies (`b_input='text'`).
- **Schema:** an advanced JSON schema: `orders[]` with header fields (`po_number`, `customer_name`, `order_date`,
  `currency`, `ship_to`, ...) and `line_items[]` (`line_no`, `material_or_sku`, `ean`, `description`, `quantity`, `uom`,
  `unit_price`). Each column is named explicitly because `ai_extract` can shift values between unnamed columns. The
  schema is governed as `order_extract_schema@production` in the Prompt Registry, next to `order_extraction`.
- **Options used:** `version '2.1'` (citations + confidence scores), `mode 'precision'` (the docs recommend it for
  long documents, high-volume outputs such as hundreds of line items, and complex nested schemas),
  `enableConfidenceScores` / `enableCitations`, and `instructions`, which must be under 20,000 characters
  (`instructions_from_prompt()` raises an error past that).
- **Output (`VARIANT`, stored as JSON in `b_raw`):** `{response, error_message, metadata}`. Each scalar leaf is
  `{value, confidence_score, citation_ids}`. `metadata.citations` holds `{id, start, stop}` character spans for text input
  (`chunk_type 'span'`), or `{id, bbox[{coord: [x0,y0,x1,y1], page_id}]}` page boxes for layout input
  (`chunk_type 'bbox'`). `src/lib/extract_adapter.py` converts the response into the `ai_query` JSON shape plus
  per-field confidence (`conf_json`). `src/lib/extract_citations.py` maps the citations to parse elements / text
  spans, which produces `extraction_citations` and the source highlights in the Review App.
- **Limits:** up to 256 schema fields, field names up to 150 characters, 12 levels of nesting, 500 enum values, and 1M
  tokens of total context. Types are enforced for `integer` / `number` / `boolean` / `enum`: a value that doesn't
  match returns an error, and that document goes to the fallback. Gold's size guard (`hybrid_max_chars` 400K,
  `hybrid_max_rows` 3,000) sends very large documents straight to `ai_query`.
- **Requirements:** Databricks Runtime 15.4 LTS+ (18.2+ recommended). Not available on Databricks SQL **Classic**
  warehouses or inside **views**. On workspaces with the Enhanced Security and Compliance add-on, enable it under
  *Previews*. Usage is billed under `AI_FUNCTIONS` (`databricks-ai-extract*` endpoints; see `run_cost` in `src/fe_bar/10_evaluate.py`).

### `ai_query` (Gold, fallback and `extraction_mode=ai_query`)
```sql
ai_query('<serving_endpoint>',                                   -- default databricks-claude-haiku-4-5
         concat('<prompt prefix>', parsed_content, '<prompt suffix>'),   -- order_extraction@production
         responseFormat  => '<registered json_schema "po_batch">',
         modelParameters => named_struct('max_tokens', 32000, 'temperature', 0.0),
         failOnError     => false)
```
- **Endpoint:** the `serving_endpoint` bundle variable. The pipeline's identity needs `CAN QUERY` on the endpoint,
  and the workspace has to be in a Model Serving region.
- **Request:** a `STRING`. The `{{document}}` placeholder in the registered `order_extraction` template is replaced
  with `parsed_content`. Rows are deduplicated by a content hash first, so a re-sent copy of a document is extracted
  once and later copies are marked `duplicate`.
- **`responseFormat`** (DBR 15.4+, chat models only): the prompt's registered `json_schema` (`orders[]` →
  `line_items[]`), so the answer is a JSON string. Gold parses it with `from_json`.
- **`modelParameters`** (DBR 15.3+; must be constants): `max_tokens` 32,000 so large order forms don't get cut off, and
  `temperature` 0.0, which is also the `ai_query` default.
- **`failOnError => false`** (DBR 15.3+): returns a struct (`result`, `errorMessage`) instead of failing the query.
  Endpoint errors become `extraction_status='ai_error'`, and JSON that can't be parsed becomes `'unparseable'`. In
  hybrid mode, an answer that wraps the array in a string is repaired, and failed documents get one more attempt
  (`oi_extract_fallback_retry`). Errors that don't come from the endpoint still fail the query.
- **Requirements / billing:** Databricks Runtime 15.4 LTS+. Not available on Databricks SQL Classic. Usage is billed
  as `MODEL_SERVING` on the extraction endpoint.

## Cost (indicative)
Extraction on **Haiku 4.5** makes the LLM line trivial; cost is dominated by `ai_parse_document` (per page) + the serving layer. On Azure at a representative enterprise discount, ~**$14–30K/yr** for ~100K docs/yr (page-count dependent) — a rounding error against the reclaimed manual-entry capacity. Confirm $/DBU on the Azure pricing calculator for your tier.

## Repo layout
```
databricks.yml            bundle: variables, targets, includes, sync
resources/                pipeline, setup/bootstrap/run/demo jobs + first-deploy job_run, app (Lakebase project: databricks.yml targets)
src/pipeline/             01_bronze.sql (mail_source=volume) | 01_bronze_outlook.py (mail_source=outlook) · 02_silver.py · 03_gold.py
src/setup/                00_schema_volume · 01_masters · 01b_sap_masters (master_source=sap) · 02_register_prompt · 03_build_review_queue · 04_publish_review_queue · 05_export_attachments · 06_fetch_outlook_items · 07_stage_inbound_files (inbound_via_table)
src/lib/sap_masters.py    SAP master SQL builders shared by 01b, Gold and the read-only validation (plain Python)
tests/                    pytest: SAP SQL on synthetic data with a local Spark (`python -m pytest tests`)
src/fe_bar/               FE Bar glue: 00_load_corpus (fictional corpus -> Volume + masters + answer key) · 10_evaluate (accuracy + time/$)
app/                      Review App (FastAPI + React); server/db.py = lakebase|warehouse backend, server/userdb.py = per-user Lakebase connection (RLS)
docs/ARCHITECTURE.md
```
