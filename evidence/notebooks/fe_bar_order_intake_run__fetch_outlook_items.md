# [dev <deployer>] fe_bar_order_intake_run / fetch_outlook_items (run 864126008699539, as executed, with outputs)

Notebook `f7f2bf47-ebcb-4244-8d4d-90d6bc1524b5`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 06 — Fetch attached Outlook items through Microsoft Graph (mail_source = outlook only)
The Lakeflow Connect Outlook connector stores an **attached Outlook message** (an email dragged into the
order email, `attachment_kind = 'itemAttachment'`, `message/rfc822`) without its bytes (`content = NULL`),
and it stores no sender display names. This task fills both gaps with **read-only** Graph GETs through a
Unity Catalog HTTP connection (`graph_connection`; base path `/v1.0`, same Entra app as the connector):
- every non-inline attachment of the mailbox with no content (itemAttachment, or a fileAttachment the
  connector left empty) → `<schema>.outlook_item_attachments` (one row per attachment):
  - itemAttachment: `GET /users/{mailbox}/messages/{id}/attachments/{attachment_id}/$value` = the attached
    message as MIME (.eml) text, stored as UTF-8 bytes;
  - fileAttachment: `GET .../attachments/{attachment_id}` → its base64 `contentBytes`, decoded;
- every message of the mailbox with a non-inline attachment → `<schema>.outlook_message_senders`
  (`GET /users/{mailbox}/messages/{id}?$select=from,sender` → display name + address).

Each attachment / message is fetched **once**. A failure is recorded (`http_status`, `error`) and retried
on later runs, at most `MAX_ATTEMPTS` times in total. Bronze (`01_bronze_outlook.py`) streams the fetched
items from this table's change feed, so an item reaches Bronze whenever its fetch succeeds. Runs BEFORE
the pipeline, so a new message's items normally reach Bronze in the same run.

`graph_connection` empty → prints a notice and does nothing (attached emails then stay out of Bronze;
everything else works). `mail_source = volume` → no-op. Only counts are printed — never bodies or MIME.
Testing without Graph: `graph_connection = mock:<catalog>.<schema>.<table>` answers each request from a
table `(path STRING, status_code INT, text STRING)` keyed by the Graph path (no query string).

