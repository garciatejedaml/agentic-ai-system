// Carson dashboard · agent rooms (groups view)
// Left rail: WhatsApp-style list of agent rooms.
// Right: strands intermediate trace rendered as chat.

(function () {
  "use strict";

  const state = {
    rooms: [],
    activeName: null,
    events: [],
    activeRoom: null,
  };

  window.showGroups = function () {
    setTab("groups");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-groups").content.cloneNode(true));
    bindCompose();
    bindNewRoom();
    loadRooms();
  };

  // ── New room modal ──────────────────────────────────────────────────

  let registryCache = null;

  async function getRegistry() {
    if (registryCache) return registryCache;
    registryCache = await fetch("/api/agent-rooms/registry").then(function (r) { return r.json(); });
    return registryCache;
  }

  function bindNewRoom() {
    const btn = document.getElementById("ar-new-btn");
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", openNewRoomModal);
  }

  async function openNewRoomModal() {
    const registry = await getRegistry();
    const overlay = document.createElement("div");
    overlay.className = "ar-modal-overlay";
    overlay.innerHTML =
      '<div class="ar-modal">' +
        '<div class="ar-modal-h">' +
          '<span class="ar-modal-tt">new agent room</span>' +
          '<button class="ar-modal-x" aria-label="close">×</button>' +
        "</div>" +
        '<div class="ar-modal-sub">pick the agent that will power this room · ' +
          'or let the router decide on the first message</div>' +
        '<div class="ar-modal-grid" id="ar-modal-grid"></div>' +
        '<div class="ar-modal-form">' +
          '<label class="ar-modal-l">title</label>' +
          '<input class="ar-modal-inp" id="ar-modal-title" type="text" ' +
            'placeholder="e.g. payments-svc retry refactor · J-2419" />' +
          '<div class="ar-modal-actions">' +
            '<button class="btn" id="ar-modal-cancel">cancel</button>' +
            '<button class="btn pri" id="ar-modal-create" disabled>create room</button>' +
          "</div>" +
        "</div>" +
      "</div>";
    document.body.appendChild(overlay);

    let pickedAgent = null;
    const grid = overlay.querySelector("#ar-modal-grid");
    registry.forEach(function (a) {
      const card = document.createElement("button");
      card.className = "ar-modal-agent";
      card.dataset.agent = a.agent;
      card.style.borderColor = a.color + "44";
      card.innerHTML =
        '<div class="ar-modal-av" style="background:' + a.color + '22;color:' + a.color +
          ';border-color:' + a.color + '88">' + esc(a.agent.slice(0, 2)) + "</div>" +
        '<div class="ar-modal-info">' +
          '<div class="ar-modal-nm" style="color:' + a.color + '">' + esc(a.agent) + "</div>" +
          '<div class="ar-modal-rl">' + esc(a.role) + "</div>" +
        "</div>";
      card.addEventListener("click", function () {
        overlay.querySelectorAll(".ar-modal-agent").forEach(function (c) {
          c.classList.remove("on");
        });
        card.classList.add("on");
        pickedAgent = a.agent;
        const create = overlay.querySelector("#ar-modal-create");
        const title = overlay.querySelector("#ar-modal-title").value.trim();
        if (title && create) create.disabled = false;
      });
      grid.appendChild(card);
    });

    const titleInput = overlay.querySelector("#ar-modal-title");
    const createBtn = overlay.querySelector("#ar-modal-create");
    titleInput.addEventListener("input", function () {
      createBtn.disabled = !(titleInput.value.trim() && pickedAgent);
    });
    titleInput.focus();

    function close() { overlay.remove(); }
    overlay.querySelector(".ar-modal-x").addEventListener("click", close);
    overlay.querySelector("#ar-modal-cancel").addEventListener("click", close);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });

    createBtn.addEventListener("click", async function () {
      const title = titleInput.value.trim();
      if (!title || !pickedAgent) return;
      createBtn.disabled = true;
      createBtn.textContent = "creating...";
      const room = await fetch("/api/agent-rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title, agent: pickedAgent }),
      }).then(function (r) { return r.json(); });
      close();
      await loadRooms();
      openRoom(room.name);
    });
  }

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  async function loadRooms() {
    state.rooms = await fetch("/api/agent-rooms").then(function (r) { return r.json(); });
    renderRail();
    if (state.rooms.length && !state.activeName) {
      // Pick first pinned, else first
      const pinned = state.rooms.find(function (r) { return r.pinned; });
      openRoom((pinned || state.rooms[0]).name);
    }
  }

  function renderRail() {
    const root = document.getElementById("ar-rooms");
    if (!root) return;
    root.innerHTML = "";

    // Group by section
    const sections = {
      pinned: [],
      coder: [],
      athena: [],
      other: [],
    };
    state.rooms.forEach(function (r) {
      if (r.pinned || r.presence === "hitl") sections.pinned.push(r);
      else if (r.track === "coder") sections.coder.push(r);
      else if (r.track === "athena") sections.athena.push(r);
      else sections.other.push(r);
    });

    if (sections.pinned.length) {
      addSectionHeader(root, "pinned · active jobs");
      sections.pinned.forEach(function (r) { root.appendChild(roomEl(r)); });
    }
    if (sections.coder.length) {
      addSectionHeader(root, "coder agents");
      sections.coder.forEach(function (r) { root.appendChild(roomEl(r)); });
    }
    if (sections.athena.length) {
      addSectionHeader(root, "athena · knowledge");
      sections.athena.forEach(function (r) { root.appendChild(roomEl(r)); });
    }
    if (sections.other.length) {
      addSectionHeader(root, "git · build · deploy · docs");
      sections.other.forEach(function (r) { root.appendChild(roomEl(r)); });
    }

    setText("ar-online", state.rooms.length + " agents · " +
      state.rooms.filter(function (r) { return r.presence === "on"; }).length + " active");
  }

  function addSectionHeader(root, label) {
    const h = document.createElement("div");
    h.className = "ar-section-h";
    h.textContent = label;
    root.appendChild(h);
  }

  function roomEl(r) {
    const el = document.createElement("div");
    el.className = "ar-room" + (r.name === state.activeName ? " on" : "");
    const agent = r.agent || r.name;
    const initials = agent.slice(0, 2);
    const color = r.color || "#7c9cff";
    const pres = r.presence || "idle";
    const title = r.title || agent;
    const presColor = {
      on: "#74d9a2", idle: "#5b6072", hitl: "#ffb059", stale: "#ff7c7c",
    }[pres] || "#5b6072";

    const titleStyle = pres === "hitl" ? 'style="color:#ffb059"' : "";
    const previewClass = pres === "hitl" ? "ar-r-pv hitl-pv" : "ar-r-pv";
    const preview = r.last_msg_preview || r.state_label || "no recent activity";
    const tm = r.last_msg_at ? fmtRel(r.last_msg_at) : "—";
    const badge = r.unread_count
      ? '<span class="ar-r-badge ' + (pres === "hitl" ? "hi" : "") + '">' +
          (pres === "hitl" ? "!" : r.unread_count) + "</span>"
      : "";
    const pin = r.pinned ? '<span class="ar-r-pin">📌</span>' : "";

    el.innerHTML =
      '<div class="ar-r-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '88">' + esc(initials) +
        '<span class="ar-r-pres" style="background:' + presColor + ';' +
          (pres === "on" || pres === "hitl" ? "animation:blink 1.6s infinite;" : "") +
        '"></span>' +
      "</div>" +
      '<div class="ar-r-mid">' +
        '<div class="ar-r-row">' +
          '<span class="ar-r-nm" ' + titleStyle + '>' + esc(title) + "</span>" +
          '<span class="ar-r-tm">' + tm + "</span>" +
        "</div>" +
        '<div class="ar-r-agent" style="color:' + color + '99">' +
          '@' + esc(agent) + " · " + esc(r.role || "") + "</div>" +
        '<div class="' + previewClass + '">' + esc(preview) + "</div>" +
      "</div>" +
      '<div class="ar-r-r">' + badge + pin + "</div>";

    el.addEventListener("click", function () { openRoom(r.name); });
    return el;
  }

  async function openRoom(name) {
    state.activeName = name;
    document.querySelectorAll(".ar-room").forEach(function (e) {
      e.classList.remove("on");
    });
    const data = await fetch("/api/agent-rooms/" + encodeURIComponent(name) + "/trace")
      .then(function (r) { return r.json(); });
    state.events = data.events || [];
    state.activeRoom = state.rooms.find(function (r) { return r.name === name; });
    renderRail();
    renderHeader();
    renderTrace();
  }

  function renderHeader() {
    const room = state.activeRoom;
    if (!room) return;
    const color = room.color || "#7c9cff";
    const agent = room.agent || room.name;
    const title = room.title || agent;
    setText("ar-h-nm", title);
    setText("ar-h-agent", "@" + agent + " · " + (room.role || ""));
    const av = document.getElementById("ar-h-av");
    if (av) {
      av.textContent = agent.slice(0, 2);
      av.style.background = color + "22";
      av.style.color = color;
      av.style.borderColor = color + "88";
    }

    // Chips
    const chips = document.getElementById("ar-h-chips");
    if (chips) {
      chips.innerHTML = "";
      // strands provider chip
      const provider = document.createElement("span");
      provider.style.fontFamily = "var(--font-mono)";
      provider.style.fontSize = "11px";
      provider.style.color = "#8b91a3";
      provider.textContent = "strands · anthropic.bedrock · sonnet-4-6";
      chips.appendChild(provider);

      // mode chip
      const det = lastEventOfType("routing");
      if (det && det.payload && det.payload.mode) {
        const m = document.createElement("span");
        m.className = "ar-chip det";
        m.textContent = det.payload.mode.replace("_", "-");
        chips.appendChild(m);
      }
      // state chip
      if (room.state_label) {
        const s = document.createElement("span");
        s.className = "ar-chip " + (room.presence === "hitl" ? "hitl" : "run");
        s.textContent = room.state_label;
        chips.appendChild(s);
      }
    }
  }

  function lastEventOfType(t) {
    for (let i = state.events.length - 1; i >= 0; i--) {
      if (state.events[i].event_type === t) return state.events[i];
    }
    return null;
  }

  function renderTrace() {
    const root = document.getElementById("ar-tape");
    if (!root) return;
    root.innerHTML = "";
    state.events.forEach(function (e) {
      const node = renderEvent(e);
      if (node) root.appendChild(node);
    });
    root.scrollTop = root.scrollHeight;
  }

  function renderEvent(e) {
    const t = e.event_type;
    if (t === "system") return sysEl(e);
    if (t === "user_message") return userEl(e);
    if (t === "routing") return routerEl(e);
    if (t === "thinking") return thinkEl(e);
    if (t === "tool_call") return toolCallEl(e);
    if (t === "tool_result") return toolResultEl(e);
    if (t === "delegation") return delegationEl(e);
    if (t === "hitl_request") return hitlEl(e);
    if (t === "agent_message") return agentMsgEl(e);
    return null;
  }

  function sysEl(e) {
    const el = document.createElement("div");
    el.className = "m m-sys";
    el.textContent = (e.payload && e.payload.text) || e.event_type;
    return el;
  }

  function userEl(e) {
    const el = document.createElement("div");
    el.className = "m m-u";
    el.innerHTML =
      '<div class="m-u-bb">' + esc(e.payload.text || "") + "</div>" +
      '<div class="m-u-mt">' + esc(e.actor || "you") + " · " + fmtRel(e.ts) + "</div>";
    return el;
  }

  function routerEl(e) {
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-rt";
    el.innerHTML =
      '<span class="m-rt-p">router</span>' +
      "<span>classified · " + esc(p.track || "") + " track → " +
        esc(p.agent || "") + " · confidence " +
        (typeof p.confidence === "number" ? p.confidence.toFixed(2) : "—") +
        (p.mode ? " · " + esc(p.mode.replace("_", "-")) : "") + "</span>";
    return el;
  }

  function thinkEl(e) {
    const room = state.activeRoom;
    const color = (room && room.color) || "#7c9cff";
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-a";
    el.innerHTML =
      '<div class="ar-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="ar-think">' +
          '<div class="ar-think-h"><span>thinking · ' + esc(p.kind || "step") + "</span>" +
            '<span class="dur">' +
              (e.duration_ms ? formatDur(e.duration_ms) : "") +
              (e.tokens ? " · " + e.tokens.toLocaleString() + " tokens" : "") +
            "</span></div>" +
          '"' + esc(p.text || "") + '"' +
        "</div>" +
      "</div>";
    return el;
  }

  function toolCallEl(e) {
    const room = state.activeRoom;
    const color = (room && room.color) || "#7c9cff";
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-a";
    el.innerHTML =
      '<div class="ar-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="ar-tool">' +
          '<div class="ar-tool-h">' +
            '<div class="ar-tool-h-l">' +
              '<span class="ar-tool-tag">tool' + (p.step ? " · " + esc(p.step) : "") + "</span>" +
              '<span class="ar-tool-arrow">→</span>' +
              '<span class="ar-tool-target">' + esc(p.tool || "") + "</span>" +
            "</div>" +
            '<span class="ar-tool-h-r">' + relAbsTime(e.ts) +
              (e.duration_ms ? " · " + formatDur(e.duration_ms) : "") + "</span>" +
          "</div>" +
          '<div class="ar-tool-body">' + jsonHL(p.args || {}) + "</div>" +
        "</div>" +
      "</div>";
    return el;
  }

  function toolResultEl(e) {
    const room = state.activeRoom;
    const color = (room && room.color) || "#7c9cff";
    const p = e.payload || {};
    const status = p.status || "ok";
    const el = document.createElement("div");
    el.className = "m m-a";
    el.innerHTML =
      '<div class="ar-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="ar-tres">' +
          '<div class="ar-tres-h">' +
            '<div class="ar-tres-h-l">' +
              '<span class="ar-tres-tag ' + (status !== "ok" ? "fail" : "") + '">result · ' +
                esc(status) + "</span>" +
              '<span class="ar-tres-name">' + esc(p.tool || "") + "</span>" +
            "</div>" +
            '<span class="ar-tres-h-r">' + esc(p.summary_short || "") + "</span>" +
          "</div>" +
          '<div class="ar-tres-cap">' + esc(p.summary || "") + "</div>" +
        "</div>" +
      "</div>";
    return el;
  }

  function delegationEl(e) {
    const room = state.activeRoom;
    const color = (room && room.color) || "#7c9cff";
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-a";
    el.innerHTML =
      '<div class="ar-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="ar-deleg">' +
          '<span class="ar-deleg-arrow">↳</span>' +
          "<div>" +
            '<div class="ar-deleg-h">' +
              '<span class="ar-deleg-tag">delegate</span>' +
              '<span class="ar-deleg-from">' + esc(e.actor || "") + "</span>" +
              '<span class="ar-tool-arrow">→</span>' +
              '<span class="ar-deleg-to">' + esc(p.to || "") + "</span>" +
            "</div>" +
            '<div class="ar-deleg-text">' + esc(p.text || "") + "</div>" +
          "</div>" +
        "</div>" +
      "</div>";
    return el;
  }

  function hitlEl(e) {
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-a";
    const actions = (p.actions || []).map(function (a) {
      return '<button class="btn ' + (a.kind === "primary" ? "pri" : "") +
        '" data-action="' + esc(a.action) + '">' + esc(a.label) + "</button>";
    }).join("");
    el.innerHTML =
      '<div class="ar-av" style="background:rgba(255,176,89,.13);color:#ffb059;border-color:rgba(255,176,89,.55)">' +
        esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="ar-hitl">' +
          '<div class="ar-hitl-tg">human-in-the-loop · ' + esc(p.job_id || "") + "</div>" +
          '<div class="ar-h-info"><span class="ar-h-info-nm" style="color:#7c9cff">' +
            esc(e.actor || "") + "</span>" +
            '<span class="ar-h-info-tm">' + fmtRel(e.ts) + "</span></div>" +
          '<div class="ar-hitl-text">' + esc(p.text || "") + "</div>" +
          '<div class="ar-hitl-actions">' + actions + "</div>" +
        "</div>" +
      "</div>";
    return el;
  }

  function agentMsgEl(e) {
    const room = state.activeRoom;
    const color = (room && room.color) || "#7c9cff";
    const p = e.payload || {};
    const el = document.createElement("div");
    el.className = "m m-a";
    let actions = "";
    if (p.actions && p.actions.length) {
      actions = '<div class="ar-hitl-actions" style="margin-top:8px">' +
        p.actions.map(function (a) {
          return '<button class="btn ' + (a.kind === "primary" ? "pri" : "") +
            '" data-action="' + esc(a.action) + '">' + esc(a.label) + "</button>";
        }).join("") + "</div>";
    }
    el.innerHTML =
      '<div class="ar-av" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(e.actor ? e.actor.slice(0, 2) : "??") + "</div>" +
      '<div class="m-bd">' +
        '<div class="m-hd"><span class="m-nm" style="color:' + color + '">' +
          esc(e.actor || "") + "</span>" +
          '<span class="m-tm">' + fmtRel(e.ts) + "</span></div>" +
        '<div class="m-bb">' + esc(p.text || "") + "</div>" + actions +
      "</div>";
    return el;
  }

  function bindCompose() {
    const form = document.getElementById("ar-compose");
    const input = document.getElementById("ar-input");
    if (!form || !input || form.dataset.bound) return;
    form.dataset.bound = "1";

    input.addEventListener("input", function () {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 120) + "px";
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
      if (!text || !state.activeName) return;
      input.value = "";
      input.style.height = "auto";
      sendMessage(text);
    });
  }

  async function sendMessage(text) {
    state.events.push({
      event_type: "user_message", actor: "martin",
      payload: { text: text }, ts: Date.now() / 1000,
      seq: state.events.length + 1,
    });
    renderTrace();
    await fetch("/api/agent-rooms/" + encodeURIComponent(state.activeName) + "/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, name: "martin" }),
    });
    // Mock router response since real wiring is in the bridge prompt
    setTimeout(function () {
      state.events.push({
        event_type: "routing", actor: "router",
        payload: { track: "coder", agent: state.activeName, confidence: 0.92 },
        ts: Date.now() / 1000, seq: state.events.length + 1,
      });
      renderTrace();
    }, 400);
  }

  // ── Helpers ───────────────────────────────────────────────────────────

  function jsonHL(obj) {
    if (!obj || (typeof obj !== "object")) return esc(String(obj));
    let out = "{<br>";
    const keys = Object.keys(obj);
    keys.forEach(function (k, i) {
      out += '&nbsp;&nbsp;<span class="key">"' + esc(k) + '"</span>: ';
      const v = obj[k];
      if (typeof v === "string") out += '<span class="str">"' + esc(v) + '"</span>';
      else if (typeof v === "number") out += '<span class="num">' + v + "</span>";
      else if (typeof v === "boolean") out += '<span class="kw">' + v + "</span>";
      else if (Array.isArray(v)) out += esc(JSON.stringify(v));
      else if (v === null) out += '<span class="kw">null</span>';
      else out += esc(JSON.stringify(v));
      out += (i < keys.length - 1 ? "," : "") + "<br>";
    });
    out += "}";
    return out;
  }

  function fmtRel(ts) {
    const d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return d + "s";
    if (d < 3600) return Math.floor(d / 60) + "m";
    if (d < 86400) return Math.floor(d / 3600) + "h";
    return Math.floor(d / 86400) + "d";
  }
  function relAbsTime(ts) {
    const d = Math.floor(Date.now() / 1000 - ts);
    return "+" + (d < 60 ? d + "s" : Math.floor(d / 60) + "m");
  }
  function formatDur(ms) {
    if (ms < 1000) return ms + "ms";
    if (ms < 60_000) return (ms / 1000).toFixed(1) + "s";
    const m = Math.floor(ms / 60_000);
    const s = Math.round((ms % 60_000) / 1000);
    return m + "m " + s + "s";
  }
  function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
