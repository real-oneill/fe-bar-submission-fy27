-- ============================================================
-- Order Intake — Lakeflow Declarative Pipeline · Phase 1: BRONZE
-- ============================================================
-- `email_attachments` is a streaming table shaped to MATCH the Lakeflow Connect
-- managed Outlook connector output (email metadata + attachment as binary/base64).
--
-- DEMO MODE (default): fed by Auto Loader (read_files, binaryFile) over the
--   `inbound_docs` folder of the configured Volume, enriched with `email_manifest`.
--   Run src/demo/generate_synthetic_corpus.py to populate the folder + manifest.
-- PRODUCTION: enable the Lakeflow Connect Outlook connector (Beta, Previews-gated).
--   It lands a managed streaming table with the SAME schema — Silver/Gold are unaffected.
--   Then either point Silver at the connector's table or replace this definition. See README.
--
-- catalog/schema are injected from the pipeline `configuration` (bundle variables). inbound_via_table (a Volume
-- the pipeline can't read directly) is supported by 01_bronze_outlook.py only (mail_source = both / outlook).
-- ============================================================

CREATE OR REFRESH STREAMING TABLE email_attachments
COMMENT "Bronze: one row per inbound email attachment (Outlook-connector-shaped)."
TBLPROPERTIES ("quality" = "bronze")
AS
SELECT
  m.email_id,
  m.from_name,
  m.from_email,
  m.subject,
  m.received_at,
  coalesce(m.attachment_filename, element_at(split(f.path, '/'), -1)) AS attachment_filename,
  -- Files not listed in email_manifest (e.g. real examples) get their type from the file extension.
  -- Keep in sync with MIME_BY_EXT in 02_silver.py / 01_bronze_outlook.py.
  coalesce(m.attachment_mime,
    CASE lower(regexp_extract(f.path, '[.]([A-Za-z0-9]+)$', 1))
      WHEN 'pdf'  THEN 'application/pdf'
      WHEN 'xlsx' THEN 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      WHEN 'xlsm' THEN 'application/vnd.ms-excel.sheet.macroEnabled.12'
      WHEN 'xls'  THEN 'application/vnd.ms-excel'
      WHEN 'csv'  THEN 'text/csv'
      WHEN 'txt'  THEN 'text/plain'
      WHEN 'edi'  THEN 'text/plain'
      WHEN 'json' THEN 'text/plain'
      WHEN 'msg'  THEN 'application/vnd.ms-outlook'
      WHEN 'eml'  THEN 'message/rfc822'
      WHEN 'png'  THEN 'image/png'
      WHEN 'jpg'  THEN 'image/jpeg'
      WHEN 'jpeg' THEN 'image/jpeg'
      WHEN 'docx' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      WHEN 'doc'  THEN 'application/msword'
      ELSE 'application/octet-stream'
    END)                                         AS attachment_mime_type,
  f.length                                       AS attachment_size_bytes,
  f.content                                      AS content,          -- raw bytes -> ai_parse_document in Silver
  base64(f.content)                              AS content_base64,   -- mirrors the connector's base64 delivery
  f.path                                         AS source_path,
  current_timestamp()                            AS ingested_at
FROM STREAM read_files(
       '/Volumes/${order_intake.volume_catalog}/${order_intake.volume_schema}/${order_intake.volume}/inbound_docs',
       format => 'binaryFile'
     ) f
LEFT JOIN ${order_intake.catalog}.${order_intake.schema}.email_manifest m
  ON element_at(split(f.path, '/'), -1) = m.attachment_filename;
