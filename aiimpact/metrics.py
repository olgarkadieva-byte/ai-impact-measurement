"""Impact metrics for each AI tool.

The core idea: compare the group that got the AI tool (treatment) with a
similar group that did not (control), before and after rollout. This
"difference-in-differences" removes changes that would have happened anyway
(a quieter month, a new process, seasonal workload), which a simple
before/after comparison wrongly credits to AI.

All confidence intervals are 95% intervals from a normal approximation, so
the browser demo (docs/app.js) can reproduce the exact same numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .contract import Task, Tool

Z95 = 1.959963984540054
WEEKS_PER_MONTH = 52 / 12
MIN_ADOPTION = 0.30  # below this, the tool is not being used enough to judge


@dataclass
class Interval:
    estimate: float
    low: float
    high: float


@dataclass
class ToolResult:
    tool: str
    # adoption
    eligible_users: int
    active_users: int
    adoption_rate: float
    retention_rate: float | None
    ai_task_share: float
    # quality
    success_rate_baseline: float
    success_rate_pilot: float
    rework_change: Interval  # difference-in-differences, in percentage points / 100
    guardrail_breached: bool
    # time
    naive_minutes_saved: float  # simple before/after on the treatment group
    minutes_saved_per_task: Interval  # difference-in-differences
    tasks_per_month: float
    hours_saved_per_month: Interval
    # money (per month)
    value_per_month: Interval
    run_cost_per_month: float
    net_value_per_month: Interval
    roi: float | None
    payback_months: float | None
    build_cost_usd: float
    # decision
    verdict: str  # keep | fix | retire
    reasons: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _var(xs: list[float]) -> float:
    """Sample variance (n - 1)."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _diff_in_diff(groups: dict[str, list[float]]) -> tuple[float, float]:
    """(treatment pilot - treatment baseline) - (control pilot - control baseline), and its standard error."""
    tp, tb, cp, cb = groups["tp"], groups["tb"], groups["cp"], groups["cb"]
    estimate = (_mean(tp) - _mean(tb)) - (_mean(cp) - _mean(cb))
    se = math.sqrt(sum(_var(g) / len(g) for g in (tp, tb, cp, cb)))
    return estimate, se


def _iso_week(t: Task) -> tuple[int, int]:
    y, w, _ = t.date.isocalendar()
    return (y, w)


