// Carson dashboard · single-file vanilla JS app.
// Hash router: #/ (live) · #/history · #/run/:id

const AGENTS = ["router", "Brandson", "Jenkins", "Spinnaker", "Inspector", "Confluence", "Jira"];

const AGENT_META = {
  router:     { role: "cdao sdk",   x: 270, y: 200, r: 32 },
  Brandson:   { role: "git",        x: 90,  y: 95,  r: 22 },
  Jenkins:    { role: "build",      x: 270, y: 75,  r: 22 },
  Spinnaker:  { role: "deploy",     x: 450, y: 95,  r: 22 },
  Inspector:  { role: "terraform",  x: 450, y: 305, r: 22 },
  Confluence: { role: "docs",       x: 270, y: 325, r: 22 },
  Jira:       { role: "tickets",    x: 90,  y: 305, r: 22 },
};

const AGENT_COLOR = {
  router:     "#7c9cff",
  Brandson:   "#a78bfa",
  Jenkins:    "#7c9cff",
  Spinnaker:  "#86d8b9",
  Inspector:  "#fbbf24",
  Confluence: "#c69bff",
  Jira:       "#74d9a2",
};

// ─── State ──────────────────────────────────────────────────────────────────
const state = {
  view: null,
  // live
  agentStatus: {},          // agent -> { status, since }
  activeEdges: new Set(),   // edge keys "router-Jenkins"
  liveLog: [],              // recent log lines (cap 200)
  liveSteps: [],             // recent step events (cap 500) for timeline
  activeRuns: new Set(),
  recentErrors: 0,
  tokensRolling: [],         // [{t, tokens}]
  latencyRolling: [],        // [ms,...]
  // history
  rangeHours: 168,
};

// Reset agent statuses to idle
AGENTS.forEach(a => state.agentStatus[a] = { status: "idle", since: 0 });

// ─── SSE ────────────────────────────────────────────────────────────────────
let es = null;

function connectSSE() {
  if (es) try { es.close(); } catch (e) {}
  es = new EventSource("/sse");
  const conn = document.querySelector(".conn");
  conn.classList.remove("on", "err");
  document.getElementById("conn-text").textContent = "connecting";

  es.onopen = () => {
    conn.classList.add("on");
    document.getElementById("conn-text").textContent = "live";
  };
  es.onerror = () => {
    conn.classList.remove("on");
    conn.classList.add("err");
    document.getElementById("conn-text").textContent = "reconnecting";
    setTimeout(connectSSE, 2000);
  };

  ["run.start", "run.end", "step", "tool_call"].forEach(ev => {
    es.addEventListener(ev, e => {
      try { handleEvent(ev, JSON.parse(e.data)); } catch (err) {}
    });
  });
}

function handleEvent(type, payload) {
  if (type === "run.start") {
    state.activeRuns.add(payload.run.id);
  } else if (type === "run.end") {
    state.activeRuns.delete(payload.run_id);
    if (payload.status === "error") state.recentErrors += 1;
    if (payload.total_tokens) {
      state.tokensRolling.push({ t: Date.now() / 1000, tokens: payload.total_tokens });
    }
  } else if (type === "step") {
    onStep(payload);
  }
  if (state.view === "live") renderLiveStats();
}

