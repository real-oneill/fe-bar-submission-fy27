# ============================================================
# Order Intake — Lakeflow Declarative Pipeline · Phase 1: BRONZE (Outlook connector source)
# ============================================================
# Used INSTEAD of 01_bronze.sql when the bundle variable `mail_source` = outlook (the bundle picks one of the
# two files as the pipeline's Bronze library). Builds the SAME `email_attachments` table, with the same
# columns, from the Lakeflow Connect Outlook connector's `email_messages` table:
#   - only the configured mailboxes (`order_intake.outlook_mailbox`, comma-separated); the connector table can hold others,
#   - one row per NON-inline attachment (inline parts are signature logos/pictures); messages with no such
#     attachment produce no rows (orders come from attachments, as in the Volume mode),
#   - streamed from the table's CHANGE FEED, keeping only `insert` changes: the connector table is an AUTO CDC
#     (SCD1) target whose rows are updated in place (is_read, folder moves, ...). Updates never stop or duplicate
#     the stream, and a new message is read even when it shares a commit with updates (a plain stream with
#     skipChangeCommits would skip that whole commit). Needs delta.enableChangeDataFeed = true on the table.
#     First start: the current snapshot arrives as inserts, then every later change (no startingVersion: version
#     0 is usually past the table's log retention).
#   - deduplicated on (mailbox, outlook_message_id), so a message the connector re-inserts (deleted + re-synced)
#     can't create a second Bronze row.
#   - ATTACHED EMAILS: the connector stores an attached Outlook message (itemAttachment) with content = NULL. The
#     job task 06_fetch_outlook_items.py (before the pipeline; needs graph_connection) fetches it from Microsoft
#     Graph as MIME into outlook_item_attachments; the second flow `email_attachments_fetched` streams that
#     table's change feed into this table (message/rfc822, file name *.eml; Silver unpacks it). The main flow
#     skips content-less attachments, so each one reaches Bronze once, when (and only if) it was fetched.
#   - from_name: the Graph display name (outlook_message_senders) when fetched, else the connector's `sender`
#     unless it is an address.
# source_path = where 05_export_attachments.py writes the attachment's bytes in the Volume, so the Review App
# can show the document. The path is outside inbound_docs/, so the Volume-mode Auto Loader never reads it.
# Silver unpacks attached emails (.eml / .msg) into their parts; Gold is unchanged.
# ============================================================
import dlt
from pyspark.sql import functions as F

CAT = spark.conf.get("order_intake.catalog")
SCH = spark.conf.get("order_intake.schema")
VOL = spark.conf.get("order_intake.volume")
# the Volume may sit in another catalog/schema than the tables (default: the same)
VCAT = spark.conf.get("order_intake.volume_catalog", "").strip() or CAT
VSCH = spark.conf.get("order_intake.volume_schema", "").strip() or SCH
SOURCE_TABLE = spark.conf.get("order_intake.outlook_table", "").strip()
# one or more mailboxes, comma-separated (e.g. the EMEA order mailbox plus the DACH country mailboxes)
MAILBOXES = [m.strip().lower() for m in spark.conf.get("order_intake.outlook_mailbox", "").split(",") if m.strip()]
MAILBOX = ", ".join(MAILBOXES)
if not SOURCE_TABLE or not MAILBOXES:
    raise ValueError("mail_source=outlook needs the bundle variables outlook_table (the connector's "
                     "email_messages table) and outlook_mailbox (the mailbox to read orders from).")

EXPORT_ROOT = f"dbfs:/Volumes/{VCAT}/{VSCH}/{VOL}/outlook_attachments"
# Written by src/setup/06_fetch_outlook_items.py (job task before the pipeline) when graph_connection is set.
# Optional prefix (var.fetch_table_prefix) so these tables don't collide with another accelerator using the same
# schema (e.g. another accelerator already owns <schema>.outlook_item_attachments).
FETCH_PREFIX = spark.conf.get("order_intake.fetch_table_prefix", "").strip()
ITEMS_TABLE = f"{CAT}.{SCH}.{FETCH_PREFIX}outlook_item_attachments"
SENDERS_TABLE = f"{CAT}.{SCH}.{FETCH_PREFIX}outlook_message_senders"
EML_MIME = "message/rfc822"

# Keep in sync with MIME_BY_EXT in 02_silver.py and the CASE in 01_bronze.sql.
MIME_BY_EXT = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "txt": "text/plain",
    "edi": "text/plain",     # X12 EDI (850/860) interchanges are plain text
    "json": "text/plain",    # portal exports / ASR transcripts: read as text
    "msg": "application/vnd.ms-outlook",
    "eml": "message/rfc822",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
}


def _mime_from_ext(filename_col):
    ext = F.lower(F.regexp_extract(filename_col, r"[.]([A-Za-z0-9]+)$", 1))
    expr = F.lit("application/octet-stream")
    for e, m in reversed(list(MIME_BY_EXT.items())):
        expr = F.when(ext == e, m).otherwise(expr)
    return expr


def _safe(col):
    """One path segment: no separators, no characters that break a Files-API URL."""
    return F.regexp_replace(col, r'[\\/:*?"<>|#%\x00-\x1f]', "_")


