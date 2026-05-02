// Carson dashboard · cost & impact view
// Hero counters, comparison bars, autonomy trend sparkline, leaderboard.

(function () {
  "use strict";

  const AGENT_COLORS = {
    aquiles: "#7c9cff", sdlc: "#c69bff", "athena-dev": "#74d9a2",
    brandson: "#ff8fb3", jenkins: "#5cd0c4", inspector: "#ffb059",
    confluence: "#c69bff", spinnaker: "#74d9a2", router: "#7c9cff",
    bob: "#74d9a2", hydra: "#5cd0c4", csb: "#9aa0b3",
    pixie: "#ff8fb3", studio: "#ffb059",
  };

  window.showCost = function () {
    setTab("cost");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-cost").content.cloneNode(true));
    refresh();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  async function refresh() {
    try {
      const [summary, comp, trend, lb] = await Promise.all([
        fetch("/api/cost/summary").then(function (r) { return r.json(); }),
        fetch("/api/cost/comparison").then(function (r) { return r.json(); }),
        fetch("/api/cost/autonomy-trend?weeks=12").then(function (r) { return r.json(); }),
        fetch("/api/cost/leaderboard?limit=8").then(function (r) { return r.json(); }),
      ]);
      renderCounters(summary);
      renderComparison(comp);
      renderTrend(trend);
      renderLeaderboard(lb);
    } catch (e) { console.warn("cost refresh failed", e); }
  }

  function renderCounters(s) {
    setText("c-prs", fmtNum(s.prs_shipped));
    setText("c-prs-d", "+ " + fmtNum(s.delta_prs_q_over_q) + " vs last quarter");
    setText("c-hours", fmtNum(s.hours_saved) + "h");
    setHTML("c-hours-d", '≈ <b style="color:#74d9a2">' + fmtMoney(s.dollars_saved) + "</b> at $100/h");
    setText("c-bugs", String(s.bugs_caught));
    setText("c-bugs-d", "− " + s.rollbacks_prevented + " incidents avoided");
    setText("c-hitl", Math.round(s.hitl_under_4min_pct * 100) + "%");
    setText("c-hitl-d", "+ " + s.delta_autonomy_pp + " pp vs last month");
  }

  function renderComparison(c) {
    const tt = c.time_to_pr_hours;
    setStyle("cmp-tt-with-fl", "width", pct(tt.with_carson, tt.manual));
    setText("cmp-tt-with-v", tt.with_carson + " h");
    setText("cmp-tt-with-d", Math.round(tt.delta_pct * 100) + "%");
    setText("cmp-tt-without-v", tt.manual + " h");

    const cp = c.cost_per_pr_usd;
    setStyle("cmp-cp-with-fl", "width", pct(cp.with_carson, cp.manual));
    setText("cmp-cp-with-v", "$" + cp.with_carson.toFixed(2));
    setText("cmp-cp-with-d", Math.round(cp.delta_pct * 100) + "%");
    setText("cmp-cp-without-v", "$" + cp.manual.toFixed(2));
  }

  function renderTrend(trend) {
    const svg = document.getElementById("c-trend-svg");
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const ns = "http://www.w3.org/2000/svg";
    const w = 600, h = 60;
    const max = 1.0, min = 0.30;
    const stepX = w / (trend.length - 1);
    const points = trend.map(function (t, i) {
      const x = i * stepX;
      const y = h - ((t.pct - min) / (max - min)) * (h - 4) - 2;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");

    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML = '<linearGradient id="cTrendG" x1="0" x2="0" y1="0" y2="1">' +
      '<stop offset="0" stop-color="#7c9cff" stop-opacity=".30"/>' +
      '<stop offset="1" stop-color="#7c9cff" stop-opacity="0"/></linearGradient>';
    svg.appendChild(defs);
    const fill = document.createElementNS(ns, "polyline");
    fill.setAttribute("points", points + " " + w + "," + h + " 0," + h);
    fill.setAttribute("fill", "url(#cTrendG)");
    svg.appendChild(fill);
    const line = document.createElementNS(ns, "polyline");
    line.setAttribute("points", points);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "#7c9cff");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(line);

    const t1 = document.createElementNS(ns, "text");
    t1.setAttribute("x", "0"); t1.setAttribute("y", h - 4);
    t1.setAttribute("font-family", "var(--font-mono)");
    t1.setAttribute("font-size", "9");
    t1.setAttribute("fill", "#5b6072");
    t1.textContent = "Q1 → " + Math.round(trend[0].pct * 100) + "%";
    svg.appendChild(t1);

    const t2 = document.createElementNS(ns, "text");
    t2.setAttribute("x", String(w)); t2.setAttribute("y", h - 4);
    t2.setAttribute("text-anchor", "end");
    t2.setAttribute("font-family", "var(--font-mono)");
    t2.setAttribute("font-size", "9");
    t2.setAttribute("fill", "#74d9a2");
    t2.textContent = "now → " + Math.round(trend[trend.length - 1].pct * 100) + "%";
    svg.appendChild(t2);
  }

  function renderLeaderboard(lb) {
    const root = document.getElementById("c-leaderboard");
    if (!root) return;
    root.innerHTML = "";
    lb.forEach(function (item, i) {
      const color = AGENT_COLORS[item.agent] || "#7c9cff";
      const initials = item.agent.replace(/[^a-z0-9-]/gi, "").slice(0, 2);
      const row = document.createElement("div");
      row.className = "lb-row";
      row.innerHTML =
        '<span class="lb-rk">#' + (i + 1) + "</span>" +
        '<span class="lb-n">' +
          '<span class="lb-av" style="background:' + color + '22;color:' + color +
          ';border-color:' + color + '55">' + esc(initials) + "</span>" +
          '<span class="lb-nm" style="color:' + color + '">' + esc(item.agent) + "</span>" +
        "</span>" +
        '<span style="font-family:var(--font-mono);font-size:11px;color:#e6e8ec">' +
          '<b>' + fmtNum(item.prs) + '</b>' +
          '<span style="color:#5b6072;margin-left:3px">prs</span>' +
        '</span>';
      root.appendChild(row);
    });
  }

  // helpers
  function pct(a, b) { return Math.max(8, (a / b) * 100).toFixed(1) + "%"; }
  function fmtNum(n) {
    if (!n) return "0";
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }
  function fmtMoney(n) {
    if (n >= 1_000_000) return "$" + (n / 1_000_000).toFixed(2) + "M";
    if (n >= 1000) return "$" + (n / 1000).toFixed(0) + "k";
    return "$" + n;
  }
  function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }
  function setHTML(id, h) { const e = document.getElementById(id); if (e) e.innerHTML = h; }
  function setStyle(id, k, v) { const e = document.getElementById(id); if (e) e.style[k] = v; }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
