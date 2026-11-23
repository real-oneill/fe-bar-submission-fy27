#!/usr/bin/env python3
"""Pre-deploy checks for the Order Intake accelerator: is THIS workspace and THIS login ready for `bundle deploy`?

    python3 scripts/preflight.py -t custom -p <cli-profile> [--var name=value ...]

Reads the target's resolved variables (`databricks bundle validate -o json`: variable-overrides.json and --var
included), then probes the workspace in the order a deploy would hit things: tooling, login, Unity Catalog
(catalog / schema / volume privileges), warehouse, model endpoints, Apps, Lakebase, the Outlook and Graph
connections (mail_source=outlook or both) and the SAP views and sales orgs (master_source=sap). It changes nothing: only reads, plus one
`SELECT 1` and one tiny `ai_query` on the warehouse.

Statuses: PASS, FAIL (will break the deploy or a run), WARN (probably a problem, or could not be checked),
INFO, MANUAL (cannot be checked from here: confirm it once). Exit code 1 when anything FAILs.
Needs only Python 3.9+ and the Databricks CLI (>= 1.19.0). Full list and the reasons: docs/PREREQUISITES.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict

MIN_CLI = (1, 19, 0)

# What the deployer (the identity the jobs and the pipeline run as) needs. Verified on a customer workspace: pipelines need
# CREATE_TABLE + CREATE_MATERIALIZED_VIEW; the UC prompt registry needs CREATE_FUNCTION + EXECUTE + MANAGE on the schema.
SCHEMA_NEED = ("USE_SCHEMA", "CREATE_TABLE", "CREATE_MATERIALIZED_VIEW", "CREATE_FUNCTION", "EXECUTE", "MANAGE")
VOLUME_NEED = ("READ_VOLUME", "WRITE_VOLUME")
SAP_SCHEMA = "db_fnd_proc"
SAP_VIEWS = ("v_customer_master", "v_address_master_customer", "v_customer_sales_org_master",
             "v_customer_master_partner_functions", "v_material_master", "v_material_master_sales",
             "v_material_master_unit_of_measures", "v_material_text", "t_sales_org_geography_look_up")

MANUAL = [
    ("Serverless compute", "Serverless compute for jobs and pipelines is enabled (the pipeline and every job run serverless)."),
    ("PyPI from serverless", "Serverless can install openpyxl, xlrd, extract-msg and mlflow (allow PyPI, or a mirror, in the network / egress policy)."),
    ("AI Functions", "ai_parse_document, ai_extract (v2.1, precision mode) and ai_query are available in the workspace's region (extraction_mode=hybrid uses all three)."),
    ("Unity Catalog prompt registry and tracing", "MLflow prompt registry in Unity Catalog and tracing to Unity Catalog are enabled for the workspace (preview features)."),
    ("Apps and Lakebase quota", "You may create Databricks Apps and Lakebase (Autoscaling) projects; the workspace quota allows one more of each."),
    ("Network", "Reviewers' browsers can reach the workspace and the app URL (IP access lists, private link)."),
]
MANUAL_RLS = [
    ("Region groups (rls_enforced=true)", "Databricks groups exist for each region (workspace groups, or account groups assigned to the workspace) and their names are in region_access."),
    ("App user authorization (rls_enforced=true)", "The workspace allows the `postgres` user-authorization scope for apps (Settings -> Development -> restrict OAuth scopes); each reviewer consents once on first open."),
]
MANUAL_OUTLOOK = [
    ("Outlook connector enabled", "The Lakeflow Connect Outlook connector (Beta) is enabled for the account and the connection of type OUTLOOK exists."),
    ("Entra app", "The connector's Entra app has the Mail.Read application permission on the mailboxes, with admin consent; the Graph (HTTP) connection uses the same app."),
]


@dataclass
class Result:
    group: str
    check: str
    status: str
    detail: str = ""
    fix: str = ""


def parse_cli_version(text: str):
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def first_error(text: str, limit: int = 240) -> str:
    """The line of CLI / SQL error output worth showing: the first one that starts with Error, else the first line."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return "failed"
    pick = next((l for l in lines if l.lower().startswith("error")), lines[0])
    return pick[:limit]


