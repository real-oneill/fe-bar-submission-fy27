# Databricks notebook source
# MAGIC %md
# MAGIC ## Setup 01b — SAP master data working tables (`master_source = sap`)
# MAGIC Refreshes small, prefixed working tables in the accelerator's schema from the SAP views in `sap_catalog`
# MAGIC (`db_fnd_proc.v_*`, one row per key), **restricted to the configured sales orgs and saleable materials** —
# MAGIC never full copies of SAP:
# MAGIC - `oi_sap_customers` — sold-to / ship-to candidates (KNA1 + ADRC street line 2 + KNVV sales org, currency,
# MAGIC   deletion/block flags, sold-to/ship-to role) with normalized match keys
# MAGIC - `oi_sap_partner_links` — KNVP sold-to -> ship-to / bill-to / payer (AG/WE/RE/RG) per sales org
# MAGIC - `oi_sap_materials` — MARA FERT/HAWA listed in MVKE for the sales orgs: 6-char prefix, EANs (MARA + MARM),
# MAGIC   German/English text (MAKT), sales orgs + sales status (shown, never filtered on)
# MAGIC - `oi_sap_region_map` — sales org + country -> SAP affiliate / market / region
# MAGIC - `po_rules` — per-customer missing-PO rule (created empty once; the business fills it)
# MAGIC
# MAGIC Runs before the pipeline in `bootstrap` and `run_medallion`. **No-op for `master_source = demo`.**
# MAGIC The SQL lives in `src/lib/sap_masters.py` (shared with the Gold layer and the read-only validation).
# MAGIC Only counts are printed.

# COMMAND ----------
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

# COMMAND ----------
for table, stmt in sm.materialize_statements(S, sap_catalog, orgs, prefix_len):
    spark.sql(stmt)
    print(f"{S}.{table}: {spark.table(f'{S}.{table}').count()} rows")

c = spark.sql(f"""SELECT count(DISTINCT kunnr) customers, count(DISTINCT CASE WHEN is_sold_to THEN kunnr END) sold_tos,
                         count(DISTINCT CASE WHEN is_ship_to THEN kunnr END) ship_tos
                  FROM {S}.{sm.T_CUSTOMERS}""").first()
print(f"customers {c.customers}, sold-tos {c.sold_tos}, ship-tos {c.ship_tos}")
