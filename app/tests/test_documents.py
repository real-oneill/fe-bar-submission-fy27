"""Document previews, the path allow-list and the citations / preview endpoints (synthetic fixtures only)."""
import csv
import io
import os
from email.message import EmailMessage
from pathlib import Path

import pytest
from openpyxl import Workbook

os.environ.setdefault("APP_BACKEND", "lakebase")
os.environ["RLS_ENFORCED"] = "false"          # user_connection -> None (the app SP connection, stubbed below)
os.environ.setdefault("UC_CATALOG", "cat")
os.environ.setdefault("UC_SCHEMA", "sch")
os.environ.setdefault("UC_VOLUME", "landing")

from server import documents as d  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = "/Volumes/cat/sch/landing"


def xlsx_bytes(sheets, hidden=()):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
        if name in hidden:
            ws.sheet_state = "hidden"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def csv_bytes(rows, delimiter=","):
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter).writerows(rows)
    return out.getvalue().encode("utf-8")


ORDER_ROWS = [
    ["Synthetic Retailer PO"],
    [None],
    ["PO Number: SYN-0001"],
    [None],
    ["Line", "SKU", "Description", "Qty", "Unit Price"],
    [1, "SKU-100001", "Test Serum 30ml", 12, 29.700000000000003],
    [2, "SKU-100002", "Test Cream 50ml", 3, None],
]


# ------------------------------------------------------------------------------------------------ allow-list
class TestAllowedPath:
    @pytest.mark.parametrize("p", [
        f"{ROOT}/inbound_docs/a.pdf", f"dbfs:{ROOT}/inbound_docs/sub/a.xlsx",
        f"{ROOT}/outlook_attachments/abc/0/order.xlsx",
    ])
    def test_allowed(self, p):
        assert d.allowed_path(p, "cat", "sch", "landing")

    @pytest.mark.parametrize("p", [
        None, "", f"{ROOT}/a.pdf", f"{ROOT}/other/a.pdf", f"{ROOT}/inbound_docs/", f"{ROOT}/inbound_docs/../x.pdf",
        f"{ROOT}/inbound_docs/./x.pdf", "/Volumes/cat/sch/other_vol/inbound_docs/a.pdf",
        "/Volumes/cat2/sch/landing/inbound_docs/a.pdf", "/Workspace/Users/x/inbound_docs/a.pdf",
        f"{ROOT}/inbound_docs//a.pdf", "/etc/passwd",
    ])
    def test_refused(self, p):
        assert not d.allowed_path(p, "cat", "sch", "landing")

    def test_needs_config(self):
        assert not d.allowed_path(f"{ROOT}/inbound_docs/a.pdf", "cat", "sch", "")


