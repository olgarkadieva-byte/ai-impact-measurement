// Checks that the browser version (docs/app.js) and the Python package give identical results.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const root = path.join(__dirname, "..");
const app = require(path.join(root, "docs", "app.js"));
const read = f => fs.readFileSync(path.join(root, f), "utf8");
const js = app.analyze(app.parseTools(read("data/tools.csv")), app.parseTasks(read("data/tasks.csv")));
const py = JSON.parse(execFileSync(process.env.PYTHON || "python", ["-m", "aiimpact", "summary", "data/tasks.csv", "data/tools.csv", "--json"], { cwd: root }));
let bad = 0;
js.forEach((j, i) => {
  const p = py[i];
  const pairs = {
    saved: [j.saved.est, p.minutes_saved_per_task.estimate], savedLow: [j.saved.low, p.minutes_saved_per_task.low],
    savedHigh: [j.saved.high, p.minutes_saved_per_task.high], net: [j.net.est, p.net_value_per_month.estimate],
    adoption: [j.adoption, p.adoption_rate], retention: [j.retention ?? -1, p.retention_rate ?? -1],
    rework: [j.rework.est, p.rework_change.estimate], runCost: [j.runCost, p.run_cost_per_month],
    naive: [j.naive, p.naive_minutes_saved], payback: [j.payback ?? -1, p.payback_months ?? -1],
  };
  for (const [k, [a, b]] of Object.entries(pairs)) if (Math.abs(a - b) > 1e-9) { bad++; console.error(`${j.tool} ${k}: js ${a} vs py ${b}`); }
  if (j.verdict !== p.verdict || JSON.stringify(j.reasons) !== JSON.stringify(p.reasons)) { bad++; console.error(`${j.tool}: verdict or reasons differ`); }
});
if (bad) { console.error(`${bad} differences`); process.exit(1); }
console.log(`Identical results for ${js.length} tools.`);
