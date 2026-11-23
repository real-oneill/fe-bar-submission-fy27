# [dev <deployer>] fe_bar_order_intake_run / publish_review_queue (run 698607378377192, as executed, with outputs)

Notebook `d05dcb68-1a66-4995-b2c1-fe5fc197c9eb`, exported 2026-11-23 19:28 UTC from https://fevm-evan-aws-01.cloud.databricks.com via the Jobs export-run API.

## Setup 04 — Publish the review queue to the Review App
Runs after `03_build_review_queue.py`, for either backend:
- **Grants**: gives the app's service principal what it needs (UC: `USE CATALOG`/`USE SCHEMA`, and for
  the warehouse backend `SELECT`+`MODIFY` on `review_orders`/`sap_outbound`). These tables don't exist when
  the app is first deployed, so they can't be app resources; the Volume and the warehouse/Postgres are.
- **backend=lakebase**: upserts the Delta `review_orders` into Lakebase (Autoscaling) Postgres, ensures
  `sap_outbound`, and grants the app's Postgres role on both tables. Rows of older builds that are no longer in
  the Delta queue are removed unless approved. Rows already `approved` in Postgres
  are never overwritten by a refresh. The Delta tables stay the lineage/source of record.
- **Row-level security** (`rls_enforced=true`, default): expands `region_access` (group -> region) with each
  group's members (workspace SCIM API) into Lakebase `user_regions(principal, region)`, creates each member's
  Postgres role, and puts Postgres RLS on `review_orders` / `sap_outbound`. The Review App connects as the
  signed-in user and `SET ROLE`s to the reviewer role, so each user sees and edits only their regions; the app's
  service principal gets no table access. `rls_enforced=false` turns RLS off and grants the app's service
  principal read/write on everything (sandbox / local dev). See README "Region filter and row-level security".

```python
%pip install "pg8000>=1.31" "scramp>=1.4.6"
# pg8000 is pure Python. (psycopg's bundled native libpq/OpenSSL can abort the process on serverless once Spark's
# native libraries are loaded.) Don't upgrade databricks-sdk here either — that breaks the notebook's Spark
# session; Lakebase is reached through its REST API with the runtime's SDK instead.
```

**Output:**

```
Looking in indexes: [REDACTED]
Collecting pg8000>=1.31
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/pg8000/1.31.6/pg8000-1.31.6-py3-none-any.whl.metadata (88 kB)
Collecting scramp>=1.4.6
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/scramp/1.5.0/scramp-1.5.0-py3-none-any.whl.metadata (34 kB)
Requirement already satisfied: python-dateutil>=2.8.2 in /databricks/python/lib/python3.12/site-packages (from pg8000>=1.31) (2.9.0.post0)
Collecting asn1crypto>=1.5.1 (from scramp>=1.4.6)
  Downloading http://package-proxy.host.local:8184/pypi/v1/packages/asn1crypto/1.5.1/asn1crypto-1.5.1-py2.py3-none-any.whl.metadata (13 kB)
Requirement already satisfied: six>=1.5 in /databricks/python/lib/python3.12/site-packages (from python-dateutil>=2.8.2->pg8000>=1.31) (1.17.0)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/pg8000/1.31.6/pg8000-1.31.6-py3-none-any.whl (57 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/scramp/1.5.0/scramp-1.5.0-py3-none-any.whl (20 kB)
Downloading http://package-proxy.host.local:8184/pypi/v1/packages/asn1crypto/1.5.1/asn1crypto-1.5.1-py2.py3-none-any.whl (105 kB)
Installing collected packages: asn1crypto, scramp, pg8000
[?25l
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━━━━━━━━ 2/3 [pg8000]
[2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3/3 [pg8000]
[?25h
[1A[2KSuccessfully installed asn1crypto-1.5.1 pg8000-1.31.6 scramp-1.5.0
Note: you may need to restart the kernel using %restart_python or dbutils.library.restartPython() to use updated packages.
```

```python
dbutils.library.restartPython()
```

