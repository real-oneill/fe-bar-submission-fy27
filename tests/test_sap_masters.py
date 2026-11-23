"""Tests for src/lib/sap_masters.py — pure Python + the generated SQL on a local Spark session over SYNTHETIC
SAP-shaped tables (no customer data).

Run:  python -m pytest tests            (needs `pyspark` with a local JVM, e.g. pyspark 4.x + Java 17/21;
                                          the Spark tests are skipped when no local Spark session can start)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "lib"))
import sap_masters as sm  # noqa: E402

ORGS = ["4160", "4020"]


# ------------------------------------------------------------------------------------------- pure Python
def test_parse_sales_orgs():
    assert sm.parse_sales_orgs(" 4160, 4020,4160 ,") == ["4160", "4020"]
    with pytest.raises(ValueError):
        sm.parse_sales_orgs("")
    with pytest.raises(ValueError):
        sm.parse_sales_orgs("4160; DROP TABLE x")


def test_parse_prefix_len():
    assert sm.parse_prefix_len("6") == 6
    with pytest.raises(ValueError):
        sm.parse_prefix_len("2")


def test_identifiers_are_checked():
    with pytest.raises(ValueError):
        sm.check_identifier("cat`; x")
    with pytest.raises(ValueError):
        sm.check_client("1OO")


def test_norm_name():
    assert sm.norm_name("Parfümerie Muster GmbH & Co. KG") == "parfuemerie muster"
    assert sm.norm_name("PARFÜMERIE MUSTER GMBH") == "parfuemerie muster"
    assert sm.norm_name("Pharmacie de l'Étoile SAS") == "pharmacie de l etoile"
    assert sm.norm_name("Straße") == "strasse"
    assert sm.norm_name(None) == ""


def test_street_key():
    assert sm.street_key("Musterstraße 26") == "musterstr"
    assert sm.street_key("MUSTERSTR. 26") == "musterstr"
    assert sm.street_key("Beispielstrasse 16-20/Hof") == "beispielstr"


def test_material_prefix():
    assert sm.material_prefix("AB12CD0000") == "AB12CD"
    assert sm.material_prefix("ab-12 cd") == "AB12CD"
    assert sm.material_prefix("AB12") is None             # too short
    assert sm.material_prefix("4000000000017") is None    # EAN-13 -> EAN lookup, not a prefix


def test_name_similarity():
    assert sm.name_similarity("abc", "abc") == 1.0
    assert sm.name_similarity("", "abc") == 0.0
    assert abs(sm.name_similarity("muster", "mustr") - (1 - 1 / 6)) < 1e-9


def test_materialize_statements_use_prefixed_tables_and_keep_po_rules():
    stmts = dict(sm.materialize_statements("c.s", "sapcat", ORGS))
    assert set(stmts) == {"oi_sap_customers", "oi_sap_partner_links", "oi_sap_materials", "oi_sap_region_map", "po_rules"}
    assert stmts["po_rules"].startswith("CREATE TABLE IF NOT EXISTS")       # never overwritten
    for t in ("oi_sap_customers", "oi_sap_partner_links", "oi_sap_materials", "oi_sap_region_map"):
        assert stmts[t].startswith(f"CREATE OR REPLACE TABLE c.s.{t} ")
    sql = " ".join(stmts.values())
    assert "`sapcat`.`db_fnd_proc`.`v_customer_master`" in sql and ".c_" not in sql   # views, never c_ change logs
    assert "VKORG IN ('4160', '4020')" in sql


# ------------------------------------------------------------------------------------------- local Spark
def _df(spark, cols, rows):
    return spark.createDataFrame(rows, ", ".join(f"`{c}` string" for c in cols))


@pytest.fixture(scope="module")
def spark(local_spark):
    load_synthetic_sap(local_spark)
    return local_spark


def load_synthetic_sap(spark):
    """A tiny SAP-shaped world (client 100) + the oi_sap_* working tables built from it. Every name/number here
    is invented. Idempotent (shared by several test modules)."""
    if spark.catalog.tableExists("default.oi_sap_customers"):
        return
    spark.sql("CREATE DATABASE IF NOT EXISTS db_fnd_proc")
    t = {}
    t["v_customer_master"] = (
        ["MANDT", "KUNNR", "NAME1", "NAME2", "NAME3", "NAME4", "LAND1", "ORT01", "PSTLZ", "STRAS", "ADRNR", "KTOKD",
         "LOEVM", "AUFSD", "SPRAS", "SORTL"],
        [("100", "0000100001", "PARFÜMERIE ALPHA GMBH", "", "", "", "DE", "MUSTERSTADT", "12345", "MUSTERSTR. 1", "A1", "Z001", "", "", "D", ""),
         ("100", "0000100002", "Alpha Filiale Nord", "", "", "", "DE", "NORDSTADT", "54321", "Nordweg 5", "A2", "Z101", "", "", "D", ""),
         ("100", "0000100003", "Alpha Filiale Süd", "", "", "", "DE", "SUEDSTADT", "11111", "Suedallee 7", "A3", "Z101", "", "", "D", ""),
         ("100", "0000200001", "Beta Drogerie", "", "", "", "AT", "WIEN", "1010", "Ringstraße 9", "B1", "Z001", "", "", "D", ""),
         ("100", "0000200002", "Beta Drogerie", "", "", "", "AT", "GRAZ", "8010", "Hauptplatz 2", "B2", "Z001", "", "", "D", ""),
         ("100", "0000300001", "Gamma Zahlstelle GmbH", "", "", "", "AT", "LINZ", "4020", "Zahlweg 1", "C1", "Z003", "", "", "D", ""),
         ("100", "0000300002", "Gamma Laden Linz", "", "", "", "AT", "LINZ", "4020", "Zahlweg 1", "C2", "Z101", "", "", "D", ""),
         ("100", "0000900001", "Outside Org Customer", "", "", "", "FR", "PARIS", "75001", "Rue 1", "Z9", "Z001", "", "", "F", "")])
    t["v_address_master_customer"] = (
        ["CLIENT", "ADDRNUMBER", "NATION", "STREET", "HOUSE_NUM1", "HOUSE_NUM2", "STR_SUPPL1", "STR_SUPPL2", "STR_SUPPL3",
         "LOCATION", "BUILDING", "FLOOR", "ROOMNUMBER", "POST_CODE1", "CITY1"],
        [("100", "A1", "", "Musterstraße", "1", "", "Hinterhaus", "", "", "", "", "3", "", "12345", "MUSTERSTADT"),
         ("100", "A1", "I", "INTL", "1", "", "", "", "", "", "", "", "", "12345", "X"),    # international version: ignored
         ("100", "A2", "", "Nordweg", "5", "", "", "", "", "", "", "", "", "54321", "NORDSTADT")])
    t["v_customer_sales_org_master"] = (
        ["MANDT", "KUNNR", "VKORG", "VTWEG", "SPART", "WAERS", "LOEVM", "AUFSD"],
        [("100", k, o, "10", d, cur, "", "") for k, o, cur in [
            ("0000100001", "4160", "EUR"), ("0000100002", "4160", "EUR"), ("0000100003", "4160", "EUR"),
            ("0000200001", "4020", "EUR"), ("0000200002", "4020", "EUR"),
            ("0000300001", "4020", "EUR"), ("0000300002", "4020", "EUR"), ("0000900001", "4130", "EUR")]
         for d in ("01", "99")])
    links = [("0000100001", "4160", "AG", "0000100001"), ("0000100001", "4160", "WE", "0000100001"),
             ("0000100001", "4160", "WE", "0000100002"),
             ("0000200001", "4020", "AG", "0000200001"), ("0000200001", "4020", "WE", "0000200001"),
             ("0000200002", "4020", "AG", "0000200002"), ("0000200002", "4020", "WE", "0000200002"),
             ("0000300002", "4020", "AG", "0000300002"), ("0000300002", "4020", "WE", "0000300002"),
             ("0000300002", "4020", "RG", "0000300001"),
             ("0000100003", "4160", "AG", "0000100003"), ("0000100003", "4160", "WE", "0000100003")]
    t["v_customer_master_partner_functions"] = (
        ["MANDT", "KUNNR", "VKORG", "VTWEG", "SPART", "PARVW", "PARZA", "KUNN2"],
        [("100", k, o, "10", "99", p, "000", k2) for k, o, p, k2 in links])
    t["v_material_master"] = (
        ["MANDT", "MATNR", "MTART", "EAN11", "MEINS", "LVORM", "MATKL", "SPART", "KUNNR"],
        [("100", "AB12CD0000", "FERT", "4000000000017", "ST", "", "X1", "01", ""),
         ("100", "AB12CD0001", "FERT", "", "ST", "", "X1", "01", ""),
         ("100", "EF34GH0000", "HAWA", "4000000000024", "ST", "", "X1", "01", ""),
         ("100", "EF34GH0001", "FERT", "4000000000024", "ST", "", "X1", "01", ""),   # EAN shared by two
         ("100", "IJ56KL0000", "ROH", "4000000000031", "ST", "", "X1", "01", ""),    # raw material: excluded
         ("100", "MN78OP0000", "FERT", "", "ST", "", "X1", "01", "")])               # listed elsewhere only
    t["v_material_master_unit_of_measures"] = (
        ["MANDT", "MATNR", "MEINH", "UMREZ", "EAN11"],
        [("100", "AB12CD0001", "KAR", "6", "04000000000048")])
    t["v_material_text"] = (
        ["MANDT", "MATNR", "SPRAS", "MAKTX"],
        [("100", "AB12CD0000", "D", "Creme 50ml"), ("100", "AB12CD0000", "E", "Cream 50ml"),
         ("100", "EF34GH0000", "E", "Serum")])
    t["v_material_master_sales"] = (
        ["MANDT", "MATNR", "VKORG", "VTWEG", "VMSTA", "LVORM"],
        [("100", "AB12CD0000", "4160", "10", "", ""), ("100", "AB12CD0001", "4160", "10", "Z5", ""),
         ("100", "EF34GH0000", "4160", "10", "", ""), ("100", "EF34GH0001", "4160", "10", "", ""),
         ("100", "IJ56KL0000", "4160", "10", "", ""), ("100", "MN78OP0000", "4020", "10", "", "")])
    t["t_sales_org_geography_look_up"] = (
        ["COUNTRY", "DIVISION", "PLANT", "/BIC/ZGEOGRPHY", "OBJVERS", "/BIC/ZRMARKET", "/BIC/ZAFFLIATE",
         "/BIC/ZDPREGION", "/BIC/ZAREA", "CDC_CODE", "LOAD_TS"],
        [("DE", "", "", "4160", "A", "DAC", "DAC", "EMA", "WHD", "I", "2025-01-01"),
         ("AT", "", "", "4020", "A", "OLD", "OLD", "EMA", "WHD", "I", "2024-01-01"),
         ("AT", "", "", "4020", "A", "DAC", "DAC", "EMA", "WHD", "U", "2025-01-01")])
    for name, (cols, rows) in t.items():
        _df(spark, cols, rows).write.mode("overwrite").saveAsTable(f"db_fnd_proc.`{name}`")
    for table, stmt in sm.materialize_statements("default", "spark_catalog", ORGS):
        # local Spark (no Delta) can't REPLACE; the warehouse is fresh, so CREATE is equivalent here
        spark.sql(stmt.replace("CREATE OR REPLACE TABLE", "CREATE TABLE", 1))


def test_customers_working_table(spark):
    rows = {(r.kunnr, r.sales_org): r for r in spark.table("default.oi_sap_customers").collect()}
    assert ("0000900001", "4130") not in rows and len({k for k, _ in rows}) == 7    # only configured orgs
    a = rows[("0000100001", "4160")]
    assert a.currency == "EUR" and a.is_sold_to and a.is_ship_to
    assert a.street == "Musterstraße 1" and a.street2 == "Hinterhaus, 3"            # ADRC (national version)
    assert a.name_norm == "parfuemerie alpha" and a.street_key == "musterstr" and a.postcode_key == "12345"
    assert not rows[("0000100002", "4160")].is_sold_to and rows[("0000100002", "4160")].is_ship_to


def test_materials_working_table(spark):
    m = {r.matnr: r for r in spark.table("default.oi_sap_materials").collect()}
    assert "IJ56KL0000" not in m                                     # MTART ROH is not saleable
    assert m["AB12CD0000"].prefix == "AB12CD" and m["AB12CD0000"].text_de == "Creme 50ml"
    assert sorted(m["AB12CD0001"].eans) == ["4000000000048"]          # MARM EAN, leading zero dropped
    assert m["AB12CD0001"].sales_status == ["4160:Z5"]                 # sales status kept for display
    assert m["MN78OP0000"].sales_orgs == ["4020"]


def test_region_map_uses_latest_version(spark):
    r = {(x.sales_org, x.country): x.affiliate for x in spark.table("default.oi_sap_region_map").collect()}
    assert r == {("4160", "DE"): "DAC", ("4020", "AT"): "DAC"}


def _resolve_customers(spark, orders, overrides=None):
    _df(spark, ["doc_id", "order_idx", "customer_name", "customer_number", "ship_to"], orders) \
        .selectExpr("doc_id", "CAST(order_idx AS INT) order_idx", "customer_name", "customer_number", "ship_to",
                    "false customer_is_supplier").createOrReplaceTempView("t_orders")
    sql = sm.customer_resolution_sql("t_orders", "default.oi_sap_customers", "default.oi_sap_partner_links", ORGS,
                                     overrides=overrides)
    return {r.doc_id: r for r in spark.sql(sql).collect()}


def test_customer_resolution(spark):
    r = _resolve_customers(spark, [
        ("name_addr", "0", "Parfümerie Alpha GmbH", None, "Musterstraße 1, 12345 Musterstadt"),
        ("number", "0", "Alpha", "100001", None),
        ("ship_ok", "0", "Parfumerie Alpha", None, "Alpha Filiale Nord, Nordweg 5, 54321 Nordstadt"),
        ("ship_bad", "0", "Parfumerie Alpha", None, "Alpha Filiale Süd, Suedallee 7, 11111 Suedstadt"),
        ("ambiguous", "0", "Beta Drogerie", None, None),
        ("by_addr", "0", "Beta Drogerie", None, "Hauptplatz 2, 8010 Graz"),
        ("payer", "0", "Gamma Zahlstelle GmbH", None, None),
        ("unknown", "0", "Nobody Known", None, "Nowhere 1, 99999 Nirgendwo"),
        ("outside", "0", "Outside Org Customer", None, None),
    ])
    assert r["name_addr"].sap_sold_to == "0000100001" and r["name_addr"].customer_match_method == "name_address"
    assert r["name_addr"].sap_sales_org == "4160" and r["name_addr"].sap_currency == "EUR"
    assert r["name_addr"].ship_to_check == "ok" and r["name_addr"].sap_ship_to == "0000100001"
    assert r["number"].sap_sold_to == "0000100001" and r["number"].customer_match_method == "customer_number"
    assert r["ship_ok"].ship_to_check == "ok" and r["ship_ok"].sap_ship_to == "0000100002"
    # a ship-to that is a separate customer, not linked to the sold-to in KNVP -> flagged, not blocked
    assert r["ship_bad"].sap_sold_to == "0000100001" and r["ship_bad"].ship_to_check == "not_linked"
    assert r["ship_bad"].sap_ship_to == "0000100003"
    assert r["ambiguous"].customer_match_method == "ambiguous" and r["ambiguous"].sap_sold_to is None
    assert sorted(r["ambiguous"].candidate_sold_tos) == ["0000200001", "0000200002"]
    assert r["by_addr"].sap_sold_to == "0000200002"                   # the address breaks the tie
    assert r["payer"].sap_sold_to == "0000300002" and r["payer"].sold_to_via_partner == "RG:0000300001"
    assert r["unknown"].customer_match_method == "none" and r["unknown"].ship_to_check == "no_sold_to"
    assert r["outside"].customer_match_method == "none"               # no sales view in the configured orgs


def test_customer_override_layer(spark):
    _df(spark, ["sap_sold_to", "retailer_canonical", "name_variant", "country", "currency"],
        [("0000200001", "Beta", "Beta Drogerie", "AT", "EUR"), ("0099999999", "Ghost", "Nobody Known", "DE", "EUR")]
        ).createOrReplaceTempView("t_cm")
    r = _resolve_customers(spark, [("pinned", "0", "Beta Drogerie", None, None),
                                   ("ghost", "0", "Nobody Known", None, None)], overrides="t_cm")
    assert r["pinned"].sap_sold_to == "0000200001" and r["pinned"].customer_match_method == "name_variant"
    assert r["ghost"].pinned_sold_to == "0099999999" and r["ghost"].pinned_in_sap is False
    assert r["ghost"].sap_sold_to is None                              # a pin that isn't in SAP is ignored


def _resolve_materials(spark, lines, sku_map=None):
    _df(spark, ["doc_id", "order_idx", "li_idx", "printed_sku", "sales_org"], lines) \
        .selectExpr("doc_id", "CAST(order_idx AS INT) order_idx", "CAST(li_idx AS INT) li_idx", "printed_sku",
                    "sales_org").createOrReplaceTempView("t_lines")
    sql = sm.material_resolution_sql("t_lines", "default.oi_sap_materials", ORGS, 6, sku_overrides=sku_map)
    return {r.li_idx: r for r in spark.sql(sql).collect()}


def test_material_resolution(spark):
    r = _resolve_materials(spark, [
        ("d", "0", "0", "AB12CD0000", "4160"),     # exact 10
        ("d", "0", "1", "AB12CD", "4160"),         # 6-char prefix, 2 materials -> valid, SAP resolves
        ("d", "0", "2", "AB12CD9999", "4160"),     # 10 given but not existing -> prefix
        ("d", "0", "3", "4000000000017", "4160"),  # EAN (MARA)
        ("d", "0", "4", "04000000000048", "4160"), # EAN (MARM) with leading zero
        ("d", "0", "5", "4000000000024", "4160"),  # EAN on two listed materials -> ambiguous
        ("d", "0", "6", "MN78OP0000", "4160"),     # exists, listed for 4020 only
        ("d", "0", "7", "ZZ99ZZ0000", "4160"),     # unknown
        ("d", "0", "8", "4000000000031", "4160"),  # EAN of a raw material -> not found
        ("d", "0", "9", "MN78OP0000", None),       # customer unresolved -> any configured org
        ("d", "0", "10", "AB-12 CD-0000", "4160"), # printed with separators
    ])
    assert (r[0].sku_resolve_method, r[0].resolved_material_no, r[0].sku_resolved) == ("exact", "AB12CD0000", True)
    assert r[0].sap_material_text == "Creme 50ml"
    assert (r[1].sku_resolve_method, r[1].resolved_material_no, r[1].material_candidates) == ("prefix", "AB12CD", 2)
    assert (r[2].sku_resolve_method, r[2].resolved_material_no) == ("prefix", "AB12CD")
    assert (r[3].sku_resolve_method, r[3].resolved_material_no) == ("ean", "AB12CD0000")
    assert (r[4].sku_resolve_method, r[4].resolved_material_no) == ("ean", "AB12CD0001")
    assert (r[5].sku_resolved, r[5].material_issue, r[5].material_candidates) == (False, "ean_ambiguous", 2)
    assert (r[6].sku_resolved, r[6].material_issue) == (False, "not_listed")
    assert (r[7].sku_resolved, r[7].material_issue) == (False, "not_found")
    assert (r[8].sku_resolved, r[8].material_issue) == (False, "not_found")
    assert r[9].sku_resolved and r[9].sku_resolve_method == "exact"
    assert r[10].resolved_material_no == "AB12CD0000"


def test_material_retailer_map_override(spark):
    _df(spark, ["retailer_canonical", "retailer_sku", "material_no"],
        [("R", "R-1", "EF34GH0000"), ("R", "R-2", "NOT-IN-SAP")]).createOrReplaceTempView("t_rs")
    r = _resolve_materials(spark, [("d", "0", "0", "R-1", "4160"), ("d", "0", "1", "R-2", "4160")], sku_map="t_rs")
    assert r[0].resolved_material_no == "EF34GH0000" and r[0].sku_from_retailer_map
    assert not r[1].sku_resolved and r[1].material_issue == "not_found"


def test_sql_and_python_normalization_agree(spark):
    samples = ["Parfümerie Muster GmbH & Co. KG", "PHARMACIE DE L'ÉTOILE SAS", "  Ölmühle  Weiß-Grün ", "Café Ñandú",
               "The Store BV", None]
    df = spark.createDataFrame([(s,) for s in samples], "s string")
    got = df.selectExpr(f"s", f"{sm.norm_name_sql('s')} n", f"{sm.norm_text_sql('s')} t",
                        f"{sm.street_key_sql('s')} k").collect()
    for row in got:
        assert row.n == sm.norm_name(row.s), row
        assert row.t == sm.norm_text(row.s), row
        assert row.k == sm.street_key(row.s), row
