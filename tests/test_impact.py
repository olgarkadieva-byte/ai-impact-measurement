import csv
import io
import math
from datetime import date, timedelta

import pytest

from aiimpact import synthetic
from aiimpact.contract import TASK_COLUMNS, ContractError, Task, Tool, parse_tasks, read_tasks, read_tools
from aiimpact.metrics import _diff_in_diff, analyze, analyze_tool
from aiimpact.report import render
from aiimpact.__main__ import main


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    tasks_path, tools_path = synthetic.write(d)
    return read_tools(tools_path), read_tasks(tasks_path), tasks_path, tools_path


def make_tool(**kw):
    base = dict(tool="T", eligible_users=4, hourly_rate_usd=60, monthly_license_usd_per_user=0,
                build_cost_usd=0, max_rework_increase=0.05)
    base.update(kw)
    return Tool(**base)


def make_tasks(effect=-10.0, rework_ai=False, adopters=4, n_users=4):
    """Tiny hand-built dataset: 2 weeks per period, deterministic minutes."""
    tasks, i = [], 0
    for arm in ("treatment", "control"):
        for u in range(n_users):
            for period, start in (("baseline", date(2026, 1, 5)), ("pilot", date(2026, 1, 19))):
                for week in range(2):
                    for k in range(3):
                        i += 1
                        used = arm == "treatment" and period == "pilot" and u < adopters
                        minutes = 30 + (k - 1) * 2 + (effect if used else 0)
                        tasks.append(Task(f"t{i}", start + timedelta(days=7 * week + k), f"{arm}{u}", "team",
                                          "T", arm, period, "x", used, True, used and rework_ai, minutes, 0.0))
    return tasks


# ---------- data contract ----------

def test_synthetic_files_follow_contract(demo):
    tools, tasks, _, _ = demo
    assert len(tools) == 4
    assert len(tasks) > 5000
    assert {t.arm for t in tasks} == {"treatment", "control"}


def test_synthetic_is_reproducible():
    a, _ = synthetic.generate(seed=7)
    b, _ = synthetic.generate(seed=7)
    assert a == b


def row(**kw):
    base = {c: "" for c in TASK_COLUMNS}
    base.update(task_id="t1", date="2026-01-05", user_id="u1", team="a", tool="T", arm="treatment",
                period="baseline", task_type="x", used_ai="0", completed="1", rework="0",
                minutes="10", ai_cost_usd="0")
    base.update(kw)
    return base


@pytest.mark.parametrize("bad", [
    {"arm": "pilot-group"},
    {"period": "after"},
    {"used_ai": "maybe"},
    {"minutes": "-3"},
    {"date": "05/01/2026"},
    {"used_ai": "1"},  # AI use is only possible for treatment rows in the pilot
])
def test_contract_rejects_bad_rows(bad):
    with pytest.raises(ContractError):
        parse_tasks([row(**bad)])


def test_contract_rejects_duplicate_ids():
    with pytest.raises(ContractError):
        parse_tasks([row(), row()])


def test_missing_column_is_reported(tmp_path):
    p = tmp_path / "tasks.csv"
    p.write_text("task_id,date\nt1,2026-01-05\n")
    with pytest.raises(ContractError, match="missing columns"):
        read_tasks(p)


# ---------- statistics ----------

def test_diff_in_diff_removes_shared_drift():
    groups = {"tb": [30.0, 32.0], "tp": [18.0, 20.0], "cb": [30.0, 32.0], "cp": [26.0, 28.0]}
    est, se = _diff_in_diff(groups)
    # Treatment fell 12, control fell 4 for unrelated reasons: AI effect is 8.
    assert est == pytest.approx(-8.0)
    assert se == pytest.approx(math.sqrt(4 * 2.0 / 2))


def test_exact_effect_is_recovered():
    r = analyze_tool(make_tool(), make_tasks(effect=-10))
    assert r.minutes_saved_per_task.estimate == pytest.approx(10.0)
    assert r.adoption_rate == 1.0
    assert r.retention_rate == 1.0
    assert r.verdict == "keep"


def test_money_math():
    tool = make_tool(hourly_rate_usd=60, monthly_license_usd_per_user=10, build_cost_usd=1000)
    r = analyze_tool(tool, make_tasks(effect=-10))
    # 4 users x 3 tasks x 2 weeks = 24 pilot tasks over 2 weeks.
    tasks_per_month = 24 / 2 * 52 / 12
    hours = 10 * tasks_per_month / 60
    assert r.hours_saved_per_month.estimate == pytest.approx(hours)
    assert r.run_cost_per_month == pytest.approx(40)
    assert r.net_value_per_month.estimate == pytest.approx(hours * 60 - 40)
    assert r.payback_months == pytest.approx(1000 / (hours * 60 - 40))


def test_guardrail_turns_keep_into_fix():
    r = analyze_tool(make_tool(), make_tasks(effect=-10, rework_ai=True))
    assert r.guardrail_breached
    assert r.verdict == "fix"


def test_low_adoption_is_fix():
    r = analyze_tool(make_tool(eligible_users=10), make_tasks(effect=-10, adopters=2))
    assert r.verdict == "fix"
    assert any("eligible" in x for x in r.reasons)


def test_no_saving_is_retire():
    r = analyze_tool(make_tool(), make_tasks(effect=+5))
    assert r.verdict == "retire"


def test_demo_verdicts(demo):
    tools, tasks, _, _ = demo
    verdicts = {r.tool: r.verdict for r in analyze(tools, tasks)}
    assert verdicts == {
        "Code Review Assistant": "keep",
        "Meeting Notes Summarizer": "fix",
        "Support Reply Drafter": "fix",
        "Sales Email Writer": "retire",
    }


def test_naive_comparison_overstates_saving(demo):
    tools, tasks, _, _ = demo
    for r in analyze(tools, tasks):
        assert r.naive_minutes_saved > r.minutes_saved_per_task.estimate


def test_unknown_tool_is_an_error(demo):
    tools, tasks, _, _ = demo
    with pytest.raises(ValueError, match="missing from tools.csv"):
        analyze(tools[:1], tasks)


# ---------- outputs ----------

def test_report_and_cli(demo, tmp_path, capsys):
    tools, tasks, tasks_path, tools_path = demo
    html = render(analyze(tools, tasks))
    assert "Code Review Assistant" in html and "Retire" in html
    out = tmp_path / "r.html"
    assert main(["report", str(tasks_path), str(tools_path), "-o", str(out)]) == 0
    assert out.read_text().startswith("<!DOCTYPE html>")
    assert main(["summary", str(tasks_path), str(tools_path)]) == 0
    assert "KEEP" in capsys.readouterr().out


def test_excel_export_with_bom_is_accepted(demo, tmp_path):
    _, _, tasks_path, tools_path = demo
    bom = tmp_path / "tasks_bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + tasks_path.read_bytes())
    assert len(read_tasks(bom)) == len(read_tasks(tasks_path))


def test_missing_file_gives_clear_error(demo, tmp_path, capsys):
    _, _, _, tools_path = demo
    assert main(["summary", str(tmp_path / "nope.csv"), str(tools_path)]) == 2
    assert "file not found" in capsys.readouterr().err


def test_tool_without_tasks_gives_clear_error(demo, tmp_path, capsys):
    _, _, tasks_path, tools_path = demo
    extra = tmp_path / "tools.csv"
    extra.write_text(tools_path.read_text() + "Unused Tool,10,50,0,0,0.05\n")
    assert main(["summary", str(tasks_path), str(extra)]) == 2
    assert "Unused Tool" in capsys.readouterr().err