```python
import pandas as pd
from databricks.sdk import WorkspaceClient

for k, d in [("catalog", "main"), ("schema", "order_intake"), ("backend", "warehouse"),
             ("lakebase_project", "order-intake"), ("lakebase_branch", "production"),
             ("lakebase_database", "databricks_postgres"), ("lakebase_schema", "public"),
             ("app_name", "order-intake-review"), ("rls_enforced", "true")]:
    dbutils.widgets.text(k, d)
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
backend = dbutils.widgets.get("backend").lower()
project, branch = dbutils.widgets.get("lakebase_project"), dbutils.widgets.get("lakebase_branch")
database, app_name = dbutils.widgets.get("lakebase_database"), dbutils.widgets.get("app_name")
pg_schema = dbutils.widgets.get("lakebase_schema").strip() or "public"
rls = dbutils.widgets.get("rls_enforced").strip().lower() not in ("false", "0", "no", "off")
S = f"{catalog}.{schema}"

w = WorkspaceClient()
app_sp = w.apps.get(name=app_name).service_principal_client_id
print(f"app {app_name!r} service principal: {app_sp}")
```

**Output:**

```
app 'fe-bar-fy27-review' service principal: a95d3fff-082a-4c8a-974f-06194ba895c5
```

```python
# ---- Unity Catalog grants for the app's service principal ----
def grant(stmt, required=True):
    try:
        spark.sql(stmt)
        print("OK  ", stmt)
    except Exception as e:  # noqa
        if required:
            raise
        print("SKIP", stmt, "->", str(e).splitlines()[0][:160])

# USE CATALOG needs catalog-level privileges the deployer may not have; the Volume app resource covers the
# PDF viewer either way, so this one is best-effort.
grant(f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{app_sp}`", required=False)
grant(f"GRANT USE SCHEMA ON SCHEMA {S} TO `{app_sp}`", required=False)
if backend == "warehouse":
    for t in ("review_orders", "sap_outbound"):
        grant(f"GRANT SELECT, MODIFY ON TABLE {S}.{t} TO `{app_sp}`")
    dbutils.notebook.exit("warehouse backend: grants applied")
if backend != "lakebase":
    raise ValueError(f"unknown backend {backend!r}")
```

**Output:**

```
OK   GRANT USE CATALOG ON CATALOG `evan_aws_01_catalog` TO `a95d3fff-082a-4c8a-974f-06194ba895c5`
OK   GRANT USE SCHEMA ON SCHEMA evan_aws_01_catalog.fe_bar_fy27 TO `a95d3fff-082a-4c8a-974f-06194ba895c5`
```

```python
# ---- Lakebase (Autoscaling): connect as the job's identity (the project owner) ----
import ssl
import pg8000.dbapi

branch_path = f"projects/{project}/branches/{branch}"
endpoints = w.api_client.do("GET", f"/api/2.0/postgres/{branch_path}/endpoints").get("endpoints", [])
endpoint = next(e for e in endpoints if e["status"]["endpoint_type"].endswith("READ_WRITE"))
host = endpoint["status"]["hosts"]["host"]
user = w.current_user.me().user_name


def connect():
    token = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={"endpoint": endpoint["name"]})["token"]
    conn = pg8000.dbapi.connect(host=host, port=5432, database=database, user=user, password=token,
                                ssl_context=ssl.create_default_context())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{pg_schema}"')   # no-op for public / an existing schema
    cur.execute(f'SET search_path TO "{pg_schema}"')
    return conn


def run_script(cur, script):
    """Execute a multi-statement DDL script one statement at a time (extended protocol = 1 statement)."""
    for stmt in (x.strip() for x in script.split(";")):
        if stmt and not all(l.strip().startswith("--") for l in stmt.splitlines()):
            cur.execute(stmt)


