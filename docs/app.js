// AI Impact Measurement: browser version.
// Same math as aiimpact/metrics.py. Everything runs on this page; no data is uploaded anywhere.
"use strict";

const Z95 = 1.959963984540054;
const WEEKS_PER_MONTH = 52 / 12;
const MIN_ADOPTION = 0.30;
const TASK_COLUMNS = ["task_id", "date", "user_id", "team", "tool", "arm", "period", "task_type",
  "used_ai", "completed", "rework", "minutes", "ai_cost_usd"];
const TOOL_COLUMNS = ["tool", "eligible_users", "hourly_rate_usd", "monthly_license_usd_per_user",
  "build_cost_usd", "max_rework_increase"];

// ---------- CSV + data contract ----------

function parseCSV(text) {
  const rows = [];
  let row = [], field = "", inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift().map(h => h.trim());
  return { header, records: rows.map(r => Object.fromEntries(header.map((h, i) => [h, (r[i] ?? "").trim()]))) };
}

class ContractError extends Error {}

function requireColumns(header, expected, name) {
  const missing = expected.filter(c => !header.includes(c));
  if (missing.length) throw new ContractError(`${name} is missing columns: ${missing.join(", ")}`);
}

function flag(v, where) {
  const s = String(v).toLowerCase();
  if (["1", "true", "yes"].includes(s)) return true;
  if (["0", "false", "no"].includes(s)) return false;
  throw new ContractError(`${where}: expected 0 or 1, got "${v}"`);
}

function num(v, where, min = 0) {
  const n = Number(v);
  if (v === "" || Number.isNaN(n)) throw new ContractError(`${where}: expected a number, got "${v}"`);
  if (n < min) throw new ContractError(`${where}: must be at least ${min}, got ${n}`);
  return n;
}

function parseTasks(text) {
  const { header, records } = parseCSV(text);
  requireColumns(header, TASK_COLUMNS, "tasks.csv");
  const seen = new Set();
  return records.map((r, i) => {
    const where = `tasks.csv row ${i + 2}`;
    if (!r.task_id) throw new ContractError(`${where}: task_id is empty`);
    if (seen.has(r.task_id)) throw new ContractError(`${where}: duplicate task_id "${r.task_id}"`);
    seen.add(r.task_id);
    const arm = r.arm.toLowerCase(), period = r.period.toLowerCase();
    if (!["treatment", "control"].includes(arm)) throw new ContractError(`${where}: arm must be treatment or control`);
    if (!["baseline", "pilot"].includes(period)) throw new ContractError(`${where}: period must be baseline or pilot`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date)) throw new ContractError(`${where}: date must be YYYY-MM-DD`);
    const used = flag(r.used_ai, `${where} used_ai`);
    if (used && !(arm === "treatment" && period === "pilot"))
      throw new ContractError(`${where}: used_ai can only be 1 for treatment rows in the pilot period`);
    return {
      date: r.date, user: r.user_id, tool: r.tool, arm, period, used,
      completed: flag(r.completed, `${where} completed`), rework: flag(r.rework, `${where} rework`),
      minutes: num(r.minutes, `${where} minutes`), cost: r.ai_cost_usd === "" ? 0 : num(r.ai_cost_usd, `${where} ai_cost_usd`),
    };
  });
}

function parseTools(text) {
  const { header, records } = parseCSV(text);
  requireColumns(header, TOOL_COLUMNS, "tools.csv");
  return records.map((r, i) => {
    const where = `tools.csv row ${i + 2}`;
    return {
      tool: r.tool,
      eligible: Math.trunc(num(r.eligible_users, `${where} eligible_users`, 1)),
      hourly: num(r.hourly_rate_usd, `${where} hourly_rate_usd`),
      license: num(r.monthly_license_usd_per_user, `${where} monthly_license_usd_per_user`),
      build: num(r.build_cost_usd, `${where} build_cost_usd`),
      maxRework: num(r.max_rework_increase, `${where} max_rework_increase`),
    };
  });
}

// ---------- statistics (mirrors metrics.py) ----------

