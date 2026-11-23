# [dev <deployer>] fe_bar_order_intake_bootstrap / load_corpus (run 1039905860731884, as executed, with outputs)

Notebook `79f90b8c-4970-4696-83af-879f6060d0bf`, exported 2026-11-23 18:08 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## FE Bar 00: Load the Maison Solenne corpus into the accelerator
The accelerator (`src/pipeline`, `src/setup`, `app/`) is unchanged production code. This task is the only glue it
needs to run on the **fictional** Brick-by-Brick corpus (`corpus/`, synced with the bundle):

1. **Documents**: copies every file in `corpus/documents/<channel>/` into the Volume's `inbound_docs/` folder
   (flat; names are unique `DOC-xxxxx.<ext>`). Bronze's Auto Loader picks them up.
2. **`email_manifest`**: one row per file from `documents/_arrivals.csv`, which holds only what the inbox or EDI gateway
   knows on arrival (sender, subject, time). It contains **no answers**.
3. **Master data** in the accelerator's demo-mode shape, built from `corpus/master_data`:
   `customer_master` (one row per name variant), `product_master` (GTIN as `ean`), `retailer_sku_map`
   (retailer item cross-reference, deliberately only about 85% complete), `retailer_rules`, `region_map`.
4. **Answer key and reference tables** (`gt_*`, `md_*`) for the evaluation (`10_evaluate.py`) and the Genie space.
   The pipeline never reads them.

Idempotent: files already in the Volume are skipped, and tables are overwritten.

```python
dbutils.widgets.text("catalog", "evan_aws_01_catalog")
dbutils.widgets.text("schema", "fe_bar_fy27")
dbutils.widgets.text("volume", "landing")
dbutils.widgets.text("corpus_path", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
corpus = dbutils.widgets.get("corpus_path").rstrip("/")
S = f"{catalog}.{schema}"
inbound = f"/Volumes/{catalog}/{schema}/{volume}/inbound_docs"
print("corpus:", corpus, "->", inbound)
```

**Output:**

```
corpus: /Workspace/Users/<deployer>/.bundle/fe-bar-submission-fy27/fevm/files/corpus -> /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs
```

### 1. Documents to the inbound folder

```python
import os, shutil
import pandas as pd

os.makedirs(inbound, exist_ok=True)
existing = set(os.listdir(inbound))
copied, skipped = 0, 0
docs_root = f"{corpus}/documents"
for channel in sorted(os.listdir(docs_root)):
    cdir = f"{docs_root}/{channel}"
    if not os.path.isdir(cdir):
        continue
    for name in sorted(os.listdir(cdir)):
        if name in existing:
            skipped += 1
            continue
        shutil.copyfile(f"{cdir}/{name}", f"{inbound}/{name}")
        copied += 1
print(f"copied {copied} file(s), {skipped} already present; inbound_docs now holds {len(os.listdir(inbound))} files")
```

**Output:**

```
copied 0 file(s), 184 already present; inbound_docs now holds 184 files
```

### 2. email_manifest (arrival metadata only)

```python
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv", "txt": "text/plain", "edi": "text/plain", "json": "text/plain",
        "eml": "message/rfc822", "png": "image/png", "jpg": "image/jpeg"}
arr = pd.read_csv(f"{docs_root}/_arrivals.csv", dtype=str)
arr["attachment_filename"] = arr["relative_path"].str.split("/").str[-1]
arr["ext"] = arr["attachment_filename"].str.rsplit(".", n=1).str[-1].str.lower()
manifest = pd.DataFrame({
    "email_id": arr["doc_id"],
    "doc_id": arr["doc_id"],
    "from_name": arr["sender"],
    "from_email": arr["sender"].where(arr["sender"].str.contains("@", na=False)),
    "subject": arr["subject"],
    "received_at": pd.to_datetime(arr["received_at"], utc=True).dt.tz_localize(None),
    "attachment_filename": arr["attachment_filename"],
    "attachment_mime": arr["ext"].map(MIME),
    "volume_path": inbound + "/" + arr["attachment_filename"],
})
(spark.createDataFrame(manifest).selectExpr(*[f"CAST({c} AS {t}) {c}" for c, t in spark.table(f"{S}.email_manifest").dtypes])
     .write.mode("overwrite").saveAsTable(f"{S}.email_manifest"))
print(f"email_manifest: {len(manifest)} rows")
display(spark.table(f"{S}.email_manifest").limit(5))
```

**Output:**

```
email_manifest: 184 rows
```

| email_id | doc_id | from_name | from_email | subject | received_at | attachment_filename | attachment_mime | volume_path |
|---|---|---|---|---|---|---|---|---|
| DOC-00001 | DOC-00001 | AS2:HALCYONFINCH |  | X12 850 ICN 926394 | 2026-09-14T07:18:50.000Z | DOC-00001.edi | text/plain | /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs/DOC-00001.edi |
| DOC-00002 | DOC-00002 | AS2:HALCYONFINCH |  | X12 850 ICN 190707 | 2026-09-20T06:15:02.000Z | DOC-00002.edi | text/plain | /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs/DOC-00002.edi |
| DOC-00003 | DOC-00003 | AS2:HALCYONFINCH |  | X12 850 ICN 721121 | 2026-09-19T08:08:21.000Z | DOC-00003.edi | text/plain | /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs/DOC-00003.edi |
| DOC-00004 | DOC-00004 | AS2:HALCYONFINCH |  | X12 850 ICN 699198 | 2026-09-16T17:34:13.000Z | DOC-00004.edi | text/plain | /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs/DOC-00004.edi |
| DOC-00005 | DOC-00005 | AS2:HALCYONFINCH |  | X12 850 ICN 648684 | 2026-09-18T11:31:55.000Z | DOC-00005.edi | text/plain | /Volumes/evan_aws_01_catalog/fe_bar_fy27/landing/inbound_docs/DOC-00005.edi |