print(f"Lakebase {branch_path} -> {host}/{database} schema {pg_schema} as {user}")
```

**Output:**

```
Lakebase projects/fe-bar-fy27/branches/production -> ep-aged-silence-d8eb35bl.database.us-east-2.cloud.databricks.com/databricks_postgres schema public as <deployer>
```

```python
REVIEW_DDL = """
CREATE TABLE IF NOT EXISTS review_orders (
  order_id              text PRIMARY KEY,
  doc_name              text,
  orig_format           text,
  po_number             text,
  customer_name         text,
  customer_number       text,
  order_date            text,
  currency              text,
  sales_org             text,
  ship_to               text,
  resolved_sap_sold_to  text,
  header_confidence     double precision,
  n_lines               bigint,
  line_items_json       text,
  avg_line_confidence   double precision,
  parse_confidence      double precision,
  parsed_content        text,
  volume_path           text,
  overall_confidence    double precision,
  status                text,
  extraction_status     text,
  parse_truncated       boolean,
  review_reasons        text,
  duplicate_of          text,
  trace_id              text,
  region                text
);
-- tables created by an earlier version of this notebook
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS review_reasons text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS duplicate_of text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS trace_id text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS region text;
CREATE INDEX IF NOT EXISTS review_orders_region_idx ON review_orders (region);
-- hybrid extraction: which extractor read the order, why the fallback ran, ai_extract's per-field confidence (JSON)
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS extractor text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS fallback_reason text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS field_confidence_json text;
-- the file the order came from (the app opens attached emails from it)
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS source_path text;
ALTER TABLE review_orders ADD COLUMN IF NOT EXISTS attachment_filename text;
"""

# Where each extracted field sits in the source document (Delta review_citations <- Gold extraction_citations).
# Derived data: fully re-published every run. Units: see docs/ARCHITECTURE.md "Citations".
CITATIONS_DDL = """
CREATE TABLE IF NOT EXISTS review_citations (
  citation_key     text PRIMARY KEY,
  order_id         text NOT NULL,
  source_path      text,
  attachment_filename text,
  order_idx        integer,
  li_idx           integer,
  field            text,
  value            text,
  confidence       double precision,
  citation_id      integer,
  source_kind      text,
  page_index       integer,
  x1               double precision,
  y1               double precision,
  x2               double precision,
  y2               double precision,
  element_id       integer,
  element_type     text,
  table_row_index  integer,
  table_row_count  integer,
  sheet_index      integer,
  sheet_name       text,
  row_number       integer,
  cell_ref         text,
  char_start       integer,
  char_stop        integer,
  snippet          text,
  b_input          text
);
CREATE INDEX IF NOT EXISTS review_citations_order_idx ON review_citations (order_id);
"""
CIT_COLS = ["citation_key", "order_id", "source_path", "attachment_filename", "order_idx", "li_idx", "field", "value",
            "confidence", "citation_id", "source_kind", "page_index", "x1", "y1", "x2", "y2", "element_id",
            "element_type", "table_row_index", "table_row_count", "sheet_index", "sheet_name", "row_number",
            "cell_ref", "char_start", "char_stop", "snippet", "b_input"]
CIT_INT_COLS = {"order_idx", "li_idx", "citation_id", "page_index", "element_id", "table_row_index", "table_row_count",
                "sheet_index", "row_number", "char_start", "char_stop"}

OUTBOUND_DDL = """
CREATE TABLE IF NOT EXISTS sap_outbound (
  order_id        text PRIMARY KEY,
  po_number       text,
  sap_sold_to     text,
  customer_name   text,
  order_date      text,
  currency        text,
  line_items_json text,
  approved_by     text,
  approved_at     timestamptz,
  idoc_type       text
);
"""

COLS = [
    "order_id", "doc_name", "orig_format", "po_number", "customer_name", "customer_number",
    "order_date", "currency", "sales_org", "ship_to", "resolved_sap_sold_to",
    "header_confidence", "n_lines", "line_items_json", "avg_line_confidence",
    "parse_confidence", "parsed_content", "volume_path", "overall_confidence",
    "status", "extraction_status", "parse_truncated", "review_reasons", "duplicate_of", "trace_id", "region",
    "extractor", "fallback_reason", "field_confidence_json", "source_path", "attachment_filename",
]
# Columns updated on conflict (everything except the PK and status — status/edits are owned by
# the app once a reviewer touches a row).
UPDATE_COLS = [c for c in COLS if c not in ("order_id", "status")]
```

```python
# ---- pull the freshly-built Delta queue ----
from pyspark.sql import functions as F
src = spark.table(f"{S}.review_orders")
if "region" not in src.columns:   # queue built by a version before regions
    src = src.withColumn("region", F.lit("Unassigned"))
