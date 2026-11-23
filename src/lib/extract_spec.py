"""ai_extract (v2.1, precision mode) spec for the hybrid extractor: the same orders-array structure as ai_query (A).

Plain Python (no Spark): builds the ai_extract schema, the instructions (derived from arm A's registered prompt
template, so both arms apply the SAME business rules) and the SQL expression.
"""
import json
import re

AI_EXTRACT_VERSION = "2.1"
MAX_INSTRUCTIONS = 20_000          # ai_extract limit (characters)


def _f(t, d):
    return {"type": t, "description": d}


# Every table column is named explicitly (ai_extract shifts values between unnamed columns).
LINE_ITEM_PROPS = {
    "line_no": _f("integer", "Line or position number as printed on the document, if any."),
    "source_row": _f("string", "Spreadsheets only: the row label of this line exactly as shown at the start of the "
                               "line, e.g. \"S1R35\" (sheet 1, row 35). Empty for PDFs and emails."),
    "material_or_sku": _f("string", "The SUPPLIER's product code exactly as printed (keep leading zeros): the "
                                    "supplier / manufacturer / vendor reference or material number. If the document "
                                    "also has the buyer's own item number, never use that one. Otherwise the "
                                    "order-code / article-number column; else the EAN/barcode."),
    "ean": _f("string", "The line's EAN / UPC / GTIN barcode exactly as printed, if the document has a barcode "
                        "column — in addition to material_or_sku, even when material_or_sku holds another code."),
    "description": _f("string", "Product description as printed."),
    "quantity": _f("number", "ORDERED quantity from the ordered-quantity column only, as a plain number "
                             "read in the document's locale, without thousands separators (German \"1.000\" = 1000, "
                             "\"3,5\" = 3.5)."),
    "uom": _f("string", "Unit of measure as printed (EA, ST, PCS, CS ...), if shown."),
    "unit_price": _f("number", "Net unit price as a plain number, if shown. Never a recommended retail price (UVP, RRP, PVP): omit it then."),
}
ORDER_PROPS = {
    "po_number": _f("string", "The BUYER'S purchase-order number, copied exactly as printed. Omit if there is none."),
    "po_number_label": _f("string", "The label text printed next to the PO number (e.g. \"PO Number\", "
                                    "\"Bestellnummer\")."),
    "customer_name": _f("string", "Name of the retailer / store / salon / distributor PLACING the order "
                                  "(never Maison Solenne or one of its brands)."),
    "customer_number": _f("string", "The customer / account / sold-to number of the buyer at the supplier, if printed."),
    "order_date": _f("string", "Order date as printed."),
    "currency": _f("string", "Order currency as an ISO code (EUR, GBP, USD, CHF ...) if shown or clearly implied by "
                             "a currency symbol."),
    "sales_org": _f("string", "Supplier sales organisation code, if printed."),
    "ship_to": _f("string", "Ship-to / delivery address as printed."),
    "quantity_column": _f("string", "Header text of the ORDERED-quantity column."),
    "quantity_column_letter": _f("string", "Spreadsheets only: the column letter of the ordered-quantity column, "
                                           "e.g. \"E\"."),
    "line_items": {"type": "array", "description": "Ordered lines only: rows whose ordered-quantity cell holds a "
                                                   "number > 0. Never totals / subtotal rows.",
                   "items": {"type": "object", "properties": LINE_ITEM_PROPS}},
}
SCHEMA = {"orders": {"type": "array",
                     "description": "One entry per distinct PO number; exactly one entry if the document has no PO "
                                    "number.",
                     "items": {"type": "object", "properties": ORDER_PROPS}}}

HEADER_FIELDS = [k for k in ORDER_PROPS if k != "line_items"]
LINE_FIELDS = list(LINE_ITEM_PROPS)

# ai_extract-specific additions to arm A's rules (known ai_extract behaviours).
ADDENDUM = (
    "\n\nOUTPUT NOTES (structured extraction)\n"
    "- Fill every line-item field from its own column; never move a value into a neighbouring field. If a column "
    "is absent or the cell is empty, leave that field empty.\n"
    "- Never add totals, subtotals, carry-forward, freight, discount or summary rows as line items.\n"
    "- Never return catalogue rows whose ordered-quantity cell is empty or 0 (price lists and order forms list the "
    "whole catalogue).\n"
    "- Numbers: return quantity and unit_price as plain numbers, reading decimal and thousands separators in the "
    "document's locale (German/French/Spanish \"1.000\" = one thousand, \"12,50\" = twelve and a half; a "
    "spreadsheet cell like \"S1R5: E=920\" is 920).\n"
    "- Do not reformat codes: copy PO numbers and product codes character by character.\n"
    "- Product code: when a document has several code columns, take the SUPPLIER's code for material_or_sku: "
    "headers naming the supplier / manufacturer / vendor (\"Référence fournisseur\", \"Lieferantenartikelnummer\", "
    "\"Lief.Art.\", \"Referencia proveedor\", \"Codice fornitore\", material number) or addressed to the supplier "
    "(\"Ihre Artikelnummer\", \"Ihre Bestellnummer\", \"Your ref\", \"Votre référence\"). The buyer's own item "
    "number (\"N°\", \"Art.No\" / \"Artikelnr.\" of the retailer, \"our article\", internal code) is never the "
    "product code. Use the EAN/barcode for material_or_sku only when no supplier code is printed. Always also copy "
    "the barcode into ean when a barcode column exists.\n"
)


def instructions_from_prompt(template):
    """Arm A's registered prompt template -> ai_extract instructions with the same business rules.
    Drops what only applies to free-form JSON output (the 'Return JSON only' line, the self-rated confidence fields,
    the document placeholder) and appends ADDENDUM."""
    t = template.split("{{document}}")[0]
    t = re.sub(r"\s*Document:\s*$", "", t.rstrip())
    t = t.replace("Return JSON only, matching the schema.", "Fill the schema.")
    t = re.sub(r"\s*Set header_confidence and line_confidence in \[0,1\]\.", "", t)
    out = t.strip() + ADDENDUM
    if len(out) > MAX_INSTRUCTIONS:
        raise ValueError(f"instructions are {len(out)} chars (ai_extract max {MAX_INSTRUCTIONS})")
    return out


def _lit(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def options(instructions, mode="precision"):
    """ai_extract options map. mode='precision' or 'default' (= no mode option)."""
    o = {"version": AI_EXTRACT_VERSION, "enableConfidenceScores": "true", "enableCitations": "true",
         "instructions": instructions}
    if mode and mode != "default":
        o["mode"] = mode
    return o


def ai_extract_sql(content_expr, instructions, mode="precision", schema=None):
    """SQL expression calling ai_extract on `content_expr` (a STRING column, or ai_parse_document VARIANT)."""
    sch = json.dumps(schema or SCHEMA, ensure_ascii=False)
    opts = ", ".join(f"'{_lit(k)}', '{_lit(v)}'" for k, v in options(instructions, mode).items())
    return f"ai_extract({content_expr}, '{_lit(sch)}', map({opts}))"
