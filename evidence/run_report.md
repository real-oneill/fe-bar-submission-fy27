# FE Bar FY27: run report (collected 2026-11-23 18:08 UTC)

Live query results from `evan_aws_01_catalog.fe_bar_fy27` on `https://fevm-evan-aws-01.cloud.databricks.com` (SQL warehouse `4a29d0ae256f1d92`), produced by the accelerator's
medallion pipeline, the review-queue jobs and `src/fe_bar/10_evaluate.py` on the 184 fictional Maison Solenne documents.
Every number below was read back from the tables when this file was generated; the CSVs are in `evidence/results/`.

## Headline

- **184 documents / 220 purchase orders / 2719 answer-key lines** processed end to end.
- Line accuracy (right material AND quantity): **0.778**; PO number found: **0.941**; customer resolved to the right sold-to: **0.905**.
- Orders routed to human review: **0.782**; orders NOT routed but wrong (false confidence): **0**.
- Effort on these 184 documents: **62.6 h** keyed by hand vs **17.4 h** with the pipeline (review + re-keying misses): **0.723 of the effort saved**.
- Annualised at the assumed volume (`roi_assumptions`): **8.1 FTE today -> 2.2 FTE with the pipeline = 5.9 FTE saved** (9832 hours, about $393294 labour a year).

## Table row counts (bronze -> silver -> gold -> queue)

| t | n |
|---|---|
| email_attachments (bronze) | 184 |
| parsed_attachments (silver) | 222 |
| extracted_parsed (gold) | 222 |
| purchase_orders (gold lines) | 2703 |
| review_orders (queue) | 217 |
| gt_manifest (answer key docs) | 184 |
| gt_lines (answer key lines) | 2719 |

## Headline metrics (raw)

| documents | purchase_orders | answer_key_lines | po_found_rate | customer_correct_rate | line_accuracy | review_rate | false_confidence_pos | corpus_manual_hours | corpus_assisted_hours | time_saved_share | annual_hours_saved | fte_manual | fte_assisted | fte_saved | annual_usd_saved |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 184 | 220 | 2719 | 0.941 | 0.905 | 0.778 | 0.782 | 0 | 62.6 | 17.4 | 0.723 | 9832 | 8.1 | 2.2 | 5.9 | 393294 |

## By document type (channel)

| channel | docs | lines | line_accuracy | customer_acc | review_rate | false_conf | fte_saved | annual_usd_saved |
|---|---|---|---|---|---|---|---|---|
| excel_buysheet | 16 | 623 | 0.829 | 1.0 | 0.88 | 0 | 1.47 | 98496 |
| amended_scan | 16 | 388 | 0.887 | 1.0 | 0.938 | 0 | 1.02 | 68297 |
| fax | 16 | 271 | 1.0 | 0.938 | 0.313 | 0 | 0.81 | 54547 |
| email_pdf | 16 | 293 | 1.0 | 1.0 | 0.313 | 0 | 0.57 | 38058 |
| email_pricelist | 16 | 153 | 0.993 | 1.0 | 0.063 | 0 | 0.39 | 26420 |
| erp_edi | 16 | 313 | 0.757 | 1.0 | 1.0 | 0 | 0.35 | 23739 |
| portal_export | 16 | 234 | 1.0 | 1.0 | 0.813 | 0 | 0.34 | 22899 |
| handwritten | 16 | 126 | 0.0 | 0.875 | 1.0 | 0 | 0.34 | 22971 |
| multimodal | 24 | 103 | 0.194 | 0.25 | 1.0 | 0 | 0.22 | 15033 |
| email_body | 16 | 126 | 0.339 | 1.0 | 0.938 | 0 | 0.18 | 12199 |
| phone | 16 | 89 | 0.0 | 1.0 | 1.0 | 0 | 0.16 | 10634 |

## By region

| region | docs | pos | line_accuracy | review_rate | fte_saved | annual_usd_saved |
|---|---|---|---|---|---|---|
| North America | 53 | 55 | 0.899 | 0.527 | 1.47 | 98573 |
| UK & Ireland | 40 | 40 | 0.649 | 0.975 | 1.25 | 84275 |
| Middle East | 36 | 70 | 0.731 | 0.9 | 1.67 | 112471 |
| DACH | 24 | 24 | 0.968 | 0.875 | 0.42 | 28428 |
| Italy | 18 | 18 | 0.0 | 1.0 | 0.37 | 24783 |
| France | 13 | 13 | 1.0 | 0.154 | 0.67 | 44765 |

