from server.routes.orders import _build_idoc


def test_idoc_sends_the_resolved_sap_material():
    lines = [{"material_or_sku": "HF-123", "resolved_material_no": "R34F011116", "quantity": 12},
             {"material_or_sku": "R34F011116", "resolved_material_no": "R34F011116", "quantity": 1},
             {"material_or_sku": "UNKNOWN", "resolved_material_no": None, "quantity": 2}]
    items = _build_idoc({"po_number": "PO1", "currency": "EUR"}, lines)["IDOC"]["E1EDP01"]
    assert items[0]["MATNR"] == "R34F011116" and items[0]["E1EDP19"] == [{"QUALF": "001", "IDTNR": "HF-123"}]
    assert items[1]["MATNR"] == "R34F011116" and "E1EDP19" not in items[1]
    assert items[2]["MATNR"] == "UNKNOWN" and "E1EDP19" not in items[2]


def test_idoc_date_formats():
    from server.routes.orders import _idoc_date as d
    assert d("2026-09-28") == "20260928"
    assert d("22/9/26") == "20260922" and d("22.09.2026") == "20260922"      # day-first (European customers)
    assert d("26 February 2004") == "20040226" and d("26. Februar 2004") == "20040226"
    assert d("Sept 22, 2026") == "20260922"
    assert d("31/02/26") is None and d("tbd") is None and d(None) is None
