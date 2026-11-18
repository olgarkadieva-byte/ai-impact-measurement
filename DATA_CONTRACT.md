# Data contract

AI Impact Measurement reads two CSV files. This page defines every column, the rules each value must follow, and why the data is shaped this way. The tool checks every row against these rules and stops with a clear message if something breaks them.

## Why two groups and two periods

To know what an AI tool changed, you need to know what would have happened without it. So the data covers:

| | Before rollout (`baseline`) | After rollout (`pilot`) |
|---|---|---|
| **Got the AI tool** (`treatment`) | normal work | work with the AI tool available |
| **Did not get it** (`control`) | normal work | normal work |

The control group's change between the two periods shows how much things moved for reasons unrelated to AI. Subtracting it from the treatment group's change leaves the AI's effect. This is called difference-in-differences.

Pick a control group that does the same kind of work as the treatment group, and keep the two periods the same length.

## tasks.csv

One row per unit of work: a code review, a support reply, a set of meeting notes.

| Column | Type | Rules | Example |
|---|---|---|---|
| `task_id` | text | Unique, not empty | `t000123` |
| `date` | date | `YYYY-MM-DD` | `2026-02-03` |
| `user_id` | text | Pseudonymous id. Never a name or email address. | `u1t007` |
| `team` | text | | `support` |
| `tool` | text | The AI tool this comparison is about. Must appear in tools.csv. Control rows use the tool they are the comparison for. | `Support Reply Drafter` |
| `arm` | text | `treatment` or `control` | `treatment` |
| `period` | text | `baseline` or `pilot` | `pilot` |
| `task_type` | text | | `support_reply` |
| `used_ai` | 0 or 1 | 1 only when the AI tool was used on this task. Can only be 1 for `treatment` rows in the `pilot` period. | `1` |
| `completed` | 0 or 1 | 1 if the task was finished | `1` |
| `rework` | 0 or 1 | 1 if the output had to be redone or corrected | `0` |
| `minutes` | number | 0 or more. Time spent on the task. | `14.5` |
| `ai_cost_usd` | number | 0 or more. Usage cost of AI for this task (tokens, API calls). 0 or empty if none. | `0.02` |

Each tool needs at least two tasks in each of the four groups (treatment/baseline, treatment/pilot, control/baseline, control/pilot). In practice, aim for hundreds: small samples give wide ranges and "not proven yet" verdicts.

## tools.csv

One row per AI tool.

| Column | Type | Rules | Example |
|---|---|---|---|
| `tool` | text | Must match `tool` in tasks.csv | `Support Reply Drafter` |
| `eligible_users` | whole number | 1 or more. People in the treatment group who could use the tool. | `30` |
| `hourly_rate_usd` | number | Loaded cost of an hour of their time | `45` |
| `monthly_license_usd_per_user` | number | Seat price per month; 0 if none | `0` |
| `build_cost_usd` | number | One-off cost to build or integrate; 0 if bought | `18000` |
| `max_rework_increase` | number | Quality guardrail: the largest acceptable rise in rework rate, as a fraction. `0.05` means 5 percentage points. | `0.05` |

## Where the data usually comes from

- **Task and timing data:** ticketing systems, code review tools, CRM or support platforms, calendar and document metadata.
- **AI usage (`used_ai`, `ai_cost_usd`):** usage logs or admin exports from the AI tool, joined to tasks by user and time.
- **Rework:** reopened tickets, follow-up corrections, revert commits, or a reviewer's flag.

## Privacy

The contract asks only for what the measurement needs. Use pseudonymous `user_id`s, leave out free text and content, and aggregate to the task level. The browser version runs entirely on the user's machine and uploads nothing.
