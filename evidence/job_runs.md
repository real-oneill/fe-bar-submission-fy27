# Job runs (collected 2026-11-23 18:08 UTC)

Workspace `https://fevm-evan-aws-01.cloud.databricks.com`. Jobs of this bundle (name contains `fe_bar_`), every run, newest first.

## [dev <deployer>] fe_bar_evaluate (job 678794842897110)

### run 1092744869857810: TERMINATED / SUCCESS
started 2026-11-23 18:00:23 UTC, ended 2026-11-23 18:01:17 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/678794842897110/run/1092744869857810

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| evaluate | SUCCESS | 2026-11-23 18:00:23 | 0.9 |  |

### run 597266705187624: TERMINATED / SUCCESS
started 2026-11-23 18:00:22 UTC, ended 2026-11-23 18:07:27 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/678794842897110/run/597266705187624

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| evaluate | FAILED | 2026-11-23 18:00:22 | 0.7 | Workload failed, see run output for details |
| evaluate | SUCCESS | 2026-11-23 18:01:09 | 6.3 |  |

### run 407905159673402: TERMINATED / SUCCESS
started 2026-11-23 17:27:28 UTC, ended 2026-11-23 17:28:32 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/678794842897110/run/407905159673402

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| evaluate | SUCCESS | 2026-11-23 17:27:28 | 1.0 |  |

### run 286769692709136: TERMINATED / SUCCESS
started 2026-11-23 17:00:54 UTC, ended 2026-11-23 17:02:03 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/678794842897110/run/286769692709136

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| evaluate | SUCCESS | 2026-11-23 17:00:54 | 1.1 |  |

## [dev <deployer>] fe_bar_load_corpus (job 791826975552843)

_no runs_

## [dev <deployer>] fe_bar_order_intake_bootstrap (job 113907385555536)

### run 897853534755561: TERMINATED / SUCCESS
started 2026-11-23 17:32:03 UTC, ended 2026-11-23 17:58:23 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/113907385555536/run/897853534755561

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| schema_volume | SUCCESS | 2026-11-23 17:32:03 | 0.3 |  |
| fetch_outlook_items | SUCCESS | 2026-11-23 17:32:21 | 0.1 |  |
| masters | SUCCESS | 2026-11-23 17:32:21 | 0.4 |  |
| stage_inbound_files | SUCCESS | 2026-11-23 17:32:21 | 0.1 |  |
| load_corpus | SUCCESS | 2026-11-23 17:32:46 | 1.0 |  |
| register_prompt | SUCCESS | 2026-11-23 17:32:46 | 3.1 |  |
| sap_masters | SUCCESS | 2026-11-23 17:32:46 | 0.1 |  |
| refresh_pipeline | SUCCESS | 2026-11-23 17:35:53 | 18.1 |  |
| export_attachments | SUCCESS | 2026-11-23 17:54:02 | 0.2 |  |
| build_review_queue | SUCCESS | 2026-11-23 17:54:14 | 0.6 |  |
| log_traces | SUCCESS | 2026-11-23 17:54:53 | 0.9 |  |
| publish_review_queue | SUCCESS | 2026-11-23 17:55:48 | 1.7 |  |
| evaluate | SUCCESS | 2026-11-23 17:57:32 | 0.7 |  |
| score_traces | SUCCESS | 2026-11-23 17:57:32 | 0.8 |  |

### run 82451320465370: TERMINATED / SUCCESS
started 2026-11-23 16:18:19 UTC, ended 2026-11-23 16:46:45 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/113907385555536/run/82451320465370

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| schema_volume | SUCCESS | 2026-11-23 16:18:19 | 0.3 |  |
| fetch_outlook_items | SUCCESS | 2026-11-23 16:18:37 | 0.2 |  |
| masters | SUCCESS | 2026-11-23 16:18:37 | 0.2 |  |
| stage_inbound_files | SUCCESS | 2026-11-23 16:18:37 | 0.1 |  |
| load_corpus | SUCCESS | 2026-11-23 16:18:52 | 1.0 |  |
| register_prompt | SUCCESS | 2026-11-23 16:18:52 | 3.1 |  |
| sap_masters | SUCCESS | 2026-11-23 16:18:52 | 0.1 |  |
| refresh_pipeline | SUCCESS | 2026-11-23 16:21:57 | 20.0 |  |
| export_attachments | SUCCESS | 2026-11-23 16:41:56 | 0.2 |  |
| build_review_queue | SUCCESS | 2026-11-23 16:42:07 | 0.5 |  |
| log_traces | SUCCESS | 2026-11-23 16:42:40 | 0.9 |  |
| publish_review_queue | SUCCESS | 2026-11-23 16:43:34 | 2.4 |  |
| evaluate | SUCCESS | 2026-11-23 16:45:56 | 0.8 |  |
| score_traces | SUCCESS | 2026-11-23 16:45:56 | 0.6 |  |

### run 97065093061579: TERMINATED / CANCELED
started 2026-11-23 15:30:16 UTC, ended 2026-11-23 15:30:42 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/113907385555536/run/97065093061579

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| masters | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| publish_review_queue | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| register_prompt | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| stage_inbound_files | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| refresh_pipeline | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| fetch_outlook_items | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| score_traces | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| sap_masters | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| export_attachments | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| build_review_queue | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| evaluate | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| load_corpus | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| log_traces | UPSTREAM_CANCELED |  | 29924130.4 | Skipped because upstream task was cancelled or timed out |
| schema_volume | CANCELED | 2026-11-23 15:30:16 | 0.4 | Run cancelled by user |