for _c in ("extractor", "fallback_reason", "field_confidence_json", "source_path", "attachment_filename"):   # older queue builds
    if _c not in src.columns:
        src = src.withColumn(_c, F.lit(None).cast("string"))
def _pg_safe(r):
    """Postgres text can't hold NUL (0x00) — some source documents contain it; drop it from every string value."""
    return tuple(v.replace("\x00", "") if isinstance(v, str) else v for v in r)


cit_rows = []
if spark.catalog.tableExists(f"{S}.review_citations"):
    _cp = spark.table(f"{S}.review_citations").select(*CIT_COLS).toPandas()
    _cp = _cp.astype(object).where(pd.notnull(_cp), None)
    _int_idx = [i for i, c in enumerate(CIT_COLS) if c in CIT_INT_COLS]   # pandas turns nullable ints into floats

    def _fix(r):
        r = list(r)
        for i in _int_idx:
            if r[i] is not None:
                r[i] = int(r[i])
        return _pg_safe(r)
    cit_rows = [_fix(r) for r in _cp.itertuples(index=False, name=None)]
print(f"{len(cit_rows)} citation rows from {S}.review_citations")
pdf = src.select(*COLS).toPandas()
pdf = pdf.astype(object).where(pd.notnull(pdf), None)
rows = [_pg_safe(r) for r in pdf.itertuples(index=False, name=None)]
print(f"{len(rows)} rows from {S}.review_orders")

placeholders = ", ".join(["%s"] * len(COLS))
set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in UPDATE_COLS)
# Preserve human work: do not overwrite rows already approved in Postgres.
upsert = (
    f"INSERT INTO review_orders ({', '.join(COLS)}) VALUES ({placeholders}) "
    f"ON CONFLICT (order_id) DO UPDATE SET {set_clause}, "
    f"status = CASE WHEN EXCLUDED.status = 'duplicate' THEN 'duplicate' ELSE 'pending' END "
    f"WHERE review_orders.status <> 'approved'"
)

c = connect()
try:
    cur = c.cursor()
    run_script(cur, REVIEW_DDL)
    run_script(cur, OUTBOUND_DDL)
    run_script(cur, CITATIONS_DDL)
    cur.executemany(upsert, rows)
    # Rows of older builds (a document re-identified — doc_id is a path hash, so moving the Volume changes it — or
    # an order re-keyed by its PO number) are no longer in the Delta queue: remove them, so each document shows its
    # current orders only. Approved rows are reviewer work and are kept.
    if rows:                                           # never empty the app because a build produced nothing
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS _current_orders (order_id text PRIMARY KEY)")
        cur.executemany("INSERT INTO _current_orders VALUES (%s) ON CONFLICT DO NOTHING", [(r[0],) for r in rows])
        cur.execute("DELETE FROM review_orders o WHERE o.status <> 'approved' "
                    "AND NOT EXISTS (SELECT 1 FROM _current_orders c WHERE c.order_id = o.order_id)")
        print(f"removed {cur.rowcount} rows of older builds (not approved, no longer in the Delta queue)")
        # an order approved under an older build's id (same document + PO): its re-built copy is a duplicate of it
        cur.execute("UPDATE review_orders p SET status = 'duplicate', duplicate_of = a.order_id FROM review_orders a "
                    "WHERE a.status = 'approved' AND p.status = 'pending' AND a.order_id <> p.order_id "
                    "AND a.doc_name = p.doc_name AND a.po_number IS NOT DISTINCT FROM p.po_number")
        print(f"{cur.rowcount} re-built orders marked duplicate of an approved one")
    cur.execute("DELETE FROM review_citations")         # derived: fully re-published every run
    if cit_rows:
        cur.executemany(f"INSERT INTO review_citations ({', '.join(CIT_COLS)}) VALUES ({', '.join(['%s'] * len(CIT_COLS))})",
                        cit_rows)
    # Approved rows keep their human edits, but their region follows the masters.
    cur.executemany("UPDATE review_orders SET region = %s WHERE order_id = %s AND region IS DISTINCT FROM %s",
                    [(r[COLS.index("region")], r[0], r[COLS.index("region")]) for r in rows])
    # rows no longer in the Delta queue (older builds) and rows from before regions: visible to `*` groups only
    cur.execute("UPDATE review_orders SET region = 'Unassigned' WHERE region IS NULL")
    # The app's Postgres role (named after its service principal) is created by the app's `postgres`
    # resource.
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_sp,))
    if not cur.fetchone():
        raise RuntimeError(f"Postgres role for the app service principal {app_sp} not found — is the app's "
                           "'postgres' resource attached (see the dev/prod targets in databricks.yml)?")
    cur.execute(f'GRANT USAGE ON SCHEMA "{pg_schema}" TO "{app_sp}"')
    if not rls:
        # No RLS: the app's service principal reads/writes every row.
        for t in ("review_orders", "sap_outbound", "review_citations"):
            cur.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
            cur.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
        cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON review_orders, sap_outbound TO "{app_sp}"')
        cur.execute(f'GRANT SELECT ON review_citations TO "{app_sp}"')
    cur.execute("SELECT count(*), count(*) FILTER (WHERE status='approved') FROM review_orders")
    total, approved = cur.fetchone()
