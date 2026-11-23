# Genie space answers (collected 2026-11-23 17:58 UTC)

Space `01f1e75fe7db1f34becb96c5dfa59b82` on https://fevm-evan-aws-01.cloud.databricks.com: https://fevm-evan-aws-01.cloud.databricks.com/genie/rooms/01f1e75fe7db1f34becb96c5dfa59b82

Each question was sent to the space through the Genie Conversation API; below is Genie's own answer, the SQL it
wrote and the rows that SQL returned.

## Q: How many FTE does the pipeline save, and how many FTE are needed today vs with the pipeline?

status: `COMPLETED`

```sql
SELECT round(sum(`fte_manual`), 1) AS `fte_today`, round(sum(`fte_assisted`), 1) AS `fte_with_pipeline`, round(sum(`fte_saved`), 1) AS `fte_saved` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
```

_You want to see the total number of full-time equivalent (FTE) staff needed today without the pipeline, the FTE needed with the pipeline, and the FTE saved by using the pipeline, along with the percentage of effort saved, annual hours saved, and annual labor cost saved in USD._

| fte_today | fte_with_pipeline | fte_saved |
|---|---|---|
| 8.1 | 2.2 | 5.9 |

(1 rows)

**Genie:** Based on the assumptions in **roi_assumptions** (illustrative planning values, not measurements), the pipeline saves **5.9 FTE**. The operation needs **8.1 FTE** today and **2.2 FTE** with the pipeline.

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
| excel_buysheet | 16 | 623 | 1.4658 | 98496.37 | 0.8291457286432161 | 0.88 |
| amended_scan | 16 | 388 | 1.0163 | 68297.15 | 0.8870056497175142 | 0.9375 |
| fax | 16 | 271 | 0.8117 | 54547.12 | 1.0 | 0.3125 |
| email_pdf | 16 | 293 | 0.5662 | 38058.05 | 1.0 | 0.3125 |
| email_pricelist | 16 | 153 | 0.3932 | 26420.33 | 0.9934640522875817 | 0.0625 |
| erp_edi | 16 | 313 | 0.3533 | 23739.14 | 0.7574750830564784 | 1.0 |
| handwritten | 16 | 126 | 0.3416 | 22971.07 | 0.0 | 1.0 |
| portal_export | 16 | 234 | 0.3408 | 22898.60 | 1.0 | 0.8125 |
| multimodal | 24 | 103 | 0.2235 | 15032.63 | 0.1941747572815534 | 1.0 |
| email_body | 16 | 126 | 0.1816 | 12199.33 | 0.33884297520661155 | 0.9375 |
| phone | 16 | 89 | 0.1582 | 10634.09 | 0.0 | 1.0 |

(11 rows)

**Genie:** Would you prefer to see the FTE saved broken down by the finer document type classification instead of channel?

**Genie:** Based on the illustrative planning values in **roi_assumptions**, **excel_buysheet** shows the highest FTE saved at **1.4658**, followed by **amended_scan** at **1.0163** and **fax** at **0.8117**. Examples include:
- **excel_buysheet**: **1.4658** FTE saved
- **amended_scan**: **1.0163** FTE saved
- **fax**: **0.8117** FTE saved
- **email_pdf**: **0.5662** FTE saved
- **email_pricelist**: **0.3932** FTE saved

Across all **11** document types shown, FTE saved ranges from **1.4658** down to **0.1582**, with **phone** the lowest.

## Q: How many FTE are saved in each region?

status: `COMPLETED`

