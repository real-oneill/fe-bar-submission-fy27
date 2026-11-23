# [dev <deployer>] fe_bar_order_intake_run / stage_inbound_files (run 362893771754524, as executed, with outputs)

Notebook `338b0ba5-2c9c-42fb-88d9-303c814b9274`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 07 — Stage inbound files into a Delta table (`inbound_via_table = true` only)
Where the Volume's storage is not reachable from serverless compute directly (only through the Files API —
a Volume in another catalog), Auto Loader can't list `inbound_docs/`. This task copies every file there that
is not staged yet into `<fetch_table_prefix>inbound_files` (the columns `binaryFile` returns: `path`,
`modificationTime`, `length`, `content`), and Bronze streams that table instead of the folder. Append only
(a streaming source); each path is staged once, as Auto Loader reads each file once. `path` keeps the
Volume path (`dbfs:/Volumes/...`), so the review app serves the file from the Volume as before.
No-op unless `inbound_via_table = true` and `mail_source` reads `inbound_docs/` (`both`).

```python
for k, d in [("catalog", "main"), ("schema", "order_intake"), ("volume", "landing"), ("volume_catalog", ""),
             ("volume_schema", ""), ("mail_source", "volume"), ("inbound_via_table", "false"),
             ("fetch_table_prefix", "")]:
    dbutils.widgets.text(k, d)
catalog, schema, volume = (dbutils.widgets.get(k) for k in ("catalog", "schema", "volume"))
vcatalog = dbutils.widgets.get("volume_catalog").strip() or catalog
vschema = dbutils.widgets.get("volume_schema").strip() or schema
mail_source = dbutils.widgets.get("mail_source").strip().lower()
via_table = dbutils.widgets.get("inbound_via_table").strip().lower() == "true"
if not via_table or mail_source != "both":
    dbutils.notebook.exit(f"inbound_via_table={via_table}, mail_source={mail_source}: nothing to stage")
```

**Output:**

```
inbound_via_table=False, mail_source=volume: nothing to stage
```

```python
import datetime as dt
import io
from databricks.sdk import WorkspaceClient
from pyspark.sql import types as T

w = WorkspaceClient()
TABLE = f"{catalog}.{schema}.{dbutils.widgets.get('fetch_table_prefix').strip()}inbound_files"
ROOT = f"/Volumes/{vcatalog}/{vschema}/{volume}/inbound_docs"
SCHEMA = T.StructType([T.StructField("path", T.StringType()), T.StructField("modificationTime", T.TimestampType()),
                       T.StructField("length", T.LongType()), T.StructField("content", T.BinaryType())])
spark.sql(f"CREATE TABLE IF NOT EXISTS {TABLE} (path STRING, modificationTime TIMESTAMP, length BIGINT, "
          f"content BINARY) COMMENT 'Files of {ROOT}/ copied through the Files API (07_stage_inbound_files); "
          f"Bronze streams this table when inbound_via_table = true. Append only.'")


def walk(d):
    for e in w.files.list_directory_contents(d):
        if e.is_directory:
            yield from walk(e.path.rstrip("/"))
        else:
            yield e


# each path once, as Auto Loader does by default (a file rewritten in place is not read again)
staged = {r.path for r in spark.table(TABLE).select("path").collect()}
new = [e for e in walk(ROOT) if "dbfs:" + e.path not in staged]
print(f"{len(staged)} staged rows; {len(new)} new or changed file(s) in {ROOT}")

for i in range(0, len(new), 50):                    # small batches: bytes are held on the driver
    rows = [("dbfs:" + e.path, dt.datetime.fromtimestamp(e.last_modified / 1000, tz=dt.timezone.utc), e.file_size,
             w.files.download(e.path).contents.read()) for e in new[i:i + 50]]
    spark.createDataFrame(rows, SCHEMA).write.mode("append").saveAsTable(TABLE)
print(f"Staged {len(new)} file(s) into {TABLE}")
```

**Output:**

```
ERROR: Command skipped
```

