# Architecture

## Medallion (one Lakeflow Declarative Pipeline, serverless)
| Layer | Object | Logic |
|---|---|---|
| Bronze | `email_attachments` (streaming) | one row per inbound attachment (email metadata + binary/base64); from the Volume (`01_bronze.sql`) or the Outlook connector table (`01_bronze_outlook.py`), per `mail_source` |
| Silver | `parsed_attachments` (MV) | `.msg`/`.eml` emails unpacked into body + attachments; PDFs/scans → `ai_parse_document` (layout + per-element confidence); Excel/CSV → `openpyxl`; unified `parsed_content` + `parse_confidence`; `parsed_layout` = the `ai_parse_document` VARIANT (PDFs/images/Word; NULL otherwise) |
| Gold | `extracted_parsed` (MV) | `extraction_mode=hybrid` (default): `ai_extract` v2.1 precision mode first, `ai_query` as the fallback (see *Hybrid extraction*); `ai_query`: `ai_query` (FM API) with prompt+schema **loaded from the MLflow Prompt Registry** `@production` for every document. Returns an orders array (single- and multi-PO docs) + `extractor`, `fallback_reason`, `field_confidence` |
| Gold | `oi_extract_route`, `oi_extract_primary`, `oi_extract_primary_checked`, `oi_extract_fallback`, `oi_extract_fallback_retry` (MV, hybrid only) | routing, the ai_extract call, its checks + fallback decision, the ai_query fallback (and one retry) |
| Gold | `extraction_citations` (MV, hybrid only) | where each extracted field sits in the source: page + box, sheet + cell, or text span (see *Citations*) |
| Gold | `purchase_orders` (MV) | explode orders/lines; resolve customer→SAP sold-to (exact + Levenshtein fuzzy) and SKU/EAN→material; composite confidence + `needs_review` |
| Gold | `oi_order_customers_doc`, `oi_customer_hints`, `oi_order_customers`, `oi_line_materials` (MV, `master_source=sap` only) | customer → SAP sold-to / sales org / currency / ship-to check, and line code → SAP material, against the `oi_sap_*` working tables; joined into `purchase_orders` |

Catalog/schema/serving-endpoint are injected via the pipeline `configuration` (bundle variables) — read as `${order_intake.catalog}` in SQL and `spark.conf.get("order_intake.catalog")` in Python. No hardcoded catalog.

