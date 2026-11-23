import re
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from urllib.parse import quote
from pydantic import BaseModel
from typing import Optional, List, Any

import time

from ..db import query, execute
from .. import feedback, userdb, documents, mailview
from ..config import (
    BACKEND,
    REVIEW_TABLE,
    OUTBOUND_TABLE,
    CITATIONS_TABLE,
    VOLUME,
    VOLUME_CATALOG,
    VOLUME_SCHEMA,
    get_workspace_client,
    get_current_user,
)

router = APIRouter()

# Columns added to review_orders by later publish-job versions (region; the hybrid-extraction columns). An app
# deployed before that publish must still work: a missing column is selected as a constant until it exists.
# Re-checked every minute while missing.
_OPTIONAL_COLS = ("region", "extractor", "fallback_reason", "field_confidence_json", "source_path", "attachment_filename")
_cols = {c: {"has": False, "checked": 0.0} for c in _OPTIONAL_COLS}


def _has_col(conn, col: str) -> bool:
    st = _cols[col]
    if st["has"] or time.time() - st["checked"] < 60:
        return st["has"]
    try:
        if BACKEND == "lakebase":
            rows = query("SELECT 1 AS x FROM information_schema.columns WHERE table_schema = current_schema() "
                         "AND table_name = 'review_orders' AND column_name = :col", {"col": col}, conn=conn)
        else:
            rows = [r for r in query(f"DESCRIBE TABLE {REVIEW_TABLE}") if r.get("col_name") == col]
        st["has"] = bool(rows)
    except Exception:  # noqa
        st["has"] = False
    st["checked"] = time.time()
    return st["has"]


def _has_region(conn) -> bool:
    return _has_col(conn, "region")


def _region_sql(conn) -> str:
    return "coalesce(region, 'Unassigned') AS region" if _has_region(conn) else "'Unassigned' AS region"


def _extraction_sql(conn) -> str:
    """extractor, fallback_reason, field_confidence_json (NULL until the publish job has added them)."""
    return ", ".join(c if _has_col(conn, c) else f"CAST(NULL AS {'STRING' if BACKEND != 'lakebase' else 'text'}) AS {c}"
                     for c in ("extractor", "fallback_reason", "field_confidence_json"))


def _source_sql(conn) -> str:
    """source_path, attachment_filename: the file the order came from (NULL until the publish job has added them)."""
    return ", ".join(c if _has_col(conn, c) else f"CAST(NULL AS {'STRING' if BACKEND != 'lakebase' else 'text'}) AS {c}"
                     for c in ("source_path", "attachment_filename"))


def _json_obj(raw) -> dict:
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, dict) else {}
    except Exception:  # noqa
        return {}


