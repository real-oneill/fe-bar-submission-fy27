"""End-to-end (local Spark, synthetic data): the REAL src/pipeline/03_gold.py purchase_orders in master_source=sap,
then the REAL src/setup/03_build_review_queue.py in sap mode on its output. dlt / mlflow / dbutils are stubbed;
SQL runs unchanged on Spark (except CREATE OR REPLACE TABLE -> drop + CREATE, local Spark has no Delta)."""
import json
import os
import sys
import types

import pytest

from test_sap_masters import load_synthetic_sap

ROOT = os.path.join(os.path.dirname(__file__), "..")
LIB = os.path.join(ROOT, "src", "lib")


class _SparkProxy:
    """Real local Spark; CREATE OR REPLACE TABLE x AS -> DROP + CREATE (no Delta locally)."""
    def __init__(self, spark):
        self._s = spark

    def sql(self, q):
        head = q.lstrip()
        if head.startswith("CREATE OR REPLACE TABLE"):
            name = head.split()[4]
            self._s.sql(f"DROP TABLE IF EXISTS {name}")
            q = head.replace("CREATE OR REPLACE TABLE", "CREATE TABLE", 1)
        return self._s.sql(q)

    def __getattr__(self, n):
        return getattr(self._s, n)


def _stub_modules(spark):
    tables = {}
    dlt = types.ModuleType("dlt")

    def table(**kw):
        def deco(f):
            tables[kw["name"]] = f
            return f
        return deco
    dlt.table, dlt.append_flow = table, table
    dlt.read = lambda name: spark.table(f"t_{name}")
    mlflow = types.ModuleType("mlflow")
    mlflow.set_registry_uri = lambda *a: None
    genai = types.ModuleType("mlflow.genai")

    class PV:
        template, response_format, version = "Extract: {{document}}", {"type": "json_schema"}, 1
    genai.load_prompt = lambda uri: PV()
    mlflow.genai = genai
    sys.modules.update({"dlt": dlt, "mlflow": mlflow, "mlflow.genai": genai})
    return tables


ORDERS_JSON = {"orders": [
    {"po_number": "PO-1001", "customer_name": "Parfümerie Alpha GmbH", "customer_number": None,
     "ship_to": "Alpha Filiale Nord, Nordweg 5, 54321 Nordstadt", "currency": "USD", "header_confidence": 0.9,
     "line_items": [{"line_no": 1, "material_or_sku": "AB12CD0000", "quantity": 3.0, "line_confidence": 0.9},
                    {"line_no": 2, "material_or_sku": "4000000000024", "quantity": 1.0, "line_confidence": 0.9},
                    {"line_no": 3, "material_or_sku": "AB12CD", "quantity": 2.0, "line_confidence": 0.9}]},
    {"po_number": None, "customer_name": "Beta Drogerie", "customer_number": None,
     "ship_to": "Hauptplatz 2, 8010 Graz", "currency": None, "header_confidence": 0.9,
     "line_items": [{"line_no": 1, "material_or_sku": "ZZ99ZZ0000", "quantity": 5.0, "line_confidence": 0.9}]},
]}