## By complexity

| complexity | docs | line_accuracy | review_rate | false_conf | fte_saved |
|---|---|---|---|---|---|
| 1 | 43 | 0.933 | 0.698 | 0 | 0.85 |
| 2 | 43 | 0.769 | 0.622 | 0 | 0.99 |
| 3 | 74 | 0.778 | 0.833 | 0 | 3.07 |
| 4 | 24 | 0.5 | 1.0 | 0 | 0.94 |

## By injected problem type

| issue_type | docs | line_accuracy | review_rate |
|---|---|---|---|
| out_of_stock | 113 | 0.827 | 0.732 |
| customer_name_variant | 69 | 0.76 | 0.771 |
| unresolvable_sku | 52 | 0.82 | 0.961 |
| price_mismatch | 47 | 0.881 | 0.787 |
| xref_missing_but_resolvable | 42 | 0.83 | 0.923 |
| uom_cases | 33 | 0.779 | 0.913 |
| discontinued_sku_successor | 33 | 1.0 | 0.485 |
| past_or_weekend_delivery_date | 23 | 0.84 | 0.865 |
| free_goods | 23 | 0.953 | 0.739 |
| multi_po_document | 18 | 0.8 | 0.889 |
| missing_po_number | 16 | 0.125 | 1.0 |
| zero_qty_rows_trap | 16 | 0.993 | 0.063 |
| handwritten_amendment | 15 | 0.891 | 0.933 |
| mixed_currency | 14 | 0.84 | 0.87 |
| mid_call_correction | 13 | 0.0 | 1.0 |
| size_omitted_default_rule | 12 | 0.0 | 1.0 |
| promo_discount_pricing | 8 | 0.714 | 1.0 |
| closed_dc_reroute | 7 | 0.737 | 1.0 |
| photo_of_handwritten_list | 7 | 0.0 | 1.0 |
| garbled_po_number | 6 | 0.575 | 0.667 |
| handwritten_customer_number | 6 | 0.667 | 1.0 |
| identify_by_image_caption | 6 | 0.0 | 1.0 |
| duplicate_submission | 5 | 0.894 | 1.0 |
| inline_images_only | 5 | 0.0 | 1.0 |
| identify_by_photo | 5 | 0.0 | 1.0 |
| amendment | 5 | 0.125 | 1.0 |
| large_document | 4 | 0.9 | 0.875 |
| handwritten_correction | 4 | 0.5 | 1.0 |
| unordered_offer_rows | 4 | 0.5 | 1.0 |
| tester_free_goods | 4 | 0.5 | 1.0 |
| circled_then_crossed_out | 3 | 0.0 | 1.0 |
| ship_to_override_note | 2 | 0.375 | 1.0 |
| chat_correction | 2 | 0.0 | 1.0 |
| photo_of_screen | 2 | 0.0 | 1.0 |
| page_upside_down | 1 | 0.5 | 1.0 |

## Answer-key lines by class

| line_class | lines | material_found | material_and_qty_correct | flagged |
|---|---|---|---|---|
| orderable | 2605 | 0.778 | 0.778 | 0.302 |
| unresolvable | 97 | 0.0 | 0.0 |  |
| cancel_line | 17 | 0.471 | 0.471 | 0.0 |

## Savings assumptions (illustrative, editable)