# ------------------------------------------------------------------------------------------------ previews
class TestSheetPreview:
    def test_xlsx_rows_numbered_like_excel_blank_rows_skipped(self):
        p = d.sheet_preview(xlsx_bytes({"Order": ORDER_ROWS}), ".xlsx")
        s = p["sheets"][0]
        assert p["kind"] == "sheet" and s["index"] == 1 and s["name"] == "Order"
        assert [r["r"] for r in s["rows"]] == [1, 3, 5, 6, 7]
        assert s["n_cols"] == 5 and all(len(r["cells"]) == 5 for r in s["rows"])
        # Silver's cell formatting: ints without .0, float noise trimmed, empty -> ""
        assert s["rows"][3]["cells"] == ["1", "SKU-100001", "Test Serum 30ml", "12", "29.7"]
        assert s["rows"][4]["cells"][4] == ""
        assert not s["truncated"] and not p["truncated"]

    def test_xlsx_hidden_sheets_skipped_and_numbering_follows_visible(self):
        b = xlsx_bytes({"Hidden": [["x"]], "Cover": [["Hello"]], "Order": ORDER_ROWS}, hidden=("Hidden",))
        p = d.sheet_preview(b, ".xlsx")
        assert [(s["index"], s["name"]) for s in p["sheets"]] == [(1, "Cover"), (2, "Order")]

    def test_xls(self):
        p = d.sheet_preview((FIXTURES / "synthetic_order.xls").read_bytes(), ".xls")
        assert [(s["index"], s["name"]) for s in p["sheets"]] == [(1, "Order"), (2, "Notes")]
        rows = p["sheets"][0]["rows"]
        assert [r["r"] for r in rows] == [1, 3, 5, 6, 7]
        assert rows[3]["cells"] == ["1", "SKU-100001", "Test Serum 30ml", "12"]
        assert rows[4]["cells"][3] == "3.5"

    def test_csv_semicolon(self):
        rows = [["SKU", "Description", "Qty"], ["A-1", "Serum 30ml", "5"], ["B-2", "Cream 50ml", "7"]]
        s = d.sheet_preview(csv_bytes(rows, ";"), ".csv")["sheets"][0]
        assert s["name"] == "csv" and s["index"] == 1
        assert [(r["r"], r["cells"]) for r in s["rows"]] == [(1, rows[0]), (2, rows[1]), (3, rows[2])]

    def test_csv_blank_rows_keep_numbers(self):
        rows = [["SKU", "Qty"], ["A-1", "5"], [], ["B-2", "7"]]
        s = d.sheet_preview(csv_bytes(rows), ".csv")["sheets"][0]
        assert [(r["r"], r["cells"]) for r in s["rows"]] == [(1, rows[0]), (2, rows[1]), (4, rows[3])]

    def test_truncation_rows_and_cols(self, monkeypatch):
        monkeypatch.setattr(d, "MAX_ROWS", 10)
        monkeypatch.setattr(d, "MAX_COLS", 3)
        rows = [[f"r{i}c{j}" for j in range(6)] for i in range(25)]
        p = d.sheet_preview(xlsx_bytes({"Big": rows}), ".xlsx")
        s = p["sheets"][0]
        assert len(s["rows"]) == 10 and s["n_cols"] == 3 and s["truncated"] and p["truncated"]
        assert s["rows"][-1]["r"] == 10

    def test_unreadable(self):
        with pytest.raises(ValueError):
            d.sheet_preview(b"not a workbook", ".xlsx")
        with pytest.raises(ValueError):
            d.sheet_preview(b"x", ".pdf")


class TestSheetsFromText:
    TEXT = ("=== Sheet S1: Order === (cells shown as COLUMN=value; empty cells omitted)\n"
            "S1R1: A=Synthetic PO\n"
            "S1R9: A=Line | B=SKU | D=Qty\n"
            "S1R10: A=1 | B=SKU-1 | C=Cream | with pipe | D=405\n\n"
            "=== Sheet S2: Notes === (cells shown as COLUMN=value; empty cells omitted)\n"
            "S2R2: AA=far right")

    def test_grid(self):
        p = d.sheets_from_text(self.TEXT)
        s1, s2 = p["sheets"]
        assert (s1["index"], s1["name"], s2["index"], s2["name"]) == (1, "Order", 2, "Notes")
        assert [r["r"] for r in s1["rows"]] == [1, 9, 10]
        assert s1["rows"][2]["cells"] == ["1", "SKU-1", "Cream | with pipe", "405"]
        assert s1["rows"][1]["cells"] == ["Line", "SKU", "", "Qty"]
        assert s2["n_cols"] == 27 and s2["rows"][0]["cells"][26] == "far right"

    def test_not_cell_text(self):
        assert d.sheets_from_text("Hello, please deliver") is None
        assert d.sheets_from_text("") is None


def test_eml_attachment():
    m = EmailMessage()
    m["Subject"] = "PO"
    m.set_content("see attached")
    m.add_attachment(b"PK-synthetic", maintype="application", subtype="octet-stream", filename="po.xlsx")
    assert d.eml_attachment(m.as_bytes(), "po.xlsx") == b"PK-synthetic"
    with pytest.raises(LookupError):
        d.eml_attachment(m.as_bytes(), "other.xlsx")


def test_col_letters():
    assert [d.col_letter(i) for i in (0, 25, 26, 701)] == ["A", "Z", "AA", "ZZ"]
    assert [d.col_index(x) for x in ("A", "Z", "AA", "ZZ")] == [0, 25, 26, 701]