function onStep(step) {
  const agent = step.agent;
  if (!AGENT_META[agent]) return;

  // update node status
  state.agentStatus[agent] = { status: step.status, since: Date.now() };

  // edge from router lights up while a non-router agent is thinking
  if (agent !== "router") {
    const key = `router-${agent}`;
    if (step.status === "thinking") state.activeEdges.add(key);
    else state.activeEdges.delete(key);
  }

  // log line
  const ts = new Date((step.started_at || Date.now() / 1000) * 1000);
  appendLog({
    t: fmtClock(ts),
    a: agent,
    m: step.summary || "",
    cls: step.status,
  });

  // timeline buffer
  if (step.ended_at) {
    state.liveSteps.push({
      agent, start: step.started_at, end: step.ended_at, status: step.status,
    });
    if (step.latency_ms) state.latencyRolling.push(step.latency_ms);
    if (state.latencyRolling.length > 200) state.latencyRolling.shift();
  }

  // schedule decay
  setTimeout(() => {
    const cur = state.agentStatus[agent];
    if (cur && cur.since <= Date.now() - 1900) {
      state.agentStatus[agent] = { status: "idle", since: Date.now() };
      if (state.view === "live") drawGraph();
    }
  }, 2200);

  if (state.view === "live") {
    drawGraph();
    drawLog();
    drawTimeline();
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────
function fmtClock(d) {
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
function fmtRelTime(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return fmtClock(d);
  const months = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
  return `${months[d.getMonth()]} ${d.getDate()} ${fmtClock(d)}`;
}
function fmtDur(s) {
  if (s == null) return "—";
  if (s < 1)  return Math.round(s * 1000) + "ms";
  if (s < 60) return s.toFixed(1) + "s";
  return Math.floor(s / 60) + "m " + Math.round(s % 60) + "s";
}
function fmtNum(n) {
  if (n == null) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}
function clearEl(el) { while (el.firstChild) el.removeChild(el.firstChild); }

function appendLog(line) {
  state.liveLog.push(line);
  if (state.liveLog.length > 200) state.liveLog.shift();
}

// ─── Live view ──────────────────────────────────────────────────────────────
function showLive() {
  state.view = "live";
  setTab("live");
  const view = document.getElementById("view");
  clearEl(view);
  view.appendChild(document.getElementById("tpl-live").content.cloneNode(true));
  drawGraph();
  drawLog();
  drawTimeline();
  renderLiveStats();
}

function drawGraph() {
  const svg = document.getElementById("agent-graph");
  if (!svg) return;
  clearEl(svg);
  const ns = "http://www.w3.org/2000/svg";

  // <defs> — radial gradient + per-agent dot fills
  const defs = document.createElementNS(ns, "defs");
  defs.innerHTML =
    '<radialGradient id="router-glow" cx="50%" cy="50%" r="50%">' +
      '<stop offset="0%" stop-color="' + AGENT_COLOR.router + '" stop-opacity=".45"/>' +
      '<stop offset="100%" stop-color="' + AGENT_COLOR.router + '" stop-opacity="0"/>' +
    '</radialGradient>';
  svg.appendChild(defs);

  // edges (smooth bezier arcs router → agent)
  const router = AGENT_META.router;
  AGENTS.filter(function (a) { return a !== "router"; }).forEach(function (a) {
    const m = AGENT_META[a];
    const dx = (m.x - router.x) * 0.4;
    const dy = (m.y - router.y) * 0.4;
    const cp1x = router.x + dx, cp1y = router.y;
    const cp2x = m.x - dx,      cp2y = m.y - dy * 0.3;
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d",
      "M" + router.x + "," + router.y +
      " C" + cp1x + "," + cp1y + " " + cp2x + "," + cp2y + " " + m.x + "," + m.y);
    const isActive = state.activeEdges.has("router-" + a);
    path.setAttribute("class", isActive ? "gedge active" : "gedge");
    svg.appendChild(path);
  });

  // router halo (always-on subtle pulse)
  const halo = document.createElementNS(ns, "circle");
  halo.setAttribute("cx", router.x);
  halo.setAttribute("cy", router.y);
  halo.setAttribute("r", 56);
  halo.setAttribute("fill", "url(#router-glow)");
  svg.appendChild(halo);

  const ring = document.createElementNS(ns, "circle");
  ring.setAttribute("cx", router.x);
  ring.setAttribute("cy", router.y);
  ring.setAttribute("r", router.r);
  ring.setAttribute("fill", "none");
  ring.setAttribute("stroke", AGENT_COLOR.router);
  ring.setAttribute("stroke-width", "1");
  ring.setAttribute("opacity", "0.5");
  const ra = document.createElementNS(ns, "animate");
  ra.setAttribute("attributeName", "r");
  ra.setAttribute("from", router.r);
  ra.setAttribute("to", router.r + 18);
  ra.setAttribute("dur", "2.4s");
  ra.setAttribute("repeatCount", "indefinite");
  const rb = document.createElementNS(ns, "animate");
  rb.setAttribute("attributeName", "opacity");
  rb.setAttribute("from", "0.5");
  rb.setAttribute("to", "0");
  rb.setAttribute("dur", "2.4s");
  rb.setAttribute("repeatCount", "indefinite");
  ring.appendChild(ra); ring.appendChild(rb);
  svg.appendChild(ring);

  // nodes
  AGENTS.forEach(function (a) {
    const m = AGENT_META[a];
    const st = state.agentStatus[a];
    const color = AGENT_COLOR[a] || "#888";
    const g = document.createElementNS(ns, "g");

    // pulse ring while thinking (above the always-on router halo)
    if (st.status === "thinking" && a !== "router") {
      const pulse = document.createElementNS(ns, "circle");
      pulse.setAttribute("cx", m.x);
      pulse.setAttribute("cy", m.y);
      pulse.setAttribute("r", m.r + 2);
      pulse.setAttribute("fill", "none");
      pulse.setAttribute("stroke", color);
      pulse.setAttribute("stroke-width", "1.2");
      pulse.setAttribute("opacity", "0.6");
      const a1 = document.createElementNS(ns, "animate");
      a1.setAttribute("attributeName", "r");
      a1.setAttribute("from", m.r);
      a1.setAttribute("to", m.r + 14);
      a1.setAttribute("dur", "1.6s");
      a1.setAttribute("repeatCount", "indefinite");
      const a2 = document.createElementNS(ns, "animate");
      a2.setAttribute("attributeName", "opacity");
      a2.setAttribute("from", "0.6");
      a2.setAttribute("to", "0");
      a2.setAttribute("dur", "1.6s");
      a2.setAttribute("repeatCount", "indefinite");
      pulse.appendChild(a1); pulse.appendChild(a2);
      g.appendChild(pulse);
    }

    // node body — colored background tint + colored stroke
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", m.x);
    c.setAttribute("cy", m.y);
    c.setAttribute("r", m.r);
    c.setAttribute("fill", hexToRgba(color, st.status === "idle" ? 0.10 : 0.22));
    c.setAttribute("stroke", color);
    c.setAttribute("stroke-width", st.status === "idle" ? "0.8" : "1.4");
    c.setAttribute("opacity", st.status === "idle" ? "0.85" : "1");
    g.appendChild(c);

    // inner status dot
    if (st.status !== "idle" && a !== "router") {
      const dot = document.createElementNS(ns, "circle");
      dot.setAttribute("cx", m.x);
      dot.setAttribute("cy", m.y);
      dot.setAttribute("r", "3");
      dot.setAttribute("fill", color);
      g.appendChild(dot);
    }

    // labels
    if (a === "router") {
      const t1 = document.createElementNS(ns, "text");
      t1.setAttribute("x", m.x); t1.setAttribute("y", m.y - 1);
      t1.setAttribute("text-anchor", "middle");
      t1.setAttribute("class", "router-label");
      t1.textContent = "router";
      const t2 = document.createElementNS(ns, "text");
      t2.setAttribute("x", m.x); t2.setAttribute("y", m.y + 13);
      t2.setAttribute("text-anchor", "middle");
      t2.setAttribute("class", "router-sub");
      t2.textContent = m.role;
      g.appendChild(t1); g.appendChild(t2);
    } else {
      // labels above for top-row nodes, below for bottom-row
      const above = m.y < router.y;
      const labelY = above ? m.y - m.r - 26 : m.y + m.r + 22;
      const subY   = above ? m.y - m.r - 12 : m.y + m.r + 36;
      const t1 = document.createElementNS(ns, "text");
      t1.setAttribute("x", m.x); t1.setAttribute("y", labelY);
      t1.setAttribute("text-anchor", "middle");
      t1.setAttribute("class", "gnode-label");
      t1.textContent = a;
      const t2 = document.createElementNS(ns, "text");
      t2.setAttribute("x", m.x); t2.setAttribute("y", subY);
      t2.setAttribute("text-anchor", "middle");
      t2.setAttribute("class", "gnode-sub" + (st.status !== "idle" ? " " + st.status : ""));
      t2.textContent = m.role;
      g.appendChild(t1); g.appendChild(t2);
    }

    svg.appendChild(g);
  });
}

function hexToRgba(hex, a) {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return "rgba(" + r + "," + g + "," + b + "," + a + ")";
}

function drawLog() {
  const log = document.getElementById("log");
  if (!log) return;
  clearEl(log);
  state.liveLog.slice(-80).forEach(l => {
    const row = document.createElement("div");
    row.className = "log-line";
    row.innerHTML = `<span class="log-t">${l.t}</span><span class="log-a">${l.a}</span><span class="log-m ${l.cls || ''}">${escapeHTML(l.m)}</span>`;
    log.appendChild(row);
  });
  log.scrollTop = log.scrollHeight;
}

function drawTimeline() {
  const tl = document.getElementById("timeline");
  if (!tl) return;
  clearEl(tl);
  const now = Date.now() / 1000;
  const window = 60;
  const cutoff = now - window;
  state.liveSteps = state.liveSteps.filter(s => s.end >= cutoff);

  AGENTS.forEach(a => {
    const row = document.createElement("div");
    row.className = "tlrow";
    row.innerHTML = `<span class="tlname">${a}</span><div class="tlbar" data-agent="${a}"></div>`;
    tl.appendChild(row);
  });
  state.liveSteps.forEach(s => {
    const bar = tl.querySelector(`.tlbar[data-agent="${s.agent}"]`);
    if (!bar) return;
    const x0 = Math.max(0, (s.start - cutoff) / window) * 100;
    const x1 = Math.min(1, (s.end   - cutoff) / window) * 100;
    if (x1 - x0 < 0.4) return;
    const seg = document.createElement("div");
    seg.className = "tlseg";
    seg.style.left = x0.toFixed(1) + "%";
    seg.style.width = (x1 - x0).toFixed(1) + "%";
    seg.style.background = AGENT_COLOR[s.agent] || "#888";
    if (s.status === "error") seg.style.background = "var(--ac-red)";
    else if (s.status === "warn") seg.style.background = "var(--ac-amber)";
    bar.appendChild(seg);
  });

  const axis = document.createElement("div");
  axis.className = "tlaxis";
  axis.innerHTML = `<span></span><div class="tlaxisbar"><span>−60s</span><span>−45</span><span>−30</span><span>−15</span><span>now</span></div>`;
  tl.appendChild(axis);
}

function renderLiveStats() {
  // tokens / min over last minute
  const now = Date.now() / 1000;
  state.tokensRolling = state.tokensRolling.filter(x => x.t >= now - 60);
  const tpm = state.tokensRolling.reduce((a, b) => a + b.tokens, 0);
  const elTpm = document.getElementById("stat-tpm"); if (elTpm) elTpm.textContent = fmtNum(tpm);

  // avg latency
  const lats = state.latencyRolling.slice(-50);
  const avg  = lats.length ? Math.round(lats.reduce((a, b) => a + b, 0) / lats.length) : 0;
  const elLat = document.getElementById("stat-lat"); if (elLat) elLat.innerHTML = `${avg}<small>ms</small>`;

  const elAct = document.getElementById("stat-active"); if (elAct) elAct.textContent = state.activeRuns.size;
  const elErr = document.getElementById("stat-err"); if (elErr) elErr.textContent = state.recentErrors;
}

// ─── History view ───────────────────────────────────────────────────────────
async function showHistory() {
  state.view = "history";
  setTab("history");
  const view = document.getElementById("view");
  clearEl(view);
  view.appendChild(document.getElementById("tpl-history").content.cloneNode(true));

  document.querySelectorAll("#range-pills .pill").forEach(p => {
    p.addEventListener("click", () => {
      document.querySelectorAll("#range-pills .pill").forEach(x => x.classList.remove("on"));
      p.classList.add("on");
      state.rangeHours = parseInt(p.dataset.hours, 10);
      loadHistory();
    });
  });

  await loadHistory();
}

async function loadHistory() {
  const hours = state.rangeHours;
  document.getElementById("agents-window").textContent = humanRange(hours);
  document.getElementById("range-meta").textContent = `${humanRange(hours)} window · loading`;

  const [stats, runs] = await Promise.all([
    fetch(`/api/stats?window_hours=${hours}`).then(r => r.json()),
    fetch(`/api/runs?limit=80&since_hours=${hours}`).then(r => r.json()),
  ]);
  renderHistoryStats(stats, runs);
  renderAgentTable(stats.by_agent);
  renderSignals(stats, runs);
  renderRunsList(runs);
  document.getElementById("range-meta").textContent =
    `${humanRange(hours)} window · ${runs.length} runs loaded`;
}

function humanRange(h) {
  if (h <= 1) return "last hour";
  if (h <= 24) return `last ${h}h`;
  return `last ${Math.round(h / 24)}d`;
}

function renderHistoryStats(stats, runs) {
  const a = stats.aggregate;
  document.getElementById("hs-runs").textContent = fmtNum(a.runs);
  document.getElementById("hs-dur").innerHTML = a.avg_duration_s ? a.avg_duration_s.toFixed(1) + "<small>s</small>" : "—";
  document.getElementById("hs-ok").innerHTML = a.success_rate.toFixed(1) + "<small>%</small>";
  document.getElementById("hs-tok").textContent = fmtNum(a.total_tokens);
}

function renderAgentTable(rows) {
  const tbody = document.getElementById("agent-table");
  clearEl(tbody);
  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.agent}</td>
      <td class="num">${fmtNum(r.runs)}</td>
      <td class="num">${Math.round(r.avg_latency || 0)}ms</td>
      <td class="num">${r.errors}</td>`;
    tbody.appendChild(tr);
  });
}

function renderSignals(stats, runs) {
  const sigs = computeSignals(stats, runs);
  const el = document.getElementById("signals");
  clearEl(el);
  if (sigs.length === 0) {
    el.innerHTML = `<div class="empty">no anomalies detected in this window</div>`;
    return;
  }
  sigs.forEach(s => {
    const d = document.createElement("div");
    d.className = "signal " + s.kind;
    d.innerHTML = `<div class="signal-cat">${s.kind} · ${escapeHTML(s.cat)}</div><div class="signal-text">${escapeHTML(s.text)}</div>`;
    el.appendChild(d);
  });
}

function computeSignals(stats, runs) {
  const out = [];
  // top error agent
  const byAgent = stats.by_agent || [];
  const worst = byAgent.slice().sort((a, b) => b.errors - a.errors)[0];
  if (worst && worst.errors > 0) {
    out.push({
      kind: "regress", cat: worst.agent.toLowerCase(),
      text: `${worst.errors} step error(s) in window. ${worst.agent} is the top error contributor — drill into recent failed runs.`,
    });
  }
  // slowest agent
  const slow = byAgent.slice().sort((a, b) => (b.avg_latency || 0) - (a.avg_latency || 0))[0];
  if (slow && slow.avg_latency > 2000) {
    out.push({
      kind: "warn", cat: slow.agent.toLowerCase(),
      text: `${slow.agent} averaging ${Math.round(slow.avg_latency)}ms per step. Above 2s threshold — check tool call durations.`,
    });
  }
  // best agent
  const fast = byAgent.slice().filter(a => a.avg_latency > 0).sort((a, b) => a.avg_latency - b.avg_latency)[0];
  if (fast) {
    out.push({
      kind: "improve", cat: fast.agent.toLowerCase(),
      text: `${fast.agent} fastest agent at ${Math.round(fast.avg_latency)}ms avg. Use as baseline for tuning others.`,
    });
  }
  // failure rate
  const failed = runs.filter(r => r.status === "error").length;
  if (failed > runs.length * 0.05 && runs.length > 0) {
    out.push({
      kind: "regress", cat: "reliability",
      text: `${failed} of ${runs.length} runs failed (${(failed / runs.length * 100).toFixed(1)}%). Above 5% threshold.`,
    });
  }
  return out;
}

function renderRunsList(runs) {
  const list = document.getElementById("runs-list");
  clearEl(list);
  if (!runs.length) {
    list.innerHTML = `<div class="empty">no runs in this window</div>`;
    return;
  }
  runs.forEach(r => {
    const dur = (r.ended_at && r.started_at) ? r.ended_at - r.started_at : null;
    const row = document.createElement("div");
    row.className = "runrow";
    row.addEventListener("click", () => location.hash = `#/run/${r.id}`);
    row.innerHTML = `
      <span class="runid">${r.id}</span>
      <span class="runtime">${fmtRelTime(r.started_at)}</span>
      <span>${fmtDur(dur)}</span>
      <span class="rstatus"><span class="rstatus-dot ${r.status}"></span>${r.status}</span>
      <span class="tags">${tagsFor(r)}</span>
      <span class="tokens">${fmtNum(r.total_tokens)}</span>`;
    list.appendChild(row);
  });
}