def _parse_lines(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _user_from_request(request: Request) -> str:
    for h in ("x-forwarded-email", "x-forwarded-preferred-username", "x-forwarded-user"):
        v = request.headers.get(h)
        if v:
            return v
    return get_current_user()


@router.get("/orders")
def list_orders(request: Request, status: Optional[str] = None, region: Optional[str] = None):
    """The queue. Row-level security already limits it to the user's regions; `region` narrows further."""
    with userdb.user_connection(request) as conn:
        conds, params = [], {}
        if status == "needs_manual":
            # flagged by a reviewer, OR still pending but impossible to send as is: no customer found in SAP or no
            # ordered line extracted (the orders someone has to key in by hand)
            conds.append("(status = 'needs_manual' OR (status = 'pending' AND "
                         "(coalesce(customer_number, '') = '' OR coalesce(n_lines, 0) = 0)))")
        elif status:
            conds.append("status = :status")
            params["status"] = status
        if region:
            if not _has_region(conn):
                return [] if region != "Unassigned" else _orders(conn, conds, params)
            conds.append("coalesce(region, 'Unassigned') = :region")
            params["region"] = region
        return _orders(conn, conds, params)


def _orders(conn, conds, params):
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return query(
        f"""
        SELECT order_id, doc_name, orig_format, po_number, customer_name,
               customer_number, currency, sales_org, n_lines, status,
               parse_confidence, header_confidence, avg_line_confidence,
               overall_confidence, review_reasons, duplicate_of,
               (volume_path IS NOT NULL) AS has_pdf, {_region_sql(conn)}
        FROM {REVIEW_TABLE}
        {where}
        ORDER BY overall_confidence ASC NULLS FIRST, doc_name
        """,
        params, conn=conn,
    )


@router.get("/regions")
def list_regions(request: Request):
    """Regions the signed-in user can see: the regions of their visible orders, plus their assigned regions
    (user_regions, RLS on) even if those have no orders yet."""
    with userdb.user_connection(request) as conn:
        if not _has_region(conn):
            return ["Unassigned"]
        regions = {r["region"] for r in query(
            f"SELECT DISTINCT coalesce(region, 'Unassigned') AS region FROM {REVIEW_TABLE}", conn=conn)}
        if conn is not None:
            regions |= {r["region"] for r in query(
                "SELECT DISTINCT region FROM user_regions WHERE principal = session_user AND region <> '*'",
                conn=conn)}
        return sorted(regions)


@router.get("/orders/{order_id}")
def get_order(order_id: str, request: Request):
    with userdb.user_connection(request) as conn:
        rows = query(
            f"""
            SELECT order_id, doc_name, orig_format, po_number, customer_name,
                   customer_number, order_date, currency, sales_org, ship_to,
                   header_confidence, n_lines, line_items_json, avg_line_confidence,
                   status, parse_confidence, parsed_content, volume_path,
                   overall_confidence, review_reasons, duplicate_of, trace_id,
                   {_extraction_sql(conn)}, {_region_sql(conn)}
            FROM {REVIEW_TABLE}
            WHERE order_id = :oid
            """,
            {"oid": order_id}, conn=conn,
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Order not found")
    row = rows[0]
    row["line_items"] = _parse_lines(row.get("line_items_json"))
    row["has_pdf"] = bool(row.get("volume_path"))
    row["field_confidence"] = _json_obj(row.pop("field_confidence_json", None))
    row["related_orders"] = _related_orders(order_id, request)
    return row


def _related_orders(order_id: str, request: Request) -> list:
    """Other review rows from the same email (e.g. the email body and its attached spreadsheet are separate rows):
    the reviewer sees they belong together and can open the other one. Empty when the source isn't recorded."""
    with userdb.user_connection(request) as conn:
        if not _has_col(conn, "source_path"):
            return []
        return query(
            f"SELECT b.order_id, b.doc_name, b.status FROM {REVIEW_TABLE} a JOIN {REVIEW_TABLE} b "
            f"ON a.source_path = b.source_path AND b.order_id <> a.order_id "
            f"WHERE a.order_id = :oid AND a.source_path IS NOT NULL AND b.status <> 'duplicate' "
            f"ORDER BY b.doc_name LIMIT 10", {"oid": order_id}, conn=conn)


class LineItem(BaseModel):
    material_or_sku: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_confidence: Optional[float] = None


class OrderUpdate(BaseModel):
    po_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_number: Optional[str] = None
    order_date: Optional[str] = None
    currency: Optional[str] = None
    ship_to: Optional[str] = None
    line_items: Optional[List[LineItem]] = None


@router.put("/orders/{order_id}")
def update_order(order_id: str, body: OrderUpdate, request: Request):
    with userdb.user_connection(request) as conn:
        return _update_order(order_id, body, request, conn)


def _update_order(order_id, body, request, conn):
    before = query(
        f"""SELECT po_number, customer_name, customer_number, order_date, currency, ship_to,
                   line_items_json, trace_id FROM {REVIEW_TABLE} WHERE order_id = :oid""",
        {"oid": order_id}, conn=conn,
    )
    if not before:   # unknown, or not in the user's regions (row-level security)
        raise HTTPException(status_code=404, detail="Order not found")
    sets = []
    params: dict[str, Any] = {"oid": order_id}
    for field in ("po_number", "customer_name", "customer_number", "order_date", "currency", "ship_to"):
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = :{field}")
            params[field] = val
    if body.line_items is not None:
        lines = [li.model_dump() for li in body.line_items]
        sets.append("line_items_json = :lij")
        sets.append("n_lines = :nlines")
        params["lij"] = json.dumps(lines)
        params["nlines"] = len(lines)
    if not sets:
        return {"success": True, "updated": 0}
    if execute(f"UPDATE {REVIEW_TABLE} SET {', '.join(sets)} WHERE order_id = :oid", params, conn=conn) == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    if before:
        b = before[0]
        changed = [f for f in ("po_number", "customer_name", "customer_number", "order_date", "currency", "ship_to")
                   if f in params and (b.get(f) or "") != (params[f] or "")]
        if "lij" in params and _parse_lines(b.get("line_items_json")) != json.loads(params["lij"]):
            changed.append("line_items")
        if changed:
            feedback.record(b.get("trace_id"), _user_from_request(request),
                            [("human_corrected", True, "changed: " + ", ".join(changed))])
    return {"success": True, "updated": len(sets)}


class ApproveRequest(BaseModel):
    sap_sold_to: Optional[str] = None


_MONTHS = {m: i + 1 for i, names in enumerate([
    "jan january januar janvier januari enero gennaio", "feb february februar fevrier février februari febrero febbraio",
    "mar march maerz märz mars maart marzo", "apr april avril abril aprile", "may mai mei mayo maggio",
    "jun june juni juin junio giugno", "jul july juli juillet julio luglio", "aug august aout août augustus agosto",
    "sep sept september septembre septiembre settembre", "oct october oktober octobre octubre ottobre",
    "nov november novembre noviembre", "dec december dezember decembre décembre diciembre dicembre"]) for m in names.split()}


def _idoc_date(value: Optional[str]) -> Optional[str]:
    """Order date as printed -> IDoc DATUM (YYYYMMDD, the format SAP expects in E1EDK02), or None if it can't be read
    unambiguously. Accepts ISO (2026-09-28), day-first numeric (22/9/26, 22.09.2026, 22-9-26: the customers are
    European, so DD/MM is assumed; a first number > 12 is certain, otherwise only day-first is tried) and
    month-name forms (26 February 2004, 26. Februar 2004, Sept 22, 2026)."""
    import datetime as dt
    t = (value or "").strip().lower()
    if not t:
        return None
    y = mth = d = None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[t ].*)?", t)
    if m:
        y, mth, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})", t)
        if m:
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{1,2})\.?\s+([a-zäéû]+)\.?,?\s+(\d{2}|\d{4})", t) or None
            if m:
                d, mth, y = int(m.group(1)), _MONTHS.get(m.group(2)), int(m.group(3))
            else:
                m = re.fullmatch(r"([a-zäéû]+)\.?\s+(\d{1,2}),?\s+(\d{2}|\d{4})", t)
                if m:
                    mth, d, y = _MONTHS.get(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (y and mth and d):
        return None
    y += 2000 if y < 100 else 0
    try:
        return dt.date(y, mth, d).strftime("%Y%m%d")
    except ValueError:
        return None


def _idoc_line(i: int, li: dict) -> dict:
    """One E1EDP01 item. MATNR = the SAP material the line resolved to (exact number, EAN or prefix — the
    prefix lets SAP pick the full number); the code the customer printed travels as the customer's material number
    (E1EDP19 qualifier 001). A line that resolved to nothing keeps the printed code in MATNR (it is reviewed first)."""
    printed = li.get("material_or_sku")
    resolved = li.get("resolved_material_no") or None
    item = {"POSEX": str(i + 1).zfill(6), "MATNR": resolved or printed, "MENGE": li.get("quantity"),
            "NETPR": li.get("unit_price"), "ARKTX": li.get("description")}
    if printed and resolved and printed != resolved:
        item["E1EDP19"] = [{"QUALF": "001", "IDTNR": printed}]
    return item


def _build_idoc(order: dict, lines: List[dict]) -> dict:
    """ORDERS05-style IDoc payload."""
    return {
        "IDOC": {
            "EDI_DC40": {
                "IDOCTYP": "ORDERS05",
                "MESTYP": "ORDERS",
                "SNDPRT": "LS",
                "CREDAT": datetime.now(timezone.utc).strftime("%Y%m%d"),
            },
            "E1EDK01": {
                "CURCY": order.get("currency"),
            },
            # The customer's PO number as printed on their document (never looked up in SAP): reference segment
            # qualifier 001 = customer purchase order, which inbound ORDERS processing writes to the sales order's
            # customer PO field (VBAK-BSTNK / VBKD-BSTKD).
            "E1EDK02": [
                {"QUALF": "001", "BELNR": order.get("po_number"), "DATUM": _idoc_date(order.get("order_date"))},
            ],
            "E1EDKA1": [
                {"PARVW": "AG", "PARTN": order.get("customer_number"), "NAME1": order.get("customer_name")},
            ],
            "E1EDP01": [_idoc_line(i, li) for i, li in enumerate(lines)],
        }
    }


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: str, body: ApproveRequest, request: Request):
    with userdb.user_connection(request) as conn:
        return _approve(order_id, body, request, conn)


