"""Render results as a self-contained HTML report (no external files)."""

from __future__ import annotations

import html
from datetime import date

from .metrics import Interval, ToolResult

VERDICT_LABEL = {"keep": "Keep", "fix": "Fix", "retire": "Retire"}

CSS = """
:root{--bg:#fff;--fg:#1c1d21;--muted:#5d6170;--line:#e3e5ea;--card:#f7f8fa;
--keep:#1f7a4d;--keep-bg:#e3f4ea;--fix:#8a5a00;--fix-bg:#fff1d6;--retire:#a32a2a;--retire-bg:#fbe4e4;--accent:#2b59c3}
@media (prefers-color-scheme:dark){:root{--bg:#121316;--fg:#ececf0;--muted:#a3a7b3;--line:#2b2d34;--card:#1b1d22;
--keep:#6fd19c;--keep-bg:#143022;--fix:#f0c060;--fix-bg:#33270c;--retire:#f08a8a;--retire-bg:#3a1717;--accent:#8fb0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:40px 20px 64px}
h1{font-size:1.9rem;margin:0 0 6px;letter-spacing:-.01em}h2{font-size:1.25rem;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 24px}
table{width:100%;border-collapse:collapse;font-size:.95rem}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:.82rem;text-transform:uppercase;letter-spacing:.04em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:.82rem}
.keep{color:var(--keep);background:var(--keep-bg)}.fix{color:var(--fix);background:var(--fix-bg)}.retire{color:var(--retire);background:var(--retire-bg)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
.card h3{margin:0 0 8px;font-size:1.05rem;display:flex;justify-content:space-between;gap:8px;align-items:center}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.kpi b{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:.82rem}
.range{color:var(--muted);font-size:.8rem}
ul.reasons{margin:8px 0 0;padding-left:18px}ul.reasons li{margin:4px 0}
.note{border-left:3px solid var(--accent);padding:8px 14px;background:var(--card);border-radius:0 8px 8px 0;color:var(--fg)}
footer{margin-top:40px;color:var(--muted);font-size:.85rem}
"""


def _money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def _range(iv: Interval, fmt) -> str:
    return f"likely {fmt(iv.low)} to {fmt(iv.high)}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def render(results: list[ToolResult], title: str = "AI impact report", source: str = "") -> str:
    e = html.escape
    rows = []
    for r in results:
        rows.append(
            f"<tr><td>{e(r.tool)}</td>"
            f"<td><span class='badge {r.verdict}'>{VERDICT_LABEL[r.verdict]}</span></td>"
            f"<td class='num'>{_pct(r.adoption_rate)}</td>"
            f"<td class='num'>{r.minutes_saved_per_task.estimate:.1f}</td>"
            f"<td class='num'>{r.hours_saved_per_month.estimate:,.0f}</td>"
            f"<td class='num'>{_money(r.net_value_per_month.estimate)}</td></tr>"
        )
    cards = []
    for r in results:
        payback = (f"{r.payback_months:.1f} months" if r.payback_months is not None
                   else ("not reached" if r.build_cost_usd > 0 else "no build cost"))
        cards.append(f"""
<div class="card">
  <h3>{e(r.tool)} <span class="badge {r.verdict}">{VERDICT_LABEL[r.verdict]}</span></h3>
  <div class="kpis">
    <div class="kpi"><b>{r.minutes_saved_per_task.estimate:.1f} min</b><span>saved per task</span>
      <div class="range">{_range(r.minutes_saved_per_task, lambda v: f"{v:.1f}")}</div></div>
    <div class="kpi"><b>{_money(r.net_value_per_month.estimate)}</b><span>net value per month</span>
      <div class="range">{_range(r.net_value_per_month, _money)}</div></div>
    <div class="kpi"><b>{_pct(r.adoption_rate)}</b><span>adoption ({r.active_users} of {r.eligible_users} people)</span></div>
    <div class="kpi"><b>{r.rework_change.estimate * 100:+.1f} pts</b><span>change in rework</span></div>
    <div class="kpi"><b>{_pct(r.retention_rate)}</b><span>still using it in the last week</span></div>
    <div class="kpi"><b>{payback}</b><span>payback on build cost</span></div>
  </div>
  <div class="range">A simple before/after would claim {r.naive_minutes_saved:.1f} min saved per task.</div>
  <ul class="reasons">{''.join(f'<li>{e(x)}</li>' for x in r.reasons)}</ul>
</div>""")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{e(title)}</h1>
<p class="sub">Generated {date.today().isoformat()}{(' from ' + e(source)) if source else ''}.
Each AI tool is compared with a similar group that did not use it, before and after rollout.</p>
<table><thead><tr><th>AI tool</th><th>Verdict</th><th class="num">Adoption</th><th class="num">Min saved / task</th>
<th class="num">Hours saved / month</th><th class="num">Net value / month</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>By tool</h2>
<div class="cards">{''.join(cards)}</div>
<h2>How to read this</h2>
<p class="note">Ranges are 95% confidence intervals. "Keep" means the time saving is proven, the tool pays for itself
and quality held. "Fix" means something specific is wrong: too few people use it, the saving is not proven yet,
or quality slipped. "Retire" means there is no evidence it saves time, or it costs more than it returns even in the best case.</p>
<footer>Made with AI Impact Measurement by Olga Arkadieva.</footer>
</div></body></html>
"""