@pytest.fixture(scope="module")
def env(local_spark):
    s = local_spark
    load_synthetic_sap(s)
    sys.path.insert(0, LIB)
    import sap_masters as sm
    gold_src = open(os.path.join(ROOT, "src", "pipeline", "03_gold.py")).read()
    orders_ddl = gold_src.split("_ORDERS_DDL = (")[1].split(")\n")[0]
    orders_ddl = "".join(json.loads(f"[{orders_ddl.strip().replace(chr(10), ',')}]"))
    checks_ddl = gold_src.split("_CHECKS_DDL = (")[1].split(")\n")[0]
    checks_ddl = "".join(json.loads(f"[{checks_ddl.strip().replace(chr(10), ',')}]"))
    checks = {"method": "text", "expected_lines": None, "extracted_lines": 4, "orders": [
        {"idx": 0, "po_issue": None, "po_in_source": True, "customer_is_supplier": False, "qty_col_resolved": False,
         "qty_letter": None, "qty_letter_derived": False,
         "lines": [{"idx": i, "sku_in_source": True, "qty_grounded": True, "drop": False} for i in range(3)]},
        {"idx": 1, "po_issue": "missing", "po_in_source": False, "customer_is_supplier": False,
         "qty_col_resolved": False, "qty_letter": None, "qty_letter_derived": False,
         "lines": [{"idx": 0, "sku_in_source": True, "qty_grounded": True, "drop": False}]}]}
    s.sql(f"""CREATE OR REPLACE TEMP VIEW t_extracted_parsed AS SELECT 'e1' email_id, 'po.pdf' attachment_filename,
              'dbfs:/Volumes/c/s/v/inbound_docs/po.pdf' source_path, TIMESTAMP'2026-10-01 10:00:00' received_at,
              0.95D parse_confidence, false parse_truncated, 'h' content_hash, CAST(NULL AS STRING) duplicate_of,
              from_json('{json.dumps(ORDERS_JSON).replace("'", "''")}', '{orders_ddl}') po, 'ok' extraction_status,
              CAST(NULL AS STRING) ai_error, '' raw_response""")
    s.sql(f"""CREATE OR REPLACE TEMP VIEW t_extraction_checks AS SELECT 'e1' email_id, 'po.pdf' attachment_filename,
              'dbfs:/Volumes/c/s/v/inbound_docs/po.pdf' source_path, from_json('{json.dumps(checks)}', '{checks_ddl}') checks""")
    for name, ddl in [("customer_master", "sap_sold_to STRING, retailer_canonical STRING, name_variant STRING, country STRING, currency STRING"),
                      ("retailer_sku_map", "retailer_canonical STRING, retailer_sku STRING, material_no STRING"),
                      ("email_manifest", "email_id STRING, doc_id STRING, from_name STRING, from_email STRING, subject STRING, received_at TIMESTAMP, attachment_filename STRING, attachment_mime STRING, volume_path STRING"),
                      ("region_map", "country STRING, region STRING")]:
        s.sql(f"DROP TABLE IF EXISTS default.{name}")
        s.sql(f"CREATE TABLE default.{name} ({ddl})")
    s.sql("INSERT INTO default.region_map VALUES ('DE', 'DACH')")
    s.sql("DROP TABLE IF EXISTS default.po_rules")
    s.sql(f"CREATE TABLE default.po_rules {sm.PO_RULES_DDL.split(' COMMENT ')[0]}")
    s.sql("INSERT INTO default.po_rules VALUES ('200002', 'generate', 'WEB-{date}')")
    for k, v in {"order_intake.catalog": "spark_catalog", "order_intake.schema": "default",
                 "order_intake.master_source": "sap", "order_intake.sap_sales_orgs": "4160,4020",
                 "order_intake.material_prefix_len": "6", "order_intake.lib_path": LIB,
                 "order_intake.extraction_mode": "ai_query"}.items():
        s.conf.set(k, v)
    tables = _stub_modules(s)
    g = {"__name__": "gold", "spark": s}
    exec(compile(gold_src, "03_gold.py", "exec"), g)
    s.sql("""CREATE OR REPLACE TEMP VIEW t_email_attachments AS SELECT 'dbfs:/Volumes/c/s/v/inbound_docs/po.pdf' source_path,
              'po.pdf' attachment_filename, CAST(NULL AS STRING) from_name, 'buyer@beta-drogerie.at' from_email,
              'Bestellung' subject""")
    s.sql("""CREATE OR REPLACE TEMP VIEW t_parsed_attachments AS SELECT 'dbfs:/Volumes/c/s/v/inbound_docs/po.pdf' source_path,
              'po.pdf' attachment_filename, 'text' parsed_content""")
    for name in ("oi_order_customers_doc", "oi_customer_hints", "oi_order_customers", "oi_line_materials"):
        tables[name]().createOrReplaceTempView(f"t_{name}")
    po = tables["purchase_orders"]()
    po.write.mode("overwrite").saveAsTable("default.purchase_orders")
    s.table("t_extracted_parsed").write.mode("overwrite").saveAsTable("default.extracted_parsed")
    s.sql("""SELECT email_id, attachment_filename, 'application/pdf' attachment_mime_type, 'x@y' from_email, 's' subject,
                    received_at, source_path, 'ai_parse_document' parse_method, 'text' parsed_content,
                    parse_confidence, parse_truncated FROM t_extracted_parsed""") \
        .write.mode("overwrite").saveAsTable("default.parsed_attachments")
    return s


def test_gold_sap_mode(env):
    rows = env.table("default.purchase_orders").collect()
    o0 = [r for r in rows if r.order_idx == 0]
    o1 = [r for r in rows if r.order_idx == 1]
    assert len(o0) == 3 and len(o1) == 1
    a = o0[0]
    assert a.resolved_sap_sold_to == "0000100001" and a.sap_sales_org == "4160" and a.sap_currency == "EUR"
    assert a.ship_to_check == "ok" and a.sap_ship_to == "0000100002"
    by_line = {r.li_idx: r for r in o0}
    assert (by_line[0].sku_resolve_method, by_line[0].resolved_material_no) == ("exact", "AB12CD0000")
    assert by_line[1].material_issue == "ean_ambiguous" and not by_line[1].sku_resolved
    assert (by_line[2].sku_resolve_method, by_line[2].resolved_material_no) == ("prefix", "AB12CD")
    r = a.review_reasons
    assert "Order currency USD differs from SAP (EUR)" in r
    assert "1 EAN(s) match several materials" in r
    assert "1 material prefix(es) match several materials — SAP will resolve" in r
    assert by_line[1].line_needs_review and not by_line[0].line_needs_review
    b = o1[0]
    assert b.resolved_sap_sold_to == "0000200002" and b.sap_sales_org == "4020"
    assert b.po_generated and b.po_number == "WEB-20261001" and b.po_ok      # customer rule: generate
    assert "Customer PO number generated by the PO rule for this customer: WEB-20261001" in b.review_reasons
    assert "1 material(s) not found in SAP" in b.review_reasons
    assert 0 < a.order_confidence <= 1


def test_review_queue_sap_mode(env):
    class W:
        v = {"catalog": "spark_catalog", "schema": "default", "master_source": "sap", "lib_path": LIB}

        def text(self, k, d):
            self.v.setdefault(k, d)

        def get(self, k):
            return self.v[k]
    dbutils = types.SimpleNamespace(widgets=W())
    src = open(os.path.join(ROOT, "src", "setup", "03_build_review_queue.py")).read()
    exec(compile(src, "03_build_review_queue.py", "exec"),
         {"__name__": "queue", "spark": _SparkProxy(env), "dbutils": dbutils, "print": lambda *a, **k: None})
    q = {r.customer_number: r for r in env.table("default.review_orders").collect()}
    a, b = q["0000100001"], q["0000200002"]
    assert (a.sales_org, a.currency, a.region) == ("4160", "EUR", "DACH")      # region_map wins
    assert (b.sales_org, b.region) == ("4020", "DAC")                          # else the SAP affiliate
    assert a.sap_ship_to == "0000100002" and a.ship_to_check == "ok"
    lines = json.loads(a.line_items_json)
    assert {l["sku_resolve_method"] for l in lines} == {"exact", "none", "prefix"}