finally:
    c.close()

print(f"Lakebase {database}.review_orders: {total} rows ({approved} approved preserved); sap_outbound ready.")
if not rls:
    dbutils.notebook.exit(f"rls_enforced=false: row-level security OFF; app role {app_sp} has read/write on all rows")
```

**Output:**

```
rls_enforced=false: row-level security OFF; app role a95d3fff-082a-4c8a-974f-06194ba895c5 has read/write on all rows
```

### Row-level security
**Who sees what** is defined once in Databricks: `region_access(group_name, region)` (Delta) maps Databricks
groups to regions (`*` = all). Here every group is expanded to its members (users, service principals,
nested groups) and written to Lakebase `user_regions(principal, region, via_group)`; principal = the Postgres
role name Lakebase uses for that identity (user: email/userName; service principal: application id).

**Postgres objects** (one set per Postgres schema):
- `oi_reviewer_<schema>` (NOLOGIN): the only role with reviewer privileges on the tables (SELECT + UPDATE of
  the editable columns on `review_orders`; SELECT/INSERT/DELETE on `sap_outbound`; SELECT on `user_regions`).
  Every principal in `user_regions` gets its own login role (`databricks_create_role`) and membership in it.
  The app logs in AS THE USER and runs `SET ROLE oi_reviewer_<schema>`: `session_user` stays the user (the
  policies key on it; SET ROLE can't change it) while privileges — and the lack of BYPASSRLS — are the
  reviewer role's. So even the project owner (whose own role has BYPASSRLS) is filtered in the app.
- `oi_publisher_<schema>` (NOLOGIN): granted to whoever runs this job; a `FOR ALL ... USING (true)` policy lets
  it maintain every row with FORCE ROW LEVEL SECURITY on (owners are subject to RLS too) without BYPASSRLS.
- Policies (ENABLE + FORCE RLS): `review_orders` rows where the region is one of the user's regions, or the
  user has `*`; `sap_outbound` rows whose order is visible in `review_orders` (inherits the region rule);
  `user_regions` only the user's own rows.
- The app's service principal keeps only USAGE on the schema: no table privileges, no reviewer role.

```python
import re as _re

ident = _re.sub(r"\W", "_", pg_schema.lower())
REVIEWER, PUBLISHER = f"oi_reviewer_{ident}", f"oi_publisher_{ident}"

# ---- expand region_access groups to principals (workspace SCIM API) ----
access = [(r.group_name, r.region) for r in spark.table(f"{S}.region_access").collect() if r.group_name and r.region]
_cache = {}


def _scim(path, **query):
    return w.api_client.do("GET", f"/api/2.0/preview/scim/v2/{path}", query=query or None)