def _approve(order_id, body, request, conn):
    rows = query(
        f"""SELECT order_id, po_number, customer_name, customer_number, order_date,
                   currency, ship_to, line_items_json, trace_id
            FROM {REVIEW_TABLE} WHERE order_id = :oid""",
        {"oid": order_id}, conn=conn,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Order not found")
    order = rows[0]
    lines = _parse_lines(order.get("line_items_json"))
    approver = _user_from_request(request)
    sold_to = body.sap_sold_to or order.get("customer_number") or ""
    idoc = _build_idoc(order, lines)
    idoc_json = json.dumps(idoc)

    # Remove any prior outbound row for idempotency, then insert.
    execute(f"DELETE FROM {OUTBOUND_TABLE} WHERE order_id = :oid", {"oid": order_id}, conn=conn)
    execute(
        f"""
        INSERT INTO {OUTBOUND_TABLE}
          (order_id, po_number, sap_sold_to, customer_name, order_date, currency,
           line_items_json, approved_by, approved_at, idoc_type)
        VALUES
          (:order_id, :po_number, :sap_sold_to, :customer_name, :order_date, :currency,
           :line_items_json, :approved_by, now(), :idoc_type)
        """,
        {
            "order_id": order_id,
            "po_number": order.get("po_number"),
            "sap_sold_to": sold_to,
            "customer_name": order.get("customer_name"),
            "order_date": order.get("order_date"),
            "currency": order.get("currency"),
            "line_items_json": idoc_json,
            "approved_by": approver,
            "idoc_type": "ORDERS05",
        },
        conn=conn,
    )
    execute(
        f"UPDATE {REVIEW_TABLE} SET status = 'approved' WHERE order_id = :oid",
        {"oid": order_id}, conn=conn,
    )
    # the reviewed order is the ground truth for this extraction
    feedback.record(order.get("trace_id"), approver, [("human_review", "approved", None)],
                    expectation=("expected_order", {
                        "po_number": order.get("po_number"), "customer_name": order.get("customer_name"),
                        "order_date": order.get("order_date"), "currency": order.get("currency"),
                        "ship_to": order.get("ship_to"),
                        "line_items": [{"material_or_sku": l.get("material_or_sku"), "quantity": l.get("quantity"),
                                        "unit_price": l.get("unit_price")} for l in lines]}))
    return {"success": True, "approved_by": approver, "idoc_type": "ORDERS05"}


@router.post("/orders/{order_id}/flag")
def flag_manual(order_id: str, request: Request):
    with userdb.user_connection(request) as conn:
        n = execute(
            f"UPDATE {REVIEW_TABLE} SET status = 'needs_manual' WHERE order_id = :oid",
            {"oid": order_id}, conn=conn,
        )
        if n == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        rows = query(f"SELECT trace_id FROM {REVIEW_TABLE} WHERE order_id = :oid", {"oid": order_id}, conn=conn)
    if rows:
        feedback.record(rows[0].get("trace_id"), _user_from_request(request),
                        [("human_review", "needs_manual", "flagged for manual entry")])
    return {"success": True}


@router.get("/outbound")
def list_outbound(request: Request):
    with userdb.user_connection(request) as conn:
        return query(
            f"""SELECT order_id, po_number, sap_sold_to, customer_name, order_date,
                       currency, approved_by, approved_at, idoc_type, line_items_json
                FROM {OUTBOUND_TABLE}
                ORDER BY approved_at DESC""",
            conn=conn,
        )


def _download(path: str) -> bytes:
    """Read a source file with the app's identity — callers check allowed_path() first."""
    return get_workspace_client().files.download(documents.volume_path(path)).contents.read()


def _allowed(path) -> bool:
    return documents.allowed_path(path, VOLUME_CATALOG, VOLUME_SCHEMA, VOLUME)


@router.get("/orders/{order_id}/document")
def get_document(order_id: str, request: Request):
    # the order lookup is region-checked (user connection); the file itself is read by the app's identity, and only
    # from the inbound folders of the configured Volume
    with userdb.user_connection(request) as conn:
        rows = query(
            f"SELECT volume_path FROM {REVIEW_TABLE} WHERE order_id = :oid",
            {"oid": order_id}, conn=conn,
        )
    if not rows or not rows[0].get("volume_path"):
        raise HTTPException(status_code=404, detail="No source PDF for this order")
    volume_path = rows[0]["volume_path"]
    if not _allowed(volume_path):
        raise HTTPException(status_code=404, detail="Document not available")
    data = _download(volume_path)
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quote(order_id)}.pdf"',
                 "X-Content-Type-Options": "nosniff"},
    )