## Hybrid extraction (`extraction_mode`, default `hybrid`)
Goal: the best extraction per document. **Primary** = `ai_extract(content, schema, map('version','2.1','mode','precision',
'enableCitations','true','enableConfidenceScores','true','instructions', ...))` — `content` is Silver's `parsed_layout`
VARIANT for PDFs/images/Word, otherwise `parsed_content` (cell-addressed spreadsheets, csv, email bodies). Schema and
instructions are governed in the Prompt Registry as `<catalog>.<schema>.order_extract_schema` (template = instructions,
response_format = schema; registered by `02_register_prompt`, its own `@production` alias; never the default mode of
ai_extract). The v2.1 `{value, citation_ids, confidence_score}` wrappers are unwrapped by `src/lib/extract_adapter.py`
into the `ai_query` JSON shape, so `extraction_checks`, SAP resolution, `purchase_orders`, the queue and the IDoc are
unchanged. **Fallback** = the `ai_query` path (same SQL as `extraction_mode=ai_query`), run only for:
- the size guard (`oi_extract_route`): more than `hybrid_max_chars` characters or `hybrid_max_rows` table rows;
- ai_extract results Gold can't trust (`src/lib/extract_select.py`, checked with Gold's own `check_document`):
  no result / error (ai_extract's silent `orders = null` on the largest documents), no order lines, fewer than
  `hybrid_min_completeness` of the filled quantity rows (cut off), codes missing on most lines while the document has
  codes (`hybrid_min_code_coverage`), fewer than `hybrid_min_verified` of the lines grounded in the source.
Where the fallback ran, each document keeps whichever result passes Gold's checks better — completeness, then the
verified-line share; tie → ai_extract — and `fallback_reason` says why in plain words. A fallback answer that failed is
retried once (`oi_extract_fallback_retry`). SAP master-data matching is not part of the choice.
Silver is a materialized view, so the new `parsed_layout` column recomputes it on the next update (no manual full
refresh; Bronze streaming state is untouched) — which re-runs `ai_parse_document` once for every document.

## Citations (`extraction_citations` → `review_citations` → Lakebase)
One row per (document, `order_idx`, `li_idx`, `field`, `citation_id`, location) for documents whose `extractor` is
`ai_extract` (ai_query has no citations). `li_idx` NULL = a header field. `order_idx` / `li_idx` are the positions in
`extracted_parsed.po.orders[*].line_items[*]` — the same keys `purchase_orders` carries and that each element of
`review_orders.line_items_json` now has.

| column | meaning |
|---|---|
| `source_path`, `attachment_filename` | the document (join keys everywhere in Gold) |
| `order_idx`, `li_idx`, `field` | which extracted value (`po_number`, `customer_name`, `order_date`, `currency`, `ship_to`, ...; per line `material_or_sku`, `quantity`, `description`, `unit_price`, `uom`, `line_no`, `source_row`) |
| `value`, `confidence` | the extracted value (string) and ai_extract's `confidence_score` (0–1, may be NULL) |
| `citation_id` | ai_extract's citation id (several fields can share one) |
| `source_kind` | `layout` (PDF/image/Word page box), `sheet` (spreadsheet/csv cell), `text` (email body / txt span) |
| `page_index` | layout: 0-based page |
| `x1, y1, x2, y2` | layout: box in **pixels of the page rendered at 200 DPI, origin top-left, y down** (PDF points = px × 72 / 200; verified on an A4 page: 1654 × 2339 px for 595.3 × 841.9 pt). ai_extract cites a whole parse element (often the entire table) |
| `element_id`, `element_type`, `table_row_index`, `table_row_count` | layout: the `ai_parse_document` element the box belongs to; for tables, the 0-based `<tr>` (incl. header rows) holding the line's code, of `table_row_count` rows — lets a UI narrow the box to the row |
| `sheet_index`, `sheet_name`, `row_number`, `cell_ref` | sheet: Silver's `S<sheet>R<row>` addressing (1-based), the sheet's name, and the cell (`E35`) whose value matches the field (NULL if none matched: the whole row is the citation) |
| `char_start`, `char_stop` | sheet/text: span in `parsed_attachments.parsed_content` |
| `snippet` | short source text: the table row, the sheet row (`A=..  | E=..`) or the cited text |
| `b_input` | `layout` or `text` (what ai_extract read) |

`03_build_review_queue` keys the rows to the review queue as Delta `review_citations` (+ `order_id`, `citation_key`),
and `04_publish_review_queue` republishes them to Lakebase `review_citations` on every run (RLS: a reviewer sees the
citations of the orders they can see). `review_orders` also gets `extractor`, `fallback_reason` and
`field_confidence_json` (ai_extract's per-field confidence for the order's header fields).

**In the Review App** (`GET /api/orders/{id}/citations`, `/preview`, `/document`; frontend `DocPane.tsx`):
citations are read over the same per-request connection as `review_orders` (as the signed-in user when RLS is on).
Documents are read with the app's identity only from `/Volumes/<catalog>/<schema>/<volume>/{inbound_docs,
outlook_attachments}/` (`server/documents.allowed_path`; `UC_VOLUME` env). PDFs are rendered with pdf.js (worker
bundled by Vite, no external hosts), every page fit to the pane, boxes as overlay divs: CSS px = px₂₀₀ × 72/200 ×
(rendered width / page width in points). For table citations the whole table is outlined and the line's row is a band:
the contract's approximation `y1 + h·(row+0.5)/rows`, moved onto the line's product code when the page's text layer
has it inside the table (header rows are taller, so the plain formula can land one row early). Spreadsheets are shown
as a grid built like Silver reads them (visible sheets numbered from 1, Excel row numbers, Silver's cell formatting),
from the workbook the citations name, else rebuilt from the cell-addressed `parsed_content` (fallback orders); cited
cells/rows highlighted. Email/text: `parsed_content[char_start:char_stop]` marked. Clicking a field or line scrolls
the document to its citation and flashes it; hovering a highlight lists the fields it supports.

## Confidence
- **Parse** (`ai_parse_document`) emits real per-element confidence → aggregated per doc. `ai_extract` v2.1 returns a `confidence_score` per field (`field_confidence`; header/line confidence = the minimum over the key fields).
- **Extraction** (`ai_query`) self-reports header/line confidence via the schema.
- **Overall** = parse_confidence × header_confidence; drives the review queue (green ≥0.90 / amber 0.75–0.90 / red <0.75).

## Ingestion — two Bronze sources (`mail_source`)
The pipeline includes exactly one Bronze library, chosen at deploy time:
`libraries: - file: path: ../src/pipeline/${var.bronze_library.${var.mail_source}}`, where `bronze_library` is an
internal complex variable `{volume: 01_bronze.sql, outlook: 01_bronze_outlook.py}`. Both files define
`email_attachments` with identical columns (email_id, from_name, from_email, subject, received_at,
attachment_filename, attachment_mime_type, attachment_size_bytes, content, content_base64, source_path, ingested_at).
An unknown `mail_source` fails `bundle validate` ("reference does not exist"). This keeps `01_bronze.sql` (and so
every existing Volume-mode deployment) byte-for-byte unchanged. (Target-level `libraries` overrides are not an
option: the CLI appends them to the top-level list rather than replacing it.)

**Volume (`01_bronze.sql`).** Auto Loader (`read_files`, binaryFile) over `<volume>/inbound_docs/` only, joined to
`email_manifest` for demo email metadata. MIME type from the manifest, else from the file extension.

**Outlook connector (`01_bronze_outlook.py`).** Lakeflow Connect's managed Outlook connector (Microsoft Graph +
Entra ID OAuth; **Beta / Previews-gated**; works from AWS or Azure; shared-mailbox support not guaranteed in Beta —
validate for your tenant) lands one row per message in `email_messages` (key `mailbox, outlook_message_id`; written
with AUTO CDC, so rows can be updated in place; attachments as `array<struct<content binary, attachment_id,
file_name, mime_type, size, attachment_kind, is_inline>>`). Bronze:
- `spark.readStream.option("readChangeFeed","true").table(outlook_table)`, keeping `_change_type = 'insert'` (CDF
  metadata columns dropped before mapping). On first start the current snapshot arrives as inserts, then each
  later change. Updates (read state, folder moves) are ignored, and a new message is read even when the connector
  writes it in the same MERGE as updates to other rows. (`skipChangeCommits` was rejected: it skips such a mixed
  commit entirely — reproduced on a mock table.) No `startingVersion`: version 0 is usually beyond the table's
  log retention (`DELTA_UNSUPPORTED_TIME_TRAVEL_BEYOND_DELETED_FILE_RETENTION_DURATION` on a customer workspace);
- **CDF must stay enabled on the connector table** (`delta.enableChangeDataFeed = true`, set by the connector). If
  it is turned off, or the connector pipeline is fully refreshed (new table), full-refresh `email_attachments`;
- `dropDuplicates(mailbox, outlook_message_id)` (streaming state, one key per order-mailbox message): a message
  the connector re-inserts can't create a second Bronze row. (Downstream, identical parsed content is extracted
  once anyway — later copies are `extraction_status = 'duplicate'` in Gold and `status = 'duplicate'` in the queue.)
- `lower(mailbox) = lower(outlook_mailbox)` before anything else (the table can hold other mailboxes);
- `posexplode(attachments)`, `is_inline = false` — one row per real attachment; no attachments → no rows;
- email_id = `outlook_message_id`, from_email = `lower(from)`, from_name = `sender` unless it is an address;
  MIME = connector `mime_type`, falling back to the extension map (kept in sync with `02_silver.py` / `01_bronze.sql`)
  when it is empty or `application/octet-stream`;
- source_path = `dbfs:/Volumes/<catalog>/<schema>/<volume>/outlook_attachments/<sha2(outlook_message_id)[:16]>/<attachment_id
  (sanitized; a 16-char hash if longer than 100 chars; position if missing)>/<sanitized file_name>`.

**Attached emails + sender names (Microsoft Graph).** The connector stores an attached Outlook item
(`attachment_kind = 'itemAttachment'`, `message/rfc822`) with `content = NULL`, and no sender display names. The
`fetch_outlook_items` job task (`src/setup/06_fetch_outlook_items.py`) runs **before** the pipeline in `run_medallion`
and `bootstrap` (no-op for `mail_source=volume` or an empty `graph_connection`):
- pending = non-inline attachments of `outlook_mailbox` with no content (itemAttachment, or a fileAttachment left
  empty) not yet fetched (and not failed 3 times). SQL `http_request(conn => graph_connection, method => 'GET',
  path => '/users/{mailbox}/messages/{id}/attachments/{attachment_id}/$value')` (every segment `url_encode`d —
  Graph ids contain `=`, `+`, `/`) returns the item as MIME text → stored as UTF-8 bytes; a fileAttachment is read
  from `.../attachments/{attachment_id}` (`contentBytes`, base64). Batches of 50 are written to a stage table (so
  each request runs once), then MERGEd into `outlook_item_attachments` (key mailbox, outlook_message_id,
  attachment_id; `http_status`, `error`, `attempts`; change data feed on). A setup error — `http_request` *returns* (doesn't raise) 404 `RESOURCE_DOES_NOT_EXIST` for a missing
  connection; also `PERMISSION_DENIED`, Graph 401/403 — records nothing for that batch, uses no attempt and stops
  (verified on fevm with a non-existent connection); so does a query-level exception.
- `GET /users/{mailbox}/messages/{id}?$select=from,sender` once per message with a non-inline attachment →
  `outlook_message_senders` (from_name, from_address), same retry rule.
- Bronze: the main flow **skips** content-less attachments; a second flow `email_attachments_fetched`
  (`@dlt.append_flow` into `email_attachments`) streams `outlook_item_attachments`' change feed (`insert` +
  `update_postimage` with content — content is set exactly once per row) and joins the connector table (static)
  for the message metadata; items become `<name>.eml`, `message/rfc822`. So each fetched attachment reaches Bronze
  exactly once, whether it was fetched before its message was streamed or later (retry, late fetch, connector
  sync between fetch and pipeline). This replaced a left join in the main flow, which would lose late fetches.
  If the table doesn't exist when the pipeline starts, the flow is simply not defined (and is added, from the
  table's snapshot, by the first update after it exists).
- from_name = `outlook_message_senders.from_name` (static join, so not backfilled for messages streamed before
  their name was fetched), else the connector's `sender` unless it is an address.
- Silver unpacks `message/rfc822` (`.eml`) like `.msg` (`unpack_mail_parts`): body → `body.txt`, each attachment a
  part named `<email>.eml / <file>`, attached emails recursively up to depth 3; inline images skipped. The parts
  keep the outer email's `email_id` / `source_path`. The review queue doesn't link `.eml` parts as PDFs (as for
  `.msg`), so the app shows their parsed text, not the PDF.
- Recreating `outlook_item_attachments` (drop + fetch again) needs a full refresh of `email_attachments`.

The `export_attachments` job task (`src/setup/05_export_attachments.py`, in `run_medallion` and `bootstrap`, after the
pipeline and before the queue) writes each Outlook attachment's bytes to its `source_path` if the file is missing
(no-op for `mail_source=volume`), so the queue's `volume_path` and the app's document view work unchanged.
`outlook_attachments/` is a sibling of `inbound_docs/`, so the Volume-mode Auto Loader never reads it.

**Switching** a deployment between sources changes the stream's source: full-refresh `email_attachments` (see README).

Fallback if the Beta is unavailable: Power Automate / Logic Apps → land attachments in `<volume>/inbound_docs/` →
`mail_source: volume`.

## Master data (`master_source`)
`demo`: `purchase_orders` joins the template tables (`customer_master`, `retailer_sku_map`, `product_master`) —
unchanged; the demo-mode SQL is byte-for-byte the previous version's (verified by rendering both).

`sap`: the real SAP masters, never copied in full.
```
SAP views (sap_catalog.db_fnd_proc.v_*) ──01b_sap_masters (job task, before the pipeline)──►
   oi_sap_customers (KNA1+ADRC+KNVV, configured sales orgs) · oi_sap_partner_links (KNVP AG/WE/RE/RG)
   oi_sap_materials (MARA FERT/HAWA listed in MVKE + MARM EANs + MAKT) · oi_sap_region_map (geography look-up)
