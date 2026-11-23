"""scripts/preflight.py: the pure helpers (the checks themselves need a workspace)."""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).parents[1] / "scripts" / "preflight.py")
pf = importlib.util.module_from_spec(spec)
sys.modules["preflight"] = pf          # dataclasses resolve their module through sys.modules
spec.loader.exec_module(pf)


def test_cli_version_parse_and_floor():
    assert pf.parse_cli_version("Databricks CLI v1.19.0") == (1, 19, 0)
    assert pf.parse_cli_version("Databricks CLI v0.294.1\n") < pf.MIN_CLI
    assert pf.parse_cli_version("nope") is None


def test_privileges_come_from_every_assignment_and_all_privileges_covers_everything():
    eff = {"privilege_assignments": [
        {"principal": "me", "privileges": [{"privilege": "USE_SCHEMA"}, {"privilege": "CREATE_TABLE"}]},
        {"principal": "a-group", "privileges": [{"privilege": "CREATE_FUNCTION"}, {"privilege": "EXECUTE"}]}]}
    have = pf.privileges_of(eff)
    assert pf.missing_privileges(have, pf.SCHEMA_NEED) == ["CREATE_MATERIALIZED_VIEW", "MANAGE"]
    assert pf.missing_privileges({"ALL_PRIVILEGES"}, pf.SCHEMA_NEED) == []
    assert pf.privileges_of(None) == set()


def test_first_error_picks_the_error_line():
    text = "Search path: [x]\nError: Schema 'c.s' does not exist.\nmore noise"
    assert pf.first_error(text) == "Error: Schema 'c.s' does not exist."
    sql = "[TABLE_OR_VIEW_NOT_FOUND] The view `c`.`s`.`v` cannot be found.\nSearch path: [x]\nTo tolerate the error on drop use DROP"
    assert pf.first_error(sql).startswith("[TABLE_OR_VIEW_NOT_FOUND]")
    assert pf.first_error("a\nb") == "a" and pf.first_error("") == "failed"


def test_manual_items_are_listed_and_results_serialize():
    assert any("Serverless" in n for n, _ in pf.MANUAL) and any("Entra" in n for n, _ in pf.MANUAL_OUTLOOK)
    r = pf.Result("g", "c", "PASS", "d")
    assert json.loads(json.dumps(pf.asdict(r)))["status"] == "PASS"
    assert "fix: x" in pf.render([pf.Result("g", "c", "FAIL", "d", "x")], False)


def test_checker_reads_resolved_variables():
    cfg = {"variables": {"catalog": {"value": "c1", "default": "main"}, "volume": {"default": "landing"}}}
    ck = pf.Checker(None, cfg, "me")
    assert ck.var("catalog") == "c1" and ck.var("volume") == "landing" and ck.var("nope", "d") == "d"


def test_sap_objects_and_manual_items_are_order_intake_specific():
    assert "v_customer_master" in pf.SAP_VIEWS and "t_sales_org_geography_look_up" in pf.SAP_VIEWS and pf.SAP_SCHEMA == "db_fnd_proc"
    assert any("ai_extract" in d for _, d in pf.MANUAL) and any("postgres" in d for _, d in pf.MANUAL_RLS)