### 3. Master data in the accelerator's (demo-mode) shape

```python
md = f"{corpus}/master_data"
cust = pd.read_csv(f"{md}/customer_master.csv", dtype=str)
prod = pd.read_csv(f"{md}/product_master.csv", dtype=str)
xref = pd.read_csv(f"{md}/retailer_item_xref.csv", dtype=str)
rules = pd.read_csv(f"{md}/retailer_rules.csv", dtype=str)

# customer_master: one row per spelling (canonical name + every name variant) -> sold-to
rows = []
for _, c in cust.iterrows():
    for v in dict.fromkeys([c.customer_name] + str(c.name_variants or "").split("|")):
        if v and v.strip():
            rows.append((c.sold_to_id, c.customer_name, v.strip(), c.country, c.currency.split("|")[0]))
cm = spark.createDataFrame(rows, "sap_sold_to string, retailer_canonical string, name_variant string, country string, currency string")
cm.write.mode("overwrite").saveAsTable(f"{S}.customer_master")

pm = pd.DataFrame({"material_no": prod.material_id, "ean": prod.gtin, "brand": prod.brand,
                   "product_name": prod.description, "size_desc": prod["size"],
                   "list_price_gbp": None, "list_price_eur": None, "list_price_usd": prod.list_price_usd.astype(float)})
spark.createDataFrame(pm, spark.table(f"{S}.product_master").schema).write.mode("overwrite").saveAsTable(f"{S}.product_master")

sm = pd.DataFrame({"retailer_canonical": xref.retailer, "retailer_sku": xref.retailer_item_id, "material_no": xref.material_id})
spark.createDataFrame(sm, spark.table(f"{S}.retailer_sku_map").schema).write.mode("overwrite").saveAsTable(f"{S}.retailer_sku_map")

rr = pd.DataFrame({"retailer_canonical": rules.retailer, "locale": None, "language": None, "sku_field_name": None,
                   "qty_before_sku": None, "orders_by": rules.rule_type,
                   "quirk_notes": rules.rule_id + ": " + rules.rule_text})
spark.createDataFrame(rr, spark.table(f"{S}.retailer_rules").schema).write.mode("overwrite").saveAsTable(f"{S}.retailer_rules")

# region_map: the corpus' countries -> sales regions shown in the Review App and the Genie space
region_rows = [("US", "North America"), ("FR", "France"), ("IT", "Italy"), ("DE", "DACH"), ("AT", "DACH"),
               ("CH", "DACH"), ("GB", "UK & Ireland"), ("UK", "UK & Ireland"), ("IE", "UK & Ireland"),
               ("AE", "Middle East")]
spark.createDataFrame(region_rows, "country string, region string").write.mode("overwrite").saveAsTable(f"{S}.region_map")
# region_access: the deployer's demo group sees every region (RLS is off in the fevm target)
spark.createDataFrame([("oi-all-regions", "*")], "group_name string, region string").write.mode("overwrite").saveAsTable(f"{S}.region_access")

for t in ["customer_master", "product_master", "retailer_sku_map", "retailer_rules", "region_map"]:
    print(f"{t}: {spark.table(f'{S}.{t}').count()} rows")
```

**Output:**

```
customer_master: 53 rows
product_master: 163 rows
retailer_sku_map: 285 rows
retailer_rules: 17 rows
region_map: 10 rows
```

### 4. Answer key and reference tables (evaluation + Genie only; the pipeline never reads them)

```python
def load_csv(path, table, comment):
    df = pd.read_csv(path, dtype=str, keep_default_na=False).replace({"": None})
    spark.createDataFrame(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{S}.{table}")
    spark.sql(f"COMMENT ON TABLE {S}.{table} IS '{comment}'")
    print(f"{table}: {len(df)} rows")

gt = f"{corpus}/ground_truth"
load_csv(f"{gt}/manifest.csv", "gt_manifest", "Answer key: one row per corpus document (channel, retailer, format, complexity 1-4, PO and line counts).")
load_csv(f"{gt}/headers.csv", "gt_headers", "Answer key: one row per purchase order (intended PO number, sold-to, ship-to after reroute rules, dates, currency, duplicates, amendments).")
load_csv(f"{gt}/lines.csv", "gt_lines", "Answer key: one row per order line (material_id or UNRESOLVABLE, quantity as written and in eaches, prices, free goods, ATP outcome).")
load_csv(f"{gt}/issues.csv", "gt_issues", "Answer key: every injected problem per document (issue_type, detail).")
load_csv(f"{md}/customer_master.csv", "md_customers", "Corpus customer master: 14 fictional retailers with country, currency, region, channel, supply plant.")
load_csv(f"{md}/product_master.csv", "md_products", "Corpus product master: 163 fictional Maison Solenne SKUs (brand, category, GTIN, list price, status, successor).")
load_csv(f"{md}/price_list.csv", "md_price_list", "Corpus contracted net prices per sold-to and material.")
load_csv(f"{md}/ship_to.csv", "md_ship_to", "Corpus ship-to locations (open/closed).")
load_csv(f"{md}/inventory_atp.csv", "md_inventory_atp", "Corpus ATP snapshot per plant and material.")
dbutils.notebook.exit(f"copied={copied} skipped={skipped} manifest={len(manifest)} customer_variants={cm.count()}")
```

**Output:**

```
copied=0 skipped=184 manifest=184 customer_variants=53
```

