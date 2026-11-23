"""GET /api/whoami-db — which Postgres identity the app's per-request user connection gets (diagnostic)."""
from fastapi import APIRouter, Request

from .. import userdb

router = APIRouter()


@router.get("/whoami-db")
def whoami_db(request: Request, probe: bool = False):
    out = {"forwarded_token": bool(request.headers.get("x-forwarded-access-token")),
           "forwarded_email": request.headers.get("x-forwarded-email")}
    if probe:  # spike: try the forwarded token directly as the Postgres password too
        out["direct_token_as_password"] = userdb.probe_direct(request)
    for key, set_role in (("login", False), ("reviewer_session", True)):
        try:
            with userdb.user_connection(request, set_role=set_role) as conn:
                if conn is None:
                    out[key] = {"ok": True, "rls_enforced": False, "note": "app service-principal connection"}
                    continue
                with conn.cursor() as cur:
                    cur.execute("SELECT current_user, session_user")
                    cu, su = cur.fetchone()
            out[key] = {"ok": True, "current_user": cu, "session_user": su}
        except Exception as e:  # noqa
            out[key] = {"ok": False, "error": f"{type(e).__name__}: {getattr(e, 'detail', None) or str(e)[:300]}"}
    out["ok"] = out["reviewer_session"]["ok"]
    return out
