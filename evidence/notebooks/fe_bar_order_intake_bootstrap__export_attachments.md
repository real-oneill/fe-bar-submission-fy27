# [dev <deployer>] fe_bar_order_intake_bootstrap / export_attachments (run 138106318106618, as executed, with outputs)

Notebook `a44cfc9d-8f41-4172-891d-3c7afd3f8dff`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 05 — Export Outlook attachments to the Volume (mail_source = outlook only)
With the Outlook connector as the mail source, attachments exist only as bytes in Bronze
`email_attachments`. The Review App shows source PDFs from the Volume, so this writes every Outlook
attachment to its Bronze `source_path` (`<volume>/outlook_attachments/...`) **if it is not there yet**.
Idempotent; existing files are never rewritten. With `mail_source = volume` it does nothing (the files
are already in `inbound_docs/`). Runs after the pipeline, before the review queue is built.

```python
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("volume", "landing")
dbutils.widgets.text("volume_catalog", "")    # the Volume's catalog/schema (default: the tables')
dbutils.widgets.text("volume_schema", "")
dbutils.widgets.text("mail_source", "volume")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
vcatalog = dbutils.widgets.get("volume_catalog").strip() or catalog
vschema = dbutils.widgets.get("volume_schema").strip() or schema
mail_source = dbutils.widgets.get("mail_source").strip().lower()

if mail_source not in ("outlook", "both"):
    dbutils.notebook.exit(f"mail_source={mail_source}: nothing to export (documents are already in the Volume)")
```

**Output:**

```
mail_source=volume: nothing to export (documents are already in the Volume)
```

```python
# Files API (not the /Volumes FUSE path): works even where the Volume's storage is not reachable from this compute.
import io
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

w = WorkspaceClient()
S = f"{catalog}.{schema}"
root = f"/Volumes/{vcatalog}/{vschema}/{volume}/outlook_attachments/"
src = (spark.table(f"{S}.email_attachments")
       .selectExpr("regexp_replace(source_path, '^dbfs:', '') AS path"))
paths = [r.path for r in src.filter(src.path.startswith(root)).distinct().collect()]


def exists(path):
    try:
        w.files.get_metadata(path)
        return True
    except NotFound:
        return False


missing = [p for p in paths if not exists(p)]
print(f"{len(paths)} Outlook attachments in Bronze; {len(missing)} not yet in {root}")

written = 0
if missing:
    # Fetch in batches so only the missing attachments' bytes are pulled to the driver.
    for i in range(0, len(missing), 200):
        batch = missing[i:i + 200]
        rows = (spark.table(f"{S}.email_attachments")
                .selectExpr("regexp_replace(source_path, '^dbfs:', '') AS path", "content")
                .where("path IN (" + ", ".join("'" + p.replace("'", "''") + "'" for p in batch) + ")")
                .dropDuplicates(["path"])
                .collect())
        for r in rows:
            if r.content is None:
                print("skipped (no content):", r.path)
                continue
            w.files.upload(r.path, io.BytesIO(bytes(r.content)), overwrite=True)   # one request: never half-written
            written += 1
print(f"Exported {written} attachment(s) to {root}")
```

**Output:**

```
ERROR: Command skipped
```

