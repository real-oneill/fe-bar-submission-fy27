# Databricks notebook source
# MAGIC %md
# MAGIC ## Setup 02 — Register the extraction prompt in the MLflow Prompt Registry
# MAGIC Registers `order_extraction` (template + JSON response schema) into the customer's
# MAGIC UC schema and aliases it `production`. **Must run BEFORE the pipeline** — the Gold
# MAGIC stage loads `prompts:/<catalog>.<schema>.order_extraction@production` at runtime.
# MAGIC
# MAGIC Prompt-governance workflow: edit the template below (or in the UI) -> `register_prompt`
# MAGIC creates v2 -> compare eval runs -> `set_prompt_alias(..,'production',2)` to promote (or deploy with
# MAGIC `--var promote_prompt=true`). Re-running is safe: an unchanged template is not re-registered and
# MAGIC @production only moves on first install or when promote=true.

# COMMAND ----------
# MAGIC %pip install "mlflow>=3.1"
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import mlflow
dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "order_intake")
dbutils.widgets.text("promote", "false")   # "true" = move @production to the version registered here
dbutils.widgets.text("promote_extract_schema", "false")   # same, for order_extract_schema (the ai_extract spec)
dbutils.widgets.text("lib_path", "")       # <bundle files>/src/lib (extract_spec.py)
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
promote = dbutils.widgets.get("promote").strip().lower() == "true"
NAME = f"{catalog}.{schema}.order_extraction"

mlflow.set_registry_uri("databricks-uc")

line_item = {"type": "object", "properties": {
    "line_no": {"type": "integer"},
    "source_row": {"type": "string"},          # spreadsheets: row label as printed, e.g. "S1R35"
    "material_or_sku": {"type": "string"}, "description": {"type": "string"},
    "quantity": {"type": "number"}, "uom": {"type": "string"}, "unit_price": {"type": "number"},
    "line_confidence": {"type": "number"}},
    "required": ["material_or_sku", "quantity"]}
order = {"type": "object", "properties": {
    "po_number": {"type": "string"},
    "po_number_label": {"type": "string"},     # the label printed next to the PO number (grounding)
    "customer_name": {"type": "string"}, "customer_number": {"type": "string"},
    "order_date": {"type": "string"}, "currency": {"type": "string"}, "sales_org": {"type": "string"},
    "ship_to": {"type": "string"},
    "quantity_column": {"type": "string"},          # header text of the ORDERED-quantity column
    "quantity_column_letter": {"type": "string"},   # spreadsheets: its column letter, e.g. "E"
    "header_confidence": {"type": "number"},
    "line_items": {"type": "array", "items": line_item}},
    "required": ["line_items"]}
response_format = {"type": "json_schema", "json_schema": {"name": "po_batch", "strict": False,
    "schema": {"type": "object", "properties": {"orders": {"type": "array", "items": order}}, "required": ["orders"]}}}

# Supplier = Maison Solenne (fictional). NEVER the customer. (Extend this list as needed.)
SUPPLIER_ENTITIES = (
    "Maison Solenne (any country entity: S.A.S., GmbH, Ltd, Inc., FZE, Travel Retail), its customer-orders / "
    "field-sales teams, and the brands Solenne Paris, Kōri Botanicals / Kori Botanicals, Atelier Noor, Velour "
    "Cosmetics, Thornfield Grooming, Mistral Hair, Lune Rouge, Ember & Oak; and any address at maisonsolenne.*"
)