def _citations(conn, order_id: str) -> list:
    """The order's review_citations rows, read over the SAME connection as its review_orders row (as the signed-in
    user with RLS on; a reviewer sees the citations of the orders they can see). [] if the table isn't published yet."""
    try:
        return query(f"SELECT * FROM {CITATIONS_TABLE} WHERE order_id = :oid", {"oid": order_id}, conn=conn)
    except Exception as e:  # noqa
        msg = str(e).lower()
        if ("review_citations" in msg and ("does not exist" in msg or "not found" in msg or "not_found" in msg)) or "undefined" in msg:
            return []
        raise


@router.get("/orders/{order_id}/citations")
def get_citations(order_id: str, request: Request):
    """Where each extracted field sits in the source document, and how the order was read."""
    with userdb.user_connection(request) as conn:
        rows = query(
            f"SELECT order_id, {_extraction_sql(conn)} FROM {REVIEW_TABLE} WHERE order_id = :oid",
            {"oid": order_id}, conn=conn,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Order not found")
        cites = _citations(conn, order_id)
    o = rows[0]
    return {
        "order_id": order_id,
        "extractor": o.get("extractor"),
        "fallback_reason": o.get("fallback_reason"),
        "field_confidence": _json_obj(o.get("field_confidence_json")),
        "citations": documents.citation_rows(cites),
    }


def _source(o: dict, cites: list) -> tuple[str | None, str | None]:
    """(source file, part name) of an order: the queue row, else what its citations name."""
    if o.get("source_path"):
        return o["source_path"], o.get("attachment_filename")
    return documents.source_of(cites)


def _order_email(order_id: str, request: Request) -> tuple[mailview.Mail, dict]:
    """The email (.eml / .msg) an order came from, region-checked like the order; 404 when it didn't come from one."""
    with userdb.user_connection(request) as conn:
        rows = query(f"SELECT order_id, {_source_sql(conn)} FROM {REVIEW_TABLE} WHERE order_id = :oid",
                     {"oid": order_id}, conn=conn)
        if not rows:
            raise HTTPException(status_code=404, detail="Order not found")
        o = rows[0]
        cites = [] if o.get("source_path") else _citations(conn, order_id)
    src, att = _source(o, cites)
    ext = documents.ext_of(src)
    if not src or ext not in documents.MAIL_EXT:
        raise HTTPException(status_code=404, detail="This order did not come from an attached email")
    if not _allowed(src):
        raise HTTPException(status_code=404, detail="Document not available")
    try:
        return mailview.open_mail(_download(src), ext), {"source_path": src, "attachment_filename": att}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)[:200])


