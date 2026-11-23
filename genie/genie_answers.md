# Genie space answers (collected 2026-11-23 19:29 UTC)

Space `01f1e75fe7db1f34becb96c5dfa59b82` on https://fevm-evan-aws-01.cloud.databricks.com: https://fevm-evan-aws-01.cloud.databricks.com/genie/rooms/01f1e75fe7db1f34becb96c5dfa59b82

Each question was sent to the space through the Genie Conversation API; below is Genie's own answer, the SQL it
wrote and the rows that SQL returned.

## Q: How many FTE does the pipeline save, and how many FTE are needed today vs with the pipeline?

status: `COMPLETED`

```sql
SELECT round(sum(`fte_manual`), 1) AS `fte_today`, round(sum(`fte_assisted`), 1) AS `fte_with_pipeline`, round(sum(`fte_saved`), 1) AS `fte_saved` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
```

_You want to see the total number of full-time equivalents (FTE) needed today without the pipeline, the total FTE needed with the pipeline, and the total FTE saved by using the pipeline._

| fte_today | fte_with_pipeline | fte_saved |
|---|---|---|
| 8.1 | 2.2 | 5.9 |

(1 rows)

**Genie:** Based on the assumptions in `roi_assumptions`, the pipeline saves **5.9 FTE**. The work requires **8.1 FTE** today and **2.2 FTE** with the pipeline, which means the pipeline reduces staffing needs by **5.9 FTE** under these illustrative planning values.

## Q: Show FTE saved by document type

status: `COMPLETED`

```sql
SELECT
  `channel` AS `document_type`,
  COUNT(*) AS `docs`,
  SUM(`gt_lines`) AS `lines`,
  SUM(`fte_saved`) AS `fte_saved`,
  SUM(`annual_usd_saved`) AS `annual_usd_saved`,
  try_divide(SUM(`lines_correct`),SUM(`lines_orderable`)) AS `line_accuracy`,
  try_divide(SUM(`pos_needs_review`),SUM(`n_pos`)) AS `review_rate`
FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
WHERE `channel` IS NOT NULL
GROUP BY `channel`
ORDER BY `fte_saved` DESC
```

_You want to see the total full-time equivalent (FTE) labor saved, along with other related metrics, broken down by document type (channel)._

| document_type | docs | lines | fte_saved | annual_usd_saved | line_accuracy | review_rate |
|---|---|---|---|---|---|---|
| excel_buysheet | 16 | 623 | 1.4732 | 99003.62 | 0.8291457286432161 | 0.88 |
| amended_scan | 16 | 388 | 1.0163 | 68297.15 | 0.8870056497175142 | 0.9375 |
| fax | 16 | 271 | 0.8020 | 53894.95 | 1.0 | 0.375 |
| email_pdf | 16 | 293 | 0.5662 | 38058.05 | 1.0 | 0.3125 |
| email_pricelist | 16 | 153 | 0.4040 | 27144.98 | 1.0 | 0.0 |
| erp_edi | 16 | 313 | 0.3544 | 23811.59 | 0.760797342192691 | 1.0 |
| handwritten | 16 | 126 | 0.3416 | 22971.07 | 0.0 | 1.0 |
| portal_export | 16 | 234 | 0.3408 | 22898.60 | 1.0 | 0.8125 |
| multimodal | 24 | 103 | 0.2235 | 15032.63 | 0.1941747572815534 | 1.0 |
| email_body | 16 | 126 | 0.1816 | 12199.33 | 0.33884297520661155 | 0.9375 |
| phone | 16 | 89 | 0.1582 | 10634.09 | 0.0 | 1.0 |

(11 rows)

**Genie:** Using the illustrative planning assumptions in `roi_assumptions`, **excel_buysheet** shows the highest FTE saved at **1.4732**, followed by **amended_scan** at **1.0163** and **fax** at **0.8020**. Examples include:
- **excel_buysheet**: **1.4732** FTE saved
- **amended_scan**: **1.0163** FTE saved
- **fax**: **0.8020** FTE saved
- **email_pdf**: **0.5662** FTE saved
- **email_pricelist**: **0.4040** FTE saved

Across all **11** document types shown, FTE saved ranges from **0.1582** for **phone** to **1.4732** for **excel_buysheet**.

## Q: How many FTE are saved in each region?

status: `COMPLETED`

