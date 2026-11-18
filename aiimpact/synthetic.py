"""Generate a realistic, fully synthetic dataset for demos and tests.

Nothing here comes from a real organization. Four made-up AI tools are each
rolled out to one group of people (treatment) while a similar group keeps
working without it (control). Everyone also gets a little faster in the pilot
month for reasons that have nothing to do with AI, which is exactly the trap a
simple before/after comparison falls into.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .contract import TASK_COLUMNS, TOOL_COLUMNS

BASELINE_START = date(2026, 1, 5)   # a Monday
PILOT_START = date(2026, 2, 2)      # four weeks later
WEEKS_PER_PERIOD = 4


@dataclass(frozen=True)
class Scenario:
    tool: str
    task_type: str
    team: str
    control_team: str
    eligible_users: int
    tasks_per_week: tuple[int, int]
    mean_minutes: float
    sd_minutes: float
    drift_minutes: float         # change everyone sees in the pilot month, AI or not
    ai_effect_minutes: float     # change on tasks where the AI tool is used
    adoption: float              # share of people who start using the tool
    use_rate: float              # share of their tasks where they use it
    base_rework: float
    ai_rework_delta: float       # change in rework probability on AI-assisted tasks
    ai_cost_per_task: float
    hourly_rate_usd: float
    monthly_license_usd_per_user: float
    build_cost_usd: float
    max_rework_increase: float


SCENARIOS = [
    # Works well: clear time saving, quality holds.
    Scenario("Code Review Assistant", "code_review", "platform", "platform-b", 24, (4, 7),
             42, 14, -3, -11, 0.85, 0.75, 0.08, 0.0, 0.03, 95, 19, 0, 0.05),
    # Promising but too few people use it to judge.
    Scenario("Meeting Notes Summarizer", "meeting_notes", "operations", "operations-b", 36, (2, 4),
             25, 10, -1, -2.5, 0.25, 0.6, 0.05, 0.0, 0.01, 70, 10, 0, 0.05),
    # Saves time, but answers need fixing more often: quality guardrail trips.
    Scenario("Support Reply Drafter", "support_reply", "support", "support-b", 30, (8, 12),
             18, 7, -1, -6, 0.9, 0.8, 0.06, 0.12, 0.02, 45, 0, 18000, 0.05),
    # Looks busy, changes nothing, costs money.
    Scenario("Sales Email Writer", "sales_email", "sales", "sales-b", 20, (4, 6),
             15, 6, -1.5, 0.5, 0.6, 0.5, 0.10, 0.02, 0.02, 60, 30, 0, 0.05),
]


def _workdays(start: date, weeks: int) -> list[date]:
    return [start + timedelta(days=w * 7 + d) for w in range(weeks) for d in range(5)]


def generate(seed: int = 42) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    tasks: list[dict] = []
    tools: list[dict] = []
    counter = 0

    for s_index, s in enumerate(SCENARIOS, start=1):
        tools.append({
            "tool": s.tool,
            "eligible_users": s.eligible_users,
            "hourly_rate_usd": s.hourly_rate_usd,
            "monthly_license_usd_per_user": s.monthly_license_usd_per_user,
            "build_cost_usd": s.build_cost_usd,
            "max_rework_increase": s.max_rework_increase,
        })
        for arm in ("treatment", "control"):
            team = s.team if arm == "treatment" else s.control_team
            for u in range(1, s.eligible_users + 1):
                user = f"u{s_index}{arm[0]}{u:03d}"
                speed = rng.gauss(1.0, 0.12)  # some people are simply faster
                adopter = arm == "treatment" and rng.random() < s.adoption
                for period, start in (("baseline", BASELINE_START), ("pilot", PILOT_START)):
                    days = _workdays(start, WEEKS_PER_PERIOD)
                    for week in range(WEEKS_PER_PERIOD):
                        week_days = days[week * 5:(week + 1) * 5]
                        for _ in range(rng.randint(*s.tasks_per_week)):
                            counter += 1
                            used = period == "pilot" and adopter and rng.random() < s.use_rate
                            minutes = rng.gauss(s.mean_minutes, s.sd_minutes) * speed
                            rework_p = s.base_rework
                            if period == "pilot":
                                minutes += s.drift_minutes
                            if used:
                                minutes += s.ai_effect_minutes + rng.gauss(0, abs(s.ai_effect_minutes) * 0.4 + 1)
                                rework_p += s.ai_rework_delta
                            minutes = max(3.0, minutes)
                            rework = rng.random() < rework_p
                            completed = rng.random() < 0.97
                            tasks.append({
                                "task_id": f"t{counter:06d}",
                                "date": rng.choice(week_days).isoformat(),
                                "user_id": user,
                                "team": team,
                                "tool": s.tool,
                                "arm": arm,
                                "period": period,
                                "task_type": s.task_type,
                                "used_ai": int(used),
                                "completed": int(completed),
                                "rework": int(rework),
                                "minutes": f"{minutes:.1f}",
                                "ai_cost_usd": f"{s.ai_cost_per_task if used else 0:.2f}",
                            })
    return tasks, tools


def write(directory: str | Path, seed: int = 42) -> tuple[Path, Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    tasks, tools = generate(seed)
    tasks_path, tools_path = out / "tasks.csv", out / "tools.csv"
    with open(tasks_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TASK_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(tasks)
    with open(tools_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TOOL_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(tools)
    return tasks_path, tools_path
