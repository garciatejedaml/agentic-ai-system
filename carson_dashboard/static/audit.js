// Carson dashboard · compliance audit view

(function () {
  "use strict";

  const TYPE_LABEL = {
    deploy: "deploy", build: "build", approval: "approval",
    hitl_approve: "hitl approve", hitl_reject: "hitl reject",
    data_access: "data access", index_sync: "index sync",
    rollback: "rollback", config_change: "config change",
  };
  const TYPE_CLASS = {
    deploy: "dep", build: "dep", approval: "app",
    hitl_approve: "hitl", hitl_reject: "hitl",
    data_access: "idx", index_sync: "idx",
    rollback: "rb", config_change: "app",
  };

  let state = {
    activeTypes: null, // null = all
    sinceHours: 30 * 24,
  };

  window.showAudit = function () {
    setTab("audit");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-audit").content.cloneNode(true));
    bindFilters();
    refresh();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  function bindFilters() {
    document.querySelectorAll("#au-filters [data-type]").forEach(function (el) {
      el.addEventListener("click", function () {
        const t = el.dataset.type;
        if (t === "all") state.activeTypes = null;
        else if (state.activeTypes && state.activeTypes.includes(t)) {
          state.activeTypes = state.activeTypes.filter(function (x) { return x !== t; });
          if (!state.activeTypes.length) state.activeTypes = null;
        } else {
          state.activeTypes = (state.activeTypes || []).concat([t]);
        }
        document.querySelectorAll("#au-filters [data-type]").forEach(function (e) {
          const v = e.dataset.type;
          const on = state.activeTypes ? state.activeTypes.includes(v) : v === "all";
          e.classList.toggle("on", on);
        });
        refresh();
      });
    });
    document.querySelectorAll("#au-filters [data-since]").forEach(function (el) {
      el.addEventListener("click", function () {
        state.sinceHours = parseInt(el.dataset.since, 10);
        document.querySelectorAll("#au-filters [data-since]").forEach(function (e) {
          e.classList.toggle("on", e === el);
        });
        refresh();
      });
    });
    const exp = document.getElementById("au-export");
    if (exp) exp.addEventListener("click", function () {
      fetch("/api/audit/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ since_hours: state.sinceHours }),
      }).then(function (r) { return r.json(); })
        .then(function (data) {
          const tip = document.getElementById("au-export-tip");
          if (tip) tip.textContent = "exported · " + data.row_count + " rows · " + data.url;
        });
    });
  }

  async function refresh() {
    try {
      const url = new URL("/api/audit/log", location.origin);
      url.searchParams.set("limit", "200");
      url.searchParams.set("since_hours", String(state.sinceHours));
      if (state.activeTypes) url.searchParams.set("types", state.activeTypes.join(","));
      const [rows, stats] = await Promise.all([
        fetch(url).then(function (r) { return r.json(); }),
        fetch("/api/audit/stats?window_days=" + (state.sinceHours / 24)).then(function (r) { return r.json(); }),
      ]);
      renderStats(stats);
      renderRows(rows);
      renderFilterCounts(stats);
    } catch (e) { console.warn("audit refresh failed", e); }
  }

  function renderStats(s) {
    setText("au-stat-approvals", String(s.approvals_this_week));
    setHTML("au-stat-time", fmtDur(s.avg_time_to_approve_sec));
    setHTML("au-stat-data",
      s.data_classifications.internal + ' <small>internal · ' +
      s.data_classifications.sensitive + ' sensitive</small>');
    setText("au-stat-pending", String(s.pending_reviews));
  }

  function renderFilterCounts(stats) {
    document.querySelectorAll("#au-filters [data-type]").forEach(function (el) {
      const t = el.dataset.type;
      const cnt = el.querySelector(".cnt");
      if (!cnt) return;
      if (t === "all") {
        const total = Object.values(stats.by_event_type).reduce(function (a, b) { return a + b; }, 0);
        cnt.textContent = String(total);
      } else {
        cnt.textContent = String(stats.by_event_type[t] || 0);
      }
    });
  }

  function renderRows(rows) {
    const tbody = document.getElementById("au-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    rows.forEach(function (r) {
      const tr = document.createElement("tr");
      const cls = TYPE_CLASS[r.event_type] || "app";
      const lbl = TYPE_LABEL[r.event_type] || r.event_type;
      tr.innerHTML =
        '<td class="ts" style="padding-left:16px">' + fmtTs(r.ts) + "</td>" +
        '<td class="actor">' + esc(r.actor) + "</td>" +
        '<td><span class="ev-tag ' + cls + '">' + esc(lbl) + "</span></td>" +
        '<td class="resource">' + escRes(r.resource) + "</td>" +
        "<td>" + esc(r.approved_by || "—") + "</td>" +
        '<td style="padding-right:16px"><a style="color:#a8bcff;cursor:pointer">' + esc(r.trace_id || "") + "</a></td>";
      tbody.appendChild(tr);
    });
  }

  function fmtTs(ts) {
    const d = new Date(ts * 1000);
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0") + " " +
      String(d.getHours()).padStart(2, "0") + ":" +
      String(d.getMinutes()).padStart(2, "0") + ":" +
      String(d.getSeconds()).padStart(2, "0");
  }
  function fmtDur(s) {
    if (s < 60) return s + "<small>s</small>";
    const m = Math.floor(s / 60), r = s % 60;
    return m + "<small>m " + (r ? r + "s</small>" : "</small>");
  }
  function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
  function setHTML(id, h) { const e = document.getElementById(id); if (e) e.innerHTML = h; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escRes(s) {
    if (!s) return "";
    // Wrap path-ish tokens in <code>
    return String(s).split(/(\s)/).map(function (tok) {
      if (/^[a-z0-9_./#-]{3,}$/i.test(tok) && /[._/#-]/.test(tok)) {
        return "<code>" + esc(tok) + "</code>";
      }
      return esc(tok);
    }).join("");
  }
})();