```sql
SELECT `region`, ROUND(SUM(`fte_manual`), 2) AS `fte_today`, ROUND(SUM(`fte_assisted`), 2) AS `fte_with_pipeline`, ROUND(SUM(`fte_saved`), 2) AS `fte_saved` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` WHERE `region` IS NOT NULL GROUP BY `region` ORDER BY `fte_saved` DESC
```

_You want to see the number of full-time equivalents (FTE) saved by the pipeline in each region, along with the FTE needed today without the pipeline and the FTE needed with the pipeline._

| region | fte_today | fte_with_pipeline | fte_saved |
|---|---|---|---|
| Middle East | 2.45 | 0.77 | 1.68 |
| North America | 1.91 | 0.43 | 1.48 |
| UK & Ireland | 1.76 | 0.51 | 1.25 |
| France | 0.69 | 0.04 | 0.66 |
| DACH | 0.62 | 0.20 | 0.42 |
| Italy | 0.67 | 0.30 | 0.37 |

(6 rows)

**Genie:** Based on the illustrative planning values in **roi_assumptions**, the FTE saved by region are:
- **Middle East:** **1.68 FTE**
- **North America:** **1.48 FTE**
- **UK & Ireland:** **1.25 FTE**
- **France:** **0.66 FTE**
- **DACH:** **0.42 FTE**

Across the 6 regions shown, **Middle East** has the highest FTE savings and **Italy** the lowest at **0.37 FTE**.

## Q: Which region has the lowest line accuracy, and what is its review rate?

status: `COMPLETED`

```sql
WITH region_metrics AS (
  SELECT
    `region`,
    try_divide(SUM(`lines_correct`),SUM(`lines_orderable`)) AS `line_accuracy`,
    try_divide(SUM(`pos_needs_review`),SUM(`n_pos`)) AS `review_rate`
  FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
  WHERE `region` IS NOT NULL
    AND `lines_correct` IS NOT NULL
    AND `lines_orderable` IS NOT NULL
    AND `pos_needs_review` IS NOT NULL
    AND `n_pos` IS NOT NULL
  GROUP BY `region`
), ranked AS (
  SELECT
    `region`,
    `line_accuracy`,
    `review_rate`,
    RANK() OVER (ORDER BY `line_accuracy` ASC) AS `rnk`
  FROM region_metrics
)
SELECT
  `region`,
  `line_accuracy`,
  `review_rate`
FROM ranked
WHERE `rnk` <= 1
```

_You want to find the region with the lowest line accuracy and see its corresponding review rate._

| region | line_accuracy | review_rate |
|---|---|---|
| Italy | 0.0 | 1.0 |

(1 rows)

**Genie:** **Italy** has the lowest line accuracy at **0.0**, and **Italy** has a review rate of **1.0**. In the returned result, **Italy** is the lowest-performing region on line accuracy and all positions in **Italy** were flagged for review.

## Q: How does line accuracy change with document complexity?

status: `COMPLETED`

```sql
SELECT `complexity`, COUNT(*) AS `docs`, SUM(`lines_orderable`) AS `lines_orderable`, SUM(`lines_correct`) AS `lines_correct`, try_divide(SUM(`lines_correct`),SUM(`lines_orderable`)) AS `line_accuracy`
FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
WHERE `complexity` IS NOT NULL
  AND `lines_orderable` IS NOT NULL
  AND `lines_correct` IS NOT NULL
  AND `lines_orderable` > 0
GROUP BY `complexity`
ORDER BY `complexity`
```

_You want to see how line accuracy varies depending on the complexity level of documents. The results show the number of documents, total orderable lines, total correctly processed lines, and the calculated line accuracy for each complexity level._

| complexity | docs | lines_orderable | lines_correct | line_accuracy |
|---|---|---|---|---|
| 1 | 43 | 551 | 498 | 0.9038112522686026 |
| 2 | 43 | 550 | 441 | 0.8018181818181818 |
| 3 | 74 | 1212 | 943 | 0.778052805280528 |
| 4 | 24 | 292 | 146 | 0.5 |

(4 rows)

**Genie:** Line accuracy **declines as document complexity increases**: it is **90.4%** at complexity **1**, **80.2%** at **2**, **77.8%** at **3**, and **50.0%** at **4**. Across all **4 complexity levels**, the highest accuracy is at **complexity 1** and the lowest is at **complexity 4**, showing a clear drop in accuracy on more complex documents.

## Q: Which 5 problem types have the lowest line accuracy?

status: `COMPLETED`

```sql
WITH issue_accuracy AS (
  SELECT
    i.`issue_type`,
    COUNT(DISTINCT i.`doc_id`) AS `docs`,
    try_divide(SUM(d.`lines_correct`),SUM(d.`lines_orderable`)) AS `line_accuracy`
  FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`gt_issues` i
  INNER JOIN `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` d
    ON i.`doc_id` = d.`doc_id`
  WHERE i.`issue_type` IS NOT NULL
    AND d.`lines_correct` IS NOT NULL
    AND d.`lines_orderable` IS NOT NULL
    AND d.`lines_orderable` > 0
  GROUP BY i.`issue_type`
), ranked AS (
  SELECT
    `issue_type`,
    `docs`,
    `line_accuracy`,
    RANK() OVER (ORDER BY `line_accuracy` ASC) AS `rnk`
  FROM issue_accuracy
)
SELECT
  `issue_type`,
  `docs`,
  `line_accuracy`
