// Carson dashboard · multi-session chat view
// Left rail: list of conversations.
// Center: active chat (full chat panel).
// New chats can be created and pinned.

(function () {
  "use strict";

  const FOCUS_COLORS = {
    general: "#7c9cff", athena: "#74d9a2", coder: "#c69bff",
    compliance: "#ff7c7c", ops: "#ffb059", pm: "#5cd0c4",
  };
  const AGENT_COLORS = {
    router: "#7c9cff", aquiles: "#7c9cff", sdlc: "#c69bff",
    bob: "#74d9a2", hydra: "#5cd0c4", csb: "#9aa0b3",
    pixie: "#ff8fb3", studio: "#ffb059", inspector: "#ffb059",
    confluence: "#c69bff", jira: "#ff8fb3",
  };

  const state = {
    sessions: [],
    activeId: null,
    messages: [],
  };

  window.showChats = function () {
    setTab("chats");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-chats").content.cloneNode(true));
    bindUi();
    loadSessions();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  function bindUi() {
    const newBtn = document.getElementById("ch-new");
    if (newBtn) newBtn.addEventListener("click", createNewSession);
    const form = document.getElementById("ch-compose");
    const input = document.getElementById("ch-input");
    if (form && input) {
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
        if (!text || !state.activeId) return;
        input.value = "";
        input.style.height = "auto";
        sendMessage(text);
      });
    }
  }

  async function loadSessions() {
    state.sessions = await fetch("/api/chats").then(function (r) { return r.json(); });
    renderSessionList();
    if (state.sessions.length && !state.activeId) {
      openSession(state.sessions[0].id);
    } else if (state.activeId) {
      openSession(state.activeId);
    }
  }

  function renderSessionList() {
    const root = document.getElementById("ch-sessions");
    if (!root) return;
    root.innerHTML = "";
    state.sessions.forEach(function (s) {
      const focusColor = FOCUS_COLORS[s.agent_focus] || "#7c9cff";
      const item = document.createElement("div");
      item.className = "ch-s-item" + (s.id === state.activeId ? " on" : "") + (s.pinned ? " pinned" : "");
      item.innerHTML =
        '<div class="ch-s-l"><span class="ch-s-dot" style="background:' + focusColor + '"></span>' +
          '<span class="ch-s-tt">' + esc(s.title) + "</span>" +
          (s.pinned ? '<span class="ch-s-pin">📌</span>' : "") +
        "</div>" +
        '<div class="ch-s-r">' +
          (s.unread ? '<span class="ch-s-unread">' + s.unread + "</span>" : "") +
          '<span class="ch-s-tm">' + (s.last_msg_at ? fmtRel(s.last_msg_at) : "") + "</span>" +
        "</div>" +
        '<div class="ch-s-pv">' + esc((s.last_msg_preview || "no messages yet")) + "</div>" +
        '<div class="ch-s-fc"><span class="ch-s-fpill" style="background:' + focusColor + '22;color:' + focusColor +
          ';border-color:' + focusColor + '55">focus · ' + esc(s.agent_focus) + "</span></div>";
      item.addEventListener("click", function () {
        openSession(s.id);
      });
      root.appendChild(item);
    });
    setText("ch-count", state.sessions.length + " conversation" + (state.sessions.length === 1 ? "" : "s"));
  }

  async function openSession(id) {
    state.activeId = id;
    document.querySelectorAll(".ch-s-item").forEach(function (e) { e.classList.remove("on"); });
    const session = state.sessions.find(function (s) { return s.id === id; });
    if (session) session.unread = 0;
    renderSessionList();
    const msgs = await fetch("/api/chats/" + encodeURIComponent(id) + "/messages")
      .then(function (r) { return r.json(); });
    state.messages = msgs;
    renderActiveSession(session);
  }

  function renderActiveSession(session) {
    if (!session) return;
    const focusColor = FOCUS_COLORS[session.agent_focus] || "#7c9cff";
    setText("ch-active-title", session.title);
    const fpill = document.getElementById("ch-active-focus");
    if (fpill) {
      fpill.textContent = "focus · " + session.agent_focus;
      fpill.style.background = focusColor + "22";
      fpill.style.color = focusColor;
      fpill.style.borderColor = focusColor + "55";
    }
    setText("ch-active-meta",
      "started " + fmtRel(session.created_at) + " · " +
      state.messages.length + " messages");

    const root = document.getElementById("ch-active-msgs");
    if (!root) return;
    root.innerHTML = "";
    state.messages.forEach(function (m) {
      const node = msgEl(m);
      if (node) root.appendChild(node);
    });
    root.scrollTop = root.scrollHeight;
  }

  function msgEl(m) {
    if (m.type === "system") {
      const e = document.createElement("div");
      e.className = "msg m-sy";
      e.textContent = m.text;
      return e;
    }
    if (m.type === "router") {
      const e = document.createElement("div");
      e.className = "msg m-rt";
      e.innerHTML = '<span class="m-rt-p">router</span><span>' + esc(m.text) + "</span>";
      return e;
    }
    if (m.type === "user") {
      const e = document.createElement("div");
      e.className = "msg m-u";
      e.innerHTML =
        '<div class="m-u-bb">' + esc(m.text) + "</div>" +
        '<div class="m-u-mt">' + esc(m.name || "you") + " · " + fmtRel(m.ts) + "</div>";
      return e;
    }
    const color = AGENT_COLORS[m.agent] || "#7c9cff";
    const initials = (m.agent || "??").slice(0, 2);
    const e = document.createElement("div");
    e.className = "msg m-a";
    e.innerHTML =
      '<div class="msg-avatar" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">' + esc(initials) + "</div>" +
      '<div class="m-bd">' +
        '<div class="m-hd"><span class="m-nm" style="color:' + color + '">' +
          esc(m.agent || "?") + '</span><span class="m-tm">' + fmtRel(m.ts) + "</span></div>" +
        '<div class="m-bb">' + esc(m.text) + "</div>" +
      "</div>";
    return e;
  }

  async function sendMessage(text) {
    if (!state.activeId) return;
    const tempMsg = { type: "user", name: "martin", text: text, ts: Date.now() / 1000 };
    state.messages.push(tempMsg);
    renderActiveSession(state.sessions.find(function (s) { return s.id === state.activeId; }));

    await fetch("/api/chats/" + encodeURIComponent(state.activeId) + "/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, name: "martin" }),
    });

    // Faux router reply for the demo. Real implementation gets it via SSE.
    setTimeout(function () {
      state.messages.push({
        type: "router",
        text: "classified · routing to focused agent · awaiting langgraph wireup",
        ts: Date.now() / 1000,
      });
      renderActiveSession(state.sessions.find(function (s) { return s.id === state.activeId; }));
    }, 600);
  }

  async function createNewSession() {
    const focuses = ["general", "athena", "coder", "compliance", "ops", "pm"];
    const focus = focuses[Math.floor(Math.random() * focuses.length)];
    const title = "New conversation · " + new Date().toLocaleTimeString();
    const s = await fetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title, agent_focus: focus, owner: "martin@jpmc" }),
    }).then(function (r) { return r.json(); });
    state.sessions.unshift(s);
    openSession(s.id);
  }

  function fmtRel(ts) {
    const d = Math.floor(Date.now() / 1000 - ts);
    if (d < 60) return d + "s";
    if (d < 3600) return Math.floor(d / 60) + "m";
    if (d < 86400) return Math.floor(d / 3600) + "h";
    return Math.floor(d / 86400) + "d";
  }
  function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
