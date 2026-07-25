/* CBMCharts — hand-rolled, dependency-free renderers for the analytics panels
 * (Analytics Phase A; prds/analytics-app-plan.md §11 decision A). Four result
 * shapes → four renderers: stat / series / breakdown / rows. SVG for line/area
 * and pie; HTML for stat, bars, and tables. Theme via the CBM palette below.
 *
 * Public API (attached to window.CBMCharts):
 *   renderPanel(el, panel, ctx)  — dispatch on panel.viz + result.shape
 * where panel = { viz, title, result: { shape, data, error, cached, computedAt } }
 * and ctx = { crmUrl }  (for record deep links in tables).
 */
(function () {
  "use strict";

  var PALETTE = [
    "#00205B", "#B58113", "#2E7D8A", "#6A8532",
    "#8E5AA0", "#C0603A", "#3E7CB1", "#A3243B",
  ];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs) if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
    return e;
  }
  function fmtNum(n) {
    if (n == null || isNaN(n)) return "—";
    return Number(n).toLocaleString();
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // --- stat ------------------------------------------------------------------
  function renderStat(host, data) {
    var wrap = el("div", "anc-stat");
    var v = data && data.value != null ? data.value : null;
    wrap.appendChild(el("div", "anc-stat__value", fmtNum(v)));
    if (data && data.unit) wrap.appendChild(el("div", "anc-stat__unit", data.unit));
    if (data && data.prior != null && v != null) {
      var delta = v - data.prior;
      var chip = el("div", "anc-stat__delta " + (delta >= 0 ? "is-up" : "is-down"));
      chip.textContent = (delta >= 0 ? "▲ " : "▼ ") + fmtNum(Math.abs(delta));
      wrap.appendChild(chip);
    }
    host.appendChild(wrap);
  }

  // --- series (line / area) --------------------------------------------------
  function renderSeries(host, data, viz) {
    var pts = (data && data.points) || [];
    if (!pts.length) {
      host.appendChild(el("p", "anc-empty", "No data in this range."));
      return;
    }
    var W = 640, H = 240, padL = 44, padR = 16, padT = 16, padB = 34;
    var innerW = W - padL - padR, innerH = H - padT - padB;
    var max = Math.max.apply(null, pts.map(function (p) { return p.value; }));
    max = max <= 0 ? 1 : max;
    var stepX = pts.length > 1 ? innerW / (pts.length - 1) : 0;
    function x(i) { return padL + stepX * i; }
    function y(val) { return padT + innerH - (val / max) * innerH; }

    var svg = svgEl("svg", {
      viewBox: "0 0 " + W + " " + H, class: "anc-svg",
      preserveAspectRatio: "xMidYMid meet", role: "img",
    });
    // y baseline + max gridline
    [0, max].forEach(function (val) {
      svg.appendChild(svgEl("line", {
        x1: padL, x2: W - padR, y1: y(val), y2: y(val), class: "anc-grid",
      }));
      svg.appendChild(svgEl("text", {
        x: padL - 8, y: y(val) + 4, class: "anc-axis anc-axis--y",
      })).textContent = fmtNum(val);
    });

    var coords = pts.map(function (p, i) { return x(i) + "," + y(p.value); });
    if (viz === "area") {
      var poly = "M" + padL + "," + y(0) + " L" + coords.join(" L") +
        " L" + x(pts.length - 1) + "," + y(0) + " Z";
      svg.appendChild(svgEl("path", { d: poly, class: "anc-area" }));
    }
    svg.appendChild(svgEl("polyline", { points: coords.join(" "), class: "anc-line" }));
    pts.forEach(function (p, i) {
      var dot = svgEl("circle", { cx: x(i), cy: y(p.value), r: 3, class: "anc-dot" });
      var t = svgEl("title", {});
      t.textContent = p.label + ": " + fmtNum(p.value);
      dot.appendChild(t);
      svg.appendChild(dot);
    });
    // sparse x labels (first, middle, last)
    var idxs = pts.length <= 3 ? pts.map(function (_, i) { return i; })
      : [0, Math.floor((pts.length - 1) / 2), pts.length - 1];
    idxs.forEach(function (i) {
      // Anchor edge labels inward so the first/last don't clip past the viewBox
      // (inline style beats the class's text-anchor).
      var anchor = i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle";
      var tx = svgEl("text", {
        x: x(i), y: H - 12, class: "anc-axis anc-axis--x",
        style: "text-anchor:" + anchor,
      });
      tx.textContent = pts[i].label;
      svg.appendChild(tx);
    });
    host.appendChild(svg);
  }

  // --- breakdown (bar / pie) -------------------------------------------------
  function renderBars(host, items) {
    var max = Math.max.apply(null, items.map(function (i) { return i.value; }));
    max = max <= 0 ? 1 : max;
    var list = el("div", "anc-bars");
    items.forEach(function (it, i) {
      var row = el("div", "anc-bar");
      row.appendChild(el("span", "anc-bar__label", it.label));
      var track = el("span", "anc-bar__track");
      var fill = el("span", "anc-bar__fill");
      fill.style.width = (it.value / max) * 100 + "%";
      fill.style.background = PALETTE[i % PALETTE.length];
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "anc-bar__val", fmtNum(it.value)));
      list.appendChild(row);
    });
    host.appendChild(list);
  }

  function renderPie(host, items) {
    var total = items.reduce(function (s, i) { return s + (i.value || 0); }, 0);
    if (total <= 0) { host.appendChild(el("p", "anc-empty", "No data.")); return; }
    var R = 80, C = 100, sw = 34, circ = 2 * Math.PI * R;
    var svg = svgEl("svg", {
      viewBox: "0 0 200 200", class: "anc-svg anc-svg--pie",
      preserveAspectRatio: "xMidYMid meet", role: "img",
    });
    var offset = 0;
    items.forEach(function (it, i) {
      var frac = it.value / total;
      var seg = svgEl("circle", {
        cx: C, cy: C, r: R, fill: "none",
        stroke: PALETTE[i % PALETTE.length], "stroke-width": sw,
        "stroke-dasharray": (frac * circ) + " " + circ,
        "stroke-dashoffset": -offset,
        transform: "rotate(-90 " + C + " " + C + ")",
      });
      var t = svgEl("title", {});
      t.textContent = it.label + ": " + fmtNum(it.value) +
        " (" + Math.round(frac * 100) + "%)";
      seg.appendChild(t);
      svg.appendChild(seg);
      offset += frac * circ;
    });
    var wrap = el("div", "anc-pie");
    wrap.appendChild(svg);
    var legend = el("div", "anc-legend");
    items.forEach(function (it, i) {
      var li = el("div", "anc-legend__item");
      var dot = el("span", "anc-legend__dot");
      dot.style.background = PALETTE[i % PALETTE.length];
      li.appendChild(dot);
      li.appendChild(el("span", "anc-legend__label", it.label));
      li.appendChild(el("span", "anc-legend__val", fmtNum(it.value)));
      legend.appendChild(li);
    });
    wrap.appendChild(legend);
    host.appendChild(wrap);
  }

  function renderBreakdown(host, data, viz) {
    var items = (data && data.items) || [];
    if (!items.length) { host.appendChild(el("p", "anc-empty", "No data.")); return; }
    if (viz === "pie") renderPie(host, items);
    else renderBars(host, items);
  }

  // --- rows (table) ----------------------------------------------------------
  function recordHref(ctx, entity, id) {
    if (!ctx || !ctx.crmUrl || !entity || !id) return null;
    return ctx.crmUrl.replace(/\/+$/, "") + "/#" + entity + "/view/" + id;
  }

  function renderTable(host, data, ctx) {
    var cols = (data && data.columns) || [];
    var rows = (data && data.rows) || [];
    if (!rows.length) { host.appendChild(el("p", "anc-empty", "Nothing to show.")); return; }
    var table = el("table", "anc-table");
    var thead = el("thead"), htr = el("tr");
    cols.forEach(function (c) {
      var th = el("th", c.align === "right" ? "is-right" : null, c.label);
      htr.appendChild(th);
    });
    thead.appendChild(htr);
    table.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (r) {
      var tr = el("tr");
      cols.forEach(function (c) {
        var td = el("td", c.align === "right" ? "is-right" : null);
        var val = r[c.key];
        var href = c.link === "record" ? recordHref(ctx, r.entity, r.recordId) : null;
        if (href) {
          var a = el("a", "anc-link", val == null ? "" : String(val));
          a.href = href; a.target = "_blank"; a.rel = "noopener";
          td.appendChild(a);
        } else {
          td.textContent = val == null ? "—" : String(val);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
  }

  // --- dispatch --------------------------------------------------------------
  function renderPanel(host, panel, ctx) {
    clear(host);
    var res = panel.result || {};
    if (res.error) {
      host.appendChild(el("p", "anc-err", res.error));
      return;
    }
    var shape = res.shape, data = res.data, viz = panel.viz;
    if (shape === "scalar") renderStat(host, data);
    else if (shape === "series") renderSeries(host, data, viz);
    else if (shape === "breakdown") renderBreakdown(host, data, viz);
    else if (shape === "rows") renderTable(host, data, ctx);
    else host.appendChild(el("p", "anc-err", "Unsupported panel type."));
  }

  window.CBMCharts = { renderPanel: renderPanel, PALETTE: PALETTE };
})();