def principal_of(ref):
    """SCIM member $ref (Users/<id> | ServicePrincipals/<id>) -> (identity_type, postgres role name)."""
    if ref not in _cache:
        kind, _id = ref.split("/", 1)
        if kind == "Users":
            u = _scim(ref, attributes="userName,active")
            _cache[ref] = ("USER", u["userName"]) if u.get("active", True) else None
        elif kind == "ServicePrincipals":
            sp = _scim(ref, attributes="applicationId,active")
            _cache[ref] = ("SERVICE_PRINCIPAL", sp["applicationId"]) if sp.get("active", True) else None
        else:
            _cache[ref] = None
    return _cache[ref]


def expand(group=None, group_id=None, seen=None):
    """All principals in a group (by display name or id), following nested groups. None = group not found."""
    seen = set() if seen is None else seen
    if group_id is None:
        found = _scim("Groups", filter=f'displayName eq "{group}"', attributes="id").get("Resources") or []
        if not found:
            return None
        group_id = found[0]["id"]
    if group_id in seen:
        return set()
    seen.add(group_id)
    members = _scim(f"Groups/{group_id}", attributes="members").get("members") or []
    out = set()
    for m in members:
        ref = m.get("$ref") or ""
        if ref.startswith("Groups/"):
            out |= expand(group_id=m["value"], seen=seen) or set()
        elif ref:
            p = principal_of(ref)
            if p:
                out.add(p)
    return out


grants = set()                      # (identity_type, principal, region, via_group)
for group, region in access:
    members = expand(group)
    if members is None:
        print(f"WARN group {group!r} (region {region}) not found in this workspace — skipped")
        continue
    print(f"group {group!r} -> region {region}: {len(members)} principal(s)")
    grants |= {(t, p, region, group) for t, p in members}
principals = {(t, p) for t, p, _, _ in grants}
if not principals:
    print("WARN no principals from region_access — nobody can see any order in the app")
