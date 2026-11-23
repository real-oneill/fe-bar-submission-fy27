# [dev <deployer>] fe_bar_order_intake_bootstrap / schema_volume (run 191863453984041, as executed, with outputs)

Notebook `491f1c17-34b3-498d-bbb6-89a68a551078`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 00 — Schema + inbound folder
Creates the target schema and ensures the `inbound_docs/` subdirectory exists inside
the **existing** Volume named by the `volume` variable.

The catalog **and the Volume must already exist** — this notebook does NOT create the
Volume (customers point the bundle at a Volume they already manage). Only the schema and
the `inbound_docs/` folder within the Volume are created here.
(Written in Python rather than plain SQL so catalog/schema/volume are parameterized via job widgets.)

```python
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("volume", "landing")
dbutils.widgets.text("volume_catalog", "")    # the Volume's catalog/schema (default: the tables')
dbutils.widgets.text("volume_schema", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
vcatalog = dbutils.widgets.get("volume_catalog").strip() or catalog
vschema = dbutils.widgets.get("volume_schema").strip() or schema

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

# Ensure the inbound_docs folder exists inside the (pre-existing) Volume. Creating a directory inside a Volume does
# NOT create the Volume itself. Through the Files API: it works even where the Volume's storage is not reachable from
# this compute (e.g. a Volume in another catalog whose storage serverless can't reach).
from databricks.sdk import WorkspaceClient
inbound_dir = f"/Volumes/{vcatalog}/{vschema}/{volume}/inbound_docs"
WorkspaceClient().files.create_directory(inbound_dir)
print(f"Ready: schema {catalog}.{schema}; inbound folder {inbound_dir}")
```

**Output:**

```
Ready: schema evan_aws_01_catalog.fe_bar_fy27; inbound folder /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs
```

