"""Dual-mode configuration: works locally (via CLI profile) and in Databricks Apps
(via auto-injected service principal).

Supports two storage backends for the review queue (set APP_BACKEND, or it is inferred):
  * "lakebase"  — Lakebase Postgres (OLTP; recommended for the interactive Review App)
  * "warehouse" — Delta tables via a SQL warehouse (the original zero-infra fallback)
"""
import os
import re
from functools import lru_cache
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

CATALOG = os.environ.get("UC_CATALOG", "main")
SCHEMA = os.environ.get("UC_SCHEMA", "order_intake")
# Volume holding the source documents: document endpoints only ever read files under
# /Volumes/<VOLUME_CATALOG>/<VOLUME_SCHEMA>/<VOLUME>/{inbound_docs,outlook_attachments}/ (server/documents.allowed_path).
VOLUME = os.environ.get("UC_VOLUME", "landing")
# the Volume may sit in another catalog/schema than the tables (default: the same)
VOLUME_CATALOG = os.environ.get("UC_VOLUME_CATALOG") or CATALOG
VOLUME_SCHEMA = os.environ.get("UC_VOLUME_SCHEMA") or SCHEMA

# --- backend selection -------------------------------------------------------
# Set from the bundle (APP_BACKEND = the target's `backend` variable).
BACKEND = os.environ.get("APP_BACKEND", "warehouse").lower()

WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

# Table identifiers used in route SQL: the warehouse backend needs the full 3-level UC
# name; Lakebase tables live in the Postgres database's `public` schema (bare names).
if BACKEND == "warehouse":
    REVIEW_TABLE = f"{CATALOG}.{SCHEMA}.review_orders"
    OUTBOUND_TABLE = f"{CATALOG}.{SCHEMA}.sap_outbound"
    CITATIONS_TABLE = f"{CATALOG}.{SCHEMA}.review_citations"
else:
    REVIEW_TABLE = "review_orders"
    OUTBOUND_TABLE = "sap_outbound"
    CITATIONS_TABLE = "review_citations"

# --- lakebase (Postgres, Autoscaling) backend -------------------------------
# The app's `postgres` resource gives its service principal a Postgres role; host + a short-lived credential
# are resolved from the project/branch via the SDK (works locally with a CLI profile too).
LAKEBASE_PROJECT = os.environ.get("LAKEBASE_PROJECT", "order-intake")
LAKEBASE_BRANCH = os.environ.get("LAKEBASE_BRANCH", "production")
PGHOST = os.environ.get("PGHOST", "")
PGPORT = int(os.environ.get("PGPORT", "5432"))
PGDATABASE = os.environ.get("PGDATABASE") or os.environ.get("LAKEBASE_DATABASE", "databricks_postgres")
PGUSER = os.environ.get("PGUSER", "")
PGSSLMODE = os.environ.get("PGSSLMODE", "require")
# Postgres schema holding review_orders / sap_outbound (set as the connection's search_path).
PGSCHEMA = os.environ.get("LAKEBASE_SCHEMA", "public")

# --- row-level security (Lakebase) ------------------------------------------
# true (default): review_orders/sap_outbound are read/written over a per-request connection AS THE SIGNED-IN USER
# (userdb.py) and Postgres RLS restricts rows to the user's regions; no forwarded user token = request refused.
# false: everything goes through the app's service-principal connection (local dev / RLS not set up).
RLS_ENFORCED = os.environ.get("RLS_ENFORCED", "true").strip().lower() not in ("false", "0", "no", "off")
# NOLOGIN role (created by the publish job, one per Postgres schema) holding the reviewers' table privileges;
# user sessions SET ROLE to it. Must match 04_publish_review_queue.py.
PG_REVIEWER_ROLE = os.environ.get("PG_REVIEWER_ROLE") or "oi_reviewer_" + re.sub(r"\W", "_", PGSCHEMA.lower())


@lru_cache(maxsize=1)
def get_workspace_client() -> WorkspaceClient:
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_oauth_token() -> str:
    """Return a workspace bearer token for both OAuth/U2M (local) and SP (app) auth."""
    w = get_workspace_client()
    if w.config.token:
        return w.config.token
    headers = w.config.authenticate()
    if headers and "Authorization" in headers:
        return headers["Authorization"].replace("Bearer ", "")
    raise RuntimeError("Unable to obtain OAuth token")


def get_workspace_hostname() -> str:
    """Return bare hostname (no scheme) for the SQL connector (warehouse backend)."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        return host.replace("https://", "").replace("http://", "").strip("/")
    host = get_workspace_client().config.host
    return host.replace("https://", "").replace("http://", "").strip("/")


def get_current_user() -> str:
    try:
        return get_workspace_client().current_user.me().user_name or "unknown"
    except Exception:
        return "unknown"


# --- Lakebase connection parameters -----------------------------------------
@lru_cache(maxsize=1)
def get_pg_endpoint():
    """The branch's read-write compute endpoint."""
    branch = f"projects/{LAKEBASE_PROJECT}/branches/{LAKEBASE_BRANCH}"
    for e in get_workspace_client().postgres.list_endpoints(parent=branch):
        if str(e.status.endpoint_type).endswith("READ_WRITE"):
            return e
    raise RuntimeError(f"No read-write endpoint on {branch}")


def get_pg_host() -> str:
    return PGHOST or get_pg_endpoint().status.hosts.host


def get_pg_user() -> str:
    """Postgres role = the authenticated principal: the app's service principal (client id) when deployed,
    the user's email locally."""
    if PGUSER:
        return PGUSER
    if IS_DATABRICKS_APP and os.environ.get("DATABRICKS_CLIENT_ID"):
        return os.environ["DATABRICKS_CLIENT_ID"]
    return get_current_user()


def get_pg_password() -> str:
    """Short-lived Lakebase OAuth credential (expires ~hourly), minted per connection."""
    return get_workspace_client().postgres.generate_database_credential(endpoint=get_pg_endpoint().name).token