def _part(order_id: str, path: str, request: Request):
    mail, _ = _order_email(order_id, request)
    try:
        return mailview.resolve(mail, path)
    except LookupError:
        raise HTTPException(status_code=404, detail="No such attachment")


def _raw_url(order_id: str, path: str) -> str:
    return f"/api/orders/{quote(order_id, safe='')}/email/raw?path={quote(path, safe='')}"


def _part_preview(order_id: str, path: str, part) -> dict:
    """An email part as the JSON the document viewers render."""
    if isinstance(part, mailview.Mail):
        return mailview.email_json(part, path)
    if part.mail is not None:
        return mailview.email_json(part.mail, path)
    base = {"name": part.name, "path": path}
    if part.data is None:
        return {**base, "kind": "text", "text": "", "note": "this attachment has no content"}
    kind = part.kind
    if kind in ("pdf", "image"):
        return {**base, "kind": kind, "url": _raw_url(order_id, path)}
    if kind == "sheet":
        try:
            return {**documents.sheet_preview(part.data, documents.ext_of(part.name)), **base, "source": "file"}
        except ValueError as e:
            return {**base, "kind": "file", "url": _raw_url(order_id, path), "note": str(e)[:200]}
    if kind == "text":
        text = mailview._text(part.data) or ""
        return {**base, "kind": "text", "text": text[:documents.MAX_TEXT_CHARS],
                "truncated": len(text) > documents.MAX_TEXT_CHARS}
    return {**base, "kind": "file", "url": _raw_url(order_id, path)}