template = (
    "You extract retailer purchase orders sent TO Maison Solenne, for entry into SAP. "
    "Return JSON only, matching the schema.\n\n"
    "HOW THE DOCUMENT IS SHOWN\n"
    "- Spreadsheets are shown cell by cell: each line is one sheet row, e.g. "
    "\"S1R35: A=Shampoo | C=AX10010000 | E=3 | F=29.7\" means sheet 1, row 35, column A = Shampoo, etc. "
    "A column letter that is missing from a row means that cell is EMPTY. Use the header row's letters to know "
    "what each column is; never assume position.\n"
    "- PDFs are shown as text with HTML tables; an empty <td></td> is an empty cell.\n\n"
    "ORDERS\n"
    "1. Return one entry in `orders` per distinct PO number. If the document has no PO number, return exactly one order.\n\n"
    "PO NUMBER\n"
    "2. `po_number` is the BUYER'S order reference, copied exactly as printed. It is printed next to a label such as "
    "PO, P.O., Purchase Order No., Order No., Order number, Bestellnummer, Bestell-Nr., Auftragsnummer, "
    "Kunden-Auftragsnummer, Bestellreferenz, Referenz, N° de commande, Numéro de commande, Bon de commande N°, "
    "Commande n°, Pedido, Nº de pedido, Ordine n., Inkoopopdracht, Ordernummer, Bestelnummer, Sipariş No. "
    "Put that label text in `po_number_label`.\n"
    "3. A PO number is NEVER: a date; the document title, heading or file name (e.g. \"BON DE COMMANDE AOÛT 2026\", "
    "\"Order form\"); a product code, EAN or SKU; a customer, account or vendor number; an invoice, delivery-note, "
    "quote or page number; a phone number. If there is no PO number, OMIT `po_number` — never guess.\n\n"
    "CUSTOMER\n"
    "4. The customer is the retailer, store, salon or distributor that PLACES the order (look at sold-to / bill-to / "
    "ship-to / Rechnungs- or Lieferadresse / Kunde / Client / customer name and number fields, the sender and "
    "signature of an email, the fine print or footer of the page, and the letterhead of a document the buyer issued).\n"
    "5. The SUPPLIER is the recipient and must NEVER be returned as `customer_name`: " + SUPPLIER_ENTITIES + ". "
    "Order forms and price lists are often the supplier's own template, so their title and logo are the supplier, "
    "not the customer. A store or salon whose name merely CONTAINS a brand (e.g. \"Studio Mira Lune Rouge "
    "exclusive Salon\") IS a customer. If only the supplier can be identified, OMIT `customer_name`.\n\n"
    "LINE ITEMS AND QUANTITY\n"
    "6. First find the table's header row and the ONE column where the customer entered the ORDERED quantity "
    "(e.g. QTY, Qty, Quantity, Order quantity, Bestellmenge, Menge, Anzahl, Stück, Cantidad, Uds, Qté, Quantité, "
    "Aantal, Quantità, Adet; on periodic order forms \"Total periode\" / \"Total période\" / \"Total period\" is the "
    "quantity ordered for that period, not a grand total). Report its header text in `quantity_column` and, for spreadsheets, its letter in "
    "`quantity_column_letter`.\n"
    "7. These are NOT the ordered quantity: first-order / initial / launch quantities (\"First Order Qty\", "
    "Erstbestellung, Erstausstattung), minimum order quantity (MOQ, Mindestmenge), pack / case / inner / outer sizes "
    "(VE, PCB, colisage), stock or on-hand, tester or display quantities, prices (UVP, EK, EP, RRP, PVP, prix), "
    "totals and price×quantity columns, EAN/barcodes, and product sizes (ml, g). A non-zero line total or "
    "price×quantity cell confirms a row was ordered — use it as a cross-check, never as the quantity.\n"
    "8. Return ONLY rows whose ordered-quantity cell contains a number greater than 0. Order forms and price lists "
    "list the whole catalog and most rows are blank in that column — skip those. Do not skip a row because OTHER "
    "columns are blank, and never drop the LAST row of a table or a row that lacks a code or description.\n"
    "8a. Header labels can sit in a merged cell or one column off from their values. Confirm the column from the data: "
    "if the form has a line-total / price×quantity column, the ordered quantity is the value that multiplies the unit "
    "price to give that total, and a row whose total is exactly 0 is NOT ordered (an EMPTY total cell proves nothing). "
    "Report the letter of the column that actually contains the quantities.\n"

    "9. For each line: `material_or_sku` = the product/order code exactly as printed (keep leading zeros; prefer the "
    "order-code/material column, otherwise the EAN); `quantity` = the value from the ordered-quantity column, "
    "reading decimal and thousands separators in the document's locale (German \"1.000\" = 1000); `source_row` = the "
    "row label for spreadsheets (e.g. \"S1R35\"); `unit_price` = the net unit price if shown. Never use a "
    "recommended retail price (UVP, RRP, PVP, MSRP, prix conseillé) as `unit_price`; if only that is printed, omit "
    "`unit_price`. `description` is the product text of the row, never a column header (\"Originalware\", \"Artikel\", "
    "\"Article\", \"Bezeichnung\", \"Designation\" are headers).\n"
    "9a. In free-text emails a number after \"nr\", \"no.\", \"shade\", \"teinte\", \"kleur\", \"tint\" is a shade number "
    "of the product named before it, not a product code; the quantity is the number next to \"x\", \"maal\", \"fois\", "
    "\"stuks\", \"pcs\" (\"concealer nr 08, 2 maal\" = concealer, shade 08, quantity 2). Put the shade in the "
    "description and leave `material_or_sku` empty unless a real code is printed.\n\n"
    "GENERAL\n"
    "10. Copy codes and numbers verbatim. Do not invent placeholder values such as UNKNOWN or N/A — omit a field you "
    "cannot find. Set header_confidence and line_confidence in [0,1].\n\n"
    "Document:\n\n{{document}}"
)