| parameter | value | unit | rationale |
|---|---|---|---|
| manual_min_per_order | 3.0 | minutes | Open the email or file, find PO, customer and ship-to, create the order header in the ERP |
| manual_min_per_line | 0.75 | minutes | Key one line: look up the material (retailer item, GTIN or name), quantity, UOM, price |
| complexity_mult_1 | 1.0 | x | Complexity 1 (EDI, portal export): manual effort multiplier |
| complexity_mult_2 | 1.2 | x | Complexity 2 (Excel, price list, email body) |
| complexity_mult_3 | 1.5 | x | Complexity 3 (fax, phone, handwritten, amended scans) |
| complexity_mult_4 | 2.0 | x | Complexity 4 (multi-PO, 90+ lines, phone photos, multimodal) |
| review_min_clean_order | 0.5 | minutes | Glance and approve an order with no review reasons |
| review_min_flagged_order | 2.0 | minutes | Open a flagged order in the Review App and check the header |
| review_min_flagged_line | 0.25 | minutes | Check one line next to the source document |
| rework_min_per_missed_line | 0.75 | minutes | Key a line the pipeline missed or got wrong (same as manual) |
| loaded_cost_per_hour_usd | 40.0 | USD/hour | Fully loaded cost of a customer-service order-entry rep |
| annual_documents | 40000.0 | documents/year | Inbound order documents a year (about 160 per working day) with the corpus' channel mix |
| fte_productive_hours_per_year | 1680.0 | hours/FTE/year | Productive hours of one full-time rep (after leave, training, meetings) |

## Review queue: 25 lowest-confidence orders (what a reviewer sees first)

