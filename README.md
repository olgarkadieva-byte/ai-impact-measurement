# AI Impact Measurement

**Find out what your AI tools actually changed.** Adoption, task success, time saved, cost, ROI and payback for every AI tool, measured against a group that did not use it, with a clear verdict: **Keep**, **Fix** or **Retire**.

**[Try the live demo](https://olgarkadieva-byte.github.io/ai-impact-measurement/)**. It runs in your browser, and your data never leaves the page.

[![tests](https://github.com/olgarkadieva-byte/ai-impact-measurement/actions/workflows/tests.yml/badge.svg)](https://github.com/olgarkadieva-byte/ai-impact-measurement/actions/workflows/tests.yml)
![License: CC BY-NC 4.0](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey.svg)

## Why this exists

Most AI ROI numbers multiply self-reported "minutes saved" by a salary. That overstates impact for two reasons: people overestimate their savings, and work speeds up or slows down for reasons that have nothing to do with AI.

This tool measures instead of asking. It compares people who got an AI tool with a similar group who did not, before and after rollout (difference-in-differences), and reports every result with a 95% range. It also watches quality: a tool that saves time but creates rework does not get a "Keep".

## What it reports, per AI tool

| Area | Metrics |
|---|---|
| Adoption | share of eligible people using it, retention from first to last week, share of tasks done with AI |
| Quality | task success before and after, change in rework rate against a guardrail |
| Time | minutes saved per task with a 95% range, hours saved per month, and what a naive before/after would have claimed |
| Money | value per month, running cost (licenses plus usage), net value, ROI, payback on build cost |
| Decision | Keep / Fix / Retire, with plain-language reasons |

## Example: the synthetic dataset

The repo ships with a fully synthetic dataset of four made-up AI tools (about 10,000 tasks). Nothing in it comes from a real organization.

```text
$ python -m aiimpact summary data/tasks.csv data/tools.csv
KEEP    Code Review Assistant: 7.4 min saved/task (4.8 to 10.0), net $6,420/month, adoption 92%
FIX     Meeting Notes Summarizer: 0.9 min saved/task (-1.0 to 2.9), net $139/month, adoption 19%
FIX     Support Reply Drafter: 4.0 min saved/task (3.2 to 4.8), net $3,846/month, adoption 93%
RETIRE  Sales Email Writer: 0.2 min saved/task (-1.0 to 1.4), net -$511/month, adoption 60%
```

The Sales Email Writer shows why the comparison group matters: a simple before/after says it saves 1.8 minutes per task, but most of that improvement also happened to the people who never used it.

## Quick start

Requires Python 3.10 or later. No dependencies beyond the standard library (tests use `pytest`).

```bash
git clone https://github.com/olgarkadieva-byte/ai-impact-measurement.git
cd ai-impact-measurement

python -m aiimpact summary data/tasks.csv data/tools.csv          # text summary
python -m aiimpact report  data/tasks.csv data/tools.csv -o report.html   # shareable HTML report
python -m aiimpact summary data/tasks.csv data/tools.csv --json   # everything, as JSON
python -m aiimpact synthetic my-data/                              # regenerate the sample data

python -m pytest
```

To use your own data, export two CSV files that follow the **[data contract](DATA_CONTRACT.md)**.

## Repository layout

| Path | What it is |
|---|---|
| [`DATA_CONTRACT.md`](DATA_CONTRACT.md) | The columns and rules for the two input files, and why the data is shaped this way |
| [`aiimpact/`](aiimpact/) | Python package: data contract checks, metrics, verdicts, HTML report, command line |
| [`data/`](data/) | Synthetic sample dataset |
| [`docs/`](docs/) | The browser demo, published with GitHub Pages. Same math as the Python package, checked for identical results. |
| [`tests/`](tests/) | Tests for the contract, the statistics, the money math and the verdicts |

## Method notes

- **Effect estimate:** difference-in-differences of mean minutes per task, (treatment after − treatment before) − (control after − control before). This is an intent-to-treat estimate: it includes treatment-group tasks done without AI, so low adoption shows up as a smaller effect rather than being hidden.
- **Uncertainty:** 95% normal-approximation intervals using the four groups' sample variances. The browser and Python versions use the same formulas and return identical numbers.
- **Monthly figures:** pilot-period volume scaled to a month (52/12 weeks).
- **Assumptions to check:** the control group should do comparable work and would have changed like the treatment group without the tool (parallel trends). Randomized rollouts make this much stronger.

## Related

- [AgentMeter](https://github.com/olgarkadieva-byte/agentmeter): tests AI agents before release (task success, reliability, tool use, permission-policy violations, cost and latency) with a Ship / Hold / Block release gate. AgentMeter tests an agent before it ships; AI Impact Measurement measures what it changed after.
- [AI Governance Kit](https://github.com/olgarkadieva-byte/ai-governance-kit): the companion tool for governance. AI inventory, risk scoring and 34 AI controls mapped to NIST AI RMF, ISO/IEC 42001 and the EU AI Act.
- [smartailayer.com](https://smartailayer.com/): free AI governance and measurement tools and articles.

## Author

Created by [Olga Arkadieva](https://olgarkadieva-byte.github.io/), IAPP AI Governance Professional (AIGP) and AI advisor to the University of San Francisco.

## License

[CC BY-NC 4.0](LICENSE): free to use, share and adapt for non-commercial purposes with attribution.
