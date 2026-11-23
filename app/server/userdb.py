"""Per-request Lakebase connection AS THE SIGNED-IN USER (Databricks Apps user authorization).

Flow (verified on fevm, see docs/ARCHITECTURE.md "Row-level security"):
  1. The Apps proxy forwards the user's downscoped OAuth token in `X-Forwarded-Access-Token` (the app must have
     the `postgres` user-authorization scope, `user_api_scopes` in resources/review_app.yml).
  2. That token is exchanged for a Lakebase database credential: POST /api/2.0/postgres/credentials
     {"endpoint": <read-write endpoint>} called WITH THE USER'S TOKEN. (The forwarded token itself is not
     accepted as the Postgres password.)
  3. psycopg logs in as the user's Postgres role (= their email, created by the publish job) with that credential.
  4. `SET ROLE oi_reviewer`: the session keeps the user's identity (`session_user`, which the RLS policies use)
     but runs with the reviewer role's privileges — no table grants, no BYPASSRLS of its own — so even a
     project owner / DATABRICKS_SUPERUSER signing in to the app sees only their regions.

RLS_ENFORCED=false (or the warehouse backend): `user_connection` yields None and db.py uses the app's
service-principal connection. With RLS on, a request without a forwarded user token is refused (default deny).
"""
import hashlib
import threading
import time
from contextlib import contextmanager

import requests
from fastapi import HTTPException, Request

from . import config

_cred_cache: dict = {}          # sha256(user token) -> (expires_at, role, db credential); memory only
_cache_lock = threading.Lock()
_CRED_TTL = 30 * 60             # Lakebase credentials live ~1h; refresh well before


def _host_url() -> str:
    h = config.get_workspace_hostname()
    return f"https://{h}"


def user_token(request: Request):
    return request.headers.get("x-forwarded-access-token")


def _role_for(request: Request, token: str) -> str:
    """Postgres role name Lakebase uses for a Databricks user = the user's email (userName)."""
    for h in ("x-forwarded-email", "x-forwarded-preferred-username"):
        v = request.headers.get(h)
        if v:
            return v
    r = requests.get(f"{_host_url()}/api/2.0/preview/scim/v2/Me",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    return r.json()["userName"]


def _credential(token: str) -> str:
    """Lakebase database credential minted with the USER's token (requires the `postgres` scope)."""
    r = requests.post(f"{_host_url()}/api/2.0/postgres/credentials",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"endpoint": config.get_pg_endpoint().name}, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=403,
                            detail=f"Lakebase credential for the signed-in user refused ({r.status_code}): "
                                   f"{r.text[:200]}")
    return r.json()["token"]


def _role_and_credential(request: Request, token: str):
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cred_cache.get(key)
        if hit and hit[0] > now:
            return hit[1], hit[2]
        for k in [k for k, v in _cred_cache.items() if v[0] <= now]:
            _cred_cache.pop(k, None)
    role, cred = _role_for(request, token), _credential(token)
    with _cache_lock:
        _cred_cache[key] = (now + _CRED_TTL, role, cred)
    return role, cred


def _connect(user: str, password: str):
    import psycopg
    return psycopg.connect(
        host=config.get_pg_host(), port=config.PGPORT, dbname=config.PGDATABASE,
        user=user, password=password, sslmode=config.PGSSLMODE,
        options=f"-c search_path={config.PGSCHEMA}", autocommit=True,
    )


@contextmanager
def user_connection(request: Request, set_role: bool = True):
    """psycopg connection for this request, as the signed-in user (see module doc); None = use the app's
    service-principal connection (RLS_ENFORCED=false or warehouse backend)."""
    if not config.RLS_ENFORCED or config.BACKEND != "lakebase":
        yield None
        return
    token = user_token(request)
    if not token:
        raise HTTPException(status_code=401,
                            detail="No user token forwarded: enable user authorization (scope 'postgres') on the "
                                   "app and sign in through the app URL. (Set RLS_ENFORCED=false only for local dev.)")
    role, cred = _role_and_credential(request, token)
    try:
        conn = _connect(role, cred)
    except Exception as e:  # noqa — most often: the user has no Postgres role yet (not in region_access)
        raise HTTPException(status_code=403,
                            detail=f"Lakebase login as {role} failed — is the user in a region group "
                                   f"(region_access) and has publish run since? ({type(e).__name__}: "
                                   f"{str(e).splitlines()[0][:200]})")
    try:
        if set_role:
            try:
                with conn.cursor() as cur:
                    cur.execute(f'SET ROLE "{config.PG_REVIEWER_ROLE}"')
            except Exception as e:  # noqa — role missing (publish not run with RLS yet) or user not a member
                raise HTTPException(status_code=403,
                                    detail=f"{role} can't use the reviewer role {config.PG_REVIEWER_ROLE} — not in "
                                           f"any region group (region_access), or the publish job hasn't run with "
                                           f"rls_enforced=true yet. ({str(e).splitlines()[0][:160]})")
        yield conn
    finally:
        conn.close()


def probe_direct(request: Request) -> str:
    """Spike only: does Lakebase accept the forwarded workspace token itself as the password?"""
    token = user_token(request)
    if not token:
        return "no forwarded token"
    try:
        role = _role_for(request, token)
        _connect(role, token).close()
        return "accepted"
    except Exception as e:  # noqa
        return f"refused: {type(e).__name__}: {str(e).splitlines()[0][:200]}"