| order_id | orig_format | po_number | customer_name | resolved_sap_sold_to | region | n_lines | overall_confidence | status | review_reasons |
|---|---|---|---|---|---|---|---|---|---|
| DOC-00155#order-1 | pdf |  |  | 400800 | UK & Ireland | 3 | 0.0 | pending | No customer PO number found in the document; No customer identified; 3 line(s) not verified against the source row; Extracted 3 lines but form has 0 filled quan |
| DOC-00156#order-1 | pdf |  |  | 300500 | Middle East | 3 | 0.138 | pending | No customer PO number found in the document; No customer identified; 2 line(s) not verified against the source row; Extracted 3 lines but form has 0 filled quan |
| DOC-00157#order-1 | pdf |  | Parfümerie Lindqvist | 200652 | DACH | 3 | 0.158 | pending | No customer PO number found in the document; 3 line(s) not verified against the source row; Extracted 3 lines but form has 0 filled quantity rows; 1 SKU(s) not  |
| DOC-00158#C3698 | pdf | C3698 |  | 300700 | Middle East | 3 | 0.166 | pending | No customer identified; 3 line(s) not verified against the source row; Extracted 3 lines but form has 0 filled quantity rows; 1 SKU(s) not in material master |
| doc-1bab4c5eed01#order-1 | pdf |  |  | 200300 | France | 2 | 0.183 | pending | No customer PO number found in the document; No customer identified; 2 line(s) not verified against the source row; 2 SKU(s) not in material master |
| doc-91168e6f5025#order-1 | pdf |  |  | 200400 | Italy | 2 | 0.189 | pending | No customer PO number found in the document; No customer identified; 2 line(s) not verified against the source row; 2 SKU(s) not in material master |
| DOC-00046#order-1 | pdf |  | CORSO PROFUMERIE | 200400 | Italy | 4 | 0.305 | pending | No customer PO number found in the document; 4 line(s) not verified against the source row; Extracted 4 lines but form has 3 filled quantity rows; 4 SKU(s) not  |
| DOC-00058#696---2-6-1 | pdf | 696 / 2 6 | Corso Profumerie | 200400 | Italy | 5 | 0.317 | pending | Customer PO number looks like a title or heading: 696 / 2 6; 5 line(s) not verified against the source row; Extracted 5 lines but form has 4 filled quantity row |
| DOC-00166#order-1 | pdf |  | Corso Centro | 200400 | Italy | 4 | 0.318 | pending | No customer PO number found in the document; Customer not in customer master; 4 line(s) not verified against the source row; 4 SKU(s) not in material master |
| DOC-00167#order-1 | pdf |  | KSS Manchester | 200653 | DACH | 5 | 0.32 | pending | No customer PO number found in the document; Customer not in customer master; 5 line(s) not verified against the source row; 5 SKU(s) not in material master |
| DOC-00165#order-1 | pdf |  | KSS Park | 400800 | UK & Ireland | 4 | 0.325 | pending | No customer PO number found in the document; Customer not in customer master; 4 line(s) not verified against the source row; 4 SKU(s) not in material master |
| DOC-00168#order-1 | pdf |  | KSS Manchester | 200653 | DACH | 5 | 0.325 | pending | No customer PO number found in the document; Customer not in customer master; 5 line(s) not verified against the source row; 5 SKU(s) not in material master |
| DOC-00162#HV-644280 | pdf | HV-644280 |  | 200600 | DACH | 6 | 0.333 | pending | No customer identified; 6 line(s) not verified against the source row; 6 SKU(s) not in material master |
| DOC-00160#HV-456261 | pdf | HV-456261 |  | 300500 | Middle East | 3 | 0.35 | pending | No customer identified; 3 line(s) not verified against the source row; 3 SKU(s) not in material master |
| DOC-00043#order-1 | pdf |  | CORSO PROFUMERIE | 200400 | Italy | 3 | 0.351 | pending | No customer PO number found in the document; 3 line(s) not verified against the source row; 3 SKU(s) not in material master |
| DOC-00161#HV-811362 | pdf | HV-811362 |  | 100200 | North America | 4 | 0.352 | pending | No customer identified; 4 line(s) not verified against the source row; 4 SKU(s) not in material master |
| DOC-00103#order-1 | email/text |  | KSS | 400800 | UK & Ireland | 7 | 0.375 | pending | No customer PO number found in the document; 7 line(s) not verified against the source row; 7 SKU(s) not in material master |
| DOC-00104#order-1 | email/text |  | Kensington Salon Supply | 400800 | UK & Ireland | 5 | 0.375 | pending | No customer PO number found in the document; 5 line(s) not verified against the source row; 5 SKU(s) not in material master |
| DOC-00105#KSS7231-1 | email/text | KSS7231 | Kensington Salon Supply | 400800 | UK & Ireland | 8 | 0.375 | pending | Customer PO number not found in the document: KSS7231; 8 line(s) not verified against the source row; 8 SKU(s) not in material master |
| DOC-00106#KSS7842-1 | email/text | KSS7842 | KSS | 400800 | UK & Ireland | 6 | 0.375 | pending | Customer PO number not found in the document: KSS7842; 6 line(s) not verified against the source row; 6 SKU(s) not in material master |
| DOC-00107#KSS7257-1 | email/text | KSS7257 | Kensington Salons | 400800 | UK & Ireland | 6 | 0.375 | pending | Customer PO number not found in the document: KSS7257; 6 line(s) not verified against the source row; 6 SKU(s) not in material master |
| DOC-00108#order-1 | email/text |  | Kensington Salons | 400800 | UK & Ireland | 7 | 0.375 | pending | No customer PO number found in the document; 7 line(s) not verified against the source row; 7 SKU(s) not in material master |
| DOC-00109#KSS7680-1 | email/text | KSS7680 | Kensington Salon Supply | 400800 | UK & Ireland | 8 | 0.375 | pending | Customer PO number not found in the document: KSS7680; 8 line(s) not verified against the source row; 8 SKU(s) not in material master |
| DOC-00110#KSS7513-1 | email/text | KSS7513 | Kensington Salons | 400800 | UK & Ireland | 4 | 0.375 | pending | Customer PO number not found in the document: KSS7513; 4 line(s) not verified against the source row; 4 SKU(s) not in material master |
| DOC-00111#KSS7642-1 | email/text | KSS7642 | Kensington Salon Supply | 400800 | UK & Ireland | 4 | 0.375 | pending | Customer PO number not found in the document: KSS7642; 4 line(s) not verified against the source row; 4 SKU(s) not in material master |

## Review queue: 15 highest-confidence orders