# Idempotent (safe to run on every bootstrap): reuse the newest version if its template + schema are
# unchanged, otherwise register a new one. @production is set on first install, or when promote=true —
# so a re-run never silently moves a version someone promoted by hand.
latest = None
for v in range(200, 0, -1):
    try:
        latest = mlflow.genai.load_prompt(f"prompts:/{NAME}/{v}")
        break
    except Exception:
        continue
if latest is not None and latest.template == template and latest.response_format == response_format:
    pv = latest
    print(f"{NAME} v{pv.version} already has this template — not re-registered")
else:
    pv = mlflow.register_prompt(
        name=NAME, template=template,
        commit_message="v3 (customer feedback): Total periode = ordered quantity; keep last/sparse rows; no UVP as unit price; "
                       "no column headers as description; shade numbers in emails; ship-to/customer from fine print",
        tags={"parser": "ai_parse_document", "extractor": "ai_query", "schema": "orders_array_v2"},
        response_format=response_format,
    )
    print(f"Registered {NAME} v{pv.version}")

try:
    current = mlflow.genai.load_prompt(f"prompts:/{NAME}@production").version
except Exception:
    current = None
if current is None or promote:
    mlflow.set_prompt_alias(NAME, "production", pv.version)
    print(f"alias production -> v{pv.version}" + (f" (was v{current})" if current else " (first install)"))
else:
    print(f"alias production stays on v{current}" + ("" if current == pv.version else
          f"; to use v{pv.version} deploy with --var promote_prompt=true or set the alias by hand"))

# COMMAND ----------
# MAGIC %md
# MAGIC ### `order_extract_schema` — the ai_extract (v2.1, precision mode) spec of the hybrid extractor
# MAGIC Template = the ai_extract **instructions** (the business rules above, adapted: src/lib/extract_spec.py);
# MAGIC response_format = the ai_extract **schema** (orders[] with header fields + line_items[], every column named).
# MAGIC Gold (extraction_mode=hybrid) loads `prompts:/<catalog>.<schema>.order_extract_schema@production`.
# MAGIC Its own alias only: `order_extraction`'s aliases are never touched here. @production moves on first install or
# MAGIC with promote_extract_schema=true.

# COMMAND ----------
import os
import sys
lib = dbutils.widgets.get("lib_path").strip() or os.path.abspath(os.path.join(os.getcwd(), "..", "lib"))
sys.path.insert(0, lib)
import extract_spec as _xs

SNAME = f"{catalog}.{schema}.order_extract_schema"
promote_x = dbutils.widgets.get("promote_extract_schema").strip().lower() == "true"
x_template = _xs.instructions_from_prompt(template)
x_schema = _xs.SCHEMA
latest_x = None
for v in range(200, 0, -1):
    try:
        latest_x = mlflow.genai.load_prompt(f"prompts:/{SNAME}/{v}")
        break
    except Exception:
        continue
if latest_x is not None and latest_x.template == x_template and latest_x.response_format == x_schema:
    xv = latest_x
    print(f"{SNAME} v{xv.version} already has this spec — not re-registered")
else:
    xv = mlflow.register_prompt(
        name=SNAME, template=x_template, response_format=x_schema,
        commit_message="ai_extract v2.1 precision spec: orders[] schema (every column named) + instructions derived "
                       "from order_extraction",
        tags={"extractor": "ai_extract", "ai_extract_version": _xs.AI_EXTRACT_VERSION, "mode": "precision",
              "schema": "orders_array_v2"})
    print(f"Registered {SNAME} v{xv.version}")
try:
    current_x = mlflow.genai.load_prompt(f"prompts:/{SNAME}@production").version
except Exception:
    current_x = None
if current_x is None or promote_x:
    mlflow.set_prompt_alias(SNAME, "production", xv.version)
    print(f"{SNAME}: alias production -> v{xv.version}" + (f" (was v{current_x})" if current_x else " (first install)"))
else:
    print(f"{SNAME}: alias production stays on v{current_x}")
