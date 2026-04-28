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
    setInterval(function () {
      if (location.hash === "#/autonomous") {
        renderHeader();
        renderJobs();
        renderAgents();
      }
    }, 1000);
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
})();