| order_id | orig_format | po_number | customer_name | resolved_sap_sold_to | region | n_lines | overall_confidence | status | review_reasons |
|---|---|---|---|---|---|---|---|---|---|
| DOC-00061#MTR-CDG-26-2490 | spreadsheet | MTR-CDG-26-2490 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 4 | 1.0 | pending | 1 SKU(s) not in material master |
| DOC-00061#MTR-DXB-26-4943 | spreadsheet | MTR-DXB-26-4943 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 11 | 1.0 | pending | 2 SKU(s) not in material master |
| DOC-00061#MTR-JFK-26-7492 | spreadsheet | MTR-JFK-26-7492 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 5 | 1.0 | pending |  |
| DOC-00061#MTR-LHR-26-6748 | spreadsheet | MTR-LHR-26-6748 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 9 | 1.0 | pending | 1 SKU(s) not in material master |
| DOC-00062#MTR-DXB-26-9176 | spreadsheet | MTR-DXB-26-9176 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 4 | 1.0 | pending | 1 SKU(s) not in material master |
| DOC-00062#MTR-JFK-26-1318 | spreadsheet | MTR-JFK-26-1318 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 16 | 1.0 | pending | 4 SKU(s) not in material master |
| DOC-00064#MTR-CDG-26-4779 | spreadsheet | MTR-CDG-26-4779 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 16 | 1.0 | pending |  |
| DOC-00064#MTR-DXB-26-7119 | spreadsheet | MTR-DXB-26-7119 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 12 | 1.0 | pending | 2 SKU(s) not in material master |
| DOC-00064#MTR-JFK-26-1304 | spreadsheet | MTR-JFK-26-1304 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 14 | 1.0 | pending | 3 SKU(s) not in material master |
| DOC-00064#MTR-SIN-26-2231 | spreadsheet | MTR-SIN-26-2231 | MERIDIAN TRAVEL RETAIL | 300500 | Middle East | 14 | 1.0 | pending | 1 SKU(s) not in material master |
| DOC-00065#MTR-CDG-26-1507 | spreadsheet | MTR-CDG-26-1507 | MERIDIAN TRAVEL RETAIL FZE | 300500 | Middle East | 8 | 1.0 | pending |  |
| DOC-00065#MTR-DXB-26-7370 | spreadsheet | MTR-DXB-26-7370 | MERIDIAN TRAVEL RETAIL FZE | 300500 | Middle East | 5 | 1.0 | pending |  |
| DOC-00065#MTR-JFK-26-4476 | spreadsheet | MTR-JFK-26-4476 | MERIDIAN TRAVEL RETAIL FZE | 300500 | Middle East | 5 | 1.0 | pending | 1 SKU(s) not in material master |
| DOC-00065#MTR-SIN-26-7975 | spreadsheet | MTR-SIN-26-7975 | MERIDIAN TRAVEL RETAIL FZE | 300500 | Middle East | 18 | 1.0 | pending | 2 SKU(s) not in material master |
| DOC-00066#MTR-CDG-26-7170 | spreadsheet | MTR-CDG-26-7170 | MERIDIAN TR | 300500 | Middle East | 5 | 1.0 | pending | 2 SKU(s) not in material master |

## Sample: answer-key lines vs what was extracted (5 documents)