FROM ranked
WHERE `rnk` <= 5
ORDER BY `line_accuracy` ASC, `issue_type` ASC
```

_You want to see the five problem types that have the lowest line accuracy._

| issue_type | docs | line_accuracy |
|---|---|---|
| chat_correction | 2 | 0.0 |
| circled_then_crossed_out | 3 | 0.0 |
| identify_by_image_caption | 6 | 0.0 |
| identify_by_photo | 5 | 0.0 |
| inline_images_only | 5 | 0.0 |
| mid_call_correction | 13 | 0.0 |
| photo_of_handwritten_list | 7 | 0.0 |
| photo_of_screen | 2 | 0.0 |
| size_omitted_default_rule | 12 | 0.0 |

(9 rows)

**Genie:** The query returned **9** problem types tied for the lowest line accuracy, and **all 9 have 0.0% line accuracy**. Examples include:
- **chat_correction** — **0.0%** line accuracy across **2** documents
- **circled_then_crossed_out** — **0.0%** across **3** documents
- **identify_by_image_caption** — **0.0%** across **6** documents
- **identify_by_photo** — **0.0%** across **5** documents
- **inline_images_only** — **0.0%** across **5** documents
This means there is no single bottom 5 by accuracy in the results shown, because every returned problem type is tied at the same lowest level.

## Q: Which documents were wrong but not routed to review?

status: `COMPLETED`

```sql
SELECT `doc_id`, `received_at`, `channel`, `retailer`, `region`, `country`, `n_pos`, `pos_needs_review`, `line_accuracy`, `min_confidence`, `doc_fully_correct` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` WHERE `doc_fully_correct` = false AND COALESCE(`pos_needs_review`, 0) = 0 AND COALESCE(`n_pos`, 0) > 0 ORDER BY `line_accuracy` ASC, `received_at` DESC
```

_You want to see the documents that were incorrect but were not sent for review. The results include document details such as ID, receipt date, channel, retailer, region, country, number of purchase orders, number of purchase orders needing review, line accuracy, minimum confidence, and whether the document was fully correct. The list is ordered by line accuracy from lowest to highest and then by the most recent receipt date._

| doc_id | received_at | channel | retailer | region | country | n_pos | pos_needs_review | line_accuracy | min_confidence | doc_fully_correct |
|---|---|---|---|---|---|---|---|---|---|---|

(0 rows)

**Genie:** There were **no documents** in the results that were incorrect and also **not routed to review**. Based on this result set, the count is **0**, so there are no examples to list.

## Q: How many orders are in the review queue by status and region?

status: `COMPLETED`

```sql
SELECT `status`, `region`, COUNT(*) AS `orders`
FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`review_orders`
WHERE `status` IS NOT NULL
  AND `region` IS NOT NULL
GROUP BY `status`, `region`
ORDER BY `orders` DESC, `status`, `region`
```

_You want to see the number of orders currently in the review queue, broken down by their status and region._

| status | region | orders |
|---|---|---|
| pending | Middle East | 70 |
| pending | North America | 50 |
| pending | UK & Ireland | 36 |
| pending | DACH | 25 |
| pending | France | 14 |
| pending | Italy | 13 |
| duplicate | North America | 5 |
| duplicate | Middle East | 4 |

(8 rows)

**Genie:** The review queue has **8 status-region combinations** in the visible data, led by **pending** orders in **Middle East (70)** and **North America (50)**. Examples include:
- **pending** — **Middle East:** **70** orders
- **pending** — **North America:** **50** orders
- **pending** — **UK & Ireland:** **36** orders
- **pending** — **DACH:** **25** orders
- **pending** — **France:** **14** orders

In this sample, **pending** is the dominant status across all shown regions, while **duplicate** appears only in **North America (5)** and **Middle East (4)**.

