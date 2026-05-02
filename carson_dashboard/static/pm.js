// Carson dashboard · project manager view
// Left rail: epic tree + confluence pages.
// Center: kanban with status columns.
// Right rail: PM chat (premium, focused on project work).

(function () {
  "use strict";

  const STATE_COLORS = {
    backlog:    "#5b6072",
    planning:   "#ffb059",
    in_progress: "#7c9cff",
    review:     "#c69bff",
    blocked:    "#ff7c7c",
    done:       "#74d9a2",
    cancelled:  "#5b6072",
  };

  const state = {
    projects: [], activeProject: null,
    epics: [], activeEpic: null,
    deliverables: [], confluence: [],
  };

  window.showPM = function () {
    setTab("pm");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-pm").content.cloneNode(true));
    bindUi();
    bootstrap();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  async function bootstrap() {
    state.projects = await fetch("/api/pm/projects").then(function (r) { return r.json(); });
    if (state.projects.length) state.activeProject = state.projects[0].id;
    renderProjectSelector();
    await loadProjectData();
    seedChat();
  }

  async function loadProjectData() {
    if (!state.activeProject) return;
    const url = new URL("/api/pm/epics", location.origin);
    url.searchParams.set("project_id", state.activeProject);
    const ep = await fetch(url).then(function (r) { return r.json(); });
    state.epics = ep;
    state.activeEpic = ep.length ? ep[0].id : null;
    state.confluence = await fetch("/api/pm/confluence?project_id=" + state.activeProject)
      .then(function (r) { return r.json(); });
    if (state.activeEpic) {
      state.deliverables = await fetch("/api/pm/deliverables?epic_id=" + state.activeEpic)
        .then(function (r) { return r.json(); });
    }
    renderEpicTree();
    renderConfluence();
    renderKanban();
  }

  function renderProjectSelector() {
    const sel = document.getElementById("pm-project");
    if (!sel) return;
    if (state.projects.length === 0) {
      sel.textContent = "no projects";
      return;
    }
    sel.innerHTML = "";
    state.projects.forEach(function (p) {
      const opt = document.createElement("span");
      opt.className = "pm-proj-opt" + (p.id === state.activeProject ? " on" : "");
      opt.textContent = p.name;
      opt.addEventListener("click", function () {
        state.activeProject = p.id;
        renderProjectSelector();
        loadProjectData();
      });
      sel.appendChild(opt);
    });
  }

  function renderEpicTree() {
    const root = document.getElementById("pm-epics");
    if (!root) return;
    root.innerHTML = "";
    state.epics.forEach(function (e) {
      const item = document.createElement("div");
      item.className = "pm-epic" + (e.id === state.activeEpic ? " on" : "");
      const counts = e.deliverable_counts || {};
      const total = Object.values(counts).reduce(function (a, b) { return a + b; }, 0);
      const done = counts.done || 0;
      const prog = total > 0 ? done / total : (e.progress_pct || 0);
      const stColor = STATE_COLORS[e.state] || "#7c9cff";
      item.innerHTML =
        '<div class="pm-epic-h">' +
          '<span class="pm-epic-jk">' + esc(e.jira_key || "DRAFT") + "</span>" +
          '<span class="pm-epic-st" style="background:' + stColor + '22;color:' + stColor +
            ';border-color:' + stColor + '55">' + esc(e.state) + "</span>" +
        "</div>" +
        '<div class="pm-epic-tt">' + esc(e.title) + "</div>" +
        '<div class="pm-epic-pb"><div class="pm-epic-pf" style="width:' + (prog * 100).toFixed(0) +
          '%;background:' + stColor + '"></div></div>' +
        '<div class="pm-epic-mt">' + esc(e.owner || "tbd") + " · " +
          (total ? done + "/" + total + " deliverables" : "no deliverables") + "</div>";
      item.addEventListener("click", async function () {
        state.activeEpic = e.id;
        state.deliverables = await fetch("/api/pm/deliverables?epic_id=" + e.id)
          .then(function (r) { return r.json(); });
        renderEpicTree();
        renderKanban();
      });
      root.appendChild(item);
    });
  }

  function renderConfluence() {
    const root = document.getElementById("pm-conf");
    if (!root) return;
    root.innerHTML = "";
    state.confluence.slice(0, 6).forEach(function (p) {
      const el = document.createElement("div");
      el.className = "pm-conf-r";
      el.innerHTML =
        '<div class="pm-conf-tt">' + esc(p.title) + "</div>" +
        '<div class="pm-conf-mt"><span class="pm-conf-sp">' + esc(p.space) + "</span> · " +
          fmtRel(p.last_edited_at) + " · " + esc(p.last_editor || "—") + "</div>";
      root.appendChild(el);
    });
  }

  function renderKanban() {
    const root = document.getElementById("pm-kanban");
    if (!root) return;
    const columns = ["backlog", "in_progress", "review", "done"];
    const grouped = {};
    columns.forEach(function (c) { grouped[c] = []; });
    state.deliverables.forEach(function (d) {
      const c = grouped[d.state] ? d.state : "backlog";
      grouped[c].push(d);
    });
    root.innerHTML = "";
    columns.forEach(function (col) {
      const items = grouped[col];
      const wrap = document.createElement("div");
      wrap.className = "pm-col";
      const stColor = STATE_COLORS[col] || "#7c9cff";
      wrap.innerHTML =
        '<div class="pm-col-h">' +
          '<span class="pm-col-tt">' + esc(col.replace(/_/g, " ")) + "</span>" +
          '<span class="pm-col-cn">' + items.length + "</span>" +
        "</div>" +
        '<div class="pm-col-acc" style="background:' + stColor + '"></div>' +
        '<div class="pm-col-list"></div>';
      const list = wrap.querySelector(".pm-col-list");
      items.forEach(function (d) {
        const card = document.createElement("div");
        card.className = "pm-card";
        card.innerHTML =
          '<div class="pm-card-h">' +
            '<span class="pm-card-jk">' + esc(d.jira_key || "DRAFT") + "</span>" +
            (d.points ? '<span class="pm-card-pt">' + d.points + " pts</span>" : "") +
          "</div>" +
          '<div class="pm-card-tt">' + esc(d.title) + "</div>" +
          '<div class="pm-card-mt">' + esc(d.owner || "tbd") + "</div>";
        list.appendChild(card);
      });
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "pm-col-empty";
        empty.textContent = "—";
        list.appendChild(empty);
      }
      root.appendChild(wrap);
    });
  }

  // ── PM chat (premium, project-aware) ───────────────────────────────

  function seedChat() {
    const root = document.getElementById("pm-chat-msgs");
    if (!root) return;
    root.innerHTML = "";
    const now = Date.now() / 1000;
    const msgs = [
      sysMsg("channel opened · pm focus · drafts go through review before commit", now - 1800),
      userMsg("Draft an epic to migrate Athena Pixie to HNSW.", now - 1700),
      routerMsg("classified · pm track → pm-agent · confidence 0.97", now - 1698),
      agentMsg("pm-agent",
        "Draft ready. 5 child tickets, target end of Q4. Confluence ADR + runbook also queued. Approve to create in Jira?",
        now - 1696,
        [
          { label: "approve & create", kind: "primary" },
          { label: "request changes", kind: "ghost" },
          { label: "preview adr", kind: "ghost" },
        ]),
      userMsg("Looks good but bump points on the migration ticket to 8.", now - 600),
      agentMsg("pm-agent", "Updated. Migration ticket → 8 points. Anything else?", now - 598),
    ];
    msgs.forEach(function (m) { root.appendChild(chatMsgEl(m)); });
    root.scrollTop = root.scrollHeight;

    const form = document.getElementById("pm-chat-form");
    const input = document.getElementById("pm-chat-input");
    if (form && input && !form.dataset.bound) {
      form.dataset.bound = "1";
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        root.appendChild(chatMsgEl(userMsg(text, Date.now() / 1000)));
        root.scrollTop = root.scrollHeight;
        // Mock router classification + drafted reply
        setTimeout(function () {
          root.appendChild(chatMsgEl(routerMsg("classified · pm track → pm-agent · confidence 0.92", Date.now() / 1000)));
          root.scrollTop = root.scrollHeight;
          setTimeout(function () {
            root.appendChild(chatMsgEl(agentMsg("pm-agent", fakeReply(text), Date.now() / 1000)));
            root.scrollTop = root.scrollHeight;
          }, 700);
        }, 300);
      });
    }
    document.querySelectorAll("#pm-chat .qr-pill").forEach(function (p) {
      p.addEventListener("click", function () {
        if (input) input.value = p.dataset.text || p.textContent;
        if (input) input.focus();
      });
    });
  }

  function sysMsg(text, ts)            { return { type: "system", text: text, ts: ts }; }
  function routerMsg(text, ts)         { return { type: "router", text: text, ts: ts }; }
  function userMsg(text, ts)           { return { type: "user", name: "martin", text: text, ts: ts }; }
  function agentMsg(agent, text, ts, actions) { return { type: "agent", agent: agent, text: text, ts: ts, actions: actions }; }

  function chatMsgEl(m) {
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
      e.innerHTML = '<div class="m-u-bb">' + esc(m.text) + "</div>" +
        '<div class="m-u-mt">' + esc(m.name || "you") + " · " + fmtRel(m.ts) + "</div>";
      return e;
    }
    const color = "#5cd0c4";
    const e = document.createElement("div");
    e.className = "msg m-a";
    let actions = "";
    if (m.actions && m.actions.length) {
      actions = '<div class="msg-actions">' + m.actions.map(function (a) {
        return '<button class="auto-btn auto-btn-' + (a.kind || "ghost") + '">' + esc(a.label) + "</button>";
      }).join("") + "</div>";
    }
    e.innerHTML =
      '<div class="msg-avatar" style="background:' + color + '22;color:' + color +
        ';border-color:' + color + '55">pm</div>' +
      '<div class="m-bd">' +
        '<div class="m-hd"><span class="m-nm" style="color:' + color + '">' +
          esc(m.agent) + '</span><span class="m-rl">project manager agent</span>' +
          '<span class="m-tm">' + fmtRel(m.ts) + "</span></div>" +
        '<div class="m-bb">' + esc(m.text) + "</div>" + actions +
      "</div>";
    return e;
  }

  function fakeReply(text) {
    const t = text.toLowerCase();
    if (t.indexOf("epic") >= 0 || t.indexOf("draft") >= 0)
      return "Drafting · you'll get a structured proposal here in ~5s with child tickets + estimated points.";
    if (t.indexOf("post-mortem") >= 0)
      return "Pulling related Jira tickets, deploy events and rollback timelines for this incident. Confluence ADR draft in progress.";
    if (t.indexOf("blocked") >= 0)
      return "3 deliverables are blocked: CARSN-1303 waits on infra approval · CARSN-1291 waits on schema review · CARSN-1304 missing assignee.";
    if (t.indexOf("summarise") >= 0 || t.indexOf("summary") >= 0)
      return "Q3 summary: 412 tickets shipped, 91% on-time, 3 incidents (all auto-rolled-back). Largest spend: athena migration (47% of total).";
    return "Got it. Would you like me to draft a Jira ticket, an epic, or a Confluence page for this?";
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

  function bindUi() {
    // already bound inside seedChat
  }
})();