| doc_id | channel | po_number | line_no | raw_item_text | truth_material | qty_as_written | qty_each | material_found | qty_correct | line_correct |
|---|---|---|---|---|---|---|---|---|---|---|
| DOC-00001 | erp_edi | 4572176148 | 1 | VELOUR COSMETICS VELVET MATTE FOUNDATION 30 ML 2N LINEN | MS4010290 | 12.0 | 12.0 | true | true | true |
| DOC-00001 | erp_edi | 4572176148 | 2 | MISTRAL HAIR SEA SALT TEXTURE SPRAY 150 ML | MS6030079 | 36.0 | 36.0 | false | false | false |
| DOC-00001 | erp_edi | 4572176148 | 3 | ATELIER NOOR CUIR FUMÉ EXTRAIT DE PARFUM 50 ML | MS3050040 | 36.0 | 36.0 | false | false | false |
| DOC-00001 | erp_edi | 4572176148 | 4 | SOLENNE PARIS CRÈME LUMIÈRE DAY CREAM 30 ML | MS1010158 | 1.0 | 6.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 1 | MISTRAL HAIR SCALP BALANCE SERUM 50 ML | MS6060099 | 2.0 | 24.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 2 | VELOUR COSMETICS BROW SCULPT PENCIL SOFT BLACK | MS4030315 | 36.0 | 36.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 3 | VELOUR COSMETICS SOFT FOCUS BLUSH ROSEWOOD | MS4020174 | 24.0 | 24.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 4 | MISTRAL HAIR COLOUR GUARD SHAMPOO 250 ML | MS6050064 | 36.0 | 36.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 5 | THORNFIELD GROOMING CEDAR SHAVE CREAM 150 ML | MS5000191 | 48.0 | 48.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 6 | KŌRI BOTANICALS HINOKI CALMING TONER 100 ML | MS2040026 | 12.0 | 12.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 7 | LUNE ROUGE LACQUER NAIL COLOUR 110 BALLET | MS7000295 | 24.0 | 24.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 8 | MISTRAL HAIR CURL DEFINE CREAM 150 ML | MS6040043 | 120.0 | 120.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 9 | EMBER & OAK BLACK TEA ROOM SPRAY 100 ML | MS8030088 | 4.0 | 4.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 10 | KŌRI BOTANICALS RICE ENZYME POLISH 100 ML | MS2030164 | 12.0 | 12.0 | false | false | false |
| DOC-00001 | erp_edi | 4574104909 | 11 | ATELIER NOOR NÉROLI SOLEIL EAU DE TOILETTE 50 ML | MS3030052 | 6.0 | 6.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 12 | VELOUR COSMETICS VELVET MATTE FOUNDATION 30 ML 1W IVORY | MS4010167 | 48.0 | 48.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 13 | KŌRI BOTANICALS CAMELLIA BARRIER CREAM 100 ML | MS2020129 | 2.0 | 12.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 14 | EMBER & OAK WILD MINT CANDLE 400 G | MS8040171 | 40.0 | 40.0 | true | true | true |
| DOC-00001 | erp_edi | 4574104909 | 15 | MISTRAL HAIR HYDRA REPAIR CONDITIONER 250 ML | MS6010029 | 24.0 | 24.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 1 | Kōri Botanicals Sakura Dew Sleeping Mask 100 ml | MS2050139 | 6.0 | 6.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 2 | Mistral Hair Bond Rebuild Mask 200 ml | MS6020068 | 48.0 | 48.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 3 | Mistral Hair Scalp Balance Serum 50 ml | MS6060099 | 96.0 | 96.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 4 | Solenne Paris Contour des Yeux Eye Cream 15 ml | MS1040049 | 48.0 | 48.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 5 | Solenne Paris Eau Micellaire Cleansing Water 200 ml | MS1030011 | 24.0 | 24.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 6 | Kōri Botanicals Camellia Barrier Cream 100 ml | MS2020129 | 36.0 | 36.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 7 | Kōri Botanicals Sakura Dew Sleeping Mask 50 ml | MS2050041 | 12.0 | 12.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 8 | Solenne Paris Sérum Absolu Regenerating Serum 15 ml | MS1000013 | 12.0 | 12.0 | true | true | true |
| DOC-00040 | fax | BC-59061 | 9 | Mistral Hair Sea Salt Texture Spray 150 ml | MS6030079 | 12.0 | 12.0 | true | true | true |
| DOC-00100 | email_body | ANT/PO/26/0679 | 1 | Velvet Matte Foundation 30 ml - 4N Honey | MS4010684 | 72.0 | 72.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 2 | Satin Lip Colour 12 Rouge Velours | MS4000478 | 144.0 | 144.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 3 | Solenne Paris Crème Lumière Day Cream 30ml | MS1010158 | 36.0 | 36.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 4 | Velvet Matte Foundation 30 ml - 1W Ivory | MS4010167 | 24.0 | 24.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 5 | Néroli Soleil EDT - 100ml | MS3030152 | 24.0 | 24.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 6 | Velvet Matte Foundation 30 ml - 5W Toffee | MS4010990 | 144.0 | 144.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 7 | Velour Cosmetics Brow Sculpt Pencil Soft Black (EAN 2950455623867) | MS4030315 | 24.0 | 24.0 | true | true | true |
| DOC-00100 | email_body | ANT/PO/26/0679 | 8 | Soft Focus Blush Apricot | MS4020362 | 24.0 | 24.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 9 | Iris Poudré EDP - 50ml | MS3060057 | 48.0 | 48.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 10 | Musc Blanc EDP - 100ml | MS3040237 | 12.0 | 12.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 11 | Velour Cosmetics Velvet Matte Foundation 30 ml 1N Porcelain | MS4010022 | 48.0 | 48.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 12 | Solenne Paris Sérum Absolu Regenerating Serum 30ml | MS1000137 | 12.0 | 12.0 | false | false | false |
| DOC-00100 | email_body | ANT/PO/26/0679 | 13 | Satin Lip Colour - 18 Berry Noir | MS4000699 | 144.0 | 144.0 | false | false | false |
| DOC-00150 | amended_scan | HV-572437 | 1 | Velour Cosmetics Soft Focus Blush Rosewood | MS4020174 | 10.0 | 120.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 2 | Solenne Paris Baume Nuit Night Balm 50 ml | MS1020161 | 8.0 | 48.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 3 | Lune Rouge Glow Highlighter Champagne | MS7030190 | 12.0 | 12.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 4 | Solenne Paris Lotion Essentielle Toner 150 ml | MS1070033 | 2.0 | 12.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 5 | Lune Rouge Lacquer Nail Colour 140 Gunmetal | MS7000824 | 24.0 | 24.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 6 | Solenne Paris Masque Éclat Radiance Mask 75 ml | MS1060170 | 2.0 | 12.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 7 | Solenne Paris Sérum Absolu Regenerating Serum 15 ml | MS1000013 | 1.0 | 6.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 8 | Lune Rouge Glow Highlighter Rose Gold | MS7030219 | 72.0 | 72.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 9 | Velour Cosmetics Satin Lip Colour 18 Berry Noir | MS4000699 | 120.0 | 120.0 | false | false | false |
| DOC-00150 | amended_scan | HV-572437 | 10 | Atelier Noor Oud Saffron Eau de Parfum 100 ml | MS3000278 | 12.0 | 12.0 | false | false | false |
| DOC-00150 | amended_scan | HV-572437 | 11 | Velour Cosmetics Soft Focus Blush Apricot | MS4020362 | 24.0 | 24.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 12 | Kōri Botanicals Camellia Barrier Cream 50 ml | MS2020048 | 2.0 | 12.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 13 | Kōri Botanicals Rice Enzyme Polish 50 ml | MS2030016 | 1.0 | 6.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 14 | Atelier Noor Vétiver Nocturne Eau de Toilette 50 ml | MS3020038 | 1.0 | 6.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 15 | Lune Rouge Precision Liquid Eyeliner Black | MS7010065 | 1.0 | 12.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 16 | Atelier Noor Rose Ambrée Eau de Parfum 100 ml | MS3010240 | 4.0 | 24.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 17 | Atelier Noor Oud Saffron Eau de Parfum 50 ml | MS3000150 | 6.0 | 36.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 18 | Kōri Botanicals Green Tea Gel Cleanser 200 ml | MS2010137 | 3.0 | 18.0 | true | true | true |
| DOC-00150 | amended_scan | HV-572437 | 19 | Velour Cosmetics Satin Lip Colour 08 Terracotta | MS4000380 | 24.0 | 24.0 | false | false | false |

