// Carson dashboard · ops view
// Renders the unified Jira intake → routing → autonomous-jobs → ops feed →
// notifications dashboard. Lives alongside dashboard.js (which still owns
// live / history / run-detail).

(function () {
  "use strict";

  // ── State ───────────────────────────────────────────────────────────────

  const ops = {
    tickets: [],         // unrouted-first, then routed (most recent first)
    activeJobs: [],      // synthetic — derived from routed tickets + HITL
    jenkins: [],
    spinnaker: [],
    github: [],
    rules: [],           // [{name, enabled}]
    hitlByJob: {},       // job_id → {summary, ts}
    routerBackend: "heuristic",
    routerSignals: [],   // last classification's signals
    es: null,
    booted: false,
  };

  const LANE_LIMIT = 12;
  const TICKETS_LIMIT = 8;
  const JOBS_LIMIT = 6;

  // ── Public entrypoint (called by dashboard.js router) ───────────────────

  window.showOps = function showOps() {
    setTab("ops");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-ops").content.cloneNode(true));

    if (!ops.booted) {
      bootSse();
      bootPermissionUi();
      ops.booted = true;
    }
    refreshAll();
    bindUi();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  // ── Initial / interval refresh ──────────────────────────────────────────

  async function refreshAll() {
    try {
      const [tickets, events, rules] = await Promise.all([
        fetch("/api/jira/tickets?limit=20").then((r) => r.json()),
        fetch("/api/ops/events?limit=60").then((r) => r.json()),
        fetch("/api/notifications/rules").then((r) => r.json()),
      ]);
      ops.tickets = tickets;
      partitionEvents(events);
      ops.rules = rules;
      buildActiveJobsFromTickets();
      renderAll();
    } catch (e) {
      console.warn("ops refreshAll failed", e);
    }
  }

  function partitionEvents(events) {
    ops.jenkins = events.filter((e) => e.source === "jenkins").slice(0, LANE_LIMIT);
    ops.spinnaker = events.filter((e) => e.source === "spinnaker").slice(0, LANE_LIMIT);
    ops.github = events.filter((e) => e.source === "github").slice(0, LANE_LIMIT);
  }

  function buildActiveJobsFromTickets() {
    // Top routed tickets become "active jobs". HITL tickets bubble to top.
    const routed = ops.tickets.filter((t) => t.track && t.track !== "unknown");
    ops.activeJobs = routed.slice(0, JOBS_LIMIT).map((t) => {
      const hitl = ops.hitlByJob[t.job_id];
      return {
        job_id: t.job_id || "J-?",
        track: t.track,
        agent: t.agent,
        summary: t.summary,
        progress: hitl ? 78 : Math.round(20 + Math.random() * 60),
        state: hitl ? "hitl" : pickState(),
        hitl: !!hitl,
      };
    });
    ops.activeJobs.sort((a, b) => (b.hitl ? 1 : 0) - (a.hitl ? 1 : 0));
  }

  function pickState() {
    const s = ["clone", "analyze", "generate", "test", "commit", "pr", "review", "build", "deploy"];
    return s[Math.floor(Math.random() * s.length)];
  }

  // ── SSE ────────────────────────────────────────────────────────────────

  function bootSse() {
    if (ops.es) try { ops.es.close(); } catch (e) {}
    ops.es = new EventSource("/sse");
    ops.es.addEventListener("jira.received", function () { /* preview only */ });
    ops.es.addEventListener("jira.routed", onJiraRouted);
    ops.es.addEventListener("ops.event", onOpsEvent);
    ops.es.addEventListener("hitl.requested", onHitl);
    ops.es.addEventListener("notify", onNotify);
    ops.es.addEventListener("rule.changed", onRuleChanged);
    ops.es.onerror = function () {
      setTimeout(bootSse, 2500);
    };
  }

  function onJiraRouted(e) {
    let p; try { p = JSON.parse(e.data); } catch (err) { return; }
    // Update or insert the ticket at the top
    const i = ops.tickets.findIndex((t) => t.key === p.key);
    const ticket = {
      key: p.key,
      summary: p.summary,
      track: p.track,
      agent: p.agent,
      confidence: p.confidence,
      signals: p.signals,
      job_id: p.job_id,
      backend: p.backend || "heuristic",
      received_at: Date.now() / 1000,
    };
    if (i >= 0) ops.tickets.splice(i, 1);
    ops.tickets.unshift(ticket);
    ops.tickets = ops.tickets.slice(0, 20);
    ops.routerBackend = p.backend || "heuristic";
    ops.routerSignals = p.signals || [];
    buildActiveJobsFromTickets();
    if (isOpsView()) {
      renderJira();
      renderRouter();
      renderJobs();
    }
  }

  function onOpsEvent(e) {
    let p; try { p = JSON.parse(e.data); } catch (err) { return; }
    const lane = p.source === "jenkins" ? ops.jenkins
                : p.source === "spinnaker" ? ops.spinnaker
                : ops.github;
    lane.unshift(p);
    if (lane.length > LANE_LIMIT) lane.length = LANE_LIMIT;
    if (isOpsView()) renderLane(p.source);
  }

  function onHitl(e) {
    let p; try { p = JSON.parse(e.data); } catch (err) { return; }
    ops.hitlByJob[p.job_id] = { summary: p.summary, ts: Date.now() };
    buildActiveJobsFromTickets();
    if (isOpsView()) renderJobs();
  }

  function onNotify(e) {
    let p; try { p = JSON.parse(e.data); } catch (err) { return; }
    fireNotification(p.title, p.body, p.tag);
    if (isOpsView()) updateToastPreview(p.title, p.body);
  }

  function onRuleChanged(e) {
    let p; try { p = JSON.parse(e.data); } catch (err) { return; }
    const r = ops.rules.find((x) => x.name === p.name);
    if (r) r.enabled = p.enabled;
    if (isOpsView()) renderRules();
  }

  function isOpsView() {
    return location.hash === "#/ops";
  }

  // ── Renderers ──────────────────────────────────────────────────────────

  function renderAll() {
    renderJira();
    renderRouter();
    renderJobs();
    renderLane("jenkins");
    renderLane("spinnaker");
    renderLane("github");
    renderRules();
  }

  function renderJira() {
    const list = document.getElementById("jira-list");
    if (!list) return;
    list.innerHTML = "";
    const items = ops.tickets.slice(0, TICKETS_LIMIT);
    document.getElementById("ops-jira-count").textContent =
      items.length + (items.length === 1 ? " ticket" : " tickets");
    items.forEach(function (t) {
      const row = document.createElement("div");
      row.className = "jira-item";
      const cls = t.track ? clsTag(t.track, t.agent) : { label: "detecting", c: "detect" };
      row.innerHTML =
        '<span class="jira-key">' + esc(t.key || "") + "</span>" +
        '<span class="jira-title">' + esc(t.summary || "") + "</span>" +
        '<span class="jira-cls cls-' + cls.c + '">' + esc(cls.label) + "</span>";
      list.appendChild(row);
    });
  }

  function clsTag(track, agent) {
    if (track === "athena") return { label: "athena·" + agent, c: "athena" };
    if (track === "coder") return { label: "coder·" + agent, c: "coder" };
    if (track === "infra") return { label: "infra", c: "infra" };
    if (track === "docs") return { label: "docs", c: "docs" };
    return { label: "unrouted", c: "detect" };
  }

  function renderRouter() {
    const svg = document.getElementById("ops-router-svg");
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const ns = "http://www.w3.org/2000/svg";

    document.getElementById("ops-router-backend").textContent =
      "backend · " + ops.routerBackend;

    // Source box (left)
    const src = el(ns, "g", { transform: "translate(20,128)" });
    src.appendChild(el(ns, "rect", { width: 92, height: 40, rx: 10,
      fill: "rgba(255,255,255,.04)", stroke: "rgba(255,255,255,.10)" }));
    src.appendChild(textel(ns, 46, 18, "jira webhook", "src-label"));
    src.appendChild(textel(ns, 46, 32, "incoming", "src-sub"));
    svg.appendChild(src);

    // Router center
    const cx = 270, cy = 148;
    const radial = el(ns, "circle", { cx, cy, r: 60,
      fill: "rgba(124,156,255,0.10)" });
    svg.appendChild(radial);
    const halo = el(ns, "circle", { cx, cy, r: 34,
      fill: "rgba(124,156,255,.20)", stroke: "rgba(124,156,255,.45)" });
    svg.appendChild(halo);
    const ring = el(ns, "circle", { cx, cy, r: 34, fill: "none",
      stroke: "rgba(124,156,255,.6)" });
    const a1 = el(ns, "animate", { attributeName: "r", from: 34, to: 50,
      dur: "2s", repeatCount: "indefinite" });
    const a2 = el(ns, "animate", { attributeName: "opacity", from: ".6",
      to: "0", dur: "2s", repeatCount: "indefinite" });
    ring.appendChild(a1); ring.appendChild(a2);
    svg.appendChild(ring);
    svg.appendChild(textel(ns, cx, cy - 2, "router", "router-label"));
    svg.appendChild(textel(ns, cx, cy + 12, "haiku 4.5", "router-sub"));

    // Destinations
    const dests = [
      { x: 420, y: 56,  label: "athena·bob",     cls: "athena" },
      { x: 420, y: 122, label: "coder·aquiles",  cls: "coder" },
      { x: 420, y: 188, label: "athena·hydra",   cls: "athena" },
      { x: 420, y: 252, label: "coder·sdlc",     cls: "coder" },
    ];
    dests.forEach(function (d) {
      // edge
      const line = el(ns, "path", {
        d: "M" + (cx + 34) + "," + cy + " L" + d.x + "," + (d.y + 14),
        stroke: "rgba(255,255,255,.08)", "stroke-width": 1.2, fill: "none",
      });
      svg.appendChild(line);
      const fill = d.cls === "athena" ? "rgba(124,156,255,.10)" : "rgba(198,155,255,.12)";
      const stroke = d.cls === "athena" ? "rgba(124,156,255,.22)" : "rgba(198,155,255,.32)";
      const color = d.cls === "athena" ? "#a8bcff" : "#d4b8ff";
      const g = el(ns, "g", { transform: "translate(" + d.x + "," + d.y + ")" });
      g.appendChild(el(ns, "rect", { width: 86, height: 28, rx: 8,
        fill: fill, stroke: stroke }));
      const t = el(ns, "text", { x: 43, y: 18, "text-anchor": "middle",
        fill: color, "font-size": 11, "font-family": "var(--font-sans)" });
      t.textContent = d.label;
      g.appendChild(t);
      svg.appendChild(g);
    });

    // Render last classifier signals
    const sg = document.getElementById("router-signals");
    if (sg) {
      sg.innerHTML = "";
      (ops.routerSignals || []).slice(0, 4).forEach(function (s) {
        const div = document.createElement("div");
        div.className = "rs-item " + (s.startsWith("+") ? "pos" : "neg");
        div.textContent = s;
        sg.appendChild(div);
      });
      if (!(ops.routerSignals || []).length) {
        const div = document.createElement("div");
        div.className = "rs-item neg";
        div.textContent = "(no recent classification yet)";
        sg.appendChild(div);
      }
    }
  }

  function renderJobs() {
    const list = document.getElementById("jobs-list");
    if (!list) return;
    list.innerHTML = "";
    document.getElementById("ops-jobs-count").textContent =
      ops.activeJobs.length + " active";
    ops.activeJobs.forEach(function (j) {
      const row = document.createElement("div");
      row.className = "job" + (j.hitl ? " hitl" : "");
      const stateLabel = j.hitl ? "hitl required" : j.state;
      row.innerHTML =
        '<div class="job-h">' +
          '<span class="job-id">' + esc(j.job_id) + "</span>" +
          '<span class="job-state ' + (j.hitl ? "hitl" : "run") + '">' + esc(stateLabel) + "</span>" +
        "</div>" +
        '<div class="job-name">' + esc(j.track + "·" + j.agent + " · " + (j.summary || "")) + "</div>" +
        '<div class="job-prog"><div class="job-bar" style="width:' + j.progress + '%"></div></div>' +
        '<div class="job-meta"><span>' + (j.hitl ? "review pr" : "in flight") + "</span></div>";
      list.appendChild(row);
    });
  }

  function renderLane(source) {
    const id = "lane-" + source;
    const list = document.getElementById(id);
    const cnt = document.getElementById("cnt-" + source);
    if (!list) return;
    list.innerHTML = "";
    const items = ops[source] || [];
    if (cnt) cnt.textContent = "last 1h · " + items.length;
    items.slice(0, LANE_LIMIT).forEach(function (ev) {
      const row = document.createElement("div");
      row.className = "ev";
      const dot = "dot-" + (ev.status || "ok");
      row.innerHTML =
        '<span class="ev-dot ' + dot + '"></span>' +
        '<span class="ev-text">' + esc(ev.detail || ev.target || "") + "</span>" +
        '<span class="ev-time">' + relTime(ev.received_at) + "</span>";
      list.appendChild(row);
    });
  }

  function renderRules() {
    const list = document.getElementById("rules-list");
    if (!list) return;
    list.innerHTML = "";
    ops.rules.forEach(function (r) {
      const row = document.createElement("div");
      row.className = "rule";
      row.innerHTML =
        '<span class="rule-name">' + esc(humanizeRule(r.name)) + "</span>" +
        '<span class="rule-toggle ' + (r.enabled ? "" : "off") + '" data-name="' + r.name + '"></span>';
      list.appendChild(row);
    });
    list.querySelectorAll(".rule-toggle").forEach(function (t) {
      t.addEventListener("click", function () { toggleRule(t); });
    });
  }

  function humanizeRule(n) {
    return ({
      hitl_requested: "HITL approval requested",
      build_failed: "Build failed (jenkins)",
      deploy_rolled_back: "Deploy rolled back (spinnaker)",
      pr_review_requested: "PR review requested · my team",
      athena_stale_24h: "Athena agent stale > 24h",
      slo_burn_breach: "SLO burn rate breached",
      cost_budget_80: "Cost budget > 80% used",
    }[n]) || n;
  }

  async function toggleRule(node) {
    const name = node.dataset.name;
    const enabled = node.classList.contains("off"); // about to flip
    node.classList.toggle("off");
    try {
      await fetch("/api/notifications/rules/" + encodeURIComponent(name), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: enabled }),
      });
    } catch (e) {}
  }

  // ── Notifications (Browser API) ────────────────────────────────────────

  function bootPermissionUi() {
    refreshPermPills();
    const btn = document.getElementById("btn-enable");
    const test = document.getElementById("btn-test");
    if (btn) btn.addEventListener("click", askPermission);
    if (test) test.addEventListener("click", function () {
      if (!supports()) return;
      if (Notification.permission !== "granted") return askPermission();
      fireNotification(
        "Carson · HITL approval needed",
        "J-2417 · coder·aquiles staged a PR in payments-svc with 3 changed files. Awaiting your review.",
        "carson-hitl-demo"
      );
      updateToastPreview("Carson · HITL approval needed",
        "J-2417 · coder·aquiles staged a PR in payments-svc.");
    });
  }

  function bindUi() {
    bootPermissionUi();
  }

  function supports() { return "Notification" in window; }

  function askPermission() {
    if (!supports()) return;
    Notification.requestPermission().then(function (p) {
      refreshPermPills();
      if (p === "granted") {
        fireNotification("Carson notifications enabled",
          "You will be alerted when human-in-the-loop is needed.");
      }
    });
  }

  function refreshPermPills() {
    const pill = document.getElementById("perm-pill");
    const state = document.getElementById("perm-state");
    const enable = document.getElementById("btn-enable");
    let p = supports() ? Notification.permission : "unsupported";
    if (pill) {
      pill.classList.remove("granted", "denied", "default", "unsupported");
      pill.classList.add(p);
      pill.textContent = p;
    }
    if (state) state.textContent = p;
    if (enable) {
      if (p === "granted") {
        enable.disabled = true;
        enable.textContent = "browser notifications enabled";
      } else if (p === "denied") {
        enable.disabled = true;
        enable.textContent = "blocked — enable in browser settings";
      } else {
        enable.disabled = false;
        enable.textContent = "enable browser notifications";
      }
    }
  }

  function fireNotification(title, body, tag) {
    if (!supports()) return;
    if (Notification.permission !== "granted") return;
    try {
      new Notification(title, { body: body || "", tag: tag || "carson", silent: false });
    } catch (e) {}
  }

  function updateToastPreview(title, body) {
    const t = document.getElementById("toast-prev");
    const b = document.getElementById("toast-b");
    if (!t) return;
    t.classList.remove("flash");
    void t.offsetWidth; // restart animation
    t.classList.add("flash");
    if (b && body) b.textContent = body;
    const head = t.querySelector(".toast-h");
    if (head) head.lastChild && (head.lastChild.textContent = " " + title);
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  function el(ns, name, attrs) {
    const node = document.createElementNS(ns, name);
    if (attrs) for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }
  function textel(ns, x, y, content, cls) {
    const t = el(ns, "text", { x, y, "text-anchor": "middle",
      "font-family": "var(--font-sans)" });
    t.setAttribute("class", cls || "");
    t.textContent = content;
    return t;
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function relTime(ts) {
    if (!ts) return "—";
    const d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return d + "s";
    if (d < 3600) return Math.floor(d / 60) + "m";
    if (d < 86400) return Math.floor(d / 3600) + "h";
    return Math.floor(d / 86400) + "d";
  }

  // ── Boot in background even if user starts on a different view ──────────
  // This ensures notifications still fire when user is on /#/ (live) etc.
  window.addEventListener("load", function () {
    bootSse();
    bootPermissionUi();
    refreshAll().catch(function () {});
  });
})();