def analyze_tool(tool: Tool, tasks: list[Task]) -> ToolResult:
    rows = [t for t in tasks if t.tool == tool.tool]
    cell = {
        "tp": [t for t in rows if t.arm == "treatment" and t.period == "pilot"],
        "tb": [t for t in rows if t.arm == "treatment" and t.period == "baseline"],
        "cp": [t for t in rows if t.arm == "control" and t.period == "pilot"],
        "cb": [t for t in rows if t.arm == "control" and t.period == "baseline"],
    }
    empty = [k for k, v in cell.items() if len(v) < 2]
    if empty:
        names = {"tp": "treatment/pilot", "tb": "treatment/baseline", "cp": "control/pilot", "cb": "control/baseline"}
        raise ValueError(f"{tool.tool}: need at least 2 tasks in each group; too few in "
                         + ", ".join(names[k] for k in empty))

    tp = cell["tp"]

    # Adoption: who in the treatment group actually used the tool during the pilot.
    ai_users = {t.user_id for t in tp if t.used_ai}
    adoption = len(ai_users) / tool.eligible_users
    weeks = sorted({_iso_week(t) for t in tp})
    first_week_users = {t.user_id for t in tp if t.used_ai and _iso_week(t) == weeks[0]}
    last_week_users = {t.user_id for t in tp if t.used_ai and _iso_week(t) == weeks[-1]}
    retention = (len(first_week_users & last_week_users) / len(first_week_users)
                 if first_week_users and len(weeks) > 1 else None)
    ai_task_share = sum(t.used_ai for t in tp) / len(tp)

    # Quality: a task "succeeds" when it is completed and needs no rework.
    def success(ts: list[Task]) -> float:
        return sum(1 for t in ts if t.completed and not t.rework) / len(ts)

    rework_est, rework_se = _diff_in_diff({k: [1.0 if t.rework else 0.0 for t in v] for k, v in cell.items()})
    rework_change = Interval(rework_est, rework_est - Z95 * rework_se, rework_est + Z95 * rework_se)
    guardrail = rework_est > tool.max_rework_increase

    # Time: minutes per task. Negative difference = faster, so flip the sign to get "saved".
    minutes = {k: [t.minutes for t in v] for k, v in cell.items()}
    naive_saved = _mean(minutes["tb"]) - _mean(minutes["tp"])
    did, se = _diff_in_diff(minutes)
    saved = Interval(-did, -did - Z95 * se, -did + Z95 * se)

    pilot_weeks = len(weeks)
    tasks_per_month = len(tp) / pilot_weeks * WEEKS_PER_MONTH
    hours = Interval(*(m * tasks_per_month / 60 for m in (saved.estimate, saved.low, saved.high)))
    value = Interval(*(h * tool.hourly_rate_usd for h in (hours.estimate, hours.low, hours.high)))

    usage_cost_per_month = sum(t.ai_cost_usd for t in tp) / pilot_weeks * WEEKS_PER_MONTH
    run_cost = tool.monthly_license_usd_per_user * tool.eligible_users + usage_cost_per_month
    net = Interval(value.estimate - run_cost, value.low - run_cost, value.high - run_cost)
    roi = net.estimate / run_cost if run_cost > 0 else None
    payback = (tool.build_cost_usd / net.estimate) if (tool.build_cost_usd > 0 and net.estimate > 0) else None

    verdict, reasons = decide(adoption, saved, net, guardrail, rework_change, tool)

    return ToolResult(
        tool=tool.tool,
        eligible_users=tool.eligible_users,
        active_users=len(ai_users),
        adoption_rate=adoption,
        retention_rate=retention,
        ai_task_share=ai_task_share,
        success_rate_baseline=success(cell["tb"]),
        success_rate_pilot=success(tp),
        rework_change=rework_change,
        guardrail_breached=guardrail,
        naive_minutes_saved=naive_saved,
        minutes_saved_per_task=saved,
        tasks_per_month=tasks_per_month,
        hours_saved_per_month=hours,
        value_per_month=value,
        run_cost_per_month=run_cost,
        net_value_per_month=net,
        roi=roi,
        payback_months=payback,
        build_cost_usd=tool.build_cost_usd,
        verdict=verdict,
        reasons=reasons,
        counts={k: len(v) for k, v in cell.items()},
    )


def decide(adoption: float, saved: Interval, net: Interval, guardrail: bool,
           rework: Interval, tool: Tool) -> tuple[str, list[str]]:
    """Turn the numbers into keep / fix / retire, with plain-language reasons."""
    reasons: list[str] = []

    if saved.high <= 0:
        reasons.append("No evidence it saves time: even the most optimistic estimate is zero or negative.")
        return "retire", reasons
    if net.high < 0:
        reasons.append("Costs more than it returns, even in the most optimistic case.")
        return "retire", reasons

    problems = []
    if guardrail:
        problems.append(f"Rework rose by {rework.estimate * 100:.1f} points, above the "
                        f"{tool.max_rework_increase * 100:.0f}-point guardrail: speed is coming at the cost of quality.")
    if adoption < MIN_ADOPTION:
        problems.append(f"Only {adoption * 100:.0f}% of eligible people use it, below the {MIN_ADOPTION * 100:.0f}% needed to judge it.")
    if saved.low <= 0:
        problems.append("The time saving is not proven yet: the range of likely effects includes zero.")
    if net.estimate <= 0:
        problems.append("The best estimate of its value does not cover its running cost.")

    if problems:
        return "fix", problems

    reasons.append(f"Saves about {saved.estimate:.1f} minutes per task (likely {saved.low:.1f} to {saved.high:.1f}), "
                   f"compared with a group that did not use it.")
    reasons.append(f"Returns more than it costs: about ${net.estimate:,.0f} net per month.")
    reasons.append("Quality held: rework stayed within the guardrail.")
    return "keep", reasons


def analyze(tools: list[Tool], tasks: list[Task]) -> list[ToolResult]:
    known = {t.tool for t in tools}
    unknown = sorted({t.tool for t in tasks} - known)
    if unknown:
        raise ValueError(f"tasks.csv mentions tools missing from tools.csv: {', '.join(unknown)}")
    return [analyze_tool(tool, tasks) for tool in tools]