## Sample: extracted, resolved lines (gold `purchase_orders`)

| doc_id | attachment_filename | po_number | customer_name | resolved_sap_sold_to | printed_sku | description | quantity | uom | resolved_material_no | sku_resolve_method | order_confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DOC-00001 | DOC-00001.edi | 4572176148 | HALCYON & FINCH | 100100 | 2993618324218 | VELOUR COSMETICS VELVET MATTE FOUNDATION 30 ML 2N LINEN | 12.0 | EA | MS4010290 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4572176148 | HALCYON & FINCH | 100100 |  | MISTRAL HAIR SEA SALT TEXTURE SPRAY 150 ML | 36.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4572176148 | HALCYON & FINCH | 100100 |  | ATELIER NOOR CUIR FUMÉ EXTRAIT DE PARFUM 50 ML | 36.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4572176148 | HALCYON & FINCH | 100100 |  | SOLENNE PARIS CRÈME LUMIÈRE DAY CREAM 30 ML | 1.0 | CA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2918367365763 | MISTRAL HAIR SCALP BALANCE SERUM 50 ML | 2.0 | CA | MS6060099 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2950455623867 | VELOUR COSMETICS BROW SCULPT PENCIL SOFT BLACK | 36.0 | EA | MS4030315 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 |  | VELOUR COSMETICS SOFT FOCUS BLUSH ROSEWOOD | 24.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2917711592121 | MISTRAL HAIR COLOUR GUARD SHAMPOO 250 ML | 36.0 | EA | MS6050064 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 |  | THORNFIELD GROOMING CEDAR SHAVE CREAM 150 ML | 48.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2904505331585 | KŌRI BOTANICALS HINOKI CALMING TONER 100 ML | 12.0 | EA | MS2040026 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2960494519830 | LUNE ROUGE LACQUER NAIL COLOUR 110 BALLET | 24.0 | EA | MS7000295 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 |  | MISTRAL HAIR CURL DEFINE CREAM 150 ML | 120.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 |  | EMBER & OAK BLACK TEA ROOM SPRAY 100 ML | 4.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 |  | KŌRI BOTANICALS RICE ENZYME POLISH 100 ML | 12.0 | EA |  | none | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2958122362316 | ATELIER NOOR NÉROLI SOLEIL EAU DE TOILETTE 50 ML | 6.0 | EA | MS3030052 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2997403447137 | VELOUR COSMETICS VELVET MATTE FOUNDATION 30 ML 1W IVORY | 48.0 | EA | MS4010167 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2944935348746 | KŌRI BOTANICALS CAMELLIA BARRIER CREAM 100 ML | 2.0 | CA | MS2020129 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2958181412472 | EMBER & OAK WILD MINT CANDLE 400 G | 40.0 | EA | MS8040171 | ean | 0.55 |
| DOC-00001 | DOC-00001.edi | 4574104909 | HALCYON FINCH NYC | 100100 | 2961796405371 | MISTRAL HAIR HYDRA REPAIR CONDITIONER 250 ML | 24.0 | EA | MS6010029 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | ATELIER NOOR IRIS POUDRÉ EAU DE PARFUM 100 ML | 6.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2960494519830 | LUNE ROUGE LACQUER NAIL COLOUR 110 BALLET | 72.0 | EA | MS7000295 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | ATELIER NOOR MUSC BLANC EAU DE PARFUM 30 ML | 120.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2967175655122 | VELOUR COSMETICS VELVET MATTE FOUNDATION 30 ML 4N HONEY | 36.0 | EA | MS4010684 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | VELOUR COSMETICS SOFT FOCUS BLUSH MAUVE | 12.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2963116566700 | SOLENNE PARIS MASQUE ÉCLAT RADIANCE MASK 75 ML | 2.0 | CA | MS1060170 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | KŌRI BOTANICALS CAMELLIA BARRIER CREAM 100 ML | 12.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2958842474511 | THORNFIELD GROOMING POST-SHAVE BALM 75 ML | 96.0 | EA | MS5040079 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | THORNFIELD GROOMING CEDAR SHAVE CREAM 150 ML | 120.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2930391171820 | SOLENNE PARIS CONTOUR DES YEUX EYE CREAM 15 ML | 6.0 | EA | MS1040049 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | LUNE ROUGE PRECISION LIQUID EYELINER BLACK | 36.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | ATELIER NOOR VÉTIVER NOCTURNE EAU DE TOILETTE 50 ML | 36.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2905297516136 | LUNE ROUGE PRECISION LIQUID EYELINER NAVY | 72.0 | EA | MS7010261 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | LUNE ROUGE LACQUER NAIL COLOUR 140 GUNMETAL | 48.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | KŌRI BOTANICALS YUZU BRIGHTENING ESSENCE 100 ML | 12.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | LUNE ROUGE GLOW HIGHLIGHTER ROSE GOLD | 24.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 | 2926398214653 | VELOUR COSMETICS SOFT FOCUS BLUSH PEACH | 24.0 | EA | MS4020080 | ean | 0.55 |
| DOC-00002 | DOC-00002.edi | 4548249394 | HALCYON & FINCH | 100100 |  | KŌRI BOTANICALS HINOKI CALMING TONER 100 ML | 48.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4558743898 | H&F INC. | 100100 |  | KŌRI BOTANICALS YUZU BRIGHTENING ESSENCE 100 ML | 4.0 | CA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4558743898 | H&F INC. | 100100 |  | MISTRAL HAIR COLOUR GUARD SHAMPOO 1 L SALON | 6.0 | EA |  | none | 0.55 |
| DOC-00002 | DOC-00002.edi | 4558743898 | H&F INC. | 100100 |  | VELOUR COSMETICS SATIN LIP COLOUR 12 ROUGE VELOURS | 24.0 | EA |  | none | 0.55 |