def missing_privileges(have: set, need) -> list:
    """Privileges in `need` that `have` lacks (ALL_PRIVILEGES covers everything)."""
    if "ALL_PRIVILEGES" in have:
        return []
    return [p for p in need if p not in have]


def privileges_of(effective: dict) -> set:
    """get-effective output -> every privilege any assignment grants (the user, or a group they are in)."""
    out = set()
    for a in (effective or {}).get("privilege_assignments", []) or []:
        for p in a.get("privileges", []) or []:
            out.add(p.get("privilege"))
    return out


class Cli:
    def __init__(self, profile: str | None):
        self.profile = profile

    def run(self, args: list[str], parse: bool = True):
        """-> (ok, data | error text). JSON output is parsed when parse=True."""
        cmd = ["databricks", *args]
        if self.profile:
            cmd += ["-p", self.profile]
        if parse:
            cmd += ["-o", "json"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        if p.returncode != 0:
            return False, first_error(p.stderr or p.stdout)
        if not parse:
            return True, p.stdout
        try:
            return True, json.loads(p.stdout or "null")
        except json.JSONDecodeError:
            return False, "unexpected output: " + (p.stdout or "")[:120]

    def sql(self, warehouse: str, statement: str):
        body = json.dumps({"warehouse_id": warehouse, "statement": statement, "wait_timeout": "50s",
                           "on_wait_timeout": "CANCEL"})
        ok, d = self.run(["api", "post", "/api/2.0/sql/statements", "--json", body])
        if not ok:
            return "FAILED", d
        st = (d.get("status") or {})
        return st.get("state"), first_error((st.get("error") or {}).get("message", "")) if st.get("error") else ""


class Checker:
    def __init__(self, cli: Cli, cfg: dict, user: str):
        self.cli, self.cfg, self.user = cli, cfg, user
        self.results: list[Result] = []

    def add(self, group, check, status, detail="", fix=""):
        self.results.append(Result(group, check, status, detail, fix))

    def var(self, name, default=""):
        v = self.cfg.get("variables", {}).get(name, {})
        val = v.get("value", v.get("default", default))
        return default if val is None else val

    def privs(self, kind, name):
        ok, d = self.cli.run(["grants", "get-effective", kind, name, "--principal", self.user])
        return (privileges_of(d), None) if ok else (set(), d)

    # --- groups -------------------------------------------------------------------------------------------------
    def unity_catalog(self):
        g = "Unity Catalog"
        cat, sch, vol = self.var("catalog"), self.var("schema"), self.var("volume")
        vcat, vsch = self.var("volume_catalog") or cat, self.var("volume_schema") or sch
        if not cat:
            self.add(g, "catalog set", "FAIL", "variable `catalog` is empty", "set it in variable-overrides.json or --var catalog=…")
            return
        ok, c = self.cli.run(["catalogs", "get", cat])
        if not ok:
            self.add(g, f"catalog {cat}", "FAIL", c, "the catalog must exist and be visible to you; create it or fix the name")
            return
        have, err = self.privs("catalog", cat)
        miss = missing_privileges(have, ("USE_CATALOG",)) if not err else []
        self.add(g, f"catalog {cat}: USE_CATALOG", "WARN" if err else ("FAIL" if miss else "PASS"),
                 err or ("missing USE_CATALOG" if miss else "ok"), "ask the catalog owner for USE CATALOG" if miss else "")

        ok, s = self.cli.run(["schemas", "get", f"{cat}.{sch}"])
        if ok:
            if s.get("owner") == self.user:
                self.add(g, f"schema {cat}.{sch}", "PASS", "you own it: all schema privileges apply")
            else:
                have, err = self.privs("schema", f"{cat}.{sch}")
                miss = missing_privileges(have, SCHEMA_NEED) if not err else []
                self.add(g, f"schema {cat}.{sch} privileges", "WARN" if err else ("FAIL" if miss else "PASS"),
                         err or ("missing " + ", ".join(miss) if miss else "ok"),
                         "GRANT " + ", ".join(miss) + f" ON SCHEMA {cat}.{sch} TO `{self.user}` (CREATE FUNCTION, EXECUTE and "
                         "MANAGE are what the Unity Catalog prompt registry needs)" if miss else "")
        else:
            have, err = self.privs("catalog", cat)
            miss = missing_privileges(have, ("CREATE_SCHEMA",)) if not err else []
            self.add(g, f"schema {cat}.{sch}", "WARN" if err else ("FAIL" if miss else "INFO"),
                     err or ("does not exist and you cannot create it (CREATE_SCHEMA)" if miss
                             else "does not exist yet: the setup job creates it and you will own it. If the volume is in this "
                                  "schema, create the schema and the volume yourself before deploying"),
                     f"GRANT CREATE SCHEMA ON CATALOG {cat} TO `{self.user}`, or create the schema" if miss else "")

        if not vol:
            self.add(g, "volume set", "FAIL", "variable `volume` is empty", "set it; the bundle does not create the volume")
            return
        vfull = f"{vcat}.{vsch}.{vol}"
        ok, v = self.cli.run(["volumes", "read", vfull])
        if not ok:
            self.add(g, f"volume {vfull}", "FAIL", v, "create the volume first, and its schema if it is new (the bundle never creates the volume): "
                     "CREATE VOLUME " + vfull)
            return
        if v.get("owner") == self.user:
            self.add(g, f"volume {vfull}", "PASS", "you own it")
        else:
            have, err = self.privs("volume", vfull)
            miss = missing_privileges(have, VOLUME_NEED) if not err else []
            self.add(g, f"volume {vfull} privileges", "WARN" if err else ("FAIL" if miss else "PASS"),
                     err or ("missing " + ", ".join(miss) if miss else "ok"),
                     f"GRANT {', '.join(miss)} ON VOLUME {vfull} TO `{self.user}`" if miss else "")
        ok, out = self.cli.run(["fs", "ls", f"dbfs:/Volumes/{vcat}/{vsch}/{vol}"], parse=False)
        self.add(g, "volume reachable through the Files API", "PASS" if ok else "FAIL", "ok" if ok else out,
                 "the jobs read and write the volume through the Files API; check the volume's storage access" if not ok else "")
        if (vcat, vsch) != (cat, sch):
            self.add(g, "volume in another catalog/schema", "INFO",
                     f"{vfull}: the review app's service principal is granted READ VOLUME on it at deploy time; that needs "
                     f"USE CATALOG on {vcat} for the app (grant it, or have a catalog MANAGE holder deploy)")

    def compute(self):
        g = "Compute and models"
        wh = self.var("warehouse_id")
        if not wh:
            self.add(g, "SQL warehouse", "FAIL", "variable `warehouse_id` is empty", "set it to a SQL warehouse you can use")
        else:
            ok, w = self.cli.run(["warehouses", "get", wh])
            if not ok:
                self.add(g, f"SQL warehouse {wh}", "FAIL", w, "pick an existing warehouse id (databricks warehouses list)")
            else:
                state, err = self.cli.sql(wh, "SELECT 1")
                slow = state in ("CANCELED", "PENDING", "RUNNING")
                self.add(g, f"SQL warehouse {wh} ({w.get('warehouse_type', '?')})",
                         "PASS" if state == "SUCCEEDED" else ("WARN" if slow else "FAIL"),
                         "SELECT 1 works" if state == "SUCCEEDED" else
                         ("did not answer within 50 s (cold start?): run the preflight again" if slow else f"{state}: {err}"),
                         "" if state == "SUCCEEDED" or slow else "you need CAN USE on the warehouse")
        for var, role in (("serving_endpoint", "extraction (ai_query batch)"), ("judge_endpoint", "LLM judges")):
            name = self.var(var)
            ok, e = self.cli.run(["serving-endpoints", "get", name]) if name else (False, "variable is empty")
            ready = ok and (e.get("state") or {}).get("ready") == "READY"
            self.add(g, f"model endpoint {name or '(unset)'} — {role}", "PASS" if ready else "FAIL",
                     "READY" if ready else (e if not ok else "not READY"),
                     f"set `{var}` to a Foundation Model endpoint that exists in this workspace (databricks serving-endpoints list)"
                     if not ready else "")
        if wh and self.var("serving_endpoint"):
            state, err = self.cli.sql(wh, f"SELECT ai_query('{self.var('serving_endpoint')}', 'Reply with OK') AS r")
            self.add(g, "ai_query reachable from SQL", "PASS" if state == "SUCCEEDED" else "WARN",
                     "ok" if state == "SUCCEEDED" else f"{state}: {err}",
                     "ai_query must be enabled and you need CAN QUERY on the endpoint" if state != "SUCCEEDED" else "")

    def platform(self):
        g = "Apps, Lakebase, MLflow"
        ok, apps = self.cli.run(["apps", "list"])
        self.add(g, "Databricks Apps available", "PASS" if ok else "FAIL", "ok" if ok else apps,
                 "Apps must be enabled for the workspace and you must be allowed to create them" if not ok else "")
        name = self.var("app_name")
        if ok and any(a.get("name") == name for a in apps):
            self.add(g, f"app name {name}", "INFO", "exists already: fine when this bundle owns it; otherwise pick another app_name")
        ok, pg = self.cli.run(["postgres", "list-projects"])
        self.add(g, "Lakebase (Autoscaling) available", "PASS" if ok else "FAIL", "ok" if ok else pg,
                 "the review app stores its queue in a Lakebase Autoscaling project: needs the feature and CLI >= 1.19.0" if not ok else "")
        proj = self.var("lakebase_project")
        exists = ok and any(p.get("project_id") == proj for p in pg)
        creates = bool(self.var("lakebase_projects", {}))
        if ok and creates and exists:
            self.add(g, f"Lakebase project {proj}", "INFO",
                     "exists already: fine on a redeploy; for a first deploy use another lakebase_project, or set lakebase_projects to {} to use it")
        elif ok and not creates:
            self.add(g, f"Lakebase project {proj} (existing, lakebase_projects is empty)", "PASS" if exists else "FAIL",
                     "found" if exists else "not found",
                     "" if exists else "create the project, or unset lakebase_projects so the bundle creates it")
        exp = self.var("quality_experiment")
        parent = os.path.dirname(exp) if exp else ""
        if parent:
            ok, _ = self.cli.run(["workspace", "get-status", parent])
            self.add(g, f"MLflow experiment folder {parent}", "PASS" if ok else "FAIL", "ok" if ok else "folder not found",
                     "the quality experiment is created under quality_experiment; its parent folder must exist" if not ok else "")

    def mail(self):
        g = "Mail"
        src = self.var("mail_source")
        if src not in ("outlook", "both"):
            self.add(g, "mail_source", "INFO", f"{src}: mail files are read from <volume>/inbound_docs/; no Outlook prerequisites")
            return
        res = self.cfg.get("resources", {})
        owns = "outlook_ingestion" in (res.get("pipelines") or {})
        table = self.var("outlook_table")
        if not table:
            self.add(g, "outlook_table", "FAIL", "mail_source=outlook but `outlook_table` is empty", "set it (catalog.schema.table)")
        if owns:
            conn = self.var("outlook_connection")
            boxes = self.var("outlook_mailboxes", [])
            self.add(g, "bundle-owned Outlook ingestion", "PASS" if conn and boxes else "FAIL",
                     f"connection {conn or '(unset)'}, {len(boxes)} mailbox(es)",
                     "set outlook_connection and outlook_mailboxes (a list) in variable-overrides.json" if not (conn and boxes) else "")
            mb = self.var("outlook_mailbox")
            if boxes and mb and mb not in boxes:
                self.add(g, "outlook_mailbox in outlook_mailboxes", "FAIL", f"{mb} is not ingested", "add it to outlook_mailboxes")
            if conn:
                self.connection(g, conn, "OUTLOOK")
        else:
            self.add(g, "Outlook table", "INFO",
                     f"{table} is written by an ingestion pipeline outside this bundle: it must exist and you need SELECT on it")
        gc = self.var("graph_connection")
        if gc:
            self.connection(g, gc, "HTTP")
        else:
            self.add(g, "graph_connection", "WARN", "not set: attached Outlook messages stay unread and are flagged for review",
                     "create a UC HTTP connection to https://graph.microsoft.com (base path /v1.0, OAuth M2M, Mail.Read) and set it")

    def connection(self, g, name, kind):
        ok, c = self.cli.run(["connections", "get", name])
        if not ok:
            self.add(g, f"connection {name}", "FAIL", c, f"a Unity Catalog connection of type {kind} named {name} must exist")
            return
        ctype = c.get("connection_type")
        extra = ""
        if kind == "HTTP":
            host = (c.get("options") or {}).get("host", "")
            extra = "" if "graph.microsoft.com" in host else f"; host is {host or '(none)'}, expected https://graph.microsoft.com"
        have, err = self.privs("connection", name)
        miss = missing_privileges(have, ("USE_CONNECTION",)) if not err else []
        bad = ctype != kind or extra or miss
        self.add(g, f"connection {name} ({ctype})", "WARN" if err and not bad else ("FAIL" if bad else "PASS"),
                 (f"type {ctype}, expected {kind}" if ctype != kind else "") + extra
                 + ("; missing USE_CONNECTION" if miss else "") or (err or "ok"),
                 f"GRANT USE CONNECTION ON CONNECTION {name} TO `{self.user}`" if miss else "")

    def sap(self):
        g = "SAP"
        if self.var("master_source") != "sap":
            self.add(g, "master_source", "INFO", "demo: customers and materials come from the template tables; no SAP prerequisites")
            return
        cat, wh, orgs = self.var("sap_catalog"), self.var("warehouse_id"), self.var("sap_sales_orgs")
        if not cat:
            self.add(g, "sap_catalog", "FAIL", "master_source=sap but `sap_catalog` is empty", "set the catalog holding the SAP views")
            return
        for view in SAP_VIEWS:
            state, err = self.cli.sql(wh, f"SELECT 1 FROM `{cat}`.`{SAP_SCHEMA}`.`{view}` LIMIT 1")
            absent = "NOT_FOUND" in err or "cannot be found" in err
            self.add(g, f"SELECT on {SAP_SCHEMA}.{view}", "PASS" if state == "SUCCEEDED" else "FAIL",
                     "ok" if state == "SUCCEEDED" else f"{state}: {err}",
                     "" if state == "SUCCEEDED" else (
                         f"{cat}.{SAP_SCHEMA}.{view} is not visible: check sap_catalog, and that the SAP data is shared to this workspace"
                         if absent else f"GRANT SELECT on {cat}.{SAP_SCHEMA}.{view} to the identity the jobs run as"))
        if not orgs:
            self.add(g, "sap_sales_orgs", "FAIL", "master_source=sap but `sap_sales_orgs` is empty",
                     "set the sales orgs (VKORG) of the affiliates this deployment serves, comma separated")
            return
        lst = ", ".join("'" + o.strip().replace("'", "") + "'" for o in orgs.split(",") if o.strip())
        state, err = self.cli.sql(wh, f"SELECT count(DISTINCT KUNNR) FROM `{cat}`.`{SAP_SCHEMA}`.`v_customer_sales_org_master` "
                                      f"WHERE MANDT = '100' AND VKORG IN ({lst})")
        self.add(g, f"customers with a sales view in {orgs}", "PASS" if state == "SUCCEEDED" else "WARN",
                 "readable (client 100)" if state == "SUCCEEDED" else f"{state}: {err}",
                 "" if state == "SUCCEEDED" else "check sap_sales_orgs: customers need a KNVV sales view in one of them")


def load_config(cli: Cli, target: str, extra_vars: list[str]):
    args = ["bundle", "validate", "-t", target]
    for v in extra_vars:
        args += ["--var", v]
    ok, d = cli.run(args)
    return (d, None) if ok and isinstance(d, dict) else (None, d)


def render(results: list[Result], color: bool) -> str:
    cols = {"PASS": "32", "FAIL": "31", "WARN": "33", "INFO": "36", "MANUAL": "35", "SKIP": "90"}
    lines, group = [], None
    for r in results:
        if r.group != group:
            group = r.group
            lines.append(f"\n{group}")
        tag = f"{r.status:<6}"
        tag = f"\033[{cols[r.status]}m{tag}\033[0m" if color else tag
        lines.append(f"  {tag} {r.check}" + (f" — {r.detail}" if r.detail else ""))
        if r.fix and r.status in ("FAIL", "WARN"):
            lines.append(f"         fix: {r.fix}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-t", "--target", required=True, help="bundle target (custom, custom_outlook, dev, prod, …)")
    ap.add_argument("-p", "--profile", help="Databricks CLI profile of the workspace to deploy to")
    ap.add_argument("--var", action="append", default=[], help="name=value, passed to the bundle (repeatable)")
    ap.add_argument("--json", action="store_true", help="print the results as JSON")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args(argv)
    cli = Cli(a.profile)
    res: list[Result] = []

    ver = ""
    if shutil.which("databricks"):
        ver = subprocess.run(["databricks", "--version"], capture_output=True, text=True).stdout
    v = parse_cli_version(ver)
    res.append(Result("Your machine", "Databricks CLI >= " + ".".join(map(str, MIN_CLI)),
                      "PASS" if v and v >= MIN_CLI else "FAIL", (ver or "not installed").strip(),
                      "install or upgrade: https://docs.databricks.com/dev-tools/cli/install" if not (v and v >= MIN_CLI) else ""))
    uv = shutil.which("uv")
    res.append(Result("Your machine", "uv installed (builds the src/lib wheel at deploy)", "PASS" if uv else "FAIL",
                      uv or "not found", "" if uv else "install: https://docs.astral.sh/uv/getting-started/installation/"))
    if not (v and v >= MIN_CLI):
        print(render(res, False))
        return 1

    ok, me = cli.run(["current-user", "me"])
    if not ok:
        res.append(Result("Login", f"authenticated (profile {a.profile or 'default'})", "FAIL", me,
                          f"databricks auth login --profile {a.profile or '<name>'}"))
        print(render(res, False))
        return 1
    user = me.get("userName", "")
    res.append(Result("Login", "authenticated", "PASS", f"{user} (profile {a.profile or 'default'})"))

    cfg, err = load_config(cli, a.target, a.var)
    if cfg is None:
        res.append(Result("Bundle", f"bundle validate -t {a.target}", "FAIL", err,
                          "fix the bundle or the variables; every variable the target needs must be set"))
        print(render(res, False))
        return 1
    res.append(Result("Bundle", f"bundle validate -t {a.target}", "PASS", "valid"))

    ck = Checker(cli, cfg, user)
    for step in (ck.unity_catalog, ck.compute, ck.platform, ck.mail, ck.sap):
        step()
    res += ck.results
    manual = (MANUAL + (MANUAL_OUTLOOK if ck.var("mail_source") in ("outlook", "both") else [])
              + (MANUAL_RLS if str(ck.var("rls_enforced")).lower() == "true" else []))
    res += [Result("Confirm once, by hand", n, "MANUAL", d) for n, d in manual]

    if a.json:
        print(json.dumps([asdict(r) for r in res], indent=2))
    else:
        color = sys.stdout.isatty() and not a.no_color
        print(f"Preflight: target {a.target} as {user}")
        print(render(res, color))
        n = {s: sum(1 for r in res if r.status == s) for s in ("PASS", "FAIL", "WARN", "MANUAL")}
        print(f"\n{n['PASS']} passed, {n['FAIL']} failed, {n['WARN']} warnings, {n['MANUAL']} to confirm by hand.")
    return 1 if any(r.status == "FAIL" for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