function tagsFor(r) {
  const tags = [];
  if (r.input_text) {
    const word = (r.input_text.split(/\s+/)[0] || "").toLowerCase();
    if (word) tags.push(word);
  }
  if (r.user) tags.push((r.user || "").split("@")[0]);
  return tags.map(t => `<span class="tag">${escapeHTML(t)}</span>`).join("");
}

// ─── Run detail view ────────────────────────────────────────────────────────
async function showRun(id) {
  state.view = "run";
  setTab("history");
  const view = document.getElementById("view");
  clearEl(view);
  view.appendChild(document.getElementById("tpl-run").content.cloneNode(true));
  document.getElementById("rd-id").textContent = id;

  let run;
  try {
    run = await fetch(`/api/runs/${id}`).then(r => { if (!r.ok) throw new Error(); return r.json(); });
  } catch (e) {
    view.innerHTML = `<div class="empty">run ${escapeHTML(id)} not found</div>`;
    return;
  }
  renderRunHero(run);
  renderSwim(run);
  renderRunSteps(run);
}

function renderRunHero(run) {
  document.getElementById("rd-runid").textContent = run.id;
  const dur = run.ended_at && run.started_at ? run.ended_at - run.started_at : null;
  document.getElementById("rd-input").textContent =
    `${run.input_text} · ${run.user || "—"} · ${fmtRelTime(run.started_at)}`;
  const stEl = document.getElementById("rd-status");
  stEl.className = "rd-status " + run.status;
  stEl.textContent = run.status;

  const badges = document.getElementById("rd-badges");
  clearEl(badges);
  const items = [
    ["duration",   fmtDur(dur)],
    ["steps",      String((run.steps || []).length)],
    ["tokens",     (run.total_tokens || 0).toLocaleString()],
    ["cost",       "$" + (run.cost_usd || 0).toFixed(2)],
    ["model",      run.model || "—"],
    ["tool calls", String((run.steps || []).reduce((a, s) => a + (s.tool_calls || []).length, 0))],
  ];
  items.forEach(([k, v]) => {
    const d = document.createElement("div");
    d.className = "badge";
    d.innerHTML = `<span class="bl">${k}</span><span class="bv">${escapeHTML(v)}</span>`;
    badges.appendChild(d);
  });
}