Gold: _sap_hdr (orders) ──customer_resolution_sql──► oi_order_customers_doc ──(not found: hints)──► oi_order_customers ──┐
      oi_customer_hints (sender / subject / file name) ─────────────────────┘
      _sap_lines + order sales org ──material_resolution_sql──► oi_line_materials ──┴──► purchase_orders
Queue: customer_number = sold-to, sales_org/currency from KNVV, region = region_map(country) | SAP affiliate
```
- **One SQL, three callers.** `src/lib/sap_masters.py` (plain Python, no Spark import) builds every statement:
  the materialization SELECTs (01b), the resolution SELECTs (Gold) and — composed as CTEs over the SAP views — the
  read-only validation. The pipeline imports it via `order_intake.lib_path` (`${workspace.file_path}/src/lib`), the
  notebooks via their `lib_path` parameter. Tests (`tests/`) run the same SQL on synthetic SAP-shaped tables in a
  local Spark, including the real `03_gold.py` (sap mode) and `03_build_review_queue.py` with stubbed `dlt`.
- **Views, not change logs.** Only the `v_*` views (one row per key) are read; the `c_*` CDC tables have several rows
  per key and partial coverage. ADRC is joined on `ADDRNUMBER = KNA1.ADRNR` with `NATION = ''` (international
  versions skipped). KNVV is per division: per (customer, sales org) the currency is the most common non-deleted
  WAERS, the sales org is "deleted" only if every division row is, and blocks (AUFSD) are kept as flags.
- **Performance.** Customers are restricted to KNVV views in the configured orgs before KNA1 is joined (DACH:
  ~39K (customer, org) rows out of 1.2M KNA1); candidate pairs are found by an equi-join on shared name/postcode
  tokens (tokens on more than 3,000 customers dropped) plus the printed customer number, so no order × customer
  cross join. The resolution steps are separate tables so each query plan stays small.
- **Customer scoring** (per order × candidate): name similarity (max of Levenshtein on the normalized name,
  order-name-inside-SAP-name = 0.9 (short single words excluded), word overlap × 0.9 with trade words such as
  Parfümerie/Drogerie ignored and at least two words); address = postcode 0.40 + city 0.25 + street 0.35 found in
  the order's name + ship-to text; printed customer number = KUNNR. Acceptable: number (+ some name/address
  evidence) | name ≥ 0.6 and address ≥ 0.4 | name ≥ 0.85 | address ≥ 0.75 and name ≥ 0.35. Score = 0.6 name +
  0.4 address (+0.3 number) − 0.1 deleted − 0.06 order block. Sold-tos within 0.05 of the best → ambiguous.
  Candidates that are only ship-to/bill-to/payer map to their sold-to(s) via KNVP when no sold-to matched directly.
- **Customer from the email or file name** (`order_intake.customer_hints`, default on). When the document's
  customer resolves to nothing (no name, the supplier printed as the customer, or not in SAP), Gold tries customer-like texts
  from around the document (`oi_customer_hints`, built by `src/lib/customer_hints.py`), best first: the sender's
  email domain (`orders@mueller-drogerie.de` → "mueller drogerie"), the sender's display name, the subject and the
  file name. For an email unpacked from a `.msg`/`.eml`, the From:/Subject: of that email (Silver writes them at the
  top of its `body.txt` part) come before the mailbox sender, so a forwarded customer email still names the
  customer. Supplier domains and brands, free-mail domains (gmail, t-online, orange, ...), dates, numbers and order
  words (Bestellung, bestelling, commande, BDC, ...) are never hints. Each hint is resolved with the same scoring
  as a printed name, together with the order's printed customer number and ship-to; the first hint that gives ONE
  sold-to wins, else the first ambiguous one (candidates listed). `customer_source` / `customer_hint` record where
  it came from; the order is always reviewed ("Customer inferred from the sender's email domain (…): … — check"),
  and the queue shows the SAP name when the document printed none.
- **Confidence** keeps the demo formula; customer score: inferred from the email/file name = 0.7 (ambiguous 0.5), number / name+address / pinned = 1.0, name or address
  only = 0.9, ambiguous = 0.6, not found = 0.5 (SAP is the full master, so "not found" weighs more than in demo).
  `line_needs_review` adds: ambiguous customer, ship-to not linked, deleted/blocked customer, deleted material,
  ambiguous EAN, material not listed / not found, a pinned sold-to that isn't in SAP.

## SAP writeback
On approve, the Review App writes the order to `sap_outbound` as an **ORDERS05-style IDoc** JSON payload (EDI_DC40 / E1EDK01 / E1EDK02 / E1EDKA1 / E1EDP01), with approver + timestamp. The customer PO is the number printed on the customer's document (never an SAP lookup); it goes in E1EDK02 with qualifier 001 (customer purchase order), which inbound ORDERS processing writes to the sales order's customer PO field (VBAK-BSTNK). Wire an outbound job/connector to deliver these to SAP.

## Review App
React (Vite) + FastAPI, deployed as a Databricks App (dual-mode auth: local CLI profile vs. app service principal). Streams source PDFs from the UC Volume for side-by-side review.

The app reads/updates `review_orders` + `sap_outbound` as native **Lakebase (Autoscaling) Postgres** tables: OLTP semantics (low-latency single-row reads/writes, real concurrency for multiple reviewers). Each target creates a Lakebase project and attaches it to the app as a `postgres` resource (the app's service principal gets a Postgres role); `04_publish_review_queue.py` upserts the Delta queue into Postgres after each pipeline run, **preserving approved rows**, and grants the app's role on both tables. The app mints a short-lived Postgres credential per connection. (`app/server/db.py` also supports a SQL-warehouse backend via `APP_BACKEND=warehouse`; no target deploys it.)

Route SQL is written once with `:param` markers; the data layer translates to psycopg's `%(param)s` for Postgres, so the routes are backend-agnostic. The Delta tables remain the lineage/source-of-record in both modes.

### Row-level security (Lakebase, as the signed-in user)
Opt-in (`rls_enforced=true`; default `false`). Region membership lives in Databricks groups; Postgres enforces it.

```
Delta region_map (country->region) ──03──► review_orders.region ──04 publish──► Lakebase review_orders.region
Delta region_access (group->region|*) ──04: SCIM group members──► Lakebase user_regions(principal, region, via_group)
                                       └─► per member: databricks_create_role + GRANT oi_reviewer_<schema>