### run 788151934612368: INTERNAL_ERROR / FAILED
started 2026-11-23 15:00:20 UTC, ended 2026-11-23 15:36:49 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/113907385555536/run/788151934612368

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| schema_volume | SUCCESS | 2026-11-23 15:00:21 | 0.3 |  |
| fetch_outlook_items | SUCCESS | 2026-11-23 15:00:38 | 0.1 |  |
| masters | SUCCESS | 2026-11-23 15:00:38 | 0.4 |  |
| stage_inbound_files | SUCCESS | 2026-11-23 15:00:38 | 0.2 |  |
| load_corpus | SUCCESS | 2026-11-23 15:01:02 | 1.5 |  |
| register_prompt | SUCCESS | 2026-11-23 15:01:02 | 3.2 |  |
| sap_masters | SUCCESS | 2026-11-23 15:01:02 | 0.3 |  |
| refresh_pipeline | SUCCESS | 2026-11-23 15:04:15 | 24.4 |  |
| export_attachments | SUCCESS | 2026-11-23 15:28:38 | 0.2 |  |
| build_review_queue | SUCCESS | 2026-11-23 15:28:50 | 0.5 |  |
| log_traces | SUCCESS | 2026-11-23 15:29:21 | 1.5 |  |
| publish_review_queue | SUCCESS | 2026-11-23 15:30:50 | 1.7 |  |
| evaluate | FAILED | 2026-11-23 15:32:30 | 0.7 | Workload failed, see run output for details |
| score_traces | SUCCESS | 2026-11-23 15:32:30 | 4.3 |  |

### run 519888600214073: INTERNAL_ERROR / FAILED
started 2026-11-23 14:55:51 UTC, ended 2026-11-23 14:59:09 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/113907385555536/run/519888600214073

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| schema_volume | SUCCESS | 2026-11-23 14:55:51 | 0.3 |  |
| fetch_outlook_items | SUCCESS | 2026-11-23 14:56:10 | 0.1 |  |
| masters | FAILED | 2026-11-23 14:56:10 | 0.4 | Workload failed, see run output for details |
| stage_inbound_files | SUCCESS | 2026-11-23 14:56:11 | 0.2 |  |
| masters | FAILED | 2026-11-23 14:56:36 | 0.4 | Workload failed, see run output for details |
| load_corpus | UPSTREAM_FAILED | 2026-11-23 14:57:02 | 0.0 | An upstream task failed. |
| register_prompt | UPSTREAM_FAILED | 2026-11-23 14:57:02 | 0.0 | An upstream task failed. |
| sap_masters | UPSTREAM_FAILED | 2026-11-23 14:57:03 | 0.0 | An upstream task failed. |
| refresh_pipeline | UPSTREAM_FAILED | 2026-11-23 14:57:03 | 0.0 | An upstream task failed. |
| export_attachments | UPSTREAM_FAILED | 2026-11-23 14:57:03 | 0.0 | An upstream task failed. |
| build_review_queue | UPSTREAM_FAILED | 2026-11-23 14:57:03 | 0.0 | An upstream task failed. |
| log_traces | UPSTREAM_FAILED | 2026-11-23 14:57:03 | 0.0 | An upstream task failed. |
| publish_review_queue | FAILED | 2026-11-23 14:57:03 | 0.6 | Workload failed, see run output for details |
| publish_review_queue | FAILED | 2026-11-23 14:57:42 | 0.6 | Workload failed, see run output for details |
| evaluate | FAILED | 2026-11-23 14:58:15 | 0.4 | Workload failed, see run output for details |
| score_traces | UPSTREAM_FAILED | 2026-11-23 14:58:15 | 0.0 | An upstream task failed. |
| evaluate | FAILED | 2026-11-23 14:58:46 | 0.4 | Workload failed, see run output for details |

## [dev <deployer>] fe_bar_order_intake_quality_review_session (job 458707369704839)

_no runs_

## [dev <deployer>] fe_bar_order_intake_run (job 881961269146439)

### run 291458661836777: TERMINATED / SUCCESS
started 2026-11-23 17:04:01 UTC, ended 2026-11-23 17:27:23 UTC, run page https://fevm-evan-aws-01.cloud.databricks.com/?o=7474649573131719#job/881961269146439/run/291458661836777

| task | result | start (UTC) | minutes | message |
|---|---|---|---|---|
| fetch_outlook_items | SUCCESS | 2026-11-23 17:04:01 | 0.2 |  |
| masters | SUCCESS | 2026-11-23 17:04:01 | 0.4 |  |
| stage_inbound_files | SUCCESS | 2026-11-23 17:04:01 | 0.3 |  |
| sap_masters | SUCCESS | 2026-11-23 17:04:25 | 0.1 |  |
| refresh_pipeline | SUCCESS | 2026-11-23 17:04:31 | 19.0 |  |
| export_attachments | SUCCESS | 2026-11-23 17:23:30 | 0.2 |  |
| build_review_queue | SUCCESS | 2026-11-23 17:23:43 | 0.6 |  |
| log_traces | SUCCESS | 2026-11-23 17:24:18 | 0.9 |  |
| publish_review_queue | SUCCESS | 2026-11-23 17:25:12 | 1.5 |  |
| score_traces | SUCCESS | 2026-11-23 17:26:45 | 0.6 |  |

## [dev <deployer>] fe_bar_order_intake_setup (job 296209682986122)

_no runs_

