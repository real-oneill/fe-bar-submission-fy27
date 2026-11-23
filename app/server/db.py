"""Data access for the Review App, with two interchangeable backends (see config.BACKEND):

  * "lakebase"  — Lakebase Postgres via psycopg (OLTP: low-latency reads + row updates,
                  real concurrency for multiple reviewers). Recommended.
  * "warehouse" — Delta tables via the Databricks SQL connector (zero extra infra).

Route SQL is written once with named `:param` markers. For Postgres we translate those to
psycopg's `%(param)s` style so the route layer is backend-agnostic. Lakebase credentials
expire hourly, so a fresh credential is minted per connection.
"""
import re
import threading
from contextlib import contextmanager

from . import config

_lock = threading.Lock()

# :name -> placeholder, but never a `::type` cast (Postgres) — require a non-colon lookbehind.
_NAMED_PARAM = re.compile(r"(?<!:):([a-zA-Z_]\w*)")


# --------------------------------------------------------------------------- warehouse
@contextmanager
def _warehouse_connection():
    from databricks import sql
    conn = sql.connect(
        server_hostname=config.get_workspace_hostname(),
        http_path=f"/sql/1.0/warehouses/{config.WAREHOUSE_ID}",
        access_token=config.get_oauth_token(),
    )
    try:
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------------- lakebase
@contextmanager
def _lakebase_connection():
    import psycopg
    conn = psycopg.connect(
        host=config.get_pg_host(),
        port=config.PGPORT,
        dbname=config.PGDATABASE,
        user=config.get_pg_user(),
        password=config.get_pg_password(),
        sslmode=config.PGSSLMODE,
        options=f"-c search_path={config.PGSCHEMA}",
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def _pg_sql(sql_text: str) -> str:
    """Translate `:name` markers to psycopg `%(name)s`."""
    return _NAMED_PARAM.sub(r"%(\1)s", sql_text)


# --------------------------------------------------------------------------- public API
def _is_lakebase() -> bool:
    return config.BACKEND == "lakebase"


def _pg_run(conn, sql_text, params, fetch):
    from psycopg.rows import dict_row
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_pg_sql(sql_text), params)
        if fetch and cur.description:
            return cur.fetchall()
        return []


def query(sql_text: str, params=None, conn=None):
    """Run a statement and return rows as dicts. `conn`: a Lakebase connection to use (the per-request user
    connection from userdb.py); None = the app's service-principal connection (or the warehouse backend)."""
    params = params or {}
    if conn is not None:
        return _pg_run(conn, sql_text, params, True)
    with _lock:
        if _is_lakebase():
            with _lakebase_connection() as c:
                return _pg_run(c, sql_text, params, True)
        with _warehouse_connection() as c:
            cur = c.cursor()
            try:
                cur.execute(sql_text, params)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
                return []
            finally:
                cur.close()


def execute(sql_text: str, params=None, conn=None):
    """Run a statement; returns the affected row count when known (Lakebase), else None."""
    params = params or {}
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(_pg_sql(sql_text), params)
            return cur.rowcount
    with _lock:
        if _is_lakebase():
            with _lakebase_connection() as c:
                with c.cursor() as cur:
                    cur.execute(_pg_sql(sql_text), params)
                    return cur.rowcount
        with _warehouse_connection() as c:
            cur = c.cursor()
            try:
                cur.execute(sql_text, params)
            finally:
                cur.close()
        return None