```sql
SELECT `region`, ROUND(SUM(`fte_manual`), 2) AS `fte_today`, ROUND(SUM(`fte_assisted`), 2) AS `fte_with_pipeline`, ROUND(SUM(`fte_saved`), 2) AS `fte_saved` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` WHERE `region` IS NOT NULL GROUP BY `region` ORDER BY `fte_saved` DESC
```

_You want to see the number of full-time equivalent (FTE) employees saved by using the pipeline in each region, along with the FTE needed today without the pipeline and the FTE needed with the pipeline._

| region | fte_today | fte_with_pipeline | fte_saved |
|---|---|---|---|
| Middle East | 2.45 | 0.78 | 1.67 |
| North America | 1.91 | 0.44 | 1.47 |
| UK & Ireland | 1.76 | 0.51 | 1.25 |
| France | 0.69 | 0.03 | 0.67 |
| DACH | 0.62 | 0.20 | 0.42 |
| Italy | 0.67 | 0.30 | 0.37 |

(6 rows)

**Genie:** Using the illustrative planning assumptions in **roi_assumptions**, FTE saved by region is:
- **Middle East:** **1.67 FTE**
- **North America:** **1.47 FTE**
- **UK & Ireland:** **1.25 FTE**
- **France:** **0.67 FTE**
- **DACH:** **0.42 FTE**

Across the 6 regions shown, **Middle East** has the highest FTE savings and **Italy** the lowest at **0.37 FTE**.

## Q: Which region has the lowest line accuracy, and what is its review rate?

status: `COMPLETED`

```sql
WITH `region_metrics` AS (
  SELECT
    `region`,
    SUM(`lines_correct`) AS `lines_correct_sum`,
    SUM(`lines_orderable`) AS `lines_orderable_sum`,
    SUM(`pos_needs_review`) AS `pos_needs_review_sum`,
    SUM(`n_pos`) AS `n_pos_sum`
  FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results`
  WHERE `region` IS NOT NULL
    AND `lines_correct` IS NOT NULL
    AND `lines_orderable` IS NOT NULL
    AND `pos_needs_review` IS NOT NULL
    AND `n_pos` IS NOT NULL
  GROUP BY `region`
), `ranked_regions` AS (
  SELECT
    `region`,
    try_divide(`lines_correct_sum`,`lines_orderable_sum`) AS `line_accuracy`,
    100 * (try_divide(`pos_needs_review_sum`,`n_pos_sum`)) AS `review_rate`,
    RANK() OVER (ORDER BY try_divide(`lines_correct_sum`,`lines_orderable_sum`) ASC) AS `accuracy_rank`
  FROM `region_metrics`
  WHERE `lines_orderable_sum` > 0
    AND `n_pos_sum` > 0
)
SELECT
  `region`,
  `line_accuracy`,
  `review_rate`
FROM `ranked_regions`
WHERE `accuracy_rank` <= 1
ORDER BY `line_accuracy` ASC, `region` ASC
```

_You want to find the region with the lowest line accuracy and see its review rate._

| region | line_accuracy | review_rate |
|---|---|---|
| Italy | 0.0 | 100.0 |

(1 rows)

**Genie:** **Italy** has the lowest line accuracy at **0.0**, and **Italy** has a review rate of **100.0%**. In the returned result, **Italy** is the only region tied for the lowest line accuracy.

## Q: How does line accuracy change with document complexity?

status: `COMPLETED`

```sql
SELECT `complexity`, COUNT(*) AS `docs`, SUM(`lines_orderable`) AS `lines_orderable`, try_divide(SUM(`lines_correct`),SUM(`lines_orderable`)) AS `line_accuracy` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` WHERE `complexity` IS NOT NULL AND `lines_orderable` IS NOT NULL GROUP BY `complexity` ORDER BY `complexity` ASC
```

_You want to see how line accuracy varies depending on the complexity level of documents._

| complexity | docs | lines_orderable | line_accuracy |
|---|---|---|---|
| 1 | 43 | 551 | 0.9328493647912885 |
| 2 | 43 | 550 | 0.769090909090909 |
| 3 | 74 | 1212 | 0.778052805280528 |
| 4 | 24 | 292 | 0.5 |

(4 rows)

**Genie:** Line accuracy is **highest at complexity 1** at **93.3%**, drops to **76.9%** at complexity 2, is **77.8%** at complexity 3, and falls to **50.0%** at complexity 4. Overall, the results show that line accuracy is much stronger for simpler documents and declines sharply for the most complex ones.

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
    AND d.`lines_orderable` IS NOT NULL
    AND d.`lines_correct` IS NOT NULL
  GROUP BY i.`issue_type`
  HAVING SUM(d.`lines_orderable`) > 0
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

_You want to see the five problem types that have the lowest line accuracy in the documents, along with the number of unique documents affected by each problem type._

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

**Genie:** The lowest line accuracy shown is **0.0%**, and because 9 problem types are tied at that level, the results below are only a sample of 5. 

- **chat_correction** — **0.0%** line accuracy across **2** documents
- **circled_then_crossed_out** — **0.0%** across **3** documents
- **identify_by_image_caption** — **0.0%** across **6** documents
- **identify_by_photo** — **0.0%** across **5** documents
- **inline_images_only** — **0.0%** across **5** documents

All **9** returned problem types are tied for the lowest observed line accuracy in this result.

## Q: Which documents were wrong but not routed to review?

status: `COMPLETED`

```sql
SELECT `d`.`doc_id`, `d`.`channel`, `d`.`retailer`, `d`.`doc_type`, `d`.`received_at`, `d`.`region`, `d`.`country`, `d`.`n_pos`, COUNT(*) AS `wrong_not_reviewed_pos`, `d`.`lines_orderable`, `d`.`lines_correct`, `d`.`line_accuracy`, `d`.`doc_fully_correct`, `d`.`min_confidence` FROM `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_order_results` `o` INNER JOIN `evan_aws_01_catalog`.`fe_bar_fy27`.`eval_doc_results` `d` ON `d`.`doc_id` = `o`.`doc_id` WHERE `o`.`needs_review` = FALSE AND `o`.`order_fully_correct` = FALSE GROUP BY `d`.`doc_id`, `d`.`channel`, `d`.`retailer`, `d`.`doc_type`, `d`.`received_at`, `d`.`region`, `d`.`country`, `d`.`n_pos`, `d`.`lines_orderable`, `d`.`lines_correct`, `d`.`line_accuracy`, `d`.`doc_fully_correct`, `d`.`min_confidence` ORDER BY `wrong_not_reviewed_pos` DESC, `d`.`line_accuracy` ASC, `d`.`min_confidence` ASC, `d`.`doc_id` ASC
```

_You want to see the documents that were incorrect but were not sent for review, including details like document ID, channel, retailer, type, received date, region, country, number of positions, count of wrong positions not reviewed, lines orderable, lines correct, line accuracy, whether the document was fully correct, and minimum confidence score, sorted by the number of wrong positions not reviewed in descending order, then by line accuracy ascending, minimum confidence ascending, and document ID ascending._

| doc_id | channel | retailer | doc_type | received_at | region | country | n_pos | wrong_not_reviewed_pos | lines_orderable | lines_correct | line_accuracy | doc_fully_correct | min_confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

(0 rows)

**Genie:** There were **no documents** in the results that were wrong and not routed to review. Based on this query, **0 documents** had at least one incorrect order position that bypassed review, so there are no examples to list.

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
| pending | Middle East | 67 |
| pending | North America | 51 |
| pending | UK & Ireland | 36 |
| pending | DACH | 23 |
| pending | Italy | 16 |
| pending | France | 15 |
| duplicate | North America | 5 |
| duplicate | Middle East | 4 |

(8 rows)

**Genie:** The review queue has **8** status-and-region groups in total, with **pending** orders making up most of the visible queue. Examples include:
- **Pending — Middle East:** **67** orders
- **Pending — North America:** **51** orders
- **Pending — UK & Ireland:** **36** orders
- **Pending — DACH:** **23** orders
- **Pending — Italy:** **16** orders

Across the results shown, **pending** appears in **6** regions while **duplicate** appears only in **North America** and the **Middle East**.

