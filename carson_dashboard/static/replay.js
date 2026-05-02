// Carson dashboard · replay / time-travel view

(function () {
  "use strict";

  const AGENT_COLORS = {
    router: "#7c9cff", aquiles: "#7c9cff", sdlc: "#c69bff",
    Brandson: "#ff8fb3", brandson: "#ff8fb3",
    Jenkins: "#5cd0c4", jenkins: "#5cd0c4",
    Spinnaker: "#74d9a2", spinnaker: "#74d9a2",
    Inspector: "#ffb059", inspector: "#ffb059",
    Confluence: "#c69bff", confluence: "#c69bff",
    Jira: "#ff8fb3", jira: "#ff8fb3", github: "#ffb059",
    bob: "#74d9a2", hydra: "#5cd0c4", csb: "#9aa0b3",
    pixie: "#ff8fb3", studio: "#ffb059",
  };

  const state = {
    timeline: null,
    runs: [],
    playhead: 0,        // seconds from run start
    playing: false,
    speed: 1.5,
    raf: null,
    lastTick: 0,
    activeRunId: null,
  };

  window.showReplay = function (runId) {
    setTab("replay");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-replay").content.cloneNode(true));
    bindControls();
    bootstrap(runId);
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  async function bootstrap(runId) {
    state.runs = await fetch("/api/replay/recent?limit=20").then(function (r) { return r.json(); });
    renderRunList();
    const target = runId || (state.runs[0] && state.runs[0].id);
    if (target) loadRun(target);
  }

  function renderRunList() {
    const root = document.getElementById("rp-runs");
    if (!root) return;
    root.innerHTML = "";
    state.runs.slice(0, 8).forEach(function (r) {
      const el = document.createElement("div");
      el.className = "rp-run-item" + (r.id === state.activeRunId ? " on" : "");
      el.innerHTML =
        '<span class="rp-r-id">' + esc(r.id) + "</span>" +
        '<span class="rp-r-st status-' + (r.status || "ok") + '">' + esc(r.status || "ok") + "</span>" +
        '<div class="rp-r-ti">' + esc((r.input_text || "").slice(0, 60)) + "</div>";
      el.addEventListener("click", function () {
        loadRun(r.id);
      });
      root.appendChild(el);
    });
  }

  async function loadRun(runId) {
    state.activeRunId = runId;
    const tl = await fetch("/api/replay/" + encodeURIComponent(runId) + "/timeline")
      .then(function (r) { return r.json(); });
    state.timeline = tl;
    state.playhead = tl.duration_s * 0.62;  // start near the interesting moment
    state.playing = false;
    setText("rp-id", tl.run_id);
    setText("rp-title", tl.title);
    setText("rp-meta",
      "started " + fmtRelAgo(tl.started_at) + " · " +
      tl.agents_involved.length + " agents · " +
      (tl.totals.tokens || 0).toLocaleString() + " tokens · " +
      "$" + (tl.totals.cost_usd || 0).toFixed(2));
    renderRunList();
    drawScrubber();
    drawSwimlanes();
    drawFrameStream();
    drawToolPop();
  }

  function bindControls() {
    document.querySelectorAll(".rp-pl button[data-act]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const a = btn.dataset.act;
        if (a === "play") {
          state.playing = !state.playing;
          if (state.playing) {
            startLoop();
            btn.classList.add("on");
            btn.textContent = "⏸";
          } else {
            stopLoop();
            btn.classList.remove("on");
            btn.textContent = "⏵";
          }
        } else if (a === "back") jumpBy(-30);
        else if (a === "fwd") jumpBy(30);
        else if (a === "first") jumpTo(0);
        else if (a === "last") jumpTo(state.timeline ? state.timeline.duration_s : 0);
      });
    });
    const sp = document.getElementById("rp-speed");
    if (sp) sp.addEventListener("click", function () {
      const opts = [0.5, 1, 1.5, 2, 5];
      const i = opts.indexOf(state.speed);
      state.speed = opts[(i + 1) % opts.length];
      sp.textContent = state.speed + "×";
    });

    const scr = document.getElementById("rp-scrubber");
    if (scr) {
      scr.addEventListener("click", function (e) {
        if (!state.timeline) return;
        const rect = scr.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        jumpTo(state.timeline.duration_s * ratio);
      });
    }
  }

  function jumpTo(t) {
    if (!state.timeline) return;
    state.playhead = Math.max(0, Math.min(state.timeline.duration_s, t));
    drawScrubber();
    drawSwimlanes();
    drawFrameStream();
    drawToolPop();
  }
  function jumpBy(dt) { jumpTo(state.playhead + dt); }

  function startLoop() {
    state.lastTick = performance.now();
    function tick(now) {
      const dt = (now - state.lastTick) / 1000;
      state.lastTick = now;
      if (state.timeline && state.playing) {
        state.playhead += dt * state.speed;
        if (state.playhead >= state.timeline.duration_s) {
          state.playhead = state.timeline.duration_s;
          state.playing = false;
          const b = document.querySelector(".rp-pl button[data-act='play']");
          if (b) { b.classList.remove("on"); b.textContent = "⏵"; }
        }
        drawScrubber();
        drawSwimlanes();
        drawFrameStream();
        drawToolPop();
      }
      if (state.playing) state.raf = requestAnimationFrame(tick);
    }
    state.raf = requestAnimationFrame(tick);
  }
  function stopLoop() {
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = null;
  }

  function drawScrubber() {
    const tl = state.timeline; if (!tl) return;
    const ratio = state.playhead / Math.max(1, tl.duration_s);
    const tk = document.getElementById("rp-track");
    const tm = document.getElementById("rp-tm");
    const evs = document.getElementById("rp-events");
    if (tk) tk.style.width = (ratio * 100).toFixed(2) + "%";
    if (tm) {
      tm.style.left = (ratio * 100).toFixed(2) + "%";
      tm.textContent = "+" + fmtDur(state.playhead);
    }
    if (evs) {
      evs.innerHTML = "";
      tl.events.forEach(function (e) {
        const r = e.ts / Math.max(1, tl.duration_s);
        const dot = document.createElement("div");
        dot.className = "scr-evt";
        if (e.type === "tool_call") dot.classList.add("ok");
        if (e.type === "phase_end" && e.status && e.status !== "ok") dot.classList.add("fail");
        if (e.status === "thinking") dot.classList.add("hi");
        dot.style.left = (r * 100).toFixed(2) + "%";
        evs.appendChild(dot);
      });
    }
    setText("rp-axis-end", "+" + fmtDur(tl.duration_s));
  }

  function drawSwimlanes() {
    const tl = state.timeline; if (!tl) return;
    const root = document.getElementById("rp-swims");
    if (!root) return;
    root.innerHTML = "";
    const ratio = state.playhead / Math.max(1, tl.duration_s);

    const ph = document.createElement("div");
    ph.className = "playhead";
    ph.style.left = "calc(80px + 10px + " + (ratio * 100).toFixed(2) + "% * 0.85)";
    root.appendChild(ph);

    tl.swimlanes.forEach(function (lane) {
      const color = AGENT_COLORS[lane.agent] || "#7c9cff";
      const row = document.createElement("div");
      row.className = "swim-r";
      row.innerHTML =
        '<span class="nm" style="color:' + color + '">' + esc(lane.agent) + "</span>" +
        '<div class="swim-track"></div>';
      const track = row.querySelector(".swim-track");
      lane.segments.forEach(function (seg) {
        const a = (seg.start / tl.duration_s) * 100;
        const w = ((seg.end - seg.start) / tl.duration_s) * 100;
        const sg = document.createElement("div");
        sg.className = "swim-seg";
        sg.style.left = a.toFixed(2) + "%";
        sg.style.width = Math.max(0.5, w).toFixed(2) + "%";
        sg.style.background = color;
        if (seg.status === "thinking") sg.style.background = "rgba(255,176,89,0.30)";
        track.appendChild(sg);
      });
      root.appendChild(row);
    });
  }

  function drawFrameStream() {
    const tl = state.timeline; if (!tl) return;
    const root = document.getElementById("rp-stream");
    if (!root) return;
    root.innerHTML = "";
    const w = 30;
    tl.frame_stream
      .filter(function (f) { return Math.abs(f.ts_rel - state.playhead) < w; })
      .forEach(function (f) {
        const isLive = Math.abs(f.ts_rel - state.playhead) < 2;
        const color = AGENT_COLORS[f.agent] || "#7c9cff";
        const row = document.createElement("div");
        row.className = "fs-l" + (isLive ? " live" : "");
        row.innerHTML =
          '<span class="fs-t">+' + fmtDur(f.ts_rel) + "</span>" +
          '<span class="fs-a" style="color:' + color + '">' + esc(f.agent) + "</span>" +
          '<span class="fs-m">' + esc(f.text) + "</span>";
        root.appendChild(row);
      });
    root.scrollTop = root.scrollHeight;
  }

  function drawToolPop() {
    const tl = state.timeline; if (!tl) return;
    const root = document.getElementById("rp-tool");
    if (!root) return;
    const recent = tl.events
      .filter(function (e) { return e.type === "tool_call" && e.ts <= state.playhead && e.ts >= state.playhead - 30; })
      .sort(function (a, b) { return b.ts - a.ts; })[0];
    if (!recent) {
      root.innerHTML = '<div class="tp-empty">no tool call in current window</div>';
      return;
    }
    root.innerHTML =
      '<div class="tp-h"><span>tool call · at +' + fmtDur(recent.ts) + "</span>" +
      '<span class="nm" style="color:#a8bcff">' + esc(recent.agent) + " → " + esc(recent.tool) + "</span></div>" +
      '<div class="tp-c">' + jsonHL(recent.args) + "</div>";
  }

  function jsonHL(obj) {
    if (!obj) return "<span class='cm'>// no args</span>";
    if (typeof obj !== "object") return esc(String(obj));
    let out = "{<br>";
    const keys = Object.keys(obj);
    keys.forEach(function (k, i) {
      out += '&nbsp;&nbsp;<span class="key">"' + esc(k) + '"</span>: ';
      const v = obj[k];
      if (typeof v === "string") out += '<span class="str">"' + esc(v) + '"</span>';
      else if (typeof v === "number") out += '<span class="num">' + v + "</span>";
      else if (typeof v === "boolean") out += '<span class="kw">' + v + "</span>";
      else out += esc(JSON.stringify(v));
      out += (i < keys.length - 1 ? "," : "") + "<br>";
    });
    out += "}";
    return out;
  }

  function fmtDur(s) {
    s = Math.max(0, Math.round(s));
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60), r = s % 60;
    if (m < 60) return m + "m " + r + "s";
    const h = Math.floor(m / 60), rm = m % 60;
    return h + "h " + rm + "m";
  }
  function fmtRelAgo(ts) {
    const d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return d + "s ago";
    if (d < 3600) return Math.floor(d / 60) + "m ago";
    if (d < 86400) return Math.floor(d / 3600) + "h ago";
    return Math.floor(d / 86400) + "d ago";
  }
  function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
