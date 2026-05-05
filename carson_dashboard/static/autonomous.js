// Carson dashboard · autonomous view
// Renders autonomous coding jobs (with phase swimlanes + HITL controls)
// and the Athena platform knowledge agents grid.

(function () {
  "use strict";

  const PHASES = ["clone", "analyze", "generate", "test", "commit", "pr", "review", "build", "deploy"];

  const auton = {
    jobs: [],
    agents: [],
    booted: false,
    es: null,
  };

  window.showAutonomous = function () {
    setTab("autonomous");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-autonomous").content.cloneNode(true));
    if (!auton.booted) {
      bootSse();
      auton.booted = true;
    }
    refresh();
    // Re-render every 15s to keep relative timestamps fresh.
    // (Was 1s — caused flicker on .auto-job cards. The timestamps
    // change at minute granularity so 15s is plenty.)
    setInterval(function () {
      if (location.hash === "#/autonomous") {
        renderHeader();
        renderJobs();
        renderAgents();
      }
    }, 15000);
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  // ── Data ────────────────────────────────────────────────────────────────

  async function refresh() {
    try {
      const [jobs, agents] = await Promise.all([
        fetch("/api/autonomous/jobs?limit=20").then(function (r) { return r.json(); }),
        fetch("/api/autonomous/agents").then(function (r) { return r.json(); }),
      ]);
      auton.jobs = jobs;
      auton.agents = agents;
      renderHeader();
      renderJobs();
      renderAgents();
    } catch (e) { console.warn("autonomous refresh failed", e); }
  }

  function bootSse() {
    if (auton.es) try { auton.es.close(); } catch (e) {}
    auton.es = new EventSource("/sse");
    auton.es.addEventListener("autonomous.state", function (e) {
      let p; try { p = JSON.parse(e.data); } catch (err) { return; }
      const j = auton.jobs.find(function (x) { return x.job_id === p.job_id; });
      if (j) {
        j.state = p.state;
        j.state_label = p.label;
      }
      renderHeader();
      renderJobs();
    });
    auton.es.onerror = function () { setTimeout(bootSse, 2500); };
  }

  // ── Render: header ──────────────────────────────────────────────────────

  function renderHeader() {
    const active = auton.jobs.filter(function (j) {
      return ["running", "awaiting_review", "awaiting_prod", "deploying"].indexOf(j.state) >= 0;
    });
    const reviewing = auton.jobs.filter(function (j) { return j.state === "awaiting_review"; }).length;
    const syncingAgents = auton.agents.filter(function (a) { return a.state === "syncing"; }).length;
    setText("autonomous-active-count", active.length + " active");
    setText("autonomous-summary-text",
      active.length + " active · " + reviewing + " awaiting review · " + syncingAgents + " syncing");
    const longest = active.reduce(function (acc, j) {
      const elapsed = (Date.now() / 1000) - (j.started_at || 0);
      return elapsed > acc ? elapsed : acc;
    }, 0);
    setText("autonomous-longest", "longest active: " + fmtDuration(longest));
    setText("autonomous-agents-count", auton.agents.length + " agents");
  }

  // ── Render: jobs ────────────────────────────────────────────────────────

  function renderJobs() {
    const root = document.getElementById("auto-jobs");
    if (!root) return;
    root.innerHTML = "";
    auton.jobs.forEach(function (job) {
      root.appendChild(jobCard(job));
    });
  }

  function jobCard(job) {
    const card = document.createElement("div");
    card.className = "auto-job" + (isHitl(job) ? " hitl" : "") + (isProdHitl(job) ? " prod" : "");

    // Top row: id · started Xm ago · state
    const top = document.createElement("div");
    top.className = "auto-job-top";
    top.innerHTML =
      '<span class="auto-job-id">' + esc(job.job_id) + "</span>" +
      '<span class="auto-job-meta">started ' + relAgo(job.started_at) +
      idleSuffix(job) + "</span>" +
      stateBadge(job);
    card.appendChild(top);

    // Title
    const title = document.createElement("div");
    title.className = "auto-job-title";
    title.textContent = job.summary;
    card.appendChild(title);

    // Tags + user + branch
    const meta = document.createElement("div");
    meta.className = "auto-job-tagline";
    const tags = (job.tags || []).map(function (t) {
      return '<span class="auto-tag">' + esc(t) + "</span>";
    }).join("");
    const ticket = job.ticket_key ? '<span class="auto-tag tag-ticket">' + esc(job.ticket_key) + "</span>" : "";
    const user = job.user ? '<span class="auto-meta">· ' + esc(job.user) + "</span>" : "";
    const branch = job.branch ? '<span class="auto-meta">· branch <code>' + esc(job.branch) + "</code></span>" : "";
    meta.innerHTML = ticket + tags + user + branch;
    card.appendChild(meta);

    // State pill (running · phase X of 9 / awaiting human review / etc.)
    const pill = document.createElement("div");
    pill.className = "auto-state-pill " + statePillClass(job);
    pill.innerHTML = '<span class="dot ' + dotClass(job) + '"></span>' + esc(job.state_label || job.state);
    card.appendChild(pill);

    // Phase swimlane
    card.appendChild(buildSwim(job));

    // Stats + actions
    const foot = document.createElement("div");
    foot.className = "auto-foot";
    foot.appendChild(buildStats(job));
    foot.appendChild(buildActions(job));
    card.appendChild(foot);

    return card;
  }

  function buildSwim(job) {
    const wrap = document.createElement("div");
    wrap.className = "swim-wrap";
    const phases = (job.phases && job.phases.length) ? job.phases : PHASES.map(function (p, i) {
      return { phase: p, status: "pending", seq: i };
    });

    // Compute progress segments — colored arc up to the live/hitl phase
    const total = PHASES.length;

    const track = document.createElement("div");
    track.className = "swim-track";
    wrap.appendChild(track);

    // Backgrounds (always present): full gray track
    const bg = document.createElement("div");
    bg.className = "swim-track-bg";
    track.appendChild(bg);

    // Progress fill (covers done phases up to current)
    const lastDoneIdx = lastDoneIndex(phases);
    const liveIdx = liveIndex(phases);
    const hitlIdx = hitlIndex(phases);
    const finalIdx = liveIdx >= 0 ? liveIdx : (hitlIdx >= 0 ? hitlIdx : lastDoneIdx);
    const pct = finalIdx >= 0 ? (finalIdx / (total - 1)) * 100 : 0;
    const fill = document.createElement("div");
    fill.className = "swim-fill" + (hitlIdx >= 0 && liveIdx < 0 ? " stop-hitl" : "");
    fill.style.width = pct.toFixed(2) + "%";
    track.appendChild(fill);

    // Dots
    const dots = document.createElement("div");
    dots.className = "swim-dots";
    PHASES.forEach(function (name, i) {
      const ph = phases.find(function (p) { return p.phase === name; }) || { status: "pending" };
      const cell = document.createElement("div");
      cell.className = "swim-cell";
      cell.style.left = ((i / (total - 1)) * 100).toFixed(2) + "%";
      const status = ph.status || "pending";
      const dot = document.createElement("div");
      dot.className = "swim-dot d-" + status;
      if (status === "done") dot.innerHTML = '<svg viewBox="0 0 12 12"><path d="M2.5 6.2 L5 8.5 L9.5 4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      else if (status === "live") dot.innerHTML = '<span class="swim-pulse"></span>';
      else if (status === "hitl") dot.innerHTML = '<span class="swim-diamond"></span>';
      cell.appendChild(dot);
      const lbl = document.createElement("div");
      lbl.className = "swim-label";
      lbl.textContent = name;
      cell.appendChild(lbl);
      const dur = document.createElement("div");
      dur.className = "swim-dur";
      dur.textContent = phaseDurationLabel(ph);
      cell.appendChild(dur);
      dots.appendChild(cell);
    });
    wrap.appendChild(dots);

    return wrap;
  }

  function buildStats(job) {
    const stats = document.createElement("div");
    stats.className = "auto-stats";
    const tests = (job.tests_total ? job.tests_passed + " / " + job.tests_total : "—");
    const testsLabel = job.tests_total === job.tests_passed && job.tests_total > 0 ? "tests ok" : "tests";
    const items = [
      [fmtTokens(job.tokens), "tokens"],
      ["$" + (Number(job.cost_usd || 0)).toFixed(2), "cost"],
      [tests, testsLabel],
      [(job.files_modified || 0), "files modified"],
    ];
    if (job.pr_number) {
      items.push(["PR " + job.pr_number, job.pr_status === "merged" ? "merged" : ""]);
    }
    items.forEach(function (it) {
      stats.innerHTML +=
        '<span class="auto-stat-num">' + esc(it[0]) + "</span>" +
        '<span class="auto-stat-lbl">' + esc(it[1]) + "</span>";
    });
    return stats;
  }

  function buildActions(job) {
    const wrap = document.createElement("div");
    wrap.className = "auto-actions";
    let buttons = [];
    if (job.state === "running" || job.state === "deploying") {
      buttons = [
        ["view trace", "ghost", "view"],
        ["cancel", "ghost", "cancel"],
      ];
    } else if (job.state === "awaiting_review") {
      buttons = [
        ["approve", "primary", "approve"],
        ["reject", "ghost", "reject"],
        ["view PR", "ghost", "view"],
      ];
    } else if (job.state === "awaiting_prod") {
      buttons = [
        ["approve prod", "primary", "approve_prod"],
        ["hold", "ghost", "hold"],
        ["view PR", "ghost", "view"],
      ];
    } else if (job.state === "held") {
      buttons = [
        ["resume", "primary", "resume"],
        ["cancel", "ghost", "cancel"],
      ];
    } else {
      buttons = [["view trace", "ghost", "view"]];
    }
    buttons.forEach(function (b) {
      const btn = document.createElement("button");
      btn.className = "auto-btn auto-btn-" + b[1];
      btn.textContent = b[0];
      btn.addEventListener("click", function () { onAction(job, b[2]); });
      wrap.appendChild(btn);
    });
    return wrap;
  }

  function onAction(job, action) {
    if (action === "view") return; // no-op preview
    fetch("/api/autonomous/jobs/" + encodeURIComponent(job.job_id) + "/" + action,
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ actor: "dashboard" }) })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        job.state = data.state;
        job.state_label = data.label;
        renderHeader();
        renderJobs();
      })
      .catch(function () {});
  }

  // ── Render: knowledge agents ────────────────────────────────────────────

  function renderAgents() {
    const root = document.getElementById("auto-agents");
    if (!root) return;
    root.innerHTML = "";
    auton.agents.forEach(function (a) {
      root.appendChild(agentCard(a));
    });
  }

  function agentCard(a) {
    const card = document.createElement("div");
    card.className = "agent-card state-" + a.state;
    const head = document.createElement("div");
    head.className = "agent-head";
    head.innerHTML =
      '<span class="agent-name">' + esc(a.name) + "</span>" +
      '<span class="agent-state-pill p-' + a.state + '">' + esc(a.state) + "</span>";
    card.appendChild(head);

    const body = document.createElement("div");
    body.className = "agent-body";
    let firstLine;
    if (a.state === "syncing") {
      firstLine = (a.chunks || 0) + " / " + (a.chunks_total || "?") +
        ' chunks · <span class="agent-pct">' + (a.sync_pct || 0) + "% done</span>";
    } else {
      firstLine = (a.chunks || 0).toLocaleString() + " chunks · last sync " +
        relAgo(a.last_sync_at);
    }
    let secondLine;
    if (a.state === "syncing") {
      const detail = a.detail || "";
      const startedAgo = a.last_sync_at ? "started " + relAgo(a.last_sync_at) : "";
      secondLine = detail + (startedAgo ? " · " + startedAgo : "");
    } else if (a.state === "stale") {
      const next = a.next_sync_at ? "next sync in " + relForward(a.next_sync_at) : "";
      secondLine = (a.detail || "stale") + (next ? " · " + next : "");
    } else {
      const next = a.next_sync_at ? "next sync in " + relForward(a.next_sync_at) : "";
      secondLine = next + (a.detail ? " · " + esc(a.detail) : "");
    }
    body.innerHTML =
      '<div class="agent-line">' + firstLine + "</div>" +
      '<div class="agent-line agent-line-2">' + secondLine + "</div>";
    card.appendChild(body);

    // Sparkline
    if (a.activity && a.activity.length) {
      card.appendChild(sparkline(a.activity, a.state));
    }

    // Sync progress bar (syncing state)
    if (a.state === "syncing") {
      const pb = document.createElement("div");
      pb.className = "agent-progress";
      const fill = document.createElement("div");
      fill.className = "agent-progress-fill";
      fill.style.width = (a.sync_pct || 0) + "%";
      pb.appendChild(fill);
      card.appendChild(pb);
    }

    return card;
  }

  function sparkline(data, state) {
    const ns = "http://www.w3.org/2000/svg";
    const w = 220, h = 22;
    const max = Math.max.apply(null, data) || 1;
    const step = data.length > 1 ? w / (data.length - 1) : w;
    const pts = data.map(function (v, i) {
      const x = i * step;
      const y = h - (v / max) * (h - 2) - 1;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("class", "agent-spark spark-" + state);
    svg.setAttribute("preserveAspectRatio", "none");
    const poly = document.createElementNS(ns, "polyline");
    poly.setAttribute("points", pts);
    poly.setAttribute("fill", "none");
    poly.setAttribute("stroke", "currentColor");
    poly.setAttribute("stroke-width", "1.4");
    poly.setAttribute("stroke-linejoin", "round");
    svg.appendChild(poly);
    return svg;
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  function isHitl(j) { return j.state === "awaiting_review"; }
  function isProdHitl(j) { return j.state === "awaiting_prod"; }
  function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function relAgo(ts) {
    if (!ts) return "—";
    const d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return d + "s ago";
    if (d < 3600) return Math.floor(d / 60) + "m ago";
    if (d < 86400) return Math.floor(d / 3600) + "h ago";
    return Math.floor(d / 86400) + "d ago";
  }
  function relForward(ts) {
    if (!ts) return "—";
    const d = Math.floor(ts - Date.now() / 1000);
    if (d < 60) return d + "s";
    if (d < 3600) return Math.floor(d / 60) + "m";
    const h = Math.floor(d / 3600);
    const m = Math.floor((d % 3600) / 60);
    return h + "h" + (m ? " " + m + "m" : "");
  }
  function fmtDuration(s) {
    if (!s || s < 60) return Math.round(s) + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h + "h" + (m ? " " + m + "m" : "");
  }
  function fmtTokens(n) {
    if (!n) return "0";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  function idleSuffix(job) {
    if (job.state === "awaiting_review" || job.state === "awaiting_prod") {
      const last = (job.phases || []).slice().reverse().find(function (p) { return p.status === "hitl"; });
      if (last && last.duration_s) return " · idle " + fmtDuration(last.duration_s);
    }
    return "";
  }

  function stateBadge(j) {
    return ""; // state shown in pill row instead, keeps top minimal
  }
  function statePillClass(j) {
    if (j.state === "awaiting_review") return "p-hitl";
    if (j.state === "awaiting_prod")   return "p-prod";
    if (j.state === "running")          return "p-running";
    if (j.state === "deploying")        return "p-running";
    if (j.state === "held")             return "p-held";
    return "p-idle";
  }
  function dotClass(j) {
    if (j.state === "awaiting_review") return "dot-hitl";
    if (j.state === "awaiting_prod")   return "dot-prod";
    if (j.state === "running")          return "dot-running";
    if (j.state === "deploying")        return "dot-running";
    return "dot-idle";
  }
  function lastDoneIndex(phases) {
    let last = -1;
    PHASES.forEach(function (p, i) {
      const ph = phases.find(function (x) { return x.phase === p; });
      if (ph && ph.status === "done") last = i;
    });
    return last;
  }
  function liveIndex(phases) {
    for (let i = 0; i < PHASES.length; i++) {
      const ph = phases.find(function (x) { return x.phase === PHASES[i]; });
      if (ph && ph.status === "live") return i;
    }
    return -1;
  }
  function hitlIndex(phases) {
    for (let i = 0; i < PHASES.length; i++) {
      const ph = phases.find(function (x) { return x.phase === PHASES[i]; });
      if (ph && ph.status === "hitl") return i;
    }
    return -1;
  }
  function phaseDurationLabel(ph) {
    if (ph.status === "live") return "live";
    if (ph.status === "pending") return "—";
    if (ph.status === "hitl") return ph.duration_s ? fmtDuration(ph.duration_s) : "review";
    if (ph.duration_s == null) return "—";
    return fmtDuration(ph.duration_s);
  }

  // ────────────────────────────────────────────────────────────────────────
  //  Chat panel — design-only mockup (router classification + multi-agent)
  //  When real LangGraph integration lands, swap fakeRoute() and
  //  fakeReply() for /api/chat or SSE streaming. The DOM contract stays.
  // ────────────────────────────────────────────────────────────────────────

  const AGENTS = {
    router:    { color: "#7c9cff", initials: "Rt", role: "haiku 4.5" },
    aquiles:   { color: "#7c9cff", initials: "aq", role: "coder · code agent" },
    sdlc:      { color: "#c69bff", initials: "sd", role: "coder · ci/release" },
    bob:       { color: "#74d9a2", initials: "bb", role: "athena · borrowing" },
    hydra:     { color: "#5cd0c4", initials: "hy", role: "athena · decision" },
    pixie:     { color: "#ff8fb3", initials: "px", role: "athena · pricing" },
    studio:    { color: "#ffb059", initials: "st", role: "athena · ml studio" },
    csb:       { color: "#9aa0b3", initials: "cs", role: "athena · syndicate" },
    Brandson:  { color: "#a78bfa", initials: "Br", role: "git agent" },
    Jenkins:   { color: "#7c9cff", initials: "Je", role: "build agent" },
    Spinnaker: { color: "#74d9a2", initials: "Sp", role: "deploy agent" },
  };

  const chat = { msgs: [], seeded: false, lastAgent: "aquiles" };

  function ensureChatBoot() {
    if (chat.seeded) {
      bindCompose();
      renderChat();
      renderRoster();
      return;
    }
    seedDemo();
    chat.seeded = true;
    bindCompose();
    renderChat();
    renderRoster();
  }

  function seedDemo() {
    const now = Date.now() / 1000;
    chat.msgs = [
      sysMsg("channel opened · router online · 3 coder agents · 7 athena agents", now - 30 * 60),
      userMsgData("martin", "Refactor the jira webhook handler · pull the retry logic into its own module.", now - 28 * 60),
      routerMsg("classified · coder track → aquiles · confidence 0.94", now - 28 * 60 + 2),
      agentMsgData("aquiles",
        "On it. I'll work in 9 phases — clone → analyze → generate → test → commit → pr → review → build → deploy. I'll ping you when I need a human in the loop.",
        now - 28 * 60 + 6),
      progressMsgData("aquiles", "analyze", 1, "found 3 retry points · pulling into retry_handler.py", now - 27 * 60),
      progressMsgData("aquiles", "test", 3, "89 / 89 tests pass · 5 files modified", now - 25 * 60),
      progressMsgData("aquiles", "pr", 5, "opened PR #4421 · auto-review green", now - 23 * 60),
      hitlMsgData("aquiles", "J-2417",
        "PR #4421 is ready for human review. 89/89 tests · no lint · no breaking changes. Merge now or hold for your review?",
        [
          { label: "merge now", kind: "primary", action: "approve" },
          { label: "I'll review first", kind: "ghost", action: "hold" },
          { label: "view PR", kind: "ghost", action: "view" },
        ],
        now - 22 * 60),
      userMsgData("martin", "I'll review first.", now - 21 * 60),
      agentMsgData("aquiles", "👍 holding. Ping me with `@aquiles resume` when you're done.", now - 21 * 60 + 3),
      agentMsgData("bob",
        "Heads up — BOB hasn't refreshed in 12m. The schema bump on `credit-decision` may already have stale embeddings. Want me to kick off a sync? ~5 min.",
        now - 8 * 60,
        [
          { label: "refresh now", kind: "primary", action: "refresh" },
          { label: "wait until prod hours", kind: "ghost", action: "dismiss" },
        ]),
    ];
  }

  function sysMsg(text, ts)             { return { type: "system", text: text, ts: ts }; }
  function routerMsg(text, ts)          { return { type: "router", text: text, ts: ts }; }
  function userMsgData(name, text, ts)  { return { type: "user", name: name, text: text, ts: ts }; }
  function agentMsgData(agent, text, ts, actions) {
    return { type: "agent", agent: agent, text: text, ts: ts, actions: actions };
  }
  function progressMsgData(agent, phase, idx, text, ts) {
    return { type: "progress", agent: agent, phase: phase, phase_idx: idx, text: text, ts: ts };
  }
  function hitlMsgData(agent, job_id, text, actions, ts) {
    return { type: "hitl", agent: agent, job_id: job_id, text: text, actions: actions, ts: ts };
  }

  function renderRoster() {
    const root = document.getElementById("chat-roster");
    if (!root) return;
    root.innerHTML = "";
    const present = ["router", "aquiles", "sdlc", "bob", "hydra"];
    present.forEach(function (name) {
      const a = AGENTS[name];
      if (!a) return;
      const node = document.createElement("span");
      node.className = "roster-pip";
      node.title = name + " · " + a.role;
      node.style.background = a.color + "26"; // ~15% alpha
      node.style.color = a.color;
      node.style.borderColor = a.color + "55";
      node.textContent = a.initials;
      root.appendChild(node);
    });
    const more = document.createElement("span");
    more.className = "roster-more";
    more.textContent = "+ 5 more · all online";
    root.appendChild(more);
  }

  function renderChat() {
    const root = document.getElementById("chat-msgs");
    if (!root) return;
    root.innerHTML = "";
    chat.msgs.forEach(function (m, i) {
      const node = messageEl(m);
      node.style.animationDelay = Math.min(i, 8) * 30 + "ms";
      root.appendChild(node);
    });
    root.scrollTop = root.scrollHeight;
  }

  function messageEl(m) {
    if (m.type === "system") return systemEl(m);
    if (m.type === "router") return routerEl(m);
    if (m.type === "user")   return userEl(m);
    if (m.type === "progress") return progressEl(m);
    if (m.type === "hitl")   return hitlEl(m);
    return agentEl(m);
  }

  function systemEl(m) {
    const el = document.createElement("div");
    el.className = "msg msg-sys";
    el.textContent = m.text;
    return el;
  }
  function routerEl(m) {
    const el = document.createElement("div");
    el.className = "msg msg-router";
    el.innerHTML =
      '<span class="msg-router-pip">router</span>' +
      '<span class="msg-router-text">' + esc(m.text) + "</span>";
    return el;
  }
  function userEl(m) {
    const el = document.createElement("div");
    el.className = "msg msg-user";
    el.innerHTML =
      '<div class="msg-user-bubble">' + esc(m.text) + "</div>" +
      '<div class="msg-user-meta">' + esc(m.name || "you") + " · " + esc(relAgo(m.ts)) + "</div>";
    return el;
  }
  function agentEl(m) {
    const a = AGENTS[m.agent] || { color: "#7c9cff", initials: m.agent.slice(0, 2), role: "" };
    const el = document.createElement("div");
    el.className = "msg msg-agent";
    let actions = "";
    if (m.actions && m.actions.length) {
      actions = '<div class="msg-actions">' + m.actions.map(function (b) {
        return '<button class="auto-btn auto-btn-' + (b.kind || "ghost") +
          '" data-action="' + esc(b.action) + '">' + esc(b.label) + "</button>";
      }).join("") + "</div>";
    }
    el.innerHTML =
      '<div class="msg-avatar" style="background:' + a.color + '22;color:' + a.color +
      ';border-color:' + a.color + '55;">' + esc(a.initials) + "</div>" +
      '<div class="msg-body">' +
        '<div class="msg-head"><span class="msg-name" style="color:' + a.color + ';">' +
          esc(m.agent) + '</span><span class="msg-role">' + esc(a.role) +
          '</span><span class="msg-time">' + esc(relAgo(m.ts)) + "</span></div>" +
        '<div class="msg-bubble">' + esc(m.text) + "</div>" +
        actions +
      "</div>";
    return el;
  }
  function progressEl(m) {
    const a = AGENTS[m.agent] || { color: "#7c9cff", initials: m.agent.slice(0, 2) };
    const el = document.createElement("div");
    el.className = "msg msg-progress";
    el.innerHTML =
      '<div class="msg-avatar" style="background:' + a.color + '22;color:' + a.color +
      ';border-color:' + a.color + '55;">' + esc(a.initials) + "</div>" +
      '<div class="msg-progress-card" style="border-color:' + a.color + '40;">' +
        '<div class="msg-progress-head"><span class="msg-progress-name" style="color:' + a.color + ';">' +
          esc(m.agent) + '</span> <span class="msg-progress-phase">phase ' + (m.phase_idx + 1) +
          ' / 9 · ' + esc(m.phase) + "</span></div>" +
        '<div class="msg-progress-text">' + esc(m.text) + "</div>" +
        '<div class="msg-progress-bar"><div class="msg-progress-fill" style="width:' +
          (((m.phase_idx + 1) / 9) * 100).toFixed(0) + '%;background:linear-gradient(90deg,' +
          a.color + ',' + a.color + ');"></div></div>' +
      "</div>";
    return el;
  }
  function hitlEl(m) {
    const a = AGENTS[m.agent] || { color: "#ffb059", initials: m.agent.slice(0, 2) };
    const el = document.createElement("div");
    el.className = "msg msg-hitl";
    const actions = (m.actions || []).map(function (b) {
      return '<button class="auto-btn auto-btn-' + (b.kind || "ghost") +
        '" data-action="' + esc(b.action) + '" data-job="' + esc(m.job_id || "") + '">' +
        esc(b.label) + "</button>";
    }).join("");
    el.innerHTML =
      '<div class="msg-avatar" style="background:' + a.color + '22;color:' + a.color +
      ';border-color:' + a.color + '55;">' + esc(a.initials) + "</div>" +
      '<div class="msg-hitl-card">' +
        '<div class="msg-hitl-tag">human-in-the-loop · ' + esc(m.job_id || "") + "</div>" +
        '<div class="msg-head"><span class="msg-name" style="color:' + a.color + ';">' +
          esc(m.agent) + '</span><span class="msg-role">' + esc(a.role || "") +
          '</span><span class="msg-time">' + esc(relAgo(m.ts)) + "</span></div>" +
        '<div class="msg-bubble">' + esc(m.text) + "</div>" +
        '<div class="msg-actions">' + actions + "</div>" +
      "</div>";
    return el;
  }

  function bindCompose() {
    const form = document.getElementById("chat-compose");
    const input = document.getElementById("chat-input");
    if (!form || !input || form.dataset.bound) return;
    form.dataset.bound = "1";

    // Auto-resize textarea
    input.addEventListener("input", function () {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 140) + "px";
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      input.style.height = "auto";
      sendUserMessage(text);
    });

    // Action buttons inside the chat
    document.getElementById("chat-msgs").addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      onChatAction(btn.dataset.action, btn.dataset.job, btn.textContent);
    });
  }

  function onChatAction(action, jobId, label) {
    const ts = Date.now() / 1000;
    chat.msgs.push(userMsgData("martin", label, ts));
    if (action === "approve" || action === "approve_prod" || action === "hold" ||
        action === "reject" || action === "cancel" || action === "resume") {
      // Optimistic state update for the demo
      if (jobId) {
        const stateMap = {
          approve: ["running", "approved · resuming"],
          approve_prod: ["deploying", "approved · deploying to prod"],
          reject: ["failed", "rejected by reviewer"],
          cancel: ["cancelled", "cancelled"],
          hold: ["held", "held by operator"],
          resume: ["running", "resumed"],
        };
        const m = stateMap[action];
        const j = auton.jobs.find(function (x) { return x.job_id === jobId; });
        if (j && m) { j.state = m[0]; j.state_label = m[1]; renderJobs(); renderHeader(); }
      }
      const ack = action === "hold"
        ? "👍 holding. I'll wait."
        : action === "approve" || action === "approve_prod"
          ? "🚀 approved · executing."
          : action === "resume"
            ? "▶️ resuming."
            : "stopped.";
      simulateReply(jobId ? findAgentForJob(jobId) : "aquiles", ack, 600);
    } else if (action === "refresh") {
      simulateReply("bob", "starting sync now · expected 5 min · I'll let you know when fresh.", 700);
    } else if (action === "dismiss") {
      simulateReply("bob", "noted · I'll wait until prod hours.", 500);
    } else if (action === "view") {
      simulateReply(jobId ? findAgentForJob(jobId) : "aquiles", "PR is at github.com/jpmc/credittech/pull/4421 · I'll wait.", 600);
    }
    renderChat();
  }

  function findAgentForJob(jobId) {
    if (jobId === "J-2418") return "aquiles";
    if (jobId === "J-2417") return "aquiles";
    if (jobId === "J-2416") return "sdlc";
    if (jobId === "J-2415") return "aquiles";
    return "aquiles";
  }

  function sendUserMessage(text) {
    const ts = Date.now() / 1000;
    chat.msgs.push(userMsgData("martin", text, ts));
    renderChat();
    // fake-classify locally for the demo
    const route = fakeClassify(text);
    setTimeout(function () {
      chat.msgs.push(routerMsg(
        "classified · " + route.track + " track → " + route.agent + " · confidence " + route.conf.toFixed(2),
        Date.now() / 1000));
      renderChat();
      simulateReply(route.agent, fakeReply(text, route.agent), 1100);
    }, 500);
  }

  function simulateReply(agent, text, delay) {
    showTyping(agent);
    setTimeout(function () {
      hideTyping();
      chat.msgs.push(agentMsgData(agent, text, Date.now() / 1000));
      chat.lastAgent = agent;
      renderChat();
    }, delay || 900);
  }

  function showTyping(agent) {
    const a = AGENTS[agent] || AGENTS.aquiles;
    const node = document.getElementById("chat-typing");
    const av = document.getElementById("typing-avatar");
    const nm = document.getElementById("typing-name");
    if (!node) return;
    if (av) {
      av.textContent = a.initials;
      av.style.background = a.color + "22";
      av.style.color = a.color;
      av.style.borderColor = a.color + "55";
    }
    if (nm) nm.textContent = agent;
    node.hidden = false;
  }
  function hideTyping() {
    const node = document.getElementById("chat-typing");
    if (node) node.hidden = true;
  }

  // Tiny on-device classifier for the demo — same intent as the
  // server-side haiku/heuristic classifier, just enough to feel real.
  function fakeClassify(text) {
    const t = text.toLowerCase();
    const has = function (kws) { return kws.some(function (k) { return t.indexOf(k) >= 0; }); };
    if (has(["bob", "borrowing"]))                  return { track: "athena", agent: "bob",     conf: 0.92 };
    if (has(["hydra", "decision"]))                  return { track: "athena", agent: "hydra",   conf: 0.91 };
    if (has(["pixie", "pricing"]))                   return { track: "athena", agent: "pixie",   conf: 0.90 };
    if (has(["studio", "feature store"]))            return { track: "athena", agent: "studio",  conf: 0.88 };
    if (has(["reindex", "re-sync", "embed", "vector"])) return { track: "athena", agent: "bob", conf: 0.84 };
    if (has(["terraform", "tf-", "vpc", "iam"]))      return { track: "coder",  agent: "sdlc",    conf: 0.93 };
    if (has(["deploy", "release", "build"]))          return { track: "coder",  agent: "sdlc",    conf: 0.86 };
    if (has(["fix", "bug", "endpoint", "api", "service", "svc", "patch", "refactor", "test"]))
      return { track: "coder", agent: "aquiles", conf: 0.94 };
    return { track: "coder", agent: "aquiles", conf: 0.71 };
  }

  function fakeReply(text, agent) {
    const t = text.toLowerCase();
    if (agent === "aquiles") {
      if (t.indexOf("test") >= 0)  return "I'll write the missing test cases next pass and rerun the suite. Ping you when green.";
      if (t.indexOf("refactor") >= 0) return "Got it — kicking off a fresh job. I'll work in 9 phases and HITL you at the PR step.";
      if (t.indexOf("fix") >= 0)   return "Reproducing locally first, then I'll patch and open a PR. Stand by.";
      return "On it. I'll create a job and post progress here as I move through the phases.";
    }
    if (agent === "sdlc") {
      if (t.indexOf("terraform") >= 0) return "Reading the existing module versions from the lockfile. I'll bump in a branch and run `terraform plan` before opening a PR.";
      return "Picking this up. I'll keep it scoped to the build/release path and ping you before any prod step.";
    }
    if (agent === "bob")     return "Looking up the affected collection now. Will report back in a few seconds.";
    if (agent === "hydra")   return "I'll re-sync the decision engine schema and let you know when fresh.";
    if (agent === "pixie")   return "On it — refreshing pricing tier vectors.";
    return "On it — I'll post back here.";
  }

  // Wire chat boot into the autonomous view bootstrap. We intercept
  // the original showAutonomous() defined above to also render the chat.
  const _origShow = window.showAutonomous;
  window.showAutonomous = function () {
    _origShow();
    setTimeout(ensureChatBoot, 50); // after template clone
  };
})();
