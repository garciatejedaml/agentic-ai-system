// Carson dashboard · autonomy meter + skills radar view

(function () {
  "use strict";

  window.showAutonomyMeter = function () {
    setTab("autonomy");
    const view = document.getElementById("view");
    while (view.firstChild) view.removeChild(view.firstChild);
    view.appendChild(document.getElementById("tpl-autonomy").content.cloneNode(true));
    refresh();
  };

  function setTab(name) {
    document.querySelectorAll(".tabs a").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === name);
    });
  }

  async function refresh() {
    try {
      const [s, sk] = await Promise.all([
        fetch("/api/autonomy/summary").then(function (r) { return r.json(); }),
        fetch("/api/autonomy/skills").then(function (r) { return r.json(); }),
      ]);
      drawGauge(s);
      drawRadar(sk);
      renderSkillRows(sk);
    } catch (e) { console.warn("autonomy refresh failed", e); }
  }

  function drawGauge(s) {
    const svg = document.getElementById("au-gauge-svg");
    const pctEl = document.getElementById("au-gauge-pct");
    const dEl = document.getElementById("au-gauge-delta");
    const lEl = document.getElementById("au-gauge-label");
    if (!svg) return;

    const ns = "http://www.w3.org/2000/svg";
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute("viewBox", "0 0 280 180");

    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML = '<linearGradient id="auGG" x1="0" x2="1" y1="0" y2="0">' +
      '<stop offset="0" stop-color="#7c9cff"/><stop offset="1" stop-color="#c69bff"/></linearGradient>';
    svg.appendChild(defs);

    // background arc — 270deg from bottom-left to bottom-right
    const bg = document.createElementNS(ns, "path");
    bg.setAttribute("d", "M 30 150 A 110 110 0 1 1 250 150");
    bg.setAttribute("fill", "none");
    bg.setAttribute("stroke", "rgba(255,255,255,0.06)");
    bg.setAttribute("stroke-width", "14");
    bg.setAttribute("stroke-linecap", "round");
    svg.appendChild(bg);

    // filled arc — 270deg total length ≈ 518.4 (3/4 of circumference 691)
    const total = 518;
    const filled = total * s.autonomy_pct;
    const fl = document.createElementNS(ns, "path");
    fl.setAttribute("d", "M 30 150 A 110 110 0 1 1 250 150");
    fl.setAttribute("fill", "none");
    fl.setAttribute("stroke", "url(#auGG)");
    fl.setAttribute("stroke-width", "14");
    fl.setAttribute("stroke-linecap", "round");
    fl.setAttribute("stroke-dasharray", filled.toFixed(0) + " 1000");
    svg.appendChild(fl);

    const head = document.createElementNS(ns, "text");
    head.setAttribute("x", "140"); head.setAttribute("y", "30");
    head.setAttribute("text-anchor", "middle");
    head.setAttribute("font-family", "var(--font-mono)");
    head.setAttribute("font-size", "9");
    head.setAttribute("fill", "#5b6072");
    head.setAttribute("letter-spacing", "1.5");
    head.textContent = "AUTONOMY";
    svg.appendChild(head);
    const t0 = document.createElementNS(ns, "text");
    t0.setAttribute("x", "20"); t0.setAttribute("y", "170");
    t0.setAttribute("font-family", "var(--font-mono)");
    t0.setAttribute("font-size", "9");
    t0.setAttribute("fill", "#5b6072");
    t0.textContent = "0%";
    svg.appendChild(t0);
    const t100 = document.createElementNS(ns, "text");
    t100.setAttribute("x", "260"); t100.setAttribute("y", "170");
    t100.setAttribute("text-anchor", "end");
    t100.setAttribute("font-family", "var(--font-mono)");
    t100.setAttribute("font-size", "9");
    t100.setAttribute("fill", "#5b6072");
    t100.textContent = "100%";
    svg.appendChild(t100);

    if (pctEl) pctEl.innerHTML = Math.round(s.autonomy_pct * 100) + "<small>%</small>";
    if (dEl) dEl.innerHTML = '<b>+ ' + s.delta_pp + ' pp</b> vs 3 months ago';
    if (lEl) lEl.textContent = s.headline;
  }

  function drawRadar(skills) {
    const svg = document.getElementById("au-radar-svg");
    if (!svg) return;
    const ns = "http://www.w3.org/2000/svg";
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute("viewBox", "0 0 280 220");

    const cx = 140, cy = 120;
    const R = 90;
    const N = skills.length;

    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML = '<radialGradient id="auRR" cx="50%" cy="50%" r="50%">' +
      '<stop offset="0" stop-color="#7c9cff" stop-opacity=".40"/>' +
      '<stop offset="1" stop-color="#c69bff" stop-opacity=".15"/></radialGradient>';
    svg.appendChild(defs);

    // concentric polygons (rings)
    [1, 0.75, 0.5, 0.25].forEach(function (k) {
      const points = [];
      for (let i = 0; i < N; i++) {
        const angle = (i / N) * 2 * Math.PI - Math.PI / 2;
        const r = R * k;
        points.push((cx + Math.cos(angle) * r).toFixed(1) + "," + (cy + Math.sin(angle) * r).toFixed(1));
      }
      const poly = document.createElementNS(ns, "polygon");
      poly.setAttribute("points", points.join(" "));
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", "rgba(255,255,255,0.05)");
      poly.setAttribute("stroke-width", "0.8");
      svg.appendChild(poly);
    });

    // spokes
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * 2 * Math.PI - Math.PI / 2;
      const x = cx + Math.cos(angle) * R;
      const y = cy + Math.sin(angle) * R;
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", cx); line.setAttribute("y1", cy);
      line.setAttribute("x2", x); line.setAttribute("y2", y);
      line.setAttribute("stroke", "rgba(255,255,255,0.04)");
      line.setAttribute("stroke-width", "0.6");
      svg.appendChild(line);
    }

    // data polygon
    const points = [];
    const verts = [];
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * 2 * Math.PI - Math.PI / 2;
      const r = R * skills[i].success_rate;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      points.push(x.toFixed(1) + "," + y.toFixed(1));
      verts.push({ x, y, label: skills[i].name, idx: i });
    }
    const poly = document.createElementNS(ns, "polygon");
    poly.setAttribute("points", points.join(" "));
    poly.setAttribute("fill", "url(#auRR)");
    poly.setAttribute("stroke", "#7c9cff");
    poly.setAttribute("stroke-width", "1.5");
    svg.appendChild(poly);

    // points on each axis
    verts.forEach(function (v) {
      const c = document.createElementNS(ns, "circle");
      c.setAttribute("cx", v.x); c.setAttribute("cy", v.y);
      c.setAttribute("r", "3"); c.setAttribute("fill", "#7c9cff");
      svg.appendChild(c);
    });

    // labels at outer edge
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * 2 * Math.PI - Math.PI / 2;
      const lr = R + 18;
      const lx = cx + Math.cos(angle) * lr;
      const ly = cy + Math.sin(angle) * lr;
      const t = document.createElementNS(ns, "text");
      t.setAttribute("x", lx); t.setAttribute("y", ly + 4);
      t.setAttribute("text-anchor", lx < cx - 5 ? "end" : (lx > cx + 5 ? "start" : "middle"));
      t.setAttribute("font-family", "var(--font-sans)");
      t.setAttribute("font-size", "11");
      const tier = skills[i].tier;
      t.setAttribute("fill", tier === "strong" ? "#e6e8ec"
                            : tier === "ramping" ? "#b0b6c4"
                            : "#8b91a3");
      t.textContent = skills[i].name;
      svg.appendChild(t);
    }
  }

  function renderSkillRows(skills) {
    const root = document.getElementById("au-skill-rows");
    if (!root) return;
    root.innerHTML = "";
    skills.forEach(function (s) {
      const grad = s.tier === "strong" ? "linear-gradient(90deg,#7c9cff,#74d9a2)"
                  : s.tier === "ramping" ? "linear-gradient(90deg,#7c9cff,#a8bcff)"
                  : "linear-gradient(90deg,#ffb059,#ff7c7c)";
      const row = document.createElement("div");
      row.className = "sk-r";
      row.innerHTML =
        '<span class="sk-nm">' + esc(s.name) + "</span>" +
        '<div class="sk-bar"><div class="sk-fl" style="width:' + (s.success_rate * 100).toFixed(0) +
          '%;background:' + grad + '"></div></div>' +
        '<span class="sk-pct">' + Math.round(s.success_rate * 100) + "% · " + s.jobs + "</span>";
      root.appendChild(row);
    });
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
})();
