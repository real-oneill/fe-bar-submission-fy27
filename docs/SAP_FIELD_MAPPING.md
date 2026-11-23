# Order intake — what we extract and how it maps to SAP

What is read from each customer order (PDF, Excel, email body or attached email) and how each value is resolved
against SAP. SAP views are in `<sap_catalog>` (schema `db_fnd_proc`), client `MANDT = '100'`,
restricted to the deployment's sales orgs (`sap_sales_orgs`). Nothing is maintained by hand: no customer or
material mapping tables.

## Fields

| Extracted field | Required | SAP table (view) | SAP field | How it's resolved |
|---|---|---|---|---|
| Customer name | yes | KNA1 `v_customer_master` (+ ADRC `v_address_master_customer`) | `NAME1`, `NAME2` | Fuzzy match against every customer with a sales view in the sales orgs (see *Customer matching*). Gives the SAP **sold-to** (`KUNNR`). |
| Customer number | no | KNA1 `v_customer_master` | `KUNNR` | Zero-padded to 10 digits. Counts only together with some name or address evidence. |
| Customer address (in the name / ship-to text) | no | KNA1 + ADRC | postcode `PSTLZ` / `POST_CODE1`, city `ORT01` / `CITY1`, street `STREET` + `HOUSE_NUM1` (or `KNA1.STRAS`) | Supports the name match (postcode, city, street found in the order text). |
| Sold-to role | — | KNVP `v_customer_master_partner_functions` | `PARVW = 'AG'` (`KUNN2 = KUNNR`) | Only sold-tos are accepted. If only a ship-to / bill-to / payer matches (`PARVW` `WE` / `RE` / `RG`), its sold-to is taken through KNVP. |
| Sales org | — | KNVV `v_customer_sales_org_master` | `VKORG` | The sold-to's sales view in the configured orgs (the first listed wins when it has several). Not taken from the document. |
| Currency | no | KNVV | `WAERS` | From the sold-to's sales view. A different currency on the document is reported. |
| Deleted / order block | — | KNA1, KNVV | `LOEVM`, `AUFSD` | Deleted or blocked customers score lower and are flagged for review. |
| Ship-to | no | KNVP (`PARVW = 'WE'`) + KNA1/ADRC | `KUNN2` | Looked up among the sold-to's ship-tos in its sales org, then among all SAP ship-tos. One not linked to the sold-to is flagged. |
| Region | — | KNA1 | `LAND1` | Country → region via `region_map` (else the SAP affiliate). Drives who may review the order. |
| Customer PO number | yes | — (not SAP) | — | Copied as printed and checked against the document text. Sent in the IDoc (`E1EDK02` qualifier `001` → `VBAK-BSTNK`). |
| Order date | no | — | — | As printed. Sent with the customer PO (`E1EDK02.DATUM`). |
| Material / SKU (per line) | yes | MARA `v_material_master` + MVKE `v_material_master_sales` | `MATNR`; listed if `VKORG` in the order's sales org | Exact material number → EAN → first 6 characters (see *Material matching*). Only finished goods / trading goods (`MTART` `FERT`, `HAWA`). |
| EAN / barcode (per line) | no | MARA, MARM `v_material_master_unit_of_measures` | `EAN11` | Leading zeros ignored. Resolves when exactly one listed material has it. |
| Description (per line) | no | MAKT `v_material_text` | `MAKTX` (`SPRAS` `D` / `E`) | Shown next to the order text so the reviewer can confirm the material. Not used for matching. |
| Quantity (per line) | yes | — | — | As printed; never changed. Availability is checked by SAP. |
| Unit / unit price (per line) | no | MARA | base unit `MEINS` (shown) | As printed; prices are not checked. |

**On approval** the app writes an ORDERS05-style IDoc to `sap_outbound` (nothing is sent to SAP): `E1EDKA1`
`PARVW = AG` with the sold-to, `E1EDK01.CURCY`, `E1EDK02` (customer PO and date), and one `E1EDP01` per line
(`MATNR`, `MENGE`, `NETPR`, `ARKTX`). `E1EDP01.MATNR` is the **resolved SAP material**
(exact, EAN or prefix); the code the customer printed goes in `E1EDP19` qualifier `001` (customer material).

## Customer matching (fuzzy)

Both sides are normalized the same way: lower case, umlauts transliterated (ä → ae, ß → ss) and accents removed,
punctuation dropped, legal forms removed (GmbH, AG, KG, B.V., N.V., SAS, SARL, Ltd …), and `strasse` → `str`.
"Parfümerie Müller GmbH" becomes "parfuemerie mueller".

1. **Candidates.** Only SAP customers that share a distinctive word (4+ letters, not used by more than 3,000
   customers) or the postcode with the order, plus the customer whose number is printed.
2. **Evidence per candidate.**
   - *Name similarity* (0–1): the best of edit-distance similarity (Levenshtein) on the full name and on NAME1;
     0.9 when the order's name appears as whole words inside the SAP name ("Le Muster" in "Parfuemerie Le
     Muster"); or 0.9 × the share of the order's words found in the SAP name and city (at least two distinctive
     words; trade words like Parfümerie, Drogerie, Salon don't count).
   - *Address* (0–1): postcode found 0.40 + city 0.25 + street 0.35, searched in the order's customer and
     ship-to text.
   - *Customer number*: printed number = `KUNNR`.
3. **Accepted when any of these holds:** customer number plus some name or address evidence; name ≥ 0.60 and
   address ≥ 0.40; name ≥ 0.85; or address ≥ 0.75 and name ≥ 0.35.
4. **Score** = 0.6 × name + 0.4 × address (+0.3 with the customer number), minus 0.10 if deleted and 0.06 if
   order-blocked.
5. **Pick.** The best-scoring **sold-to** wins. If another sold-to scores within **0.05** of it, the order is
   *ambiguous*: no customer is picked and the reviewer chooses from the candidates.
6. **Fallback.** If the document doesn't resolve a customer (no name printed, the supplier printed as the customer, or no
   match), the same matching runs on hints: the sender's email domain, the sender's name, the subject and the
   file name, in that order. A customer found this way is always flagged for review.

## Material matching

Per line, in this order (the first that resolves wins):

1. **Exact material number** — the printed code (letters and digits only) equals `MATNR`.
2. **EAN / UPC** — the line's barcode (8–14 digits, leading zeros ignored) is on exactly one material listed for
   the sales org (MARA or MARM). On several → *ambiguous*.
3. **Prefix** — the first 6 characters match a material's prefix; the prefix is passed on and SAP resolves the
   full number.

The material must be listed (MVKE) in the order's sales org — any configured org while the customer is
unresolved. Sales status (`VMSTA`) is shown, never filtered on. Quantities are never changed.