```

**Output:**

```
ERROR: Command skipped
```

```python
c = connect()
try:
    cur = c.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
    cur.execute("SELECT rolname FROM pg_roles")
    existing = {r[0] for r in cur.fetchall()}
    for role in (REVIEWER, PUBLISHER):
        if role not in existing:
            cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
    cur.execute(f'GRANT "{PUBLISHER}" TO CURRENT_USER')
    # Each principal's own login role (the Lakebase OAuth role for that Databricks identity) + reviewer membership.
    for t, p in sorted(principals):
        if p not in existing:
            cur.execute("SELECT databricks_create_role(%s, %s)", (p, t))
            print(f"created Postgres role for {t} {p}")
        cur.execute(f'GRANT "{REVIEWER}" TO "{p}"')
    # Principals no longer in any region group lose the reviewer role.
    cur.execute("SELECT m.rolname FROM pg_auth_members am JOIN pg_roles r ON r.oid = am.roleid "
                "JOIN pg_roles m ON m.oid = am.member WHERE r.rolname = %s", (REVIEWER,))
    for (member,) in cur.fetchall():
        if member not in {p for _, p in principals}:
            cur.execute(f'REVOKE "{REVIEWER}" FROM "{member}"')
            print(f"revoked {REVIEWER} from {member} (no longer in a region group)")

    # One transaction: mapping, grants and policies change together (no window with the wrong access).
    c.autocommit = False
    run_script(cur, """
CREATE TABLE IF NOT EXISTS user_regions (
  principal text NOT NULL,      -- Postgres role name of the Databricks identity (user email / SP application id)
  region    text NOT NULL,      -- a region, or * = all regions
  via_group text NOT NULL,      -- the region_access group that granted it
  PRIMARY KEY (principal, region, via_group)
)""")
    cur.execute("DELETE FROM user_regions")      # derived table: fully re-published every run
    if grants:
        cur.executemany("INSERT INTO user_regions (principal, region, via_group) VALUES (%s, %s, %s)",
                        [(p, r, g) for _, p, r, g in sorted(grants)])
    visible = ("(coalesce(region, 'Unassigned') IN "
               "(SELECT ur.region FROM user_regions ur WHERE ur.principal = session_user) "
               "OR EXISTS (SELECT 1 FROM user_regions ur WHERE ur.principal = session_user AND ur.region = '*'))")
    order_visible = "EXISTS (SELECT 1 FROM review_orders r WHERE r.order_id = sap_outbound.order_id)"
    cit_visible = "EXISTS (SELECT 1 FROM review_orders r WHERE r.order_id = review_citations.order_id)"
    run_script(cur, f"""
REVOKE ALL ON review_orders, sap_outbound, user_regions, review_citations FROM "{app_sp}";
REVOKE ALL ON review_orders, sap_outbound, user_regions, review_citations FROM "{REVIEWER}";
GRANT SELECT ON review_citations TO "{REVIEWER}";
GRANT SELECT, INSERT, UPDATE, DELETE ON review_citations TO "{PUBLISHER}";
ALTER TABLE review_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_citations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oi_publisher_all ON review_citations;
DROP POLICY IF EXISTS oi_region_citations ON review_citations;
CREATE POLICY oi_publisher_all ON review_citations FOR ALL TO "{PUBLISHER}" USING (true) WITH CHECK (true);
CREATE POLICY oi_region_citations ON review_citations FOR SELECT TO "{REVIEWER}" USING ({cit_visible});
GRANT USAGE ON SCHEMA "{pg_schema}" TO "{REVIEWER}";
GRANT SELECT ON review_orders, user_regions TO "{REVIEWER}";
GRANT UPDATE (po_number, customer_name, customer_number, order_date, currency, ship_to, line_items_json, n_lines, status)
  ON review_orders TO "{REVIEWER}";
GRANT SELECT, INSERT, DELETE ON sap_outbound TO "{REVIEWER}";
GRANT SELECT, INSERT, UPDATE, DELETE ON review_orders, sap_outbound, user_regions TO "{PUBLISHER}";
ALTER TABLE review_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE sap_outbound ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap_outbound FORCE ROW LEVEL SECURITY;
ALTER TABLE user_regions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_regions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oi_publisher_all ON review_orders;
DROP POLICY IF EXISTS oi_region_select ON review_orders;
DROP POLICY IF EXISTS oi_region_update ON review_orders;
DROP POLICY IF EXISTS oi_publisher_all ON sap_outbound;
DROP POLICY IF EXISTS oi_region_outbound ON sap_outbound;
DROP POLICY IF EXISTS oi_publisher_all ON user_regions;
DROP POLICY IF EXISTS oi_own_rows ON user_regions;
CREATE POLICY oi_publisher_all ON review_orders FOR ALL TO "{PUBLISHER}" USING (true) WITH CHECK (true);
CREATE POLICY oi_region_select ON review_orders FOR SELECT TO "{REVIEWER}" USING {visible};
CREATE POLICY oi_region_update ON review_orders FOR UPDATE TO "{REVIEWER}" USING {visible} WITH CHECK {visible};
CREATE POLICY oi_publisher_all ON sap_outbound FOR ALL TO "{PUBLISHER}" USING (true) WITH CHECK (true);
CREATE POLICY oi_region_outbound ON sap_outbound FOR ALL TO "{REVIEWER}" USING ({order_visible}) WITH CHECK ({order_visible});
CREATE POLICY oi_publisher_all ON user_regions FOR ALL TO "{PUBLISHER}" USING (true) WITH CHECK (true);
CREATE POLICY oi_own_rows ON user_regions FOR SELECT TO "{REVIEWER}" USING (principal = session_user)
""")
    c.commit()
    c.autocommit = True
    cur.execute("SELECT region, count(*) FROM review_orders GROUP BY 1 ORDER BY 1")
    by_region = cur.fetchall()
finally:
    c.close()

print(f"RLS on: {len(principals)} principal(s), {len(grants)} grant row(s) in user_regions; reviewer role {REVIEWER}; "
      f"app service principal {app_sp} has no table access. Orders by region: {by_region}")
```

**Output:**

```
ERROR: Command skipped
```