# Attachments the connector stored WITHOUT content that 06_fetch_outlook_items.py fetches from Graph (attached
# emails = itemAttachment; empty fileAttachments). Keep in sync with FETCHABLE in src/setup/06_fetch_outlook_items.py.
def _fetchable(a):
    kind = F.lower(a["attachment_kind"])
    return ((a["content"].isNull() | (F.length(a["content"]) == 0)) & a["attachment_id"].isNotNull()
            & (kind.like("%item%") | kind.like("%file%")))


def _table_exists(name):
    # (spark.catalog.tableExists returns False inside a pipeline for tables it doesn't manage; resolve it instead)
    try:
        spark.read.table(name).schema
        return True
    except Exception:  # noqa
        return False


def _with_sender_names(df):
    """Display names fetched from Graph (outlook_message_senders); else the connector's `sender` unless it is an
    address. Static side of a stream-static join: a name fetched after its message was streamed isn't backfilled
    (the fetch task runs before the pipeline, so new messages normally have it)."""
    connector_name = (F.when(F.col("sender").contains("@") | (F.trim(F.col("sender")) == ""),
                             F.lit(None).cast("string")).otherwise(F.col("sender")))
    if not _table_exists(SENDERS_TABLE):
        return df.withColumn("from_name", connector_name)
    names = (spark.read.table(SENDERS_TABLE)
             .filter((F.lower(F.col("mailbox")).isin(MAILBOXES)) & F.col("from_name").isNotNull()
                     & (F.trim(F.col("from_name")) != ""))
             .select("outlook_message_id", F.col("from_name").alias("graph_name"))
             .dropDuplicates(["outlook_message_id"]))
    return (df.join(names, "outlook_message_id", "left")
            .withColumn("from_name", F.coalesce(F.col("graph_name"), connector_name)).drop("graph_name"))


def _bronze_columns(att):
    """att: one row per attachment with outlook_message_id, from_addr, sender, subject, received_at, att_idx and
    a = struct(content, attachment_id, file_name, mime_type, size). -> the email_attachments columns."""
    file_name = F.coalesce(F.nullif(F.trim(F.col("a.file_name")), F.lit("")),
                           F.concat(F.lit("attachment-"), F.col("att_idx").cast("string")))
    mime = F.lower(F.trim(F.col("a.mime_type")))
    aid = _safe(F.col("a.attachment_id"))
    # Graph attachment ids are long (they embed the message id): use them when short, else a stable hash.
    att_dir = (F.when(aid.isNull() | (aid == ""), F.col("att_idx").cast("string"))
                .when(F.length(aid) <= 100, aid)
                .otherwise(F.substring(F.sha2(F.col("a.attachment_id"), 256), 1, 16)))
    return _with_sender_names(att).select(
        F.col("outlook_message_id").alias("email_id"),
        "from_name",
        F.lower(F.trim(F.col("from_addr"))).alias("from_email"),
        "subject",
        "received_at",
        file_name.alias("attachment_filename"),
        # Graph sometimes reports a generic type; then use the file extension (as 01_bronze.sql does).
        F.when(mime.isNull() | (mime == "") | (mime == "application/octet-stream"), _mime_from_ext(file_name))
         .otherwise(mime).alias("attachment_mime_type"),
        F.coalesce(F.col("a.size"), F.length(F.col("a.content")).cast("bigint")).alias("attachment_size_bytes"),
        F.col("a.content").alias("content"),
        F.base64(F.col("a.content")).alias("content_base64"),
        F.concat_ws("/", F.lit(EXPORT_ROOT), F.substring(F.sha2(F.col("outlook_message_id"), 256), 1, 16),
                    att_dir, _safe(file_name)).alias("source_path"),
        F.current_timestamp().alias("ingested_at"),
    )


@dlt.table(
    name="email_attachments",
    comment="Bronze: one row per inbound email attachment, from the Lakeflow Connect Outlook connector "
            f"({SOURCE_TABLE}, mailbox {MAILBOX}); inline images skipped; attached emails fetched from Graph "
            "(outlook_item_attachments) arrive through the flow `email_attachments_fetched`.",
    table_properties={"quality": "bronze"},
)
def email_attachments():
    msgs = (
        spark.readStream.option("readChangeFeed", "true").table(SOURCE_TABLE)
        .filter(F.lower(F.col("mailbox")).isin(MAILBOXES))          # filter BEFORE anything else
        .filter(F.col("_change_type") == "insert")                     # new messages only; updates ignored
        .select(F.lower(F.col("mailbox")).alias("mbx"), "outlook_message_id", F.col("`from`").alias("from_addr"),
                "sender", "subject", "received_at", "attachments")      # CDF metadata columns dropped here
        .dropDuplicates(["mbx", "outlook_message_id"])                 # a re-inserted message is read once
        .drop("mbx")
    )
    att = (
        msgs.select("*", F.posexplode("attachments").alias("att_idx", "a"))   # no attachments -> no rows
        .filter(~F.coalesce(F.col("a.is_inline"), F.lit(False)))
        # Content-less items/files come through email_attachments_fetched once Graph returned them (else never).
        .filter(~_fetchable(F.col("a")))
    )
    return _bronze_columns(att)


