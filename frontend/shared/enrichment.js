/* Lead enrichment — the AI research panel, shared by Campaign Management (a
   lead) and Client Administration (a client's company).
   prds/lead-enrichment/build-plan-phase-2.md § 4.4; rulings E7–E19.

   CBMEnrichment.panel(host, { targetType: "lead" | "company", recordId })
     Renders the panel into ``host``: the summary, the findings with Accept /
     Reject, and Run AI research. ``recordId`` is the lead's id, or the
     ENGAGEMENT's id for a client (the server finds the company through it).
     The panel hides itself when the CRM lacks the findings record type, or
     when the feature is switched off and nothing has been found yet.

   CBMEnrichment.startRun({ targetType, ids, engagementId, onStarted })
     Shows the estimate against the month's budget, then starts the run.

   Buttons are never disabled or hidden: a refusal explains itself on click. */
(function () {
  "use strict";
  var API = "/enrichment/api";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function money(v) { return "$" + (Number(v) || 0).toFixed(2); }

  async function call(path, body) {
    var init = { method: body ? "POST" : "GET", credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    var res;
    try { res = await fetch(API + path, init); }
    catch (e) { throw new Error("The server could not be reached — check the connection, then try again."); }
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      var d = data && data.detail;
      throw new Error(typeof d === "string" ? d : ("The request failed (HTTP " + res.status + ")."));
    }
    return data;
  }

  // --- the start dialog ---------------------------------------------------------------------
  var overlay = null;
  function dialog() {
    if (overlay) return overlay;
    overlay = el("div", "enr__overlay"); overlay.hidden = true;
    overlay.setAttribute("role", "dialog"); overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML = '<div class="enr__dialog"><h3 id="enrTitle">Run AI research</h3><div id="enrBody"></div>'
      + '<p class="enr__msg" id="enrMsg" role="alert"></p><div class="enr__buttons">'
      + '<button type="button" class="cbm-button cbm-button--secondary" id="enrCancel">Cancel</button>'
      + '<button type="button" class="cbm-button" id="enrStart">Start</button></div></div>';
    document.body.appendChild(overlay);
    overlay.querySelector("#enrCancel").addEventListener("click", function () { overlay.hidden = true; });
    overlay.addEventListener("keydown", function (ev) { if (ev.key === "Escape") overlay.hidden = true; });
    return overlay;
  }

  async function startRun(opts) {
    var ov = dialog(), body = ov.querySelector("#enrBody"), msg = ov.querySelector("#enrMsg");
    var startBtn = ov.querySelector("#enrStart");
    body.innerHTML = ""; msg.textContent = "";
    var req = { targetType: opts.targetType, ids: opts.ids || [], engagementId: opts.engagementId || "" };
    var est;
    try { est = await call("/estimate", req); }
    catch (e) { body.appendChild(el("p", null, e.message)); ov.hidden = false; startBtn.onclick = function () { msg.textContent = e.message; }; return; }
    var n = est.records;
    body.appendChild(el("p", null, "Research " + n.toLocaleString() + (n === 1 ? " business" : " businesses")
      + " on the web with the AI model. Findings come back for review; on a lead, a verified website or email fills an empty field."));
    body.appendChild(el("p", null, "Estimated cost: " + money(est.estimate) + " (about " + money(est.perRecord) + " a business"
      + (est.measured ? ", the average of recent runs)." : ", an estimate until runs are measured).")));
    body.appendChild(el("p", null, "This month: " + money(est.spent) + " spent, " + money(est.reserved) + " held for runs still going, "
      + money(est.left) + " left of " + money(est.budget) + "."));
    if (est.reason) body.appendChild(el("p", "enr__state enr__state--warn", est.reason));
    else if (!est.fits) body.appendChild(el("p", "enr__state enr__state--warn", "This run would pass the month's budget."));
    ov.hidden = false;
    startBtn.focus();
    startBtn.onclick = async function () {
      if (est.reason) { msg.textContent = est.reason; return; }
      var done = window.CBMBusy ? window.CBMBusy.start(startBtn) : function () {};
      try {
        var r = await call("/start", Object.assign({}, req, { estimate: est.estimate }));
        ov.hidden = true;
        if (opts.onStarted) opts.onStarted(r);
      } catch (e) { msg.textContent = e.message; }
      finally { done(); }
    };
  }

  // --- the panel ----------------------------------------------------------------------------
  function describe(f) {
    if (f.kind === "Person") return [f.personName, f.personTitle, f.personEmail].filter(Boolean).join(" · ");
    return f.proposedValue || "";
  }
  function label(f) {
    if (f.kind === "Person") return "Person";
    var names = { website: "Website", email: "Email", emailAddress: "Email", phone: "Phone", phoneNumber: "Phone", industry: "Industry" };
    return names[f.targetField] || f.targetField || f.kind;
  }

  function panel(host, opts) {
    var root = el("section", "enr"); root.hidden = true;
    host.appendChild(root);
    var timer = null;
    var path = opts.targetType === "lead" ? "/lead/" + encodeURIComponent(opts.recordId)
                                          : "/engagement/" + encodeURIComponent(opts.recordId);

    async function load() {
      clearTimeout(timer);
      var data;
      try { data = await call(path); }
      catch (e) { root.hidden = false; root.innerHTML = ""; root.appendChild(el("p", "enr__state enr__state--warn", e.message)); return; }
      var any = data.summary || (data.findings || []).length;
      if (!data.available || (!data.ready && !any && !data.pending)) { root.hidden = true; return; }
      render(data);
      if (data.pending) timer = setTimeout(load, 10000);
    }

    function render(data) {
      root.hidden = false; root.innerHTML = "";
      var head = el("div", "enr__head");
      head.appendChild(el("h4", "enr__title", opts.targetType === "lead" ? "AI research" : "Business picture"));
      var run = el("button", "cbm-button cbm-button--secondary", "Run AI research"); run.type = "button";
      run.addEventListener("click", function () {
        if (!data.ready) { state.textContent = data.reason; state.className = "enr__state enr__state--warn"; return; }
        startRun({ targetType: opts.targetType,
                   ids: opts.targetType === "lead" ? [opts.recordId] : [],
                   engagementId: opts.targetType === "lead" ? "" : opts.recordId,
                   onStarted: function () { load(); } });
      });
      head.appendChild(run);
      var state = el("span", "enr__state");
      if (data.pending) state.textContent = "Researching… this usually takes one to three minutes.";
      else if (data.last) state.textContent = "Last researched " + (data.last.at || "").slice(0, 16).replace("T", " ") + " UTC"
        + (data.last.status === "failed" ? " — failed: " + (data.last.error || "unknown reason") : "") + " · cost " + money(data.last.cost);
      else if (!data.ready) state.textContent = data.reason;
      head.appendChild(state);
      root.appendChild(head);
      if (data.company && data.company.name) root.appendChild(el("p", "enr__state", "Company researched: " + data.company.name));

      if (data.summary) {
        var s = el("div", "enr__summary");
        s.appendChild(el("p", null, data.summary.summary || ""));
        if (data.summary.sourceUrl) {
          var a = el("a", null, "Source"); a.href = data.summary.sourceUrl; a.target = "_blank"; a.rel = "noopener noreferrer";
          s.appendChild(a);
        }
        root.appendChild(s);
      }
      var rows = data.findings || [];
      if (!rows.length) { root.appendChild(el("p", "enr__empty", data.pending ? "No findings yet." : "No findings.")); return; }
      var tbl = el("table", "enr__table"), thead = el("thead"), tr = el("tr");
      ["What", "Found", "Confidence", "Source", "Status", ""].forEach(function (h) { tr.appendChild(el("th", null, h)); });
      thead.appendChild(tr); tbl.appendChild(thead);
      var tb = el("tbody");
      rows.forEach(function (f) {
        var r = el("tr");
        r.appendChild(el("td", null, label(f)));
        var v = el("td", "enr__value", describe(f));
        if (f.currentValue) v.title = "The record held " + f.currentValue + " when this was found.";
        r.appendChild(v);
        var c = el("td"); var chip = el("span", "enr__chip enr__chip--" + (f.confidence || ""), f.confidence || "—");
        chip.title = f.factsMatched ? ("Facts that agreed:\n" + f.factsMatched) : "";
        c.appendChild(chip); r.appendChild(c);
        var src = el("td");
        if (f.sourceUrl) { var l = el("a", null, "Open"); l.href = f.sourceUrl; l.target = "_blank"; l.rel = "noopener noreferrer"; src.appendChild(l); }
        else src.textContent = "—";
        r.appendChild(src);
        r.appendChild(el("td", null, f.findingStatus + (f.decidedBy && f.findingStatus !== "Proposed" ? " · " + f.decidedBy : "")));
        var acts = el("td", "enr__acts");
        if (f.findingStatus === "Proposed") {
          [["Accept", "Accepted"], ["Reject", "Rejected"]].forEach(function (pair) {
            var b = el("button", "cbm-button cbm-button--secondary", pair[0]); b.type = "button";
            b.addEventListener("click", async function () {
              var done = window.CBMBusy ? window.CBMBusy.start(b) : function () {};
              try {
                await call("/decide", { targetType: opts.targetType, recordId: opts.recordId, findingId: f.id, decision: pair[1] });
                if (opts.onChange) opts.onChange();
                load();
              } catch (e) { state.textContent = e.message; state.className = "enr__state enr__state--warn"; }
              finally { done(); }
            });
            acts.appendChild(b);
          });
        }
        r.appendChild(acts);
        tb.appendChild(r);
      });
      tbl.appendChild(tb); root.appendChild(tbl);
    }

    load();
    return { reload: load, stop: function () { clearTimeout(timer); } };
  }

  window.CBMEnrichment = { panel: panel, startRun: startRun };
})();