# ------------------------------------------------------------------------------------------------ endpoints
ORDERS = {
    "doc-1#PO-1": {"order_id": "doc-1#PO-1", "doc_name": "PO-1.pdf", "orig_format": "pdf",
                   "volume_path": f"{ROOT}/inbound_docs/PO-1.pdf", "parsed_content": "text",
                   "extractor": "ai_extract", "fallback_reason": None,
                   "field_confidence_json": '{"po_number": 1.0, "customer_name": 0.9}'},
    "doc-2#PO-2": {"order_id": "doc-2#PO-2", "doc_name": "PO-2.xlsx", "orig_format": "spreadsheet",
                   "volume_path": None, "parsed_content": TestSheetsFromText.TEXT,
                   "extractor": "ai_extract", "fallback_reason": None, "field_confidence_json": None},
    "doc-3#PO-3": {"order_id": "doc-3#PO-3", "doc_name": "PO-3.xlsx", "orig_format": "spreadsheet",
                   "volume_path": None, "parsed_content": TestSheetsFromText.TEXT, "extractor": "ai_query",
                   "fallback_reason": "ai_extract found no order lines", "field_confidence_json": None},
    "doc-4#PO-4": {"order_id": "doc-4#PO-4", "doc_name": "mail-body.txt", "orig_format": "email/text",
                   "volume_path": None, "parsed_content": "Please send 5 x SKU-1", "extractor": "ai_query",
                   "fallback_reason": None, "field_confidence_json": None},
    "doc-5#PO-5": {"order_id": "doc-5#PO-5", "doc_name": "x.pdf", "orig_format": "pdf",
                   "volume_path": "/Volumes/cat/sch/landing/secret/x.pdf", "parsed_content": "t",
                   "extractor": None, "fallback_reason": None, "field_confidence_json": None},
}
CITES = {
    "doc-1#PO-1": [
        {"order_id": "doc-1#PO-1", "source_path": f"dbfs:{ROOT}/inbound_docs/PO-1.pdf", "attachment_filename": "PO-1.pdf",
         "order_idx": 0, "li_idx": 0, "field": "quantity", "value": "453.0", "confidence": 1, "citation_id": 1,
         "source_kind": "layout", "page_index": 0, "x1": 51, "y1": 246, "x2": 1528, "y2": 917, "element_id": 2,
         "element_type": "table", "table_row_index": 1, "table_row_count": 23, "snippet": "1 | SKU-1 | 453"},
        {"order_id": "doc-1#PO-1", "source_path": f"dbfs:{ROOT}/inbound_docs/PO-1.pdf", "attachment_filename": "PO-1.pdf",
         "order_idx": 0, "li_idx": None, "field": "po_number", "value": "PO-1", "confidence": 1.0, "citation_id": 0,
         "source_kind": "layout", "page_index": 0, "x1": 55, "y1": 87, "x2": 390, "y2": 218, "element_type": "text"},
    ],
    "doc-2#PO-2": [
        {"order_id": "doc-2#PO-2", "source_path": f"dbfs:{ROOT}/inbound_docs/PO-2.xlsx",
         "attachment_filename": "PO-2.xlsx", "order_idx": 0, "li_idx": 0, "field": "quantity", "value": "405.0",
         "source_kind": "sheet", "sheet_index": 1, "sheet_name": "Order", "row_number": 10, "cell_ref": "D10"},
    ],
}


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from server.routes import orders

    calls = []

    def fake_query(sql, params=None, conn=None):
        calls.append((sql, params, conn))
        oid = (params or {}).get("oid")
        if "information_schema.columns" in sql:
            return [{"x": 1}]
        if "review_citations" in sql:
            return [dict(r) for r in CITES.get(oid, [])]
        return [dict(ORDERS[oid])] if oid in ORDERS else []

    files = {f"{ROOT}/inbound_docs/PO-1.pdf": b"%PDF-1.4 synthetic",
             f"{ROOT}/inbound_docs/PO-2.xlsx": xlsx_bytes({"Order": ORDER_ROWS})}
    downloads = []

    def fake_download(path):
        downloads.append(path)
        return files[d.volume_path(path)]

    monkeypatch.setattr(orders, "query", fake_query)
    monkeypatch.setattr(orders, "_download", fake_download)
    monkeypatch.setattr(orders, "CATALOG", "cat")
    monkeypatch.setattr(orders, "SCHEMA", "sch")
    monkeypatch.setattr(orders, "VOLUME", "landing")
    for c in orders._cols.values():
        c.update(has=False, checked=0.0)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(orders.router, prefix="/api")
    c = TestClient(app)
    c.calls, c.downloads = calls, downloads
    return c


