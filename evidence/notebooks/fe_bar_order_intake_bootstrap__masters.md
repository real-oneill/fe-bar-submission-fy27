# [dev <deployer>] fe_bar_order_intake_bootstrap / masters (run 942200234507859, as executed, with outputs)

Notebook `4c0740d8-b60f-47ae-83b3-b3f99330643c`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 01 — Master (tribal-knowledge) tables + SAP outbound target
Creates the lookup tables the Gold layer joins against, as **empty typed templates**. With
`master_source = sap` the customer and material mapping tables are NOT created: SAP is the only source.
Load your own data into these (see the comments / README). The pipeline resolves:
  customer name  -> `customer_master` (name variants -> SAP sold-to)
  retailer SKU   -> `retailer_sku_map` (retailer article no -> supplier material)
  EAN            -> `product_master.ean` -> supplier material
`email_manifest` maps each attachment file to a doc_id + email metadata (demo mode).
`sap_outbound` is the write target for approved orders (ORDERS05 IDoc payload).
`region_map` (country -> region) gives every order a `region` (via its customer's country);
`region_access` (Databricks group -> region, `*` = all regions) decides who sees which regions in the
Review App (published to Lakebase as `user_regions`, enforced by Postgres row-level security).
Both are seeded with an editable default only while empty — edit them freely, re-runs keep your rows.

```python
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("master_source", "demo")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
master_source = dbutils.widgets.get("master_source").strip().lower() or "demo"
S = f"{catalog}.{schema}"

ddl = {
"customer_master": """(
  sap_sold_to STRING, retailer_canonical STRING, name_variant STRING, country STRING, currency STRING
) COMMENT 'One row per retailer NAME VARIANT -> a single SAP sold-to. Add every spelling/legal name a retailer uses.'""",

"product_master": """(
  material_no STRING, ean STRING, brand STRING, product_name STRING, size_desc STRING,
  list_price_gbp DOUBLE, list_price_eur DOUBLE, list_price_usd DOUBLE
) COMMENT 'Product master keyed by supplier material number; ean used to resolve EAN-ordered lines.'""",

"retailer_sku_map": """(
  retailer_canonical STRING, retailer_sku STRING, material_no STRING
) COMMENT 'Retailer article number -> supplier material number (per retailer). The tribal-knowledge cross-reference.'""",

"retailer_rules": """(
  retailer_canonical STRING, locale STRING, language STRING, sku_field_name STRING,
  qty_before_sku BOOLEAN, orders_by STRING, quirk_notes STRING
) COMMENT 'Optional per-retailer parsing hints (e.g. retailer wording, EAN-vs-SKU ordering).'""",

"email_manifest": """(
  email_id STRING, doc_id STRING, from_name STRING, from_email STRING, subject STRING,
  received_at TIMESTAMP, attachment_filename STRING, attachment_mime STRING, volume_path STRING
) COMMENT 'DEMO: maps each file in the inbound_docs/ folder of the landing Volume to a doc_id + email metadata. In production the Outlook connector supplies email metadata directly.'""",

"sap_outbound": """(
  order_id STRING, po_number STRING, sap_sold_to STRING, customer_name STRING, order_date STRING,
  currency STRING, line_items_json STRING, approved_by STRING, approved_at TIMESTAMP, idoc_type STRING
) COMMENT 'Write target: approved orders as an ORDERS05-style IDoc payload (populated by the Review App).'""",

"region_map": """(
  country STRING, region STRING
) COMMENT 'customer_master.country -> sales region shown/filtered in the Review App. Countries not listed -> Other; orders whose customer is unresolved -> Unassigned. Seeded with a default only when empty; edit freely.'""",

"region_access": """(
  group_name STRING, region STRING
) COMMENT 'Databricks group (exact display name) -> region its members may review. region = * means all regions (admins / GSM leads). Expanded to members and published to Lakebase user_regions; Postgres RLS enforces it. Seeded with placeholder groups only when empty; replace with your groups.'""",
}

# master_source=sap resolves customers and materials from SAP only: no business-maintained mapping tables
SAP_ONLY_SKIP = {"customer_master", "retailer_sku_map"}
for name, spec in ddl.items():
    if master_source == "sap" and name in SAP_ONLY_SKIP:
        print(f"skipped (master_source=sap, SAP data only): {S}.{name}")
        continue
    spark.sql(f"CREATE TABLE IF NOT EXISTS {S}.{name} {spec}")
    print("created (if absent):", f"{S}.{name}")

# ---- editable defaults (only into empty tables, so edits survive re-runs) ----
SEEDS = {
    "region_map": [("DE", "DACH"), ("AT", "DACH"), ("CH", "DACH"),
                   ("ES", "Iberia"), ("PT", "Iberia"),
                   ("AE", "Middle East"), ("SA", "Middle East"), ("KW", "Middle East"), ("QA", "Middle East"),
                   ("IL", "Middle East"),
                   ("GB", "UK & Ireland"), ("UK", "UK & Ireland"), ("IE", "UK & Ireland")],
    # Placeholder group names — create these groups (or put your own names here). '*' = every region.
    "region_access": [("oi-region-dach", "DACH"), ("oi-region-iberia", "Iberia"),
                      ("oi-region-middle-east", "Middle East"), ("oi-region-uk-ireland", "UK & Ireland"),
                      ("oi-region-other", "Other"), ("oi-all-regions", "*")],
}
for name, rows in SEEDS.items():
    if spark.table(f"{S}.{name}").limit(1).count() == 0:
        spark.createDataFrame(rows, spark.table(f"{S}.{name}").schema).write.mode("append").saveAsTable(f"{S}.{name}")
        print(f"seeded {S}.{name} with {len(rows)} default rows")

if master_source == "sap":
    dbutils.notebook.exit("master_source=sap: customers and materials come from SAP; nothing to load")
print("\nLoad your master data with INSERT/COPY INTO/MERGE, e.g.:")
print(f"  INSERT INTO {S}.customer_master VALUES ('100100','Halcyon & Finch','HALCYON AND FINCH','US','USD');")
```

**Output:**

```
created (if absent): evan_aws_01_catalog.fe_bar_fy27.customer_master
created (if absent): evan_aws_01_catalog.fe_bar_fy27.product_master
created (if absent): evan_aws_01_catalog.fe_bar_fy27.retailer_sku_map
created (if absent): evan_aws_01_catalog.fe_bar_fy27.retailer_rules
created (if absent): evan_aws_01_catalog.fe_bar_fy27.email_manifest
created (if absent): evan_aws_01_catalog.fe_bar_fy27.sap_outbound
created (if absent): evan_aws_01_catalog.fe_bar_fy27.region_map
created (if absent): evan_aws_01_catalog.fe_bar_fy27.region_access

Load your master data with INSERT/COPY INTO/MERGE, e.g.:
  INSERT INTO evan_aws_01_catalog.fe_bar_fy27.customer_master VALUES ('100100','Halcyon & Finch','HALCYON AND FINCH','US','USD');
```