# Attachments fetched from Graph: streamed from outlook_item_attachments' change feed (a row's content is set once,
# by an insert or by the update of a failed row that a retry fixed), joined to the connector table (static) for the
# message's metadata. Each attachment reaches Bronze exactly once, when its fetch succeeds — no matter whether that
# was before or after its message was streamed above (the main flow never emits these attachments).
if _table_exists(ITEMS_TABLE):
    @dlt.append_flow(target="email_attachments", name="email_attachments_fetched",
                     comment="Attachments the connector stored without content, fetched from Microsoft Graph.")
    def email_attachments_fetched():
        fetched = (
            spark.readStream.option("readChangeFeed", "true").table(ITEMS_TABLE)
            .filter(F.col("_change_type").isin("insert", "update_postimage"))
            .filter((F.lower(F.col("mailbox")).isin(MAILBOXES)) & F.col("mime_content").isNotNull())
            .select("outlook_message_id", "attachment_id", "attachment_kind", "file_name", "mime_type", "size",
                    "mime_content")
            .dropDuplicates(["outlook_message_id", "attachment_id"])
        )
        meta = (spark.read.table(SOURCE_TABLE)
                .filter(F.lower(F.col("mailbox")).isin(MAILBOXES))
                .select("outlook_message_id", F.col("`from`").alias("from_addr"), "sender", "subject", "received_at")
                .dropDuplicates(["outlook_message_id"]))
        is_item = F.lower(F.col("attachment_kind")).like("%item%")
        name = F.coalesce(F.nullif(F.trim(F.col("file_name")), F.lit("")), F.lit("attached-message"))
        # An attached email is MIME text: message/rfc822, file name ending .eml (Silver unpacks it).
        name = F.when(is_item & ~F.lower(name).endswith(".eml"), F.concat(name, F.lit(".eml"))).otherwise(name)
        att = fetched.join(meta, "outlook_message_id", "left").select(
            "outlook_message_id", "from_addr", "sender", "subject", "received_at",
            F.lit(None).cast("int").alias("att_idx"),
            F.struct(F.col("mime_content").alias("content"), "attachment_id", name.alias("file_name"),
                     F.when(is_item, F.lit(EML_MIME)).otherwise(F.col("mime_type")).alias("mime_type"),
                     F.length("mime_content").cast("bigint").alias("size")).alias("a"))
        return _bronze_columns(att)


# mail_source = both: ALSO read the files dropped in the Volume's inbound_docs/ folder (same columns and mapping as
# 01_bronze.sql), so a demo can mix real mailbox mail with example documents. A separate append flow with its own
# checkpoint: adding or removing it never forces a full refresh of the mailbox flow.
if spark.conf.get("order_intake.mail_source", "outlook").strip().lower() == "both":
    INBOUND = f"/Volumes/{VCAT}/{VSCH}/{VOL}/inbound_docs"
    MANIFEST = f"{CAT}.{SCH}.email_manifest"
    # inbound_via_table: the Volume's storage is not readable from the pipeline (only through the Files API), so the
    # job task 07_stage_inbound_files.py copies new files into this append-only table (binaryFile columns) first.
    VIA_TABLE = spark.conf.get("order_intake.inbound_via_table", "false").strip().lower() == "true"
    INBOUND_TABLE = f"{CAT}.{SCH}.{FETCH_PREFIX}inbound_files"

    @dlt.append_flow(target="email_attachments", name="email_attachments_volume",
                     comment="Files dropped in the Volume's inbound_docs/ folder (mail_source = both).")
    def email_attachments_volume():
        raw = (spark.readStream.table(INBOUND_TABLE) if VIA_TABLE else
               spark.readStream.format("cloudFiles").option("cloudFiles.format", "binaryFile").load(INBOUND))
        files = raw.withColumn("fname", F.element_at(F.split("path", "/"), -1))
        if _table_exists(MANIFEST):
            m = spark.read.table(MANIFEST).select(
                "email_id", "from_name", "from_email", "subject", "received_at",
                F.col("attachment_filename").alias("m_filename"), F.col("attachment_mime").alias("m_mime"))
            files = files.join(m, files.fname == m.m_filename, "left")
        else:
            files = files.select("*", *[F.lit(None).cast(t).alias(c) for c, t in [
                ("email_id", "string"), ("from_name", "string"), ("from_email", "string"), ("subject", "string"),
                ("received_at", "timestamp"), ("m_filename", "string"), ("m_mime", "string")]])
        return files.select(
            "email_id", "from_name", "from_email", "subject", F.col("received_at").cast("timestamp"),
            F.coalesce("m_filename", "fname").alias("attachment_filename"),
            F.coalesce("m_mime", _mime_from_ext(F.col("fname"))).alias("attachment_mime_type"),
            F.col("length").cast("bigint").alias("attachment_size_bytes"),
            "content", F.base64("content").alias("content_base64"),
            F.col("path").alias("source_path"), F.current_timestamp().alias("ingested_at"))