@router.get("/orders/{order_id}/email/part")
def email_part(order_id: str, request: Request, path: str = ""):
    """The order's source email (path '') or one of its attachments ('0', '1.0' inside an attached email)."""
    return _part_preview(order_id, path, _part(order_id, path, request))


@router.get("/orders/{order_id}/email/raw")
def email_raw(order_id: str, request: Request, path: str):
    """An attachment's bytes: PDFs and images inline (for the viewers), anything else as a download."""
    part = _part(order_id, path, request)
    if isinstance(part, mailview.Mail) or part.data is None:
        raise HTTPException(status_code=404, detail="No file for this attachment")
    inline = part.mime in mailview.INLINE_MIME
    name = quote(part.name)
    return Response(part.data, media_type=part.mime if inline else "application/octet-stream",
                    headers={"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{name}",
                             "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.get("/orders/{order_id}/original")
def original_document(order_id: str, request: Request):
    """The source file exactly as received (xlsx/xls/csv/PDF, or the attachment inside the email), as a download, so
    a reviewer can open it in Excel / a PDF reader when the in-app view cuts cells off."""
    with userdb.user_connection(request) as conn:
        rows = query(
            f"SELECT order_id, doc_name, orig_format, volume_path, {_source_sql(conn)} "
            f"FROM {REVIEW_TABLE} WHERE order_id = :oid", {"oid": order_id}, conn=conn)
        if not rows:
            raise HTTPException(status_code=404, detail="Order not found")
        o = rows[0]
        cites = [] if o.get("volume_path") else _citations(conn, order_id)
    headers = {"X-Content-Type-Options": "nosniff"}
    if o.get("volume_path"):
        if not _allowed(o["volume_path"]):
            raise HTTPException(status_code=404, detail="Document not available")
        name = (o.get("doc_name") or order_id)
        return Response(_download(o["volume_path"]), media_type="application/pdf",
                        headers={**headers, "Content-Disposition": f'inline; filename="{quote(name)}"'})
    src, att = _source(o, cites)
    if not src or not _allowed(src):
        raise HTTPException(status_code=404, detail="Original not available")
    data, name = _download(src), att or src.rsplit("/", 1)[-1]
    if documents.ext_of(src) in documents.MAIL_EXT and att:
        try:
            mail = mailview.open_mail(data, documents.ext_of(src))
            path = mailview.find_part(mail, att)
            part = mailview.resolve(mail, path) if path is not None else None
            if isinstance(part, mailview.Part) and part.data is not None:
                data = part.data
        except (LookupError, ValueError):
            name = src.rsplit("/", 1)[-1]          # the email itself
    return Response(data, media_type="application/octet-stream",
                    headers={**headers, "Content-Disposition": f'attachment; filename="{quote(name)}"'})


@router.get("/orders/{order_id}/preview")
def preview_document(order_id: str, request: Request):
    """The source document as JSON for the in-app viewer:
      * PDF (volume_path)          -> {"kind": "pdf", "url"} (the frontend renders /document with pdf.js)
      * a part of an attached email (.eml / .msg) -> that part: a PDF ({"kind": "pdf", "url"}) or a workbook
                                      ({"kind": "sheet"}) read from the email, else the text below
      * spreadsheet / csv          -> {"kind": "sheet", "sheets": [...]} read from the workbook the citations name
                                      (allow-listed Volume path), else rebuilt from the cell-addressed text the
                                      extraction read
      * email body / text / other  -> {"kind": "text", "text"}
    When the order came from an attached email, "email_url" points at the email itself (/email/part)."""
    with userdb.user_connection(request) as conn:
        rows = query(
            f"SELECT order_id, doc_name, orig_format, volume_path, parsed_content, {_source_sql(conn)} "
            f"FROM {REVIEW_TABLE} WHERE order_id = :oid",
            {"oid": order_id}, conn=conn,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Order not found")
        o = rows[0]
        cites = [] if o.get("volume_path") else _citations(conn, order_id)
    text = o.get("parsed_content") or ""
    if o.get("volume_path"):
        if not _allowed(o["volume_path"]):
            return {"kind": "text", "text": text[:documents.MAX_TEXT_CHARS], "note": "document not available"}
        return {"kind": "pdf", "url": f"/api/orders/{quote(order_id, safe='')}/document"}

    src, att = _source(o, cites)
    name = att or src or o.get("doc_name") or ""
    note = None
    extra = {}
    if src and documents.ext_of(src) in documents.MAIL_EXT and _allowed(src):
        extra["email_url"] = f"/api/orders/{quote(order_id, safe='')}/email/part"
        try:
            mail = mailview.open_mail(_download(src), documents.ext_of(src))
            path = mailview.find_part(mail, att)
            part = mailview.resolve(mail, path) if path is not None else None
            if isinstance(part, mailview.Part) and part.data is not None and part.kind in ("pdf", "sheet"):
                shown = _part_preview(order_id, path, part)
                if shown.get("kind") in ("pdf", "sheet"):
                    return {**shown, **extra}
        except (LookupError, ValueError) as e:
            note = str(e)[:200]
    elif src and documents.ext_of(name) in documents.SHEET_EXT:
        if not _allowed(src):
            note = "document not available"
        else:
            try:
                return {**documents.sheet_preview(_download(src), documents.ext_of(name)), "source": "file",
                        "filename": att}
            except ValueError as e:
                note = str(e)[:200]
    if (o.get("orig_format") or "") == "spreadsheet" or documents.ext_of(name) in documents.SHEET_EXT:
        grid = documents.sheets_from_text(text)
        if grid:
            return {**grid, "source": "text", "note": note, **extra}
    return {"kind": "text", "text": text[:documents.MAX_TEXT_CHARS],
            "truncated": len(text) > documents.MAX_TEXT_CHARS, "note": note, **extra}
