"""Command line interface.

    python -m aiimpact report data/tasks.csv data/tools.csv -o report.html
    python -m aiimpact summary data/tasks.csv data/tools.csv
    python -m aiimpact synthetic data/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import synthetic
from .contract import ContractError, read_tasks, read_tools
from .metrics import analyze
from .report import _money, render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aiimpact", description="Measure what AI tools actually change.")
    sub = p.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="write an HTML report")
    rep.add_argument("tasks")
    rep.add_argument("tools")
    rep.add_argument("-o", "--output", default="report.html")

    summ = sub.add_parser("summary", help="print results as text or JSON")
    summ.add_argument("tasks")
    summ.add_argument("tools")
    summ.add_argument("--json", action="store_true")

    syn = sub.add_parser("synthetic", help="write the synthetic demo dataset")
    syn.add_argument("directory")
    syn.add_argument("--seed", type=int, default=42)

    args = p.parse_args(argv)

    if args.command == "synthetic":
        tasks_path, tools_path = synthetic.write(args.directory, args.seed)
        print(f"Wrote {tasks_path} and {tools_path}")
        return 0

    try:
        results = analyze(read_tools(args.tools), read_tasks(args.tasks))
    except (ContractError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "report":
        Path(args.output).write_text(render(results, source=Path(args.tasks).name), encoding="utf-8")
        print(f"Wrote {args.output}")
    elif args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            s = r.minutes_saved_per_task
            print(f"{r.verdict.upper():7} {r.tool}: {s.estimate:.1f} min saved/task "
                  f"({s.low:.1f} to {s.high:.1f}), net {_money(r.net_value_per_month.estimate)}/month, "
                  f"adoption {r.adoption_rate:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