def q(oid):
    return oid.replace("#", "%23")


class TestCitationsEndpoint:
    def test_layout_citations(self, client):
        r = client.get(f"/api/orders/{q('doc-1#PO-1')}/citations")
        assert r.status_code == 200
        b = r.json()
        assert b["extractor"] == "ai_extract" and b["fallback_reason"] is None
        assert b["field_confidence"] == {"po_number": 1.0, "customer_name": 0.9}
        assert [c["field"] for c in b["citations"]] == ["po_number", "quantity"]     # header first
        line = b["citations"][1]
        assert (line["order_idx"], line["li_idx"], line["page_index"], line["x2"]) == (0, 0, 0, 1528.0)
        assert (line["table_row_index"], line["table_row_count"]) == (1, 23)
        assert "source_path" not in line            # paths stay server-side

    def test_order_without_citations(self, client):
        b = client.get(f"/api/orders/{q('doc-3#PO-3')}/citations").json()
        assert b["extractor"] == "ai_query" and b["citations"] == []
        assert b["fallback_reason"] == "ai_extract found no order lines" and b["field_confidence"] == {}

    def test_unknown_order(self, client):
        assert client.get("/api/orders/nope/citations").status_code == 404

    def test_same_connection_for_order_and_citations(self, client, monkeypatch):
        """Citations are read over the request's user connection (RLS), like review_orders."""
        from server.routes import orders
        import contextlib
        sentinel = object()

        @contextlib.contextmanager
        def fake_conn(request, set_role=True):
            yield sentinel

        monkeypatch.setattr(orders.userdb, "user_connection", fake_conn)
        client.get(f"/api/orders/{q('doc-1#PO-1')}/citations")
        used = [conn for sql, _, conn in client.calls if "review_" in sql]
        assert used and all(c is sentinel for c in used)


class TestPreviewEndpoint:
    def test_pdf(self, client):
        b = client.get(f"/api/orders/{q('doc-1#PO-1')}/preview").json()
        assert b == {"kind": "pdf", "url": "/api/orders/doc-1%23PO-1/document"}

    def test_sheet_from_workbook_named_by_citations(self, client):
        b = client.get(f"/api/orders/{q('doc-2#PO-2')}/preview").json()
        assert b["kind"] == "sheet" and b["source"] == "file"
        assert client.downloads == [f"dbfs:{ROOT}/inbound_docs/PO-2.xlsx"]
        assert [r["r"] for r in b["sheets"][0]["rows"]] == [1, 3, 5, 6, 7]

    def test_sheet_without_citations_rebuilt_from_text(self, client):
        b = client.get(f"/api/orders/{q('doc-3#PO-3')}/preview").json()
        assert b["kind"] == "sheet" and b["source"] == "text" and client.downloads == []
        assert b["sheets"][0]["rows"][2]["cells"][3] == "405"

    def test_text(self, client):
        b = client.get(f"/api/orders/{q('doc-4#PO-4')}/preview").json()
        assert b["kind"] == "text" and b["text"] == "Please send 5 x SKU-1"

    def test_disallowed_pdf_path_is_not_read(self, client):
        b = client.get(f"/api/orders/{q('doc-5#PO-5')}/preview").json()
        assert b["kind"] == "text" and client.downloads == []
        assert client.get(f"/api/orders/{q('doc-5#PO-5')}/document").status_code == 404
        assert client.downloads == []

    def test_document(self, client):
        r = client.get(f"/api/orders/{q('doc-1#PO-1')}/document")
        assert r.status_code == 200 and r.content == b"%PDF-1.4 synthetic"
        assert r.headers["content-type"] == "application/pdf"

    def test_disallowed_sheet_path_falls_back_to_text(self, client, monkeypatch):
        monkeypatch.setitem(CITES, "doc-2#PO-2", [dict(CITES["doc-2#PO-2"][0],
                                                      source_path="dbfs:/Volumes/cat/sch/landing/../x.xlsx")])
        b = client.get(f"/api/orders/{q('doc-2#PO-2')}/preview").json()
        assert b["kind"] == "sheet" and b["source"] == "text" and client.downloads == []
