"""The data contract: the columns and rules every input file must follow.

Two CSV files feed the tool:

* tasks.csv - one row per unit of work (a code review, a support reply, ...),
  from both the group that got the AI tool and a comparison group that did not.
* tools.csv - one row per AI tool: who could use it and what it costs.

See DATA_CONTRACT.md for the human-readable version.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TASK_COLUMNS = [
    "task_id",       # unique id for the task
    "date",          # YYYY-MM-DD the task was done
    "user_id",       # pseudonymous person id (never a name or email)
    "team",          # team name
    "tool",          # the AI tool this comparison is about
    "arm",           # "treatment" (got the tool) or "control" (did not)
    "period",        # "baseline" (before rollout) or "pilot" (after rollout)
    "task_type",     # kind of work, e.g. code_review
    "used_ai",       # 1 if the AI tool was used on this task, else 0
    "completed",     # 1 if the task was finished, else 0
    "rework",        # 1 if the output had to be redone or corrected, else 0
    "minutes",       # minutes spent on the task
    "ai_cost_usd",   # usage cost of AI for this task (tokens, API calls); 0 if none
]

TOOL_COLUMNS = [
    "tool",                          # must match tasks.csv
    "eligible_users",                # people in the treatment group who could use it
    "hourly_rate_usd",               # loaded cost of an hour of their time
    "monthly_license_usd_per_user",  # seat price; 0 if none
    "build_cost_usd",                # one-off cost to build or integrate; 0 if bought
    "max_rework_increase",           # guardrail: largest allowed rise in rework rate, e.g. 0.05
]

ARMS = {"treatment", "control"}
PERIODS = {"baseline", "pilot"}


class ContractError(ValueError):
    """Raised when an input file breaks the data contract."""


@dataclass(frozen=True)
class Task:
    task_id: str
    date: date
    user_id: str
    team: str
    tool: str
    arm: str
    period: str
    task_type: str
    used_ai: bool
    completed: bool
    rework: bool
    minutes: float
    ai_cost_usd: float


@dataclass(frozen=True)
class Tool:
    tool: str
    eligible_users: int
    hourly_rate_usd: float
    monthly_license_usd_per_user: float
    build_cost_usd: float
    max_rework_increase: float


def _flag(value: str, where: str) -> bool:
    v = value.strip().lower()
    if v in {"1", "true", "yes"}:
        return True
    if v in {"0", "false", "no"}:
        return False
    raise ContractError(f"{where}: expected 0 or 1, got {value!r}")


def _number(value: str, where: str, minimum: float = 0.0) -> float:
    try:
        n = float(value)
    except ValueError as exc:
        raise ContractError(f"{where}: expected a number, got {value!r}") from exc
    if n < minimum:
        raise ContractError(f"{where}: must be at least {minimum}, got {n}")
    return n


def _check_header(found: list[str] | None, expected: list[str], name: str) -> None:
    missing = [c for c in expected if c not in (found or [])]
    if missing:
        raise ContractError(f"{name} is missing columns: {', '.join(missing)}")


def parse_tasks(rows: list[dict[str, str]]) -> list[Task]:
    tasks: list[Task] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        where = f"tasks.csv row {i}"
        tid = r["task_id"].strip()
        if not tid:
            raise ContractError(f"{where}: task_id is empty")
        if tid in seen:
            raise ContractError(f"{where}: duplicate task_id {tid!r}")
        seen.add(tid)
        arm = r["arm"].strip().lower()
        if arm not in ARMS:
            raise ContractError(f"{where}: arm must be treatment or control, got {r['arm']!r}")
        period = r["period"].strip().lower()
        if period not in PERIODS:
            raise ContractError(f"{where}: period must be baseline or pilot, got {r['period']!r}")
        used_ai = _flag(r["used_ai"], f"{where} used_ai")
        if used_ai and not (arm == "treatment" and period == "pilot"):
            raise ContractError(f"{where}: used_ai can only be 1 for treatment rows in the pilot period")
        try:
            d = date.fromisoformat(r["date"].strip())
        except ValueError as exc:
            raise ContractError(f"{where}: date must be YYYY-MM-DD, got {r['date']!r}") from exc
        tasks.append(Task(
            task_id=tid,
            date=d,
            user_id=r["user_id"].strip(),
            team=r["team"].strip(),
            tool=r["tool"].strip(),
            arm=arm,
            period=period,
            task_type=r["task_type"].strip(),
            used_ai=used_ai,
            completed=_flag(r["completed"], f"{where} completed"),
            rework=_flag(r["rework"], f"{where} rework"),
            minutes=_number(r["minutes"], f"{where} minutes"),
            ai_cost_usd=_number(r["ai_cost_usd"] or "0", f"{where} ai_cost_usd"),
        ))
    return tasks


def parse_tools(rows: list[dict[str, str]]) -> list[Tool]:
    tools = []
    for i, r in enumerate(rows, start=2):
        where = f"tools.csv row {i}"
        eligible = _number(r["eligible_users"], f"{where} eligible_users", minimum=1)
        tools.append(Tool(
            tool=r["tool"].strip(),
            eligible_users=int(eligible),
            hourly_rate_usd=_number(r["hourly_rate_usd"], f"{where} hourly_rate_usd"),
            monthly_license_usd_per_user=_number(r["monthly_license_usd_per_user"], f"{where} monthly_license_usd_per_user"),
            build_cost_usd=_number(r["build_cost_usd"], f"{where} build_cost_usd"),
            max_rework_increase=_number(r["max_rework_increase"], f"{where} max_rework_increase"),
        ))
    return tools


def read_tasks(path: str | Path) -> list[Task]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _check_header(reader.fieldnames, TASK_COLUMNS, "tasks.csv")
        return parse_tasks(list(reader))


def read_tools(path: str | Path) -> list[Tool]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _check_header(reader.fieldnames, TOOL_COLUMNS, "tools.csv")
        return parse_tools(list(reader))
