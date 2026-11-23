# [dev <deployer>] fe_bar_order_intake_run / sap_masters (run 66251696678067, as executed, with outputs)

Notebook `92957242-3723-4e1b-be10-87a79cb6c5da`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 01b — SAP master data working tables (`master_source = sap`)
Refreshes small, prefixed working tables in the accelerator's schema from the SAP views in `sap_catalog`
(`db_fnd_proc.v_*`, one row per key), **restricted to the configured sales orgs and saleable materials** —
never full copies of SAP:
- `oi_sap_customers` — sold-to / ship-to candidates (KNA1 + ADRC street line 2 + KNVV sales org, currency,
  deletion/block flags, sold-to/ship-to role) with normalized match keys
- `oi_sap_partner_links` — KNVP sold-to -> ship-to / bill-to / payer (AG/WE/RE/RG) per sales org
- `oi_sap_materials` — MARA FERT/HAWA listed in MVKE for the sales orgs: 6-char prefix, EANs (MARA + MARM),
  German/English text (MAKT), sales orgs + sales status (shown, never filtered on)
- `oi_sap_region_map` — sales org + country -> SAP affiliate / market / region
- `po_rules` — per-customer missing-PO rule (created empty once; the business fills it)

Runs before the pipeline in `bootstrap` and `run_medallion`. **No-op for `master_source = demo`.**
The SQL lives in `src/lib/sap_masters.py` (shared with the Gold layer and the read-only validation).
Only counts are printed.

```python
import os
import sys

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("master_source", "demo")
dbutils.widgets.text("sap_catalog", "")
dbutils.widgets.text("sap_sales_orgs", "")
dbutils.widgets.text("material_prefix_len", "6")
dbutils.widgets.text("lib_path", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
master_source = dbutils.widgets.get("master_source").strip() or "demo"
S = f"{catalog}.{schema}"

if master_source not in ("demo", "sap"):
    raise ValueError(f"master_source must be 'demo' or 'sap', got {master_source!r}")
if master_source == "demo":
    print("master_source=demo: SAP master tables not used — nothing to do.")
    dbutils.notebook.exit("skipped (demo)")

sys.path.insert(0, dbutils.widgets.get("lib_path") or os.path.abspath(os.path.join(os.getcwd(), "..", "lib")))
import sap_masters as sm  # noqa: E402

sap_catalog = sm.check_identifier(dbutils.widgets.get("sap_catalog").strip(), "sap_catalog")
orgs = sm.parse_sales_orgs(dbutils.widgets.get("sap_sales_orgs"))
prefix_len = sm.parse_prefix_len(dbutils.widgets.get("material_prefix_len"))
print(f"SAP source {sap_catalog}.{sm.SAP_SCHEMA}, sales orgs {', '.join(orgs)}, material prefix {prefix_len}")
```

**Output:**

```
skipped (demo)
```

```python
for table, stmt in sm.materialize_statements(S, sap_catalog, orgs, prefix_len):
    spark.sql(stmt)
    print(f"{S}.{table}: {spark.table(f'{S}.{table}').count()} rows")

c = spark.sql(f"""SELECT count(DISTINCT kunnr) customers, count(DISTINCT CASE WHEN is_sold_to THEN kunnr END) sold_tos,
                         count(DISTINCT CASE WHEN is_ship_to THEN kunnr END) ship_tos
                  FROM {S}.{sm.T_CUSTOMERS}""").first()
print(f"customers {c.customers}, sold-tos {c.sold_tos}, ship-tos {c.ship_tos}")
```

**Output:**

```
ERROR: Command skipped
```