const mean = xs => xs.reduce((a, b) => a + b, 0) / xs.length;
function variance(xs) {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1);
}
function diffInDiff(g) {
  const est = (mean(g.tp) - mean(g.tb)) - (mean(g.cp) - mean(g.cb));
  const se = Math.sqrt(["tp", "tb", "cp", "cb"].reduce((a, k) => a + variance(g[k]) / g[k].length, 0));
  return [est, se];
}
function isoWeek(s) {
  const d = new Date(s + "T00:00:00Z");
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const year = d.getUTCFullYear();
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const week = 1 + Math.round(((d - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return year * 100 + week;
}
const pick = (rows, fn) => Object.fromEntries(Object.entries(rows).map(([k, v]) => [k, v.map(fn)]));

function analyzeTool(tool, tasks) {
  const rows = tasks.filter(t => t.tool === tool.tool);
  const cell = {
    tp: rows.filter(t => t.arm === "treatment" && t.period === "pilot"),
    tb: rows.filter(t => t.arm === "treatment" && t.period === "baseline"),
    cp: rows.filter(t => t.arm === "control" && t.period === "pilot"),
    cb: rows.filter(t => t.arm === "control" && t.period === "baseline"),
  };
  const names = { tp: "treatment/pilot", tb: "treatment/baseline", cp: "control/pilot", cb: "control/baseline" };
  const empty = Object.keys(cell).filter(k => cell[k].length < 2);
  if (empty.length) throw new Error(`${tool.tool}: need at least 2 tasks in each group; too few in ${empty.map(k => names[k]).join(", ")}`);
  const tp = cell.tp;

  const aiUsers = new Set(tp.filter(t => t.used).map(t => t.user));
  const adoption = aiUsers.size / tool.eligible;
  const weeks = [...new Set(tp.map(t => isoWeek(t.date)))].sort((a, b) => a - b);
  const first = new Set(tp.filter(t => t.used && isoWeek(t.date) === weeks[0]).map(t => t.user));
  const last = new Set(tp.filter(t => t.used && isoWeek(t.date) === weeks[weeks.length - 1]).map(t => t.user));
  const retention = first.size && weeks.length > 1 ? [...first].filter(u => last.has(u)).length / first.size : null;

  const success = ts => ts.filter(t => t.completed && !t.rework).length / ts.length;
  const [rwEst, rwSe] = diffInDiff(pick(cell, t => (t.rework ? 1 : 0)));
  const rework = { est: rwEst, low: rwEst - Z95 * rwSe, high: rwEst + Z95 * rwSe };
  const guardrail = rwEst > tool.maxRework;

  const minutes = pick(cell, t => t.minutes);
  const naive = mean(minutes.tb) - mean(minutes.tp);
  const [did, se] = diffInDiff(minutes);
  const saved = { est: -did, low: -did - Z95 * se, high: -did + Z95 * se };

  const tasksPerMonth = tp.length / weeks.length * WEEKS_PER_MONTH;
  const scale = (iv, f) => ({ est: f(iv.est), low: f(iv.low), high: f(iv.high) });
  const hours = scale(saved, m => m * tasksPerMonth / 60);
  const value = scale(hours, h => h * tool.hourly);
  const usage = tp.reduce((a, t) => a + t.cost, 0) / weeks.length * WEEKS_PER_MONTH;
  const runCost = tool.license * tool.eligible + usage;
  const net = scale(value, v => v - runCost);
  const roi = runCost > 0 ? net.est / runCost : null;
  const payback = tool.build > 0 && net.est > 0 ? tool.build / net.est : null;
  const [verdict, reasons] = decide(adoption, saved, net, guardrail, rework, tool);

  return { tool: tool.tool, eligible: tool.eligible, active: aiUsers.size, adoption, retention,
    successBefore: success(cell.tb), successAfter: success(tp), rework, guardrail, naive, saved,
    tasksPerMonth, hours, value, runCost, net, roi, payback, build: tool.build, verdict, reasons };
}

function decide(adoption, saved, net, guardrail, rework, tool) {
  if (saved.high <= 0) return ["retire", ["No evidence it saves time: even the most optimistic estimate is zero or negative."]];
  if (net.high < 0) return ["retire", ["Costs more than it returns, even in the most optimistic case."]];
  const problems = [];
  if (guardrail) problems.push(`Rework rose by ${(rework.est * 100).toFixed(1)} points, above the ${(tool.maxRework * 100).toFixed(0)}-point guardrail: speed is coming at the cost of quality.`);
  if (adoption < MIN_ADOPTION) problems.push(`Only ${(adoption * 100).toFixed(0)}% of eligible people use it, below the ${(MIN_ADOPTION * 100).toFixed(0)}% needed to judge it.`);
  if (saved.low <= 0) problems.push("The time saving is not proven yet: the range of likely effects includes zero.");
  if (net.est <= 0) problems.push("The best estimate of its value does not cover its running cost.");
  if (problems.length) return ["fix", problems];
  return ["keep", [
    `Saves about ${saved.est.toFixed(1)} minutes per task (likely ${saved.low.toFixed(1)} to ${saved.high.toFixed(1)}), compared with a group that did not use it.`,
    `Returns more than it costs: about ${money(net.est)} net per month.`,
    "Quality held: rework stayed within the guardrail.",
  ]];
}

function analyze(tools, tasks) {
  const known = new Set(tools.map(t => t.tool));
  const unknown = [...new Set(tasks.map(t => t.tool))].filter(t => !known.has(t));
  if (unknown.length) throw new Error(`tasks.csv mentions tools missing from tools.csv: ${unknown.join(", ")}`);
  return tools.map(t => analyzeTool(t, tasks));
}

// ---------- rendering ----------

function money(x) { return (x < 0 ? "-$" : "$") + Math.round(Math.abs(x)).toLocaleString("en-US"); }
const pct = x => (x === null ? "n/a" : `${Math.round(x * 100)}%`);
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LABEL = { keep: "Keep", fix: "Fix", retire: "Retire" };

function chart(results) {
  // Minutes saved per task: fair estimate with its likely range, and the naive before/after figure.
  const w = 640, rowH = 46, top = 16, left = 190, right = 24, h = top + rowH * results.length + 30;
  const vals = results.flatMap(r => [r.saved.low, r.saved.high, r.naive, 0]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || 1;
  const x = v => left + ((v - (lo - pad)) / ((hi + pad) - (lo - pad))) * (w - left - right);
  const ticks = [];
  const step = niceStep((hi - lo) / 5);
  for (let t = Math.ceil((lo - pad) / step) * step; t <= hi + pad; t += step) ticks.push(+t.toFixed(6));
  let s = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Minutes saved per task by tool">`;
  ticks.forEach(t => {
    s += `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 8}" y2="${h - 26}" class="grid${t === 0 ? " zero" : ""}"/>`;
    s += `<text x="${x(t)}" y="${h - 8}" class="tick" text-anchor="middle">${t}</text>`;
  });
  results.forEach((r, i) => {
    const y = top + rowH * i + rowH / 2;
    s += `<text x="${left - 12}" y="${y + 4}" class="label" text-anchor="end">${esc(r.tool)}</text>`;
    s += `<line x1="${x(r.saved.low)}" x2="${x(r.saved.high)}" y1="${y}" y2="${y}" class="ci ${r.verdict}"/>`;
    s += `<circle cx="${x(r.saved.est)}" cy="${y}" r="6" class="dot ${r.verdict}"><title>${esc(r.tool)}: ${r.saved.est.toFixed(1)} min (likely ${r.saved.low.toFixed(1)} to ${r.saved.high.toFixed(1)})</title></circle>`;
    s += `<path d="M${x(r.naive)} ${y - 7} l5 7 l-5 7 l-5 -7z" class="naive"><title>Simple before/after: ${r.naive.toFixed(1)} min</title></path>`;
  });
  s += `</svg>`;
  return s;
}
function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / p;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
}

function render(results) {
  const counts = { keep: 0, fix: 0, retire: 0 };
  results.forEach(r => counts[r.verdict]++);
  const totalNet = results.reduce((a, r) => a + r.net.est, 0);
  const totalHours = results.reduce((a, r) => a + r.hours.est, 0);
  const retireCost = results.filter(r => r.verdict === "retire").reduce((a, r) => a + r.runCost, 0);

  const summary = `
    <div class="tiles">
      <div class="tile"><b>${results.length}</b><span>AI tools measured</span></div>
      <div class="tile"><b>${Math.round(totalHours).toLocaleString("en-US")}</b><span>hours saved per month (best estimate)</span></div>
      <div class="tile"><b>${money(totalNet)}</b><span>net value per month, all tools</span></div>
      <div class="tile"><b>${money(retireCost)}</b><span>monthly spend on tools to retire</span></div>
    </div>
    <p class="verdicts"><span class="badge keep">${counts.keep} keep</span> <span class="badge fix">${counts.fix} fix</span> <span class="badge retire">${counts.retire} retire</span></p>`;

  const cards = results.map(r => {
    const payback = r.payback !== null ? `${r.payback.toFixed(1)} months` : (r.build > 0 ? "not reached" : "no build cost");
    return `<article class="card">
      <h3>${esc(r.tool)} <span class="badge ${r.verdict}">${LABEL[r.verdict]}</span></h3>
      <div class="kpis">
        <div><b>${r.saved.est.toFixed(1)} min</b><span>saved per task</span><em>likely ${r.saved.low.toFixed(1)} to ${r.saved.high.toFixed(1)}</em></div>
        <div><b>${money(r.net.est)}</b><span>net value per month</span><em>likely ${money(r.net.low)} to ${money(r.net.high)}</em></div>
        <div><b>${pct(r.adoption)}</b><span>adoption (${r.active} of ${r.eligible} people)</span></div>
        <div><b>${(r.rework.est * 100 >= 0 ? "+" : "") + (r.rework.est * 100).toFixed(1)} pts</b><span>change in rework</span></div>
        <div><b>${pct(r.retention)}</b><span>still using it in the last week</span></div>
        <div><b>${payback}</b><span>payback on build cost</span></div>
      </div>
      <p class="naive-note">A simple before/after would claim ${r.naive.toFixed(1)} min saved per task.</p>
      <ul>${r.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    </article>`;
  }).join("");

  return `${summary}
    <h2>Minutes saved per task</h2>
    <div class="chart">${chart(results)}</div>
    <p class="legend"><span class="key dot-key"></span> fair estimate, with its likely range &nbsp; <span class="key naive-key"></span> what a simple before/after would claim</p>
    <h2>By tool</h2>
    <div class="cards">${cards}</div>`;
}

// ---------- page wiring ----------

const state = { tasks: null, tools: null, tasksName: "", toolsName: "" };

function show(html) { document.getElementById("results").innerHTML = html; }
function showError(msg) { show(`<div class="error" role="alert"><b>Could not analyze the data.</b> ${esc(msg)}</div>`); }

function run() {
  if (!state.tasks || !state.tools) return;
  try {
    const results = analyze(parseTools(state.tools), parseTasks(state.tasks));
    show(render(results));
    document.getElementById("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { showError(e.message); }
}

async function loadSample() {
  const btn = document.getElementById("sample");
  btn.disabled = true; btn.textContent = "Loading…";
  try {
    const [tasks, tools] = await Promise.all(["sample/tasks.csv", "sample/tools.csv"].map(u => fetch(u).then(r => {
      if (!r.ok) throw new Error(`could not load ${u}`);
      return r.text();
    })));
    Object.assign(state, { tasks, tools, tasksName: "sample tasks.csv", toolsName: "sample tools.csv" });
    updateFileLabels();
    run();
  } catch (e) { showError(e.message); }
  finally { btn.disabled = false; btn.textContent = "Run on synthetic sample data"; }
}

function updateFileLabels() {
  document.getElementById("tasks-name").textContent = state.tasksName || "No file chosen";
  document.getElementById("tools-name").textContent = state.toolsName || "No file chosen";
}

function bindFile(id, key, nameKey) {
  document.getElementById(id).addEventListener("change", e => {
    const f = e.target.files[0];
    if (!f) return;
    f.text().then(t => { state[key] = t; state[nameKey] = f.name; updateFileLabels(); run(); });
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("sample").addEventListener("click", loadSample);
    bindFile("tasks-file", "tasks", "tasksName");
    bindFile("tools-file", "tools", "toolsName");
  });
}

if (typeof module !== "undefined") module.exports = { analyze, parseTasks, parseTools, ContractError };