function renderSwim(run) {
  const el = document.getElementById("swim");
  clearEl(el);
  const start = run.started_at;
  const end   = run.ended_at || (run.steps?.[run.steps.length - 1]?.ended_at) || (start + 1);
  const total = Math.max(0.5, end - start);

  AGENTS.forEach(a => {
    const row = document.createElement("div");
    row.className = "swimrow";
    row.innerHTML = `<span class="swimname">${a}</span><div class="swimtrack" data-agent="${a}"></div>`;
    el.appendChild(row);
  });
  (run.steps || []).forEach(s => {
    if (!s.ended_at) return;
    const track = el.querySelector(`.swimtrack[data-agent="${s.agent}"]`);
    if (!track) return;
    const x0 = (s.started_at - start) / total * 100;
    const w  = Math.max(1.2, (s.ended_at - s.started_at) / total * 100);
    const seg = document.createElement("div");
    seg.className = "swimseg";
    seg.style.left = x0.toFixed(1) + "%";
    seg.style.width = w.toFixed(1) + "%";
    if (s.status === "error")      seg.style.background = "var(--ac-red)";
    else if (s.status === "warn")  seg.style.background = "var(--ac-amber)";
    else                            seg.style.background = AGENT_COLOR[s.agent] || "#666";
    seg.textContent = s.summary && w > 8 ? s.summary.slice(0, 30) : "";
    seg.addEventListener("click", () => {
      const target = document.getElementById(`step-${s.seq}`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    track.appendChild(seg);
  });

  const axis = document.createElement("div");
  axis.className = "swimaxis";
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(p => (p * total < 1 ? Math.round(p * total * 1000) + "ms" : (p * total).toFixed(1) + "s"));
  axis.innerHTML = `<span></span><div class="swimaxisbar">${ticks.map(t => `<span>${t}</span>`).join("")}</div>`;
  el.appendChild(axis);
}

function renderRunSteps(run) {
  const el = document.getElementById("rd-steps");
  document.getElementById("rd-stepcount").textContent = `${(run.steps || []).length} steps`;
  clearEl(el);
  (run.steps || []).forEach(s => {
    const row = document.createElement("div");
    row.id = `step-${s.seq}`;
    row.className = "rd-step";
    const offset = (s.started_at - run.started_at);
    const role = AGENT_META[s.agent]?.role || "";
    const reasoningHTML = s.reasoning
      ? `<span class="think">${escapeHTML(s.reasoning)}</span>`
      : "";
    let summaryHTML = escapeHTML(s.summary || "");
    if (s.status === "error") summaryHTML = `<span class="err">${summaryHTML || "error"}</span>`;
    row.innerHTML = `
      <span class="rd-stept">+${offset.toFixed(1)}s</span>
      <span class="rd-stepa">${s.agent}<small>${escapeHTML(role)}</small></span>
      <span class="rd-stepm">${summaryHTML}${reasoningHTML}</span>
      <span class="rd-num">${(s.latency_ms || 0).toLocaleString()}ms<small>latency</small></span>
      <span class="rd-num">${(s.tokens || 0).toLocaleString()}<small>tokens</small></span>`;
    el.appendChild(row);
  });
}

// ─── Router ─────────────────────────────────────────────────────────────────
function setTab(name) {
  document.querySelectorAll(".tabs a").forEach(a => {
    a.classList.toggle("on", a.dataset.tab === name);
  });
}

function route() {
  const hash = location.hash || "#/";
  if (hash === "#/" || hash === "") return showLive();
  if (hash === "#/autonomous" && typeof window.showAutonomous === "function") return window.showAutonomous();
  if (hash === "#/chats" && typeof window.showChats === "function") return window.showChats();
  if (hash === "#/pm" && typeof window.showPM === "function") return window.showPM();
  if (hash === "#/ops" && typeof window.showOps === "function") return window.showOps();
  if (hash === "#/cost" && typeof window.showCost === "function") return window.showCost();
  if (hash.startsWith("#/replay") && typeof window.showReplay === "function") {
    const parts = hash.split("/");
    return window.showReplay(parts[2]);
  }
  if (hash === "#/autonomy" && typeof window.showAutonomyMeter === "function") return window.showAutonomyMeter();
  if (hash === "#/audit" && typeof window.showAudit === "function") return window.showAudit();
  if (hash === "#/history") return showHistory();
  if (hash.startsWith("#/run/")) return showRun(hash.slice(6));
  showLive();
}

function escapeHTML(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

window.addEventListener("hashchange", route);
window.addEventListener("load", () => {
  route();
  connectSSE();
  bootShortcuts();
  bootScreenshotMode();
  setTimeout(bootOnboarding, 600);  // let the first view finish rendering
  // refresh stats once a second when on live view
  setInterval(() => { if (state.view === "live") renderLiveStats(); }, 1000);
});

// ─── Polish: keyboard shortcuts ─────────────────────────────────────────
function bootShortcuts() {
  const TAB_HASHES = {
    "1": "#/",            "2": "#/autonomous",
    "3": "#/chats",       "4": "#/pm",
    "5": "#/ops",         "6": "#/cost",
    "7": "#/replay",      "8": "#/autonomy",
    "9": "#/audit",       "0": "#/history",
  };
  document.addEventListener("keydown", (e) => {
    // Don't intercept when typing in an input/textarea
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || document.activeElement.isContentEditable) return;
    // Bare digit keys — jump to tab
    if (TAB_HASHES[e.key] && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      location.hash = TAB_HASHES[e.key];
      return;
    }
    // Cmd/Ctrl + / → focus the first chat input
    if ((e.metaKey || e.ctrlKey) && e.key === "/") {
      e.preventDefault();
      const inp = document.querySelector("#chat-input, #ch-input, #pm-chat-input");
      if (inp) inp.focus();
    }
  });
  // Show a small hint at the bottom-right (collapsible)
  showShortcutHint();
}

function showShortcutHint() {
  if (document.getElementById("kb-hint")) return;
  const h = document.createElement("div");
  h.id = "kb-hint";
  h.innerHTML =
    '<span class="kb-k">1</span><span class="kb-k">2</span>…<span class="kb-k">0</span>' +
    '<span class="kb-t">jump to tab</span>' +
    '<button class="kb-x" type="button" aria-label="hide">×</button>';
  document.body.appendChild(h);
  h.querySelector(".kb-x").addEventListener("click", () => h.remove());
  // Auto-dismiss after 8s
  setTimeout(() => { if (h.parentNode) h.classList.add("kb-dim"); }, 8000);
}

// ─── Polish: screenshot mode (?screenshot=1) ────────────────────────────
function bootScreenshotMode() {
  const u = new URL(location.href);
  if (u.searchParams.get("screenshot") === "1") {
    document.body.classList.add("screenshot-mode");
  }
}

// ─── Polish: onboarding tour (first visit) ──────────────────────────────
function bootOnboarding() {
  try {
    if (localStorage.getItem("carson_onboarded") === "1") return;
    if (location.search.indexOf("tour=1") < 0 &&
        localStorage.getItem("carson_seen") === "1") {
      localStorage.setItem("carson_seen", "1");
      return;
    }
    localStorage.setItem("carson_seen", "1");
  } catch (e) { /* private browsing — show once anyway */ }

  const STEPS = [
    {
      tab: "live", title: "live · the agent graph",
      body: "7 Carson agents around the central router. Pulses show activity in real time. Logs and the 60s timeline complete the picture.",
    },
    {
      tab: "autonomous", title: "autonomous · coder swimlanes",
      body: "4 active jobs in 9-phase swimlanes. Diamond markers are HITL pauses. Athena knowledge agents are at the bottom — fresh / syncing / stale.",
    },
    {
      tab: "chats", title: "chats · multi-session",
      body: "One sidebar per conversation, each with a focus (athena / coder / pm / compliance / ops / general) so the router knows who should answer.",
    },
    {
      tab: "pm", title: "pm · drafts before commit",
      body: "Epic tree, Confluence pages, kanban, and a PM agent that drafts Jira tickets from a sentence. Drafts always go through your review.",
    },
    {
      tab: "cost", title: "cost · the demo opener",
      body: "What Carson saved this quarter, in plain numbers. PRs shipped, eng-hours, dollars, bugs caught. The CFO panel.",
    },
    {
      tab: "replay", title: "replay · time-travel any run",
      body: "Pick a past run, hit play, watch agents collaborate frame by frame. Tool calls inspected. Reasoning stream synced to the playhead.",
    },
    {
      tab: "audit", title: "audit · compliance trail",
      body: "Every meaningful agent action gets logged: deploys, approvals, data access, rollbacks. Filter, export to PDF.",
    },
  ];

  let idx = 0;
  const wrap = document.createElement("div");
  wrap.id = "onb-overlay";
  wrap.innerHTML =
    '<div class="onb-card">' +
      '<div class="onb-step" id="onb-step">1 / ' + STEPS.length + '</div>' +
      '<div class="onb-title" id="onb-title"></div>' +
      '<div class="onb-body" id="onb-body"></div>' +
      '<div class="onb-actions">' +
        '<button class="onb-skip" id="onb-skip" type="button">skip tour</button>' +
        '<button class="onb-next" id="onb-next" type="button">next →</button>' +
      "</div>" +
      '<div class="onb-progress"><div class="onb-progress-fl" id="onb-progress-fl"></div></div>' +
    "</div>";
  document.body.appendChild(wrap);

  const stepEl = document.getElementById("onb-step");
  const titleEl = document.getElementById("onb-title");
  const bodyEl = document.getElementById("onb-body");
  const nextBtn = document.getElementById("onb-next");
  const skipBtn = document.getElementById("onb-skip");
  const progressFl = document.getElementById("onb-progress-fl");

  function render() {
    const s = STEPS[idx];
    if (!s) return finish();
    location.hash = "#/" + (s.tab === "live" ? "" : s.tab);
    stepEl.textContent = (idx + 1) + " / " + STEPS.length;
    titleEl.textContent = s.title;
    bodyEl.textContent = s.body;
    nextBtn.textContent = (idx === STEPS.length - 1) ? "got it ✓" : "next →";
    progressFl.style.width = (((idx + 1) / STEPS.length) * 100).toFixed(1) + "%";
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("onb-glow", a.dataset.tab === s.tab);
    });
  }

  function finish() {
    document.querySelectorAll(".tabs a").forEach(function (a) { a.classList.remove("onb-glow"); });
    try { localStorage.setItem("carson_onboarded", "1"); } catch (e) {}
    wrap.classList.add("onb-fadeout");
    setTimeout(function () { if (wrap.parentNode) wrap.remove(); }, 250);
  }

  nextBtn.addEventListener("click", function () {
    idx++;
    if (idx >= STEPS.length) finish();
    else render();
  });
  skipBtn.addEventListener("click", finish);
  document.addEventListener("keydown", function escHandler(e) {
    if (e.key === "Escape") { finish(); document.removeEventListener("keydown", escHandler); }
  });

  render();
}