Browser ─► Apps proxy (user token, scope postgres) ─► app: POST /api/2.0/postgres/credentials WITH THE USER'S TOKEN
        ─► psycopg login as <user email> ─► SET ROLE oi_reviewer_<schema> ─► RLS policies on session_user
```
- **Spike result (fevm, 2026-10-14).** With `user_api_scopes: [postgres]` the proxy forwards
  `X-Forwarded-Access-Token` (effective scopes `postgres`, `iam.current-user:read`, `iam.access-control:read`; the
  `iam.*` defaults can't be listed in `user_api_scopes` — the API rejects them). `POST /api/2.0/postgres/credentials`
  called with that token returns a credential for the user, and Lakebase accepts a login as the user's role (email)
  — `current_user`/`session_user` = the user. Lakebase also accepted the forwarded token itself as the password,
  but that isn't documented, so the app uses the documented credential exchange. Verified for the project owner
  and for two service principals with no Lakebase project ACL of their own (they called the app with M2M tokens;
  the `users` group had only `CAN_CREATE` on projects).
- **Postgres roles.** One login role per Databricks identity (Lakebase maps users by email, service principals by
  application id; a group role would make `current_user` the group, losing the individual). Created by the publish
  job for every member of a `region_access` group.
- **Why `SET ROLE` + `session_user`.** The project owner's role has BYPASSRLS (and `DATABRICKS_SUPERUSER`), so a plain
  login would see every row. After `SET ROLE oi_reviewer_<schema>` (NOLOGIN, no BYPASSRLS, the only role with
  reviewer privileges) RLS applies to everyone, and the policies identify the user by `session_user`, which `SET
  ROLE` doesn't change (`SET SESSION AUTHORIZATION` needs superuser). The app issues only its own fixed SQL, so a
  session can't `RESET ROLE`.
- **Policies** (`FORCE ROW LEVEL SECURITY`, so owners are subject too):
  `review_orders` SELECT/UPDATE for `oi_reviewer_*`: `coalesce(region,'Unassigned') IN (user's regions) OR user has '*'`
  (UPDATE also `WITH CHECK`; column-level UPDATE grant excludes `region`); `sap_outbound` ALL for the reviewer:
  `EXISTS (visible review_orders row with the same order_id)` (inherits the region rule; INSERT `WITH CHECK`);
  `user_regions` SELECT: `principal = session_user`. `oi_publisher_<schema>` (granted to whoever runs publish) has
  `FOR ALL USING (true)` on all three so the publish needs no BYPASSRLS.
- **Publish writes**: queue upsert, region refresh (also for approved rows), `user_regions` replaced in one
  transaction together with grants and policies.
- **App SP**: only `USAGE` on the schema; `REVOKE ALL` on the tables. Feedback/MLflow logging and the PDF download
  (after an RLS-checked lookup of `volume_path`) still use the app's identity.
- **Per request**: credentials cached in memory per token hash for 30 min (Lakebase credentials live ~1 h, checked
  only at login); one connection per request. No token → 401 (default deny); `RLS_ENFORCED=false` → the app's
  service-principal connection (publish with `rls_enforced=false` disables RLS and grants the SP).
- **Not chosen: option 2** (UC row filter on Delta + `sql` scope through the warehouse): would move the app's OLTP
  reads/writes back to the warehouse. Not needed since the Lakebase path works.

## Extraction quality controls
- **Cell-addressed spreadsheets (Silver).** xlsx/xls/csv are rendered one row per line with every value tagged by its column (`S1R35: A=Shampoo | C=AX10010000 | E=3`). Empty cells are omitted but can never shift a value into the wrong column — the cause of order forms returning the whole catalog with prices read as quantities. Multi-line header cells are joined; float noise is removed; styled-but-empty ranges are bounded.
- **Prompt v2 (Prompt Registry).** Finds the *ordered*-quantity column (and names the look-alikes that aren't: First Order Qty, MOQ, pack size, prices, price×qty) and returns only rows with quantity > 0; PO-number rules (labels to look for; never a date/title/SKU/invoice no.); an explicit supplier list that may never be the customer. It also returns grounding fields: `quantity_column(_letter)`, per-line `source_row`, `po_number_label`.
- **Deterministic checks (Gold `extraction_checks`).** Each line is verified against its source row (SKU present, quantity in the stated column); completeness compares filled ordered-quantity rows in the form to extracted lines; PO numbers are checked for format and presence in the document; supplier-as-customer is detected (a salon whose name contains a brand is still a customer).
- **Confidence = verification, not self-rating.** `order_confidence = parse_confidence × (0.35·header + 0.45·verified-line share + 0.20·completeness)`, where header = PO valid & found + customer (supplier/missing = 0, resolved = 1, unresolved = 0.75 because masters may be incomplete). Every order carries plain-language `review_reasons`.
- **Dedup.** Identical parsed content is extracted once (later copies: `extraction_status='duplicate'`); orders with the same valid PO for the same customer (incl. an email body vs. its attachment) are kept with `status='duplicate'` + `duplicate_of`. Nothing is silently dropped — orders with no ordered lines are queued too.