```python
import re
from datetime import datetime, timezone

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("mail_source", "volume"),
             ("outlook_table", ""), ("outlook_mailbox", ""), ("graph_connection", ""),
             ("fetch_table_prefix", "")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
mail_source = dbutils.widgets.get("mail_source").strip().lower()
source_table = dbutils.widgets.get("outlook_table").strip()
# one or more mailboxes, comma-separated; validated because they are inlined into SQL below
import re
mailboxes = [m.strip().lower() for m in dbutils.widgets.get("outlook_mailbox").split(",") if m.strip()]
bad = [m for m in mailboxes if not re.fullmatch(r"[a-z0-9._%+'-]+@[a-z0-9.-]+", m)]
if bad:
    raise ValueError(f"outlook_mailbox: not an email address: {bad}")
mailbox = ", ".join(mailboxes)                      # for messages
mb_in = ", ".join(f"'{m}'" for m in mailboxes)      # for SQL
graph_connection = dbutils.widgets.get("graph_connection").strip()

if mail_source not in ("outlook", "both"):
    dbutils.notebook.exit(f"mail_source={mail_source}: nothing to fetch")
if not source_table or not mailboxes:
    raise ValueError("mail_source=outlook needs outlook_table and outlook_mailbox")

S = f"{catalog}.{schema}"
# Same prefix as Bronze (order_intake.fetch_table_prefix): keeps these tables separate from another accelerator's.
prefix = dbutils.widgets.get("fetch_table_prefix").strip()
ITEMS, SENDERS = f"{S}.{prefix}outlook_item_attachments", f"{S}.{prefix}outlook_message_senders"
MAX_ATTEMPTS = 3      # first try + 2 retries (one per run)
BATCH = 50            # requests per http_request query

# Bronze reads these tables (ITEMS through its change feed), so they exist even when nothing is fetched.
spark.sql(f"""CREATE TABLE IF NOT EXISTS {ITEMS} (
  mailbox STRING, outlook_message_id STRING, attachment_id STRING, attachment_kind STRING, file_name STRING,
  mime_type STRING, size BIGINT, mime_content BINARY, fetched_at TIMESTAMP, http_status INT, error STRING,
  attempts INT)
COMMENT 'Attachments the Outlook connector stored without content (attached emails = itemAttachment), fetched from Microsoft Graph by 06_fetch_outlook_items.py. mime_content = .eml bytes (itemAttachment) or the file bytes.'
TBLPROPERTIES (delta.enableChangeDataFeed = true)""")
spark.sql(f"""CREATE TABLE IF NOT EXISTS {SENDERS} (
  mailbox STRING, outlook_message_id STRING, from_name STRING, from_address STRING, fetched_at TIMESTAMP,
  http_status INT, error STRING, attempts INT)
COMMENT 'Sender display names of the order mailbox messages (the connector stores addresses only), from Microsoft Graph.'""")

# Attachments Graph can fill: not inline, no content, has an id; itemAttachment or fileAttachment.
# Keep this predicate in sync with _FETCHABLE in src/pipeline/01_bronze_outlook.py.
FETCHABLE = """NOT coalesce(a.is_inline, false) AND (a.content IS NULL OR length(a.content) = 0)
  AND a.attachment_id IS NOT NULL
  AND (lower(a.attachment_kind) LIKE '%item%' OR lower(a.attachment_kind) LIKE '%file%')"""
spark.sql(f"""SELECT lower(m.mailbox) mailbox, m.outlook_message_id, a.attachment_id, a.attachment_kind,
    a.file_name, a.mime_type, a.size, lower(a.attachment_kind) LIKE '%item%' is_item, a.content, a.is_inline
  FROM {source_table} m LATERAL VIEW explode(m.attachments) t AS a
  WHERE lower(m.mailbox) IN ({mb_in})""").createOrReplaceTempView("_att")
n_fetchable = spark.sql(f"SELECT count(*) n FROM _att a WHERE {FETCHABLE}").first().n

if not graph_connection:
    dbutils.notebook.exit(
        f"graph_connection is not set: {n_fetchable} attachment(s) of {mailbox} have no content in the connector "
        "table (attached emails); they are not fetched and stay out of Bronze. Create the Graph HTTP connection "
        "and set the bundle variable graph_connection to fetch them (see README).")

mock_table = graph_connection[5:].strip() if graph_connection.startswith("mock:") else None
if not mock_table and not re.fullmatch(r"[A-Za-z0-9_\-]+", graph_connection):
    raise ValueError(f"graph_connection must be a connection name (got {graph_connection!r})")


# http_request returns (not raises) these: connection missing (404 RESOURCE_DOES_NOT_EXIST), no USE CONNECTION,
# Graph 401/403 (token / app permission / application access policy). They'd fail every item the same way, so
# they must not use up the items' attempts.
CONFIG_ERROR = ("(http_status IN (401, 403) OR error LIKE '%RESOURCE_DOES_NOT_EXIST%' "
                "OR error LIKE '%PERMISSION_DENIED%')")


def _request(view, params_sql="NULL"):
    """SQL selecting every column of `view` + r = struct(status_code, text) for its `path` column."""
    if mock_table:
        return (f"SELECT p.*, named_struct('status_code', coalesce(m.status_code, 404), 'text', "
                f"coalesce(m.text, '{{\"error\":{{\"code\":\"ErrorItemNotFound\"}}}}')) r "
                f"FROM {view} p LEFT JOIN {mock_table} m ON m.path = p.path")
    params = "" if params_sql == "NULL" else f", params => {params_sql}"
    return (f"SELECT p.*, http_request(conn => '{graph_connection}', method => 'GET', path => p.path{params}) r "
            f"FROM {view} p")


def _run(kind, pending_sql, stage_sql, merge_sql):
    """Fetch the pending keys in batches: stage table (http_request evaluated once) -> MERGE -> drop."""
    pending_df = spark.sql(pending_sql)
    pending = pending_df.collect()                       # keys + metadata only (small)
    ok = failed = 0
    stage = f"{S}._outlook_fetch_stage"
    for i in range(0, len(pending), BATCH):
        spark.createDataFrame(pending[i:i + BATCH], schema=pending_df.schema).createOrReplaceTempView("_batch")
        try:
            spark.sql(f"CREATE OR REPLACE TABLE {stage} AS {stage_sql}")
        except Exception as e:  # query-level failure (e.g. network): nothing recorded, no attempt used
            spark.sql(f"DROP TABLE IF EXISTS {stage}")
            msg = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
            print(f"{kind}: Graph request failed for the whole batch, stopping (nothing recorded): {msg}")
            return ok, failed, len(pending), True
        c = spark.sql(f"SELECT count_if(http_status BETWEEN 200 AND 299 AND error IS NULL) ok, "
                      f"count_if(NOT (http_status BETWEEN 200 AND 299 AND error IS NULL)) failed, "
                      f"max_by(error, {CONFIG_ERROR}) cfg_error, count_if({CONFIG_ERROR}) n_cfg FROM {stage}").first()
        if c.n_cfg:   # setup problem, not a problem of these items: record nothing, use no attempt, stop
            spark.sql(f"DROP TABLE IF EXISTS {stage}")
            print(f"{kind}: connection/permission error, stopping (nothing recorded): {(c.cfg_error or '')[:300]}")
            return ok, failed, len(pending), True
        ok, failed = ok + c.ok, failed + c.failed
        spark.sql(merge_sql.format(stage=stage))
        spark.sql(f"DROP TABLE IF EXISTS {stage}")
    return ok, failed, len(pending), False


now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
# Graph ids contain '=', '+', '/', '-': url_encode every path segment.
items = _run(
    "attachments",
    f"""SELECT DISTINCT a.mailbox, a.outlook_message_id, a.attachment_id, a.attachment_kind, a.file_name,
          a.mime_type, a.size, a.is_item,
          concat('/users/', url_encode(a.mailbox), '/messages/', url_encode(a.outlook_message_id),
                 '/attachments/', url_encode(a.attachment_id), CASE WHEN a.is_item THEN '/$value' ELSE '' END) path
        FROM _att a
        LEFT ANTI JOIN {ITEMS} i
          ON i.mailbox = a.mailbox AND i.outlook_message_id = a.outlook_message_id
         AND i.attachment_id = a.attachment_id
         AND (i.mime_content IS NOT NULL OR i.attempts >= {MAX_ATTEMPTS})
        WHERE {FETCHABLE}""",
    f"""SELECT mailbox, outlook_message_id, attachment_id, attachment_kind, file_name, mime_type, size,
          CAST(r.status_code AS INT) http_status, content AS mime_content,
          CASE WHEN NOT r.status_code BETWEEN 200 AND 299 THEN substr(r.text, 1, 500)
               WHEN content IS NULL THEN 'response has no content' END error,
          timestamp'{now}' fetched_at
        FROM (SELECT *, CASE WHEN r.status_code BETWEEN 200 AND 299 THEN
                     CASE WHEN is_item THEN nullif(encode(r.text, 'UTF-8'), X'')            -- MIME text
                          ELSE unbase64(get_json_object(r.text, '$.contentBytes')) END END content
              FROM ({_request('_batch')}))""",
    f"""MERGE INTO {ITEMS} t USING {{stage}} s
        ON t.mailbox = s.mailbox AND t.outlook_message_id = s.outlook_message_id AND t.attachment_id = s.attachment_id
        WHEN MATCHED THEN UPDATE SET mime_content = s.mime_content, http_status = s.http_status, error = s.error,
          fetched_at = s.fetched_at, attempts = t.attempts + 1
        WHEN NOT MATCHED THEN INSERT (mailbox, outlook_message_id, attachment_id, attachment_kind, file_name,
          mime_type, size, mime_content, fetched_at, http_status, error, attempts)
          VALUES (s.mailbox, s.outlook_message_id, s.attachment_id, s.attachment_kind, s.file_name, s.mime_type,
          s.size, s.mime_content, s.fetched_at, s.http_status, s.error, 1)""")

senders = _run(
    "senders",
    f"""SELECT DISTINCT a.mailbox, a.outlook_message_id,
          concat('/users/', url_encode(a.mailbox), '/messages/', url_encode(a.outlook_message_id)) path
        FROM _att a
        LEFT ANTI JOIN {SENDERS} s
          ON s.mailbox = a.mailbox AND s.outlook_message_id = a.outlook_message_id
         AND (s.error IS NULL OR s.attempts >= {MAX_ATTEMPTS})
        WHERE NOT coalesce(a.is_inline, false)""",
    f"""SELECT mailbox, outlook_message_id, CAST(r.status_code AS INT) http_status,
          coalesce(get_json_object(r.text, '$.from.emailAddress.name'),
                   get_json_object(r.text, '$.sender.emailAddress.name')) from_name,
          lower(coalesce(get_json_object(r.text, '$.from.emailAddress.address'),
                         get_json_object(r.text, '$.sender.emailAddress.address'))) from_address,
          CASE WHEN NOT r.status_code BETWEEN 200 AND 299 THEN substr(r.text, 1, 500) END error,
          timestamp'{now}' fetched_at
        FROM ({_request('_batch', "map('$select', 'from,sender')")})""",
    f"""MERGE INTO {SENDERS} t USING {{stage}} s
        ON t.mailbox = s.mailbox AND t.outlook_message_id = s.outlook_message_id
        WHEN MATCHED THEN UPDATE SET from_name = s.from_name, from_address = s.from_address,
          http_status = s.http_status, error = s.error, fetched_at = s.fetched_at, attempts = t.attempts + 1
        WHEN NOT MATCHED THEN INSERT (mailbox, outlook_message_id, from_name, from_address, fetched_at,
          http_status, error, attempts)
          VALUES (s.mailbox, s.outlook_message_id, s.from_name, s.from_address, s.fetched_at, s.http_status,
          s.error, 1)""")

summary = spark.sql(f"""SELECT count_if(mime_content IS NOT NULL) fetched,
    count_if(mime_content IS NULL AND attempts < {MAX_ATTEMPTS}) retry_later,
    count_if(mime_content IS NULL AND attempts >= {MAX_ATTEMPTS}) given_up
  FROM {ITEMS} WHERE mailbox IN ({mb_in})""").first()
lines = [f"{kind}: {n} pending, {ok} fetched now, {failed} failed now" + (" (STOPPED: see above)" if aborted else "")
         for kind, (ok, failed, n, aborted) in [("attachments", items), ("senders", senders)]]
lines.append(f"{ITEMS} for {mailbox}: {summary.fetched} fetched, {summary.retry_later} failed (retried next run), "
             f"{summary.given_up} failed {MAX_ATTEMPTS} times (not retried)")
print("\n".join(lines))
dbutils.notebook.exit("; ".join(lines))
```

**Output:**

```
mail_source=volume: nothing to fetch
```

