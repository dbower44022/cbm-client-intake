/* Campaign Management — the staff app (prds/prospect-marketing/build-plan.md § 3.8).
 *
 * One shared IIFE serves the grid page (/campaigns/) and the record page
 * (/campaigns/record/{id}, its own stable browser tab with a single-owner lock).
 * Every action button stays visible and clickable; validation happens on click
 * and names the missing input or grant. No page width cap.
 */
(function () {
  "use strict";
  var segs = location.pathname.split("/");
  var RECORD_ID = segs[2] === "record" ? decodeURIComponent(segs[3] || "") : null;
  var API = "/campaigns/api";
  var HOST = (document.querySelector('meta[name="cbm-org"]') || {}).content || "";

  var state = {
    session: null, fields: null,
    campaigns: [], sort: { key: "createdAt", dir: -1 },
    prospects: [], psort: { key: "createdAt", dir: -1 },
    record: null, links: null, responses: null,
    section: "campaigns",
  };

  function $(id) { return document.getElementById(id); }
  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }
  function text(el, v) { if (el) el.textContent = v == null ? "" : String(v); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function el(tag, cls, content) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (content != null) e.textContent = content;
    return e;
  }
  function fmtDate(v) {
    if (!v) return "—";
    var d = new Date(v.length === 10 ? v + "T00:00:00" : v.replace(" ", "T") + (v.length === 19 ? "Z" : ""));
    if (isNaN(d.getTime())) return v;
    return v.length === 10 ? d.toLocaleDateString() : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  function money(v, cur) { if (v == null || v === "") return "—"; return Number(v).toFixed(2) + " " + (cur || ""); }

  function notice(msg, kind) {
    var n = $("notice");
    if (!n) return;
    if (!msg) { hide(n); return; }
    n.textContent = msg; n.className = "cm__notice" + (kind ? " cm__notice--" + kind : ""); show(n);
  }

  async function api(path, opts) {
    opts = opts || {};
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, 60000);
    var init = { method: opts.method || "GET", headers: { Accept: "application/json" }, signal: ctrl.signal, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    var res;
    try { res = await fetch(API + path, init); } finally { clearTimeout(timer); }
    if (res.status === 401) { location.assign("/?next=" + encodeURIComponent("/campaigns/")); throw Object.assign(new Error("Signed out"), { status: 401 }); }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok) {
      var err = new Error((data && data.detail) || ("Request failed (" + res.status + ")"));
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }

  // --- the single-owner lock for a record tab (the sessions pattern) ------------
  function acquireRecordLock(key) {
    return new Promise(function (resolve) {
      var BC = window.BroadcastChannel;
      if (!BC) { resolve(true); return; }
      var ch;
      try { ch = new BC("cbm-record-lock"); } catch (_) { resolve(true); return; }
      var me = { openedAt: Date.now(), tabId: Math.random().toString(36).slice(2) + "-" + Date.now() };
      var decided = false, owner = true;
      function isOlder(a, b) { return a.openedAt < b.openedAt || (a.openedAt === b.openedAt && a.tabId < b.tabId); }
      ch.onmessage = function (ev) {
        var m = ev.data || {};
        if (!m || m.key !== key || m.tabId === me.tabId) return;
        if (m.type === "hello") { try { ch.postMessage({ type: "present", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {} }
        if ((m.type === "hello" || m.type === "present") && isOlder(m, me) && !decided) {
          // Named in the console so a false block can be traced to whatever answered.
          try { console.info("[campaigns] record lock yielded to an older tab", m); } catch (_) {}
          decided = true; owner = false; resolve(false);
        }
        if (m.type === "bye" && m.owner && !owner) location.reload();
      };
      try { ch.postMessage({ type: "hello", key: key, openedAt: me.openedAt, tabId: me.tabId }); } catch (_) {}
      window.__cbmRecordLock = ch;
      window.addEventListener("pagehide", function () { try { ch.postMessage({ type: "bye", key: key, tabId: me.tabId, owner: owner }); } catch (_) {} });
      setTimeout(function () { if (!decided) { decided = true; resolve(true); } }, 350);
    });
  }

  // --- modal ------------------------------------------------------------------------
  var modal = { onSave: null };
  function openModal(title, bodyNode, onSave, saveLabel) {
    text($("modalTitle"), title);
    var body = $("modalBody"); body.innerHTML = ""; body.appendChild(bodyNode);
    text($("modalMsg"), ""); $("modalMsg").className = "cm__modal-msg";
    modal.onSave = onSave;
    text($("modalSave"), saveLabel || "Save");
    $("modalSave").hidden = !onSave;
    show($("modal"));
  }
  function closeModal() { hide($("modal")); modal.onSave = null; }
  function modalMsg(msg, kind) { var m = $("modalMsg"); m.textContent = msg || ""; m.className = "cm__modal-msg" + (kind ? " cm__modal-msg--" + kind : ""); }
  $("modalClose").addEventListener("click", closeModal);
  $("modalCancel").addEventListener("click", closeModal);
  $("modalSave").addEventListener("click", async function () {
    if (!modal.onSave) return;
    try { await modal.onSave(); } catch (e) { modalMsg(e.message, "error"); }
  });

  // --- shared form builder for a campaign ----------------------------------------------
  function statusClass(s) {
    var k = (s || "Draft").toLowerCase();
    if (k.indexOf("awaiting") === 0) k = "awaiting"; else if (k.indexOf("signed") === 0) k = "signed";
    return "cm__badge cm__badge--" + k.replace(/[^a-z]/g, "");
  }

  function pickList(name, label, options, chosenIds, hint) {
    var wrap = el("div", "cm__linkpick");
    var h = el("h4", null, label); wrap.appendChild(h);
    if (hint) wrap.appendChild(el("p", "cm__hint", hint));
    if (options === null) { wrap.appendChild(el("p", "cm__readonly", "Your CRM role cannot list these, so they are read-only here.")); return wrap; }
    var filter = el("input"); filter.type = "search"; filter.placeholder = "Filter…"; filter.setAttribute("aria-label", "Filter " + label);
    wrap.appendChild(filter);
    var list = el("div", "cm__linkpick-list");
    var chosen = {}; (chosenIds || []).forEach(function (i) { chosen[i] = true; });
    function render(q) {
      list.innerHTML = "";
      q = (q || "").toLowerCase();
      options.forEach(function (o) {
        if (q && o.name.toLowerCase().indexOf(q) < 0 && !chosen[o.id]) return;
        var lab = el("label"); var cb = el("input"); cb.type = "checkbox"; cb.value = o.id; cb.checked = !!chosen[o.id];
        cb.setAttribute("data-pick", name);
        cb.addEventListener("change", function () { chosen[o.id] = cb.checked; });
        lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + o.name)); list.appendChild(lab);
      });
      if (!options.length) list.appendChild(el("span", "cm__readonly", "None to pick."));
    }
    filter.addEventListener("input", function () { render(filter.value); });
    render("");
    wrap.appendChild(list);
    wrap.getChosen = function () { return Object.keys(chosen).filter(function (k) { return chosen[k]; }); };
    return wrap;
  }

  function campaignForm(record, chosenPartners, chosenEvents, chosenTeams) {
    var f = state.fields, s = state.session;
    var root = el("div", "cm__plan");
    var groups = {};
    f.fields.forEach(function (spec) {
      if (!groups[spec.group]) {
        var g = el("div", "cm__group"); g.appendChild(el("h4", null, spec.group));
        var grid = el("div", "cm__fields"); g.appendChild(grid); groups[spec.group] = grid; root.appendChild(g);
      }
      var field = el("div", "cm__field" + (spec.type === "wysiwyg" ? " cm__field--wide" : "") + (spec.kinds ? " cm__field--kinds" : ""));
      if (spec.kinds) field.setAttribute("data-kinds", spec.kinds.join("|"));
      var lab = el("label", null, spec.label + (spec.required ? " *" : "")); lab.htmlFor = "f_" + spec.name; field.appendChild(lab);
      var input;
      var value = record ? record[spec.name] : "";
      if (spec.type === "enum") {
        input = el("select"); input.appendChild(el("option", null, "—")).value = "";
        (f.options[spec.name] || []).forEach(function (o) {
          var opt = el("option", null, o); opt.value = o;
          if (spec.name === "campaignKind" && f.kindsBuilt.indexOf(o) < 0) { opt.disabled = true; opt.textContent = o + " (a later phase)"; }
          input.appendChild(opt);
        });
        input.value = value || "";
      } else if (spec.type === "date") { input = el("input"); input.type = "date"; input.value = value || "";
      } else if (spec.type === "wysiwyg") { input = el("textarea"); input.rows = 6; input.value = value || "";
      } else if (spec.type === "textarea") { input = el("textarea"); input.rows = 4; input.value = value || "";
        (function (ta) {
          var counter = el("span", "cm__help");
          function count() { var p = smsParts(ta.value); counter.textContent = p.characters + " characters · " + p.parts + " message part" + (p.parts === 1 ? "" : "s") + " (" + p.encoding + ")" + (/\bstop\b/i.test(ta.value) ? "" : " · must include the word STOP"); }
          ta.addEventListener("input", count); setTimeout(count, 0); ta._counter = counter;
        })(input);
      } else { input = el("input"); input.type = "text"; input.value = value || ""; }
      input.id = "f_" + spec.name; input.setAttribute("data-field", spec.name);
      field.appendChild(input);
      if (input._counter) field.appendChild(input._counter);
      if (spec.help) field.appendChild(el("span", "cm__help", spec.help));
      groups[spec.group].appendChild(field);
    });
    var rel = el("div", "cm__group"); rel.appendChild(el("h4", null, "Partners and events"));
    var partners = pickList("partners", "Partners (CM-2)", f.partnerOptions, chosenPartners, "The partners this campaign is for. A client who arrives through it is credited to every one.");
    var events = pickList("events", "Events (CM-6)", f.eventOptions, chosenEvents, "The events this campaign advertises.");
    rel.appendChild(partners); rel.appendChild(events); root.appendChild(rel);
    // Who calls (ruling 36): a call campaign's own teams. None named means the
    // Marketing Admin Team; naming the Mentor Team opens its calls to mentors.
    var callers = el("div", "cm__group cm__field--kinds"); callers.setAttribute("data-kinds", "Call");
    callers.appendChild(el("h4", null, "Who calls"));
    var teams = pickList("teams", "Teams that call", f.teamOptions, chosenTeams || [], "The members of these teams see this campaign's calls on the Calls page. Name none and it is the Marketing Admin Team's.");
    callers.appendChild(teams); root.appendChild(callers);
    var kindSel = root.querySelector('[data-field="campaignKind"]');
    function showKinds() {
      var kind = kindSel ? kindSel.value : "";
      Array.prototype.forEach.call(root.querySelectorAll(".cm__field--kinds"), function (fld) {
        var kinds = (fld.getAttribute("data-kinds") || "").split("|");
        fld.hidden = kinds.indexOf(kind) < 0;
      });
    }
    if (kindSel) kindSel.addEventListener("change", showKinds);
    showKinds();
    // The shared editor: CBMRichText.create(initialHtml) returns a host element
    // whose value is read through host._cbmRichText.getValue(); null when Jodit
    // is not loaded, in which case the textarea stays.
    var notes = root.querySelector('[data-field="description"]');
    var editorHost = null;
    if (notes && window.CBMRichText && CBMRichText.create) {
      try { editorHost = CBMRichText.create(notes.value || "", { height: 220 }); } catch (_) { editorHost = null; }
      if (editorHost) { notes.hidden = true; notes.parentNode.insertBefore(editorHost, notes.nextSibling); }
    }
    root.collect = function () {
      var changes = {};
      Array.prototype.forEach.call(root.querySelectorAll("[data-field]"), function (inp) {
        var name = inp.getAttribute("data-field");
        var fld = inp.closest(".cm__field");
        if (fld && fld.hidden) { changes[name] = null; return; }
        if (name === "description") {
          changes[name] = editorHost && editorHost._cbmRichText ? editorHost._cbmRichText.getValue() : inp.value;
          return;
        }
        changes[name] = inp.value;
      });
      var isCall = kindSel && kindSel.value === "Call";
      return { changes: changes, partnerIds: partners.getChosen ? partners.getChosen() : null, eventIds: events.getChosen ? events.getChosen() : null,
               teamIds: isCall && teams.getChosen ? teams.getChosen() : null };
    };
    return root;
  }

  // --- campaigns grid -------------------------------------------------------------------
  function fillSelect(sel, options, keepFirst) {
    var first = keepFirst ? Array.prototype.slice.call(sel.options, 0, keepFirst) : [];
    sel.innerHTML = ""; first.forEach(function (o) { sel.appendChild(o); });
    (options || []).forEach(function (o) { var opt = el("option", null, o); opt.value = o; sel.appendChild(opt); });
  }

  async function loadCampaigns() {
    try {
      var res = await api("/campaigns");
      state.campaigns = res.campaigns || [];
      renderCampaigns();
    } catch (e) { notice(e.message, "error"); }
  }

  function renderCampaigns() {
    var q = ($("campaignSearch").value || "").toLowerCase();
    var st = $("statusFilter").value, kind = $("kindFilter").value;
    var rows = state.campaigns.filter(function (c) {
      if (st && c.campaignStatus !== st) return false;
      if (kind && c.campaignKind !== kind) return false;
      if (!q) return true;
      var hay = [c.name, c.campaignKind, c.campaignStatus, c.assignedUserName, (c.partners || []).map(function (p) { return p.name; }).join(" ")].join(" ").toLowerCase();
      return hay.indexOf(q) >= 0;
    });
    var k = state.sort.key, dir = state.sort.dir;
    rows.sort(function (a, b) {
      var x = a[k], y = b[k];
      if (x == null || x === "") return 1; if (y == null || y === "") return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
      return String(x).localeCompare(String(y), undefined, { numeric: true }) * dir;
    });
    var body = $("campaignRows"); body.innerHTML = "";
    rows.forEach(function (c) {
      var tr = el("tr");
      var nameTd = el("td"); var a = el("a", "cm__link", c.name || "(unnamed)");
      a.href = "/campaigns/record/" + encodeURIComponent(c.id);
      a.addEventListener("click", function (ev) {
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1) return;
        ev.preventDefault(); window.open(a.href, "cbm-rec-campaigns-" + c.id);
      });
      nameTd.appendChild(a); tr.appendChild(nameTd);
      tr.appendChild(el("td", null, c.campaignKind || "—"));
      var stTd = el("td"); stTd.appendChild(el("span", statusClass(c.campaignStatus), c.campaignStatus || "Draft")); tr.appendChild(stTd);
      tr.appendChild(el("td", null, c.assignedUserName || "—"));
      tr.appendChild(el("td", null, c.partners === null || c.partners === undefined ? "—" : (c.partners.length ? c.partners.map(function (p) { return p.name; }).join(", ") : "none")));
      tr.appendChild(el("td", null, (c.startDate || c.endDate) ? (fmtDate(c.startDate) + " – " + fmtDate(c.endDate)) : "—"));
      tr.appendChild(el("td", "num", c.links)); tr.appendChild(el("td", "num", c.visits)); tr.appendChild(el("td", "num", c.submissions));
      body.appendChild(tr);
    });
    text($("campaignCount"), rows.length + " of " + state.campaigns.length);
    $("campaignsEmpty").hidden = state.campaigns.length > 0;
  }

  // --- new / edit campaign ----------------------------------------------------------------
  async function ensureFields() {
    if (!state.fields) state.fields = await api("/fields");
    return state.fields;
  }

  async function openNewCampaign() {
    try { await ensureFields(); } catch (e) { notice(e.message, "error"); return; }
    var form = campaignForm(null, [], []);
    openModal("New campaign", form, async function () {
      var data = form.collect();
      if (!data.changes.name) { modalMsg("Give the campaign a name.", "error"); return; }
      if (!data.changes.campaignKind) { modalMsg("Choose the campaign's kind.", "error"); return; }
      var res = await api("/campaigns", { method: "POST", body: data });
      closeModal();
      notice("Created \"" + res.campaign.name + "\".", "ok");
      window.open("/campaigns/record/" + encodeURIComponent(res.campaign.id), "cbm-rec-campaigns-" + res.campaign.id);
      loadCampaigns();
    }, "Create");
  }

  async function openEditCampaign() {
    var rec = state.record; if (!rec) return;
    try { await ensureFields(); } catch (e) { notice(e.message, "error"); return; }
    var form = campaignForm(rec.campaign, (rec.partners || []).map(function (p) { return p.id; }), (rec.events || []).map(function (p) { return p.id; }), rec.callerTeamIds || []);
    openModal("Edit campaign", form, async function () {
      var data = form.collect();
      if (!data.changes.name) { modalMsg("A campaign needs a name.", "error"); return; }
      var changes = {};
      Object.keys(data.changes).forEach(function (k) { if ((data.changes[k] || "") !== (rec.campaign[k] || "")) changes[k] = data.changes[k]; });
      if (Object.keys(changes).length) await api("/campaigns/" + encodeURIComponent(rec.campaign.id), { method: "PUT", body: { changes: changes } });
      var rel = {};
      if (data.partnerIds !== null) rel.partnerIds = data.partnerIds;
      if (data.eventIds !== null) rel.eventIds = data.eventIds;
      if (Object.keys(rel).length) await api("/campaigns/" + encodeURIComponent(rec.campaign.id) + "/relations", { method: "PUT", body: rel });
      if (data.teamIds !== null && rec.callerTeamIds !== null) {
        var before = (rec.callerTeamIds || []).slice().sort().join(","), after = data.teamIds.slice().sort().join(",");
        if (before !== after) await api("/campaigns/" + encodeURIComponent(rec.campaign.id) + "/teams", { method: "PUT", body: { teamIds: data.teamIds } });
      }
      closeModal(); notice("Saved.", "ok"); loadRecord();
    });
  }

  // --- the record page ------------------------------------------------------------------------
  async function loadRecord() {
    try {
      state.record = await api("/campaigns/" + encodeURIComponent(RECORD_ID));
      renderRecord();
    } catch (e) {
      if (e.status === 404) notice("This campaign was not found.", "error"); else notice(e.message, "error");
    }
  }

  function chips(ul, items, none) {
    ul.innerHTML = "";
    if (items === null || items === undefined) { ul.appendChild(el("li", "cm__chips--none", "—")); return; }
    if (!items.length) { ul.appendChild(el("li", "cm__chips--none", none)); return; }
    items.forEach(function (i) { ul.appendChild(el("li", null, i.name)); });
  }

  function tiles(host, pairs) {
    host.innerHTML = "";
    pairs.forEach(function (p) {
      var t = el("div", "cm__tile"); t.appendChild(el("div", "cm__tile-value", p[1] == null ? "—" : p[1])); t.appendChild(el("div", "cm__tile-label", p[0])); host.appendChild(t);
    });
  }

  function renderRecord() {
    var rec = state.record, c = rec.campaign;
    document.title = HOST + " — " + (c.name || "Campaign");
    text($("recName"), c.name); text($("recKind"), c.campaignKind || "");
    var st = $("recStatus"); st.textContent = c.campaignStatus || "Draft"; st.className = statusClass(c.campaignStatus);
    var facts = $("recFacts"); facts.innerHTML = "";
    var pairs = [
      ["Kind", c.campaignKind], ["Platform", c.platform], ["Status", c.campaignStatus], ["Owner", c.assignedUserName],
      ["Window", (c.startDate || c.endDate) ? fmtDate(c.startDate) + " – " + fmtDate(c.endDate) : null],
      ["Mail vendor template", c.vendorTemplateId], ["Postcard size", c.postcardSize],
      ["Selection", c.selectionSummary],
      [c.campaignKind === "Call" ? "People on the list" : c.campaignKind === "Postcard" ? "Pieces signed off" : "People signed off", c.pieceCount], ["Estimated cost", c.estimatedCost != null ? money(c.estimatedCost, c.estimatedCostCurrency) : null],
      ["Signed off by", c.signedOffByName], ["Signed off at", c.signedOffAt ? fmtDate(c.signedOffAt) : null],
      ["Run started", c.runStartedAt ? fmtDate(c.runStartedAt) : null], ["Run completed", c.runCompletedAt ? fmtDate(c.runCompletedAt) : null],
      ["Created", fmtDate(c.createdAt)],
    ];
    pairs.forEach(function (p) {
      // The sign-off record (ruling 13) and the run belong to every kind that
      // selects an audience; the mail-vendor facts to the postcard alone.
      var selecting = ["Postcard", "Call", "SMS", "Email"].indexOf(c.campaignKind) >= 0;
      if (c.campaignKind !== "Postcard" && ["Mail vendor template", "Postcard size", "Estimated cost"].indexOf(p[0]) >= 0) return;
      if (!selecting && ["Selection", "Pieces signed off", "People signed off", "People on the list", "Signed off by", "Signed off at", "Run started", "Run completed"].indexOf(p[0]) >= 0) return;
      if (c.campaignKind !== "Social media" && p[0] === "Platform") return;
      facts.appendChild(el("dt", null, p[0])); facts.appendChild(el("dd", null, p[1] == null || p[1] === "" ? "—" : p[1]));
    });
    chips($("recPartners"), rec.partners, "No partner named."); chips($("recEvents"), rec.events, "No event linked.");
    var notes = $("recNotes");
    notes.innerHTML = window.CBMRichText && CBMRichText.sanitizeHtml ? CBMRichText.sanitizeHtml(c.description || "") : esc(c.description || "");
    var acts = $("statusActions"); acts.innerHTML = "";
    (rec.manualMoves || []).forEach(function (s) {
      var b = el("button", "cbm-button cbm-button--secondary", "Move to " + s); b.type = "button";
      b.addEventListener("click", async function () {
        try { await api("/campaigns/" + encodeURIComponent(c.id) + "/status", { method: "POST", body: { status: s } }); notice("Moved to " + s + ".", "ok"); loadRecord(); }
        catch (e) { notice(e.message, "error"); }
      });
      acts.appendChild(b);
    });
    var pc = $("postcardCard");
    if (c.campaignKind === "Postcard") {
      show(pc);
      var sum = rec.touchSummary || {};
      tiles($("touchTiles"), [["Planned", sum.planned], ["Sent", sum.sent], ["Delivered", sum.delivered], ["Returned", sum.returned], ["Scanned", sum.scanned],
        ["Est. cost", money(rec.estimatedCost, rec.currency)]]);
      var rule = rec.rule || {};
      var statuses = rule.statuses || ["Unqualified", "Qualified"];
      $("ruleUnqualified").checked = statuses.indexOf("Unqualified") >= 0;
      $("ruleQualified").checked = statuses.indexOf("Qualified") >= 0;
      $("ruleCompanies").checked = (rule.stages || []).length > 0;
      text($("ruleSummary"), c.selectionSummary || "The list has not been built yet.");
      var editable = !c.campaignStatus || c.campaignStatus === "Draft" || c.campaignStatus === "Awaiting sign-off";
      $("ruleUnqualified").disabled = !editable; $("ruleQualified").disabled = !editable; $("ruleCompanies").disabled = !editable;
      var note = $("runNote");
      if (c.campaignStatus === "Signed off") text(note, "Signed off. The worker picks the run up within a minute and mails each planned piece" + (state.session.postal.provider === "dryrun" ? " (dry run: nothing is printed)." : "."));
      else if (c.campaignStatus === "Running") text(note, "Running — the worker is mailing. Reload to follow the counts.");
      else if (c.campaignStatus === "Complete") text(note, "Complete. Every planned piece was handed to the vendor.");
      else text(note, "Build the list, read the count and the cost, then sign off. Nothing is mailed until signed (ruling 13).");
    } else hide(pc);
    renderCallCard(rec);
    renderSmsCard(rec);
    renderEmailCard(rec);
    show($("recordPanel"));
  }

  // --- the email kind (§ 3.3; rulings 19, 25) ---------------------------------------------------
  var EMAIL_PUSHED = "pushed to the mailing list";
  function renderEmailCard(rec) {
    var c = rec.campaign, card = $("emailCard");
    if (c.campaignKind !== "Email") { hide(card); return; }
    show(card);
    var touches = rec.touches || [];
    var pushed = touches.filter(function (t) { return t.touchStatus === "Planned" && t.vendorStatus === EMAIL_PUSHED; }).length;
    var withheld = touches.filter(function (t) { return t.touchStatus === "Cancelled" && (t.vendorStatus || "").indexOf("withheld") === 0; }).length;
    var sum = rec.touchSummary || {};
    tiles($("emailTiles"), [["To push", (sum.planned || 0) - pushed], ["On the list", pushed], ["Withheld", withheld], ["Sent", sum.sent]]);
    var rule = rec.rule || {}, chosen = rule.stages || [];
    var editable = !c.campaignStatus || c.campaignStatus === "Draft" || c.campaignStatus === "Awaiting sign-off";
    var host = $("emailStages"); host.innerHTML = "";
    (state.session.emailStages || ["Prospect", "Engaged", "Opportunity"]).forEach(function (st) {
      var lab = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; cb.value = st; cb.checked = chosen.indexOf(st) >= 0;
      cb.disabled = !editable; cb.setAttribute("data-emailstage", st);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" Contacts typed Prospect at ")); lab.appendChild(el("strong", null, st)); host.appendChild(lab);
    });
    $("emailDormant").checked = rule.dormantDays !== null && rule.dormantDays !== undefined;
    if ($("emailDormant").checked) $("emailDormantDays").value = rule.dormantDays;
    $("emailDormant").disabled = !editable; $("emailDormantDays").disabled = !editable;
    text($("emailRuleSummary"), c.selectionSummary || "The list has not been built yet.");
    var note = $("emailNote");
    if (!state.session.emailOn) text(note, "Campaign emails are switched off on this deployment (CAMPAIGNS_EMAIL at /setup).");
    else if (!state.session.mailingConnected) text(note, "The mailing service is not connected here (System Settings, Mailing).");
    else if (c.campaignStatus === "Signed off") text(note, "Signed off. The worker pushes the list to the mailing service within a minute, as its own list named for this campaign.");
    else if (c.campaignStatus === "Running") text(note, "On the mailing service as the list \u201cCampaign \u2014 " + c.name + "\u201d. Design the notice there with this campaign's links (Links tab), send it to that list, then press Mark as sent.");
    else if (c.campaignStatus === "Complete") text(note, "Complete: the notice was sent.");
    else text(note, "Build the list, read the count, then sign off. The application never sends email: the mailing service does.");
  }

  function emailRule() {
    var stages = Array.prototype.filter.call(document.querySelectorAll("[data-emailstage]"), function (cb) { return cb.checked; }).map(function (cb) { return cb.value; });
    return { stages: stages, dormantDays: $("emailDormant").checked ? Number($("emailDormantDays").value || 0) : null };
  }

  $("emailBuildBtn").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("The list cannot be rebuilt once the campaign is " + c.campaignStatus + ".", "warn"); return; }
    var rule = emailRule();
    if (!rule.stages.length && rule.dormantDays === null) { notice("Tick at least one stage, or the dormant clients.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: { rule: rule } });
      notice("List built: " + res.pieces + " people (" + res.created + " new, " + res.cancelled + " dropped).", "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  $("emailSignoffBtn").addEventListener("click", function () {
    if (!state.record) return;
    var c = state.record.campaign, sum = state.record.touchSummary || {};
    if (!sum.planned) { notice("Build the list first — there is nobody on it.", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "This pushes " + sum.planned + " " + (sum.planned === 1 ? "person" : "people") + " to the mailing service as the list \u201cCampaign \u2014 " + c.name + "\u201d. Nobody is emailed until you send a notice there."));
    body.appendChild(el("p", "cm__hint", "Type the number of people to confirm."));
    var f = el("div", "cm__field"); var lab = el("label", null, "Number of people"); lab.htmlFor = "emailConfirm"; var inp = el("input"); inp.type = "text"; inp.id = "emailConfirm"; inp.autocomplete = "off";
    f.appendChild(lab); f.appendChild(inp); body.appendChild(f);
    openModal("Sign off and push", body, async function () {
      await api("/campaigns/" + encodeURIComponent(c.id) + "/signoff", { method: "POST", body: { confirm: inp.value } });
      closeModal(); notice("Signed off. The worker pushes the list within a minute.", "ok"); loadRecord();
    }, "Sign off and push");
    setTimeout(function () { inp.focus(); }, 50);
  });

  $("emailSentBtn").addEventListener("click", function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (c.campaignStatus !== "Running") { notice("Mark as sent comes after the list is on the mailing service (the campaign reads Running).", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "Press this only after you sent the notice to \u201cCampaign \u2014 " + c.name + "\u201d at the mailing service. Every person on the list is recorded as sent and the campaign completes."));
    openModal("Mark as sent", body, async function () {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/mark-sent", { method: "POST" });
      closeModal(); notice("Marked sent: " + res.sent + " people.", "ok"); loadRecord();
    }, "Mark as sent");
  });

  // --- the text-message kind (§ 3.5; rulings 38, 39) -------------------------------------------
  // Mirrors core/sms.segments: GSM-7 is 160 alone / 153 a part, anything else 70 / 67.
  var GSM7 = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà";
  var GSM7_EXT = "^{}\\[~]|€";
  function smsParts(text) {
    text = text || ""; var gsm = true, units = 0;
    for (var i = 0; i < text.length; i++) { var ch = text[i]; if (GSM7_EXT.indexOf(ch) >= 0) units += 2; else if (GSM7.indexOf(ch) >= 0) units += 1; else { gsm = false; break; } }
    if (!gsm) units = text.length;
    var single = gsm ? 160 : 70, multi = gsm ? 153 : 67;
    return { characters: text.length, parts: units === 0 ? 0 : (units <= single ? 1 : Math.ceil(units / multi)), encoding: gsm ? "GSM-7" : "UCS-2" };
  }

  function renderSmsCard(rec) {
    var c = rec.campaign, card = $("smsCard");
    if (c.campaignKind !== "SMS") { hide(card); return; }
    show(card);
    var sum = rec.touchSummary || {}, review = (rec.touches || []).filter(function (t) { return (t.vendorStatus || "").indexOf("sending") === 0; }).length;
    tiles($("smsTiles"), [["To send", sum.planned], ["Sent", sum.sent], ["Delivered", sum.delivered], ["Needs review", review]]);
    var host = $("smsStages"); host.innerHTML = "";
    var chosen = (rec.rule && rec.rule.stages) || [];
    var editable = !c.campaignStatus || c.campaignStatus === "Draft" || c.campaignStatus === "Awaiting sign-off";
    ((state.session.sms || {}).stages || ["Prospect", "Engaged", "Opportunity"]).forEach(function (st) {
      var lab = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; cb.value = st; cb.checked = chosen.indexOf(st) >= 0;
      cb.disabled = !editable; cb.setAttribute("data-smsstage", st);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" Contacts typed Prospect at ")); lab.appendChild(el("strong", null, st)); host.appendChild(lab);
    });
    text($("smsRuleSummary"), c.selectionSummary || "The list has not been built yet.");
    var chk = rec.smsCheck || {};
    text($("smsText"), c.smsMessage || "(no message written yet)");
    text($("smsParts"), (chk.characters || 0) + " characters · " + (chk.parts || 0) + " message part" + (chk.parts === 1 ? "" : "s") + (chk.encoding ? " (" + chk.encoding + ")" : ""));
    var prob = $("smsProblem");
    if (chk.fieldAvailable === false) { prob.textContent = "This CRM has no Text message field on the campaign yet (ruling 39: coutreach-entities-crm-handoff.md § 9)."; show(prob); }
    else if ((chk.problems || []).length) { prob.textContent = chk.problems[0]; show(prob); } else hide(prob);
    var s = state.session.sms || {}, note = $("smsNote");
    var where = s.provider === "dryrun" ? " The texting service is the dry run: nothing reaches a phone." : "";
    if (!state.session.smsOn) text(note, "Campaign texts are switched off on this deployment (CAMPAIGNS_SMS at /setup).");
    else if (c.campaignStatus === "Signed off") text(note, "Signed off. The worker sends within a minute, between " + (s.hours || "9-20") + " h " + (s.timezone || "") + "." + where);
    else if (c.campaignStatus === "Running") text(note, "Sending. Reload to follow the counts." + (review ? " " + review + " text(s) were interrupted mid-send: check the texting service before resending — they are never resent by themselves." : "") + where);
    else if (c.campaignStatus === "Complete") text(note, "Complete. Every text was handed to the texting service." + where);
    else text(note, "Write the message (Edit), build the list, read the count, then sign off. A text cannot be called back." + where);
  }

  $("smsBuildBtn").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("The list cannot be rebuilt once the campaign is " + c.campaignStatus + ".", "warn"); return; }
    var stages = Array.prototype.filter.call(document.querySelectorAll("[data-smsstage]"), function (cb) { return cb.checked; }).map(function (cb) { return cb.value; });
    if (!stages.length) { notice("Tick at least one stage to text.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: { rule: { stages: stages } } });
      notice("List built: " + res.pieces + " to text (" + res.created + " new, " + res.cancelled + " dropped).", "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  $("smsSignoffBtn").addEventListener("click", function () {
    if (!state.record) return;
    var c = state.record.campaign, sum = state.record.touchSummary || {}, chk = state.record.smsCheck || {};
    if ((chk.problems || []).length) { notice(chk.problems[0], "warn"); return; }
    if (!sum.planned) { notice("Build the list first — there is nobody on it to text.", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "This texts " + sum.planned + " " + (sum.planned === 1 ? "person" : "people") + " the message below, " + chk.parts + " message part" + (chk.parts === 1 ? "" : "s") + " each." + ((state.session.sms || {}).provider === "dryrun" ? " (Dry run — nothing reaches a phone.)" : "")));
    body.appendChild(el("p", "cm__smstext", c.smsMessage || ""));
    body.appendChild(el("p", "cm__hint", "Type the number of people to confirm. A text cannot be called back, and the message is frozen from now on."));
    var f = el("div", "cm__field"); var lab = el("label", null, "Number of people"); lab.htmlFor = "smsConfirm"; var inp = el("input"); inp.type = "text"; inp.id = "smsConfirm"; inp.autocomplete = "off";
    f.appendChild(lab); f.appendChild(inp); body.appendChild(f);
    openModal("Sign off and send", body, async function () {
      await api("/campaigns/" + encodeURIComponent(c.id) + "/signoff", { method: "POST", body: { confirm: inp.value } });
      closeModal(); notice("Signed off. The worker sends within a minute, inside the texting hours.", "ok"); loadRecord();
    }, "Sign off and send");
    setTimeout(function () { inp.focus(); }, 50);
  });

  // --- the call kind (§ 3.4; ruling 36) ------------------------------------------------------
  function callsPageUrl() { return location.origin + "/campaigns/calls.html"; }

  function renderCallCard(rec) {
    var c = rec.campaign, card = $("callCard");
    if (c.campaignKind !== "Call") { hide(card); return; }
    show(card);
    var sum = rec.touchSummary || {}, b = rec.callBreakdown || {};
    tiles($("callTiles"), [["To call", sum.planned], ["Called", b.done], ["No answer", b["No answer"]], ["Interested", b.Interested], ["Declined", b.Declined]]);
    var host = $("callStages"); host.innerHTML = "";
    var rule = rec.rule || {};
    var chosenStatuses = rule.statuses || (rule.stages ? [] : ["Unqualified", "Qualified"]);
    var chosenStages = rule.stages || [];
    var editable = !c.campaignStatus || c.campaignStatus === "Draft" || c.campaignStatus === "Awaiting sign-off";
    // Ruling 44: leads at Unqualified or Qualified; Contacts typed Prospect at a stage.
    (state.session.callStatuses || ["Unqualified", "Qualified"]).forEach(function (st) {
      var lab = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; cb.value = st; cb.checked = chosenStatuses.indexOf(st) >= 0;
      cb.disabled = !editable; cb.setAttribute("data-callstatus", st);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" Leads at ")); lab.appendChild(el("strong", null, st)); host.appendChild(lab);
    });
    (state.session.callStages || ["Prospect", "Engaged", "Opportunity"]).forEach(function (st) {
      var lab = el("label", "cm__check"); var cb = el("input"); cb.type = "checkbox"; cb.value = st; cb.checked = chosenStages.indexOf(st) >= 0;
      cb.disabled = !editable; cb.setAttribute("data-callstage", st);
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" Contacts typed Prospect at ")); lab.appendChild(el("strong", null, st)); host.appendChild(lab);
    });
    text($("callRuleSummary"), c.selectionSummary || "The list has not been built yet.");
    var note = $("callNote");
    if (c.campaignStatus === "Running") text(note, "Running. Callers see each row on the Calls page until it is recorded; the campaign completes itself when the last row is.");
    else if (c.campaignStatus === "Complete") text(note, "Complete. Every row was recorded.");
    else text(note, "Build the list, read who is on it, then sign off. Nobody is called until you do.");
    text($("callersLine"), rec.callerTeams ? "Who calls: members of " + rec.callerTeams.join(", ") + " (the teams named on this campaign — ruling 36; Edit to change them)." : "Who calls: the teams named on this campaign could not be read.");
    text($("callsUrl"), callsPageUrl());
    if (!state.session.callsOn) text(note, "Campaign calls are switched off on this deployment (CAMPAIGNS_CALLS at /setup), so this list cannot be built or run.");
  }

  function chosenCallRule() {
    function ticked(attr) {
      return Array.prototype.filter.call(document.querySelectorAll("[" + attr + "]"), function (cb) { return cb.checked; }).map(function (cb) { return cb.value; });
    }
    return { statuses: ticked("data-callstatus"), stages: ticked("data-callstage") };
  }

  $("callBuildBtn").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("The list cannot be rebuilt once the campaign is " + c.campaignStatus + ".", "warn"); return; }
    var callRule = chosenCallRule();
    if (!callRule.statuses.length && !callRule.stages.length) { notice("Tick at least one lead status or stage to call.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: { rule: callRule } });
      notice("List built: " + res.pieces + " to call (" + res.created + " new, " + res.cancelled + " dropped).", "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  $("callSignoffBtn").addEventListener("click", function () {
    if (!state.record) return;
    var c = state.record.campaign, sum = state.record.touchSummary || {};
    if (!sum.planned) { notice("Build the list first — there is nobody on it to call.", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, sum.planned + " " + (sum.planned === 1 ? "person goes" : "people go") + " on the call list, for " + ((state.record.callerTeams || []).join(", ") || "the campaign's teams") + " to call."));
    body.appendChild(el("p", "cm__hint", "Signing off starts the list at once: no worker runs a call campaign, people do."));
    openModal("Sign off and start calling", body, async function () {
      await api("/campaigns/" + encodeURIComponent(c.id) + "/signoff", { method: "POST", body: { confirm: "" } });
      closeModal(); notice("Signed off. The list is on the Calls page now.", "ok"); loadRecord();
    }, "Sign off and start");
  });

  $("callsUrlCopy").addEventListener("click", function () { copyText(callsPageUrl(), $("callsUrlCopy")); });

  function currentRule() {
    // Ruling 44: Unqualified and Qualified leads; Companies typed Prospect
    // (already contacted) only when ticked.
    var statuses = [];
    if ($("ruleUnqualified").checked) statuses.push("Unqualified");
    if ($("ruleQualified").checked) statuses.push("Qualified");
    return { statuses: statuses, stages: $("ruleCompanies").checked ? ["Prospect", "Engaged", "Opportunity"] : [] };
  }

  $("buildBtn").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (c.campaignKind !== "Postcard") { notice("Only a postcard campaign builds a list.", "warn"); return; }
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("The list cannot be rebuilt once the campaign is " + c.campaignStatus + ".", "warn"); return; }
    var postcardRule = currentRule();
    if (!postcardRule.statuses.length && !postcardRule.stages.length) { notice("Tick at least one: Unqualified leads, Qualified leads, or Companies typed Prospect.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: { rule: postcardRule } });
      notice("List built: " + res.pieces + " planned (" + res.created + " new, " + res.cancelled + " dropped). Estimated cost " + money(res.estimatedCost, res.currency) + ".", "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  $("signoffBtn").addEventListener("click", function () {
    if (!state.record) return;
    var c = state.record.campaign, sum = state.record.touchSummary || {};
    if (c.campaignKind !== "Postcard") { notice("Only a postcard campaign is signed off.", "warn"); return; }
    if (!sum.planned) { notice("Build the list first — there is nothing planned to sign off.", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "This mails " + sum.planned + " piece" + (sum.planned === 1 ? "" : "s") + " at an estimated " + money(state.record.estimatedCost, state.record.currency) + (state.session.postal.provider === "dryrun" ? " (dry run — nothing is printed)." : ".")));
    body.appendChild(el("p", "cm__hint", "Type the piece count to confirm. Nothing is mailed until you do (ruling 13)."));
    var f = el("div", "cm__field"); var lab = el("label", null, "Piece count"); lab.htmlFor = "confirmCount"; var inp = el("input"); inp.type = "text"; inp.id = "confirmCount"; inp.autocomplete = "off";
    f.appendChild(lab); f.appendChild(inp); body.appendChild(f);
    openModal("Sign off and run", body, async function () {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/signoff", { method: "POST", body: { confirm: inp.value } });
      closeModal(); notice("Signed off: " + res.campaign.pieceCount + " pieces. The worker runs it within a minute.", "ok"); loadRecord();
    }, "Sign off and run");
    setTimeout(function () { inp.focus(); }, 50);
  });

  $("editBtn").addEventListener("click", openEditCampaign);

  // --- links tab --------------------------------------------------------------------------------
  function destinationLabel(l) {
    if (l.destination_kind === "form") { var d = (state.session.formDestinations || []).filter(function (x) { return x.slug === l.destination_target; })[0]; return (d ? d.title : l.destination_target) + " form"; }
    if (l.destination_kind === "programme") return "Workshops and webinars page";
    if (l.destination_kind === "event") return "Event: " + (l.destinationName || l.destination_slug || l.destination_target);
    if (l.destination_kind === "landing") return "Postcard landing page (each card adds its own token)";
    return l.destination_kind;
  }

  async function loadLinks() {
    try {
      state.links = (await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/links")).links;
      renderLinks();
    } catch (e) { var n = $("linksNotice"); n.textContent = e.message; n.className = "cm__notice cm__notice--error"; show(n); }
  }

  function copyText(t, btn) {
    var done = function () { var old = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = old; }, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, function () { window.prompt("Copy the address", t); });
    else window.prompt("Copy the address", t);
  }

  function renderLinks() {
    var body = $("linkRows"); body.innerHTML = "";
    var links = state.links || [];
    links.forEach(function (l) {
      var tr = el("tr");
      tr.appendChild(el("td", null, l.name));
      var sTd = el("td"); sTd.appendChild(el("span", "cm__short", l.shortUrl)); sTd.appendChild(document.createTextNode(" "));
      var copy = el("button", "cm__rowbtn", "Copy"); copy.type = "button"; copy.addEventListener("click", function () { copyText(l.shortUrl, copy); }); sTd.appendChild(copy); tr.appendChild(sTd);
      tr.appendChild(el("td", null, destinationLabel(l)));
      var stTd = el("td"); stTd.appendChild(el("span", "cm__badge" + (l.state === "retired" ? " cm__badge--late" : ""), l.state)); tr.appendChild(stTd);
      var c = l.counts || {};
      tr.appendChild(el("td", "num", c.visits || 0)); tr.appendChild(el("td", "num", c.late || 0)); tr.appendChild(el("td", "num", c.scans || 0));
      var subs = c.submissions || {}; var keys = Object.keys(subs);
      tr.appendChild(el("td", null, keys.length ? keys.map(function (k) { return k + ": " + subs[k]; }).join(", ") : "—"));
      var qTd = el("td"); var img = el("img", "cm__qr"); img.alt = "QR code for " + l.name;
      img.src = API + "/campaigns/" + encodeURIComponent(RECORD_ID) + "/links/" + encodeURIComponent(l.id) + "/qr.png"; qTd.appendChild(img); tr.appendChild(qTd);
      var aTd = el("td");
      if (l.destination_kind !== "landing") {
        var corr = el("button", "cm__rowbtn", "Correct destination"); corr.type = "button"; corr.addEventListener("click", function () { openLinkModal(l); }); aTd.appendChild(corr);
      }
      var ret = el("button", "cm__rowbtn", l.state === "retired" ? "Reactivate" : "Retire"); ret.type = "button";
      ret.addEventListener("click", async function () {
        try { await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/links/" + encodeURIComponent(l.id) + (l.state === "retired" ? "/reactivate" : "/retire"), { method: "POST" }); loadLinks(); }
        catch (e) { notice(e.message, "error"); }
      });
      aTd.appendChild(ret); tr.appendChild(aTd);
      body.appendChild(tr);
    });
    $("linksEmpty").hidden = links.length > 0;
  }

  function openLinkModal(existing) {
    var s = state.session, f = state.fields || {};
    var body = el("div", "cm__fields");
    var nameF = el("div", "cm__field cm__field--wide"); var nl = el("label", null, "Name"); nl.htmlFor = "lk_name"; var nameIn = el("input"); nameIn.type = "text"; nameIn.id = "lk_name"; nameIn.maxLength = 200;
    nameIn.value = existing ? existing.name : ""; nameIn.disabled = !!existing; nameF.appendChild(nl); nameF.appendChild(nameIn); body.appendChild(nameF);
    var kindF = el("div", "cm__field"); var kl = el("label", null, "Opens"); kl.htmlFor = "lk_kind"; var kind = el("select"); kind.id = "lk_kind";
    [["form", "A public form"], ["programme", "The workshops and webinars page"], ["event", "One event's page"]].forEach(function (o) { var opt = el("option", null, o[1]); opt.value = o[0]; kind.appendChild(opt); });
    kindF.appendChild(kl); kindF.appendChild(kind); body.appendChild(kindF);
    var tgtF = el("div", "cm__field"); var tl = el("label", null, "Which"); tl.htmlFor = "lk_target"; var target = el("select"); target.id = "lk_target"; tgtF.appendChild(tl); tgtF.appendChild(target); body.appendChild(tgtF);
    function fillTarget() {
      target.innerHTML = "";
      if (kind.value === "form") (s.formDestinations || []).forEach(function (d) { var o = el("option", null, d.title); o.value = d.slug; target.appendChild(o); });
      else if (kind.value === "event") {
        if (!f.eventOptions) { var o = el("option", null, "Your role cannot list events"); o.value = ""; target.appendChild(o); }
        else f.eventOptions.forEach(function (e) { var o2 = el("option", null, e.name); o2.value = e.id; target.appendChild(o2); });
      }
      tgtF.hidden = kind.value === "programme";
    }
    kind.addEventListener("change", fillTarget);
    kind.value = existing ? existing.destination_kind : "form"; fillTarget();
    if (existing && existing.destination_target) target.value = existing.destination_target;
    openModal(existing ? "Correct where \"" + existing.name + "\" goes" : "New link", body, async function () {
      if (!existing && !nameIn.value.trim()) { modalMsg("Name the link for where it will be posted.", "error"); return; }
      var payload = { kind: kind.value, target: kind.value === "programme" ? null : target.value };
      if (kind.value !== "programme" && !payload.target) { modalMsg("Choose where the link opens.", "error"); return; }
      if (existing) await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/links/" + encodeURIComponent(existing.id), { method: "PUT", body: payload });
      else await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/links", { method: "POST", body: Object.assign({ name: nameIn.value.trim() }, payload) });
      closeModal(); loadLinks();
    }, existing ? "Correct" : "Create");
  }

  $("newLinkBtn").addEventListener("click", async function () {
    try { await ensureFields(); } catch (e) { notice(e.message, "error"); return; }
    openLinkModal(null);
  });

  // --- responses tab ------------------------------------------------------------------------------
  async function loadResponses() {
    try {
      state.responses = await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/responses");
      renderResponses();
    } catch (e) { notice(e.message, "error"); }
  }

  function renderResponses() {
    var r = state.responses || { responses: [], totals: {} }, rec = state.record || {};
    var sum = rec.touchSummary || {};
    // Ruling 46's three counts, then the per-form totals, then a postcard
    // campaign's piece counts. Converted counts calls too (the record payload's
    // callConversions), so it agrees with the Analytics page.
    var calls = (rec.callBreakdown || {}).callConversions || 0;
    var t = [["Responded", r.responded || 0], ["Converted", (r.converted || 0) + calls],
             ["Became a client, partner or funder", r.became || 0]];
    t = t.concat(Object.keys(r.totals || {}).map(function (k) { return [k, r.totals[k]]; }));
    if ((rec.campaign || {}).campaignKind === "Postcard") t = t.concat([["Pieces", sum.pieces], ["Delivered", sum.delivered], ["Returned", sum.returned], ["Scanned", sum.scanned]]);
    if ((rec.campaign || {}).campaignKind === "SMS") t = t.concat([["Texts sent", (sum.sent || 0) + (sum.delivered || 0)], ["Delivered", sum.delivered]]);
    tiles($("responseTiles"), t);
    var body = $("responseRows"); body.innerHTML = "";
    (r.responses || []).forEach(function (x) {
      var tr = el("tr");
      tr.appendChild(el("td", null, fmtDate(x.receivedAt))); tr.appendChild(el("td", null, x.form)); tr.appendChild(el("td", null, x.status));
      tr.appendChild(el("td", "cm__short", x.linkToken || "—")); tr.appendChild(el("td", null, x.email || "—"));
      var recTd = el("td");
      // Through to the record each door created: the engagement opens in
      // Client Administration's popup, a partner or funder on its own record
      // page, a registration on its event in Event Administration, and an
      // information request in Submission Admin — plus the submission itself.
      var ids = x.records || {}; var links = [];
      if (ids.engagementId) links.push(["Engagement", "/assignments/?engagement=" + encodeURIComponent(ids.engagementId)]);
      if (ids.partnerProfileId) links.push(["Partner", "/partnersessions/record/" + encodeURIComponent(ids.partnerProfileId)]);
      if (ids.sponsorProfileId) links.push(["Funder", "/sponsorsessions/record/" + encodeURIComponent(ids.sponsorProfileId)]);
      if (ids.eventRegistrationId && ids.eventId) links.push(["Registration", "/events/?event=" + encodeURIComponent(ids.eventId)]);
      if (ids.informationRequestId || x.form === "info-request" || x.form === "info-email") links.push(["Information request", "/ops/?submission=" + encodeURIComponent(x.id)]);
      else links.push(["Submission", "/ops/?submission=" + encodeURIComponent(x.id)]);
      links.forEach(function (l) { var a = el("a", "cm__link", l[0]); a.href = l[1]; a.target = "_blank"; a.rel = "noopener"; recTd.appendChild(a); recTd.appendChild(document.createTextNode(" ")); });
      tr.appendChild(recTd); body.appendChild(tr);
    });
    $("responsesEmpty").hidden = (r.responses || []).length > 0;
    var touches = rec.touches || [];
    var ts = $("touchSection"); ts.hidden = !touches.length;
    var tb = $("touchRows"); tb.innerHTML = "";
    touches.forEach(function (t2) {
      var tr = el("tr");
      tr.appendChild(el("td", null, t2.prospectName || t2.companyName || t2.contactName || t2.name));
      tr.appendChild(el("td", null, t2.touchStatus)); tr.appendChild(el("td", null, t2.outcome || "—"));
      tr.appendChild(el("td", null, t2.sentAt ? fmtDate(t2.sentAt) : "—")); tr.appendChild(el("td", "cm__short", t2.vendorPieceId || "—"));
      tr.appendChild(el("td", "num", t2.scanCount || 0)); tr.appendChild(el("td", null, (t2.mailedAddress || "—").replace(/\n/g, ", ")));
      var aTd = el("td");
      if (t2.vendorPieceId || t2.touchStatus === "Planned") {
        var pv = el("a", "cm__rowbtn", "Preview"); pv.href = API + "/campaigns/" + encodeURIComponent(RECORD_ID) + "/touches/" + encodeURIComponent(t2.id) + "/preview"; pv.target = "_blank"; pv.rel = "noopener"; aTd.appendChild(pv);
      }
      if (t2.channel === "SMS" && state.session && state.session.sms && state.session.sms.provider === "dryrun" && t2.vendorPieceId) {
        [["text-delivered", "Simulate delivered"], ["stop", "Simulate a STOP reply"]].forEach(function (k) {
          var b = el("button", "cm__rowbtn", k[1]); b.type = "button";
          b.addEventListener("click", async function () {
            try { await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/touches/" + encodeURIComponent(t2.id) + "/simulate", { method: "POST", body: { status: k[0] } }); notice(k[1].replace("Simulate ", "Simulated ") + ".", "ok"); await loadRecord(); renderResponses(); }
            catch (e) { notice(e.message, "error"); }
          });
          aTd.appendChild(b);
        });
      } else if (state.session && state.session.postal.provider === "dryrun" && t2.vendorPieceId && t2.touchStatus !== "Returned") {
        ["delivered", "returned"].forEach(function (k) {
          var b = el("button", "cm__rowbtn", "Simulate " + k); b.type = "button";
          b.addEventListener("click", async function () {
            try { await api("/campaigns/" + encodeURIComponent(RECORD_ID) + "/touches/" + encodeURIComponent(t2.id) + "/simulate", { method: "POST", body: { status: k } }); notice("Simulated " + k + ".", "ok"); await loadRecord(); renderResponses(); }
            catch (e) { notice(e.message, "error"); }
          });
          aTd.appendChild(b);
        });
      }
      tr.appendChild(aTd); tb.appendChild(tr);
    });
  }

  // --- tabs on the record page -------------------------------------------------------------------
  Array.prototype.forEach.call(document.querySelectorAll("#recordTabs .cm__tab"), function (btn) {
    btn.addEventListener("click", function () {
      Array.prototype.forEach.call(document.querySelectorAll("#recordTabs .cm__tab"), function (b) { b.classList.toggle("is-active", b === btn); });
      var tab = btn.getAttribute("data-tab");
      Array.prototype.forEach.call(document.querySelectorAll("#recordPanel .cm__tabpanel"), function (p) { p.hidden = p.getAttribute("data-panel") !== tab; });
      if (tab === "links") loadLinks();
      // The Responses tab re-reads the campaign first: a worker run (a text
      // sent, a list pushed) since the page opened changes the touch rows and
      // the buttons each row offers (found on the Phase 4 pass, C4).
      if (tab === "responses") loadRecord().then(loadResponses);
      if (tab === "analytics") loadAnalytics(false);
    });
  });

  // --- analytics tab: the campaign's dashboard (CM-9, § 6) -------------------------------------
  var anaLoaded = false;
  async function loadAnalytics(force) {
    if (anaLoaded && !force) return;
    anaLoaded = true;
    var grid = $("anaGrid"), msg = $("anaMsg");
    grid.innerHTML = ""; msg.hidden = false; msg.textContent = "Loading…";
    try {
      var url = "/analytics/api/record/COutreachCampaign/" + encodeURIComponent(RECORD_ID);
      var r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      var body = await r.json();
      if (!r.ok) throw new Error((body && body.detail) || ("Request failed (" + r.status + ")"));
      if (!body.available) { msg.textContent = "No dashboard has been set up for campaigns yet (Analytics must be on at /setup)."; return; }
      var panels = body.panels || [];
      if (!panels.length) { msg.textContent = "No panels to show."; return; }
      msg.hidden = true;
      panels.forEach(function (p) {
        var art = el("article", "an-panel"); art.style.setProperty("--span", Math.max(3, Math.min(12, p.width || 4)));
        var head = el("header", "an-panel__head"); head.appendChild(el("h3", null, p.title));
        var bodyEl = el("div", "an-panel__body"); art.appendChild(head); art.appendChild(bodyEl);
        try { CBMCharts.renderPanel(bodyEl, p, { crmUrl: body.crmUrl }); }
        catch (e) { bodyEl.innerHTML = ""; bodyEl.appendChild(el("p", "anc-err", "Could not render this panel.")); }
        grid.appendChild(art);
      });
    } catch (e) { anaLoaded = false; msg.hidden = false; msg.textContent = e.message; }
  }
  $("anaRefreshBtn").addEventListener("click", function () { loadAnalytics(true); });

  // --- leads (rulings 41-53) ---------------------------------------------------------------------
  async function loadProspects() {
    try {
      var q = [];
      if ($("stageFilter").value) q.push("status=" + encodeURIComponent($("stageFilter").value));
      if ($("exitFilter").value) q.push("exit=" + encodeURIComponent($("exitFilter").value));
      if ($("doorFilter").value) q.push("source=" + encodeURIComponent($("doorFilter").value));
      state.prospects = (await api("/prospects" + (q.length ? "?" + q.join("&") : ""))).prospects || [];
      renderProspects();
    } catch (e) { notice(e.message, "error"); }
  }

  function renderProspects() {
    var q = ($("prospectSearch").value || "").toLowerCase();
    var rows = state.prospects.filter(function (p) {
      if (!q) return true;
      return [p.name, p.businessName, p.mailingAddressCity, p.mailingAddressPostalCode, p.importBatch, p.externalReference, p.email].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    var k = state.psort.key, dir = state.psort.dir;
    rows.sort(function (a, b) { var x = a[k] || "", y = b[k] || ""; if (x === "") return 1; if (y === "") return -1; return String(x).localeCompare(String(y), undefined, { numeric: true }) * dir; });
    var body = $("prospectRows"); body.innerHTML = "";
    rows.forEach(function (p) {
      var tr = el("tr");
      var nTd = el("td"); var a = el("a", "cm__link", p.businessName || p.name || "(unnamed)"); a.href = "#"; a.addEventListener("click", function (ev) { ev.preventDefault(); openProspect(p.id); }); nTd.appendChild(a); tr.appendChild(nTd);
      tr.appendChild(el("td", null, p.leadStatus || "—")); tr.appendChild(el("td", null, p.sideExit || "—")); tr.appendChild(el("td", null, p.leadSource || "—"));
      tr.appendChild(el("td", null, p.mailingAddressCity || "—")); tr.appendChild(el("td", null, p.addressStatus || "—"));
      tr.appendChild(el("td", null, p.importBatch || "—")); tr.appendChild(el("td", null, fmtDate(p.createdAt)));
      body.appendChild(tr);
    });
    text($("prospectCount"), rows.length + " of " + state.prospects.length);
    $("prospectsEmpty").hidden = rows.length > 0;
  }

  async function openProspect(id) {
    try {
      var res = await api("/prospects/" + encodeURIComponent(id));
      var p = res.prospect;
      var body = el("div", "cm__plan");
      var facts = el("dl", "cm__facts");
      [["Business", p.businessName], ["Person", [p.firstName, p.lastName].filter(Boolean).join(" ")], ["Address", [p.mailingAddressStreet, p.mailingAddressCity, p.mailingAddressState, p.mailingAddressPostalCode].filter(Boolean).join(", ")],
       ["Address status", p.addressStatus], ["Website", p.website], ["Email", p.email], ["Phone", p.phone],
       ["Lead status", p.leadStatus], ["Status changed", p.leadStatusChangedAt ? fmtDate(p.leadStatusChangedAt) : null], ["Lead Source", p.leadSource], ["Stopped because", p.sideExit], ["Reason note", p.sideExitNote],
       ["Qualified by", p.qualifiedBy], ["Qualified at", p.qualifiedAt ? fmtDate(p.qualifiedAt) : null], ["Batch", p.importBatch], ["Reference", p.externalReference],
       ["Converted to company", p.promotedCompanyName], ["Converted to contact", p.promotedContactName], ["Duplicate of company", p.alreadyKnownCompanyName]
      ].forEach(function (f) { facts.appendChild(el("dt", null, f[0])); facts.appendChild(el("dd", null, f[1] || "—")); });
      body.appendChild(facts);
      body.appendChild(el("h4", null, "Touches"));
      if (!(res.touches || []).length) body.appendChild(el("p", "cm__hint", "No touch yet."));
      else {
        var tbl = el("table", "cm__grid"); var tb = el("tbody");
        res.touches.forEach(function (t) { var tr = el("tr"); [t.outreachCampaignName, t.channel, t.touchStatus, t.outcome || "—", t.sentAt ? fmtDate(t.sentAt) : "—", "scans " + (t.scanCount || 0)].forEach(function (v) { tr.appendChild(el("td", null, v)); }); tb.appendChild(tr); });
        tbl.appendChild(tb); body.appendChild(tbl);
      }
      body.appendChild(el("h4", null, "Review"));
      body.appendChild(reviewActions(p, function () { closeModal(); loadProspects(); }));
      openModal(p.businessName || p.name, body, null);
    } catch (e) { notice(e.message, "error"); }
  }

  // --- review actions (§ 2.3, § 3.8) ----------------------------------------------------------
  // Every action is offered on every record; one that does not apply explains
  // itself on click (buttons are never hidden or disabled).
  var REVIEW_ACTIONS = [
    ["qualify", "Qualify", "Note (optional)", false],
    ["disqualify", "Disqualify…", "Why will it never be a client, partner or funder? (required)", true],
    ["do-not-contact", "Do Not Contact…", "Note (optional)", false],
    ["not-same-company", "Not the same company…", "Note (optional)", false],
  ];

  function reviewWhyNot(p, action) {
    var status = p.leadStatus || "Unqualified";
    if (action === "not-same-company") return p.sideExit === "Duplicate" ? "" : "Only a lead marked Duplicate can be told it is not the same company.";
    if (p.sideExit) return "This lead has already stopped being worked (" + p.sideExit + "); a reason is never written over another.";
    if (action === "qualify" && status !== "Unqualified") return "Only an Unqualified lead is qualified by review; this one is " + status + ".";
    if (action === "qualify" && !p.website && !p.email) return "A lead without a website or an email can never be Qualified (ruling 42). Add one to the lead in the CRM first, or leave it Unqualified — campaigns may still reach it.";
    if (action === "disqualify" && status !== "Unqualified" && status !== "Qualified") return "Only an Unqualified or Qualified lead can be disqualified; this one is " + status + ".";
    if (action === "do-not-contact" && status === "Converted") return "This lead is Converted; its Company or Contact is the record now.";
    return "";
  }

  function reviewActions(p, after) {
    var box = el("div", "cm__runactions");
    REVIEW_ACTIONS.forEach(function (a) {
      var b = el("button", "cbm-button cbm-button--secondary", a[1]); b.type = "button";
      b.addEventListener("click", function () { runReview(p, a, after); });
      box.appendChild(b);
    });
    return box;
  }

  function runReview(p, a, after) {
    var why = reviewWhyNot(p, a[0]);
    if (why) { notice(why, "warn"); modalMsg(why, "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, (p.businessName || p.name) + " — " + a[1].replace("…", "")));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, a[2]); lab.htmlFor = "rv_note";
    var ta = el("textarea"); ta.id = "rv_note"; ta.rows = 3; ta.maxLength = 4000; f.appendChild(lab); f.appendChild(ta); body.appendChild(f);
    openModal(a[1].replace("…", ""), body, async function () {
      if (a[3] && !ta.value.trim()) { modalMsg("Say why — the note is required.", "error"); return; }
      await api("/prospects/" + encodeURIComponent(p.id) + "/review", { method: "POST", body: { action: a[0], note: ta.value } });
      closeModal(); notice(a[1].replace("…", "") + ": " + (p.businessName || p.name) + ".", "ok");
      if (after) after();
    }, a[1].replace("…", ""));
    setTimeout(function () { ta.focus(); }, 50);
  }

  // --- the Review tab: the leads waiting at Unqualified ----------------------------------------
  async function loadReview() {
    try {
      state.review = (await api("/prospects?status=Unqualified&exit=none")).prospects || [];
      renderReview();
    } catch (e) { notice(e.message, "error"); }
  }

  function renderReview() {
    var q = ($("reviewSearch").value || "").toLowerCase();
    var rows = (state.review || []).filter(function (p) {
      return !q || [p.businessName, p.name, p.firstName, p.lastName, p.email, p.phone, p.website, p.mailingAddressCity, p.importBatch].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    var body = $("reviewRows"); body.innerHTML = "";
    rows.forEach(function (p) {
      var tr = el("tr");
      var nTd = el("td"); var a = el("a", "cm__link", p.businessName || p.name || "(unnamed)"); a.href = "#"; a.addEventListener("click", function (ev) { ev.preventDefault(); openProspect(p.id); }); nTd.appendChild(a); tr.appendChild(nTd);
      tr.appendChild(el("td", null, [p.firstName, p.lastName].filter(Boolean).join(" ") || "—"));
      tr.appendChild(el("td", null, p.phone || "—")); tr.appendChild(el("td", null, p.email || "—")); tr.appendChild(el("td", null, p.website || "—"));
      tr.appendChild(el("td", null, p.mailingAddressCity || "—")); tr.appendChild(el("td", null, p.importBatch || "—"));
      var aTd = el("td");
      [REVIEW_ACTIONS[0], REVIEW_ACTIONS[1]].forEach(function (act) {
        var b = el("button", "cm__rowbtn", act[1]); b.type = "button";
        b.addEventListener("click", function () { runReview(p, act, loadReview); }); aTd.appendChild(b);
      });
      tr.appendChild(aTd); body.appendChild(tr);
    });
    text($("reviewCount"), rows.length + " waiting");
    $("reviewEmpty").hidden = rows.length > 0;
  }

  // --- imports ---------------------------------------------------------------------------------------
  async function loadImports() {
    try {
      var res = await api("/prospects/imports");
      var body = $("importRows"); body.innerHTML = "";
      (res.batches || []).forEach(function (b) {
        var tr = el("tr");
        tr.appendChild(el("td", null, b.name)); tr.appendChild(el("td", null, b.source)); tr.appendChild(el("td", "num", b.rowCount)); tr.appendChild(el("td", null, b.status));
        tr.appendChild(el("td", null, fmtDate(b.createdAt))); tr.appendChild(el("td", null, b.appliedAt ? fmtDate(b.appliedAt) : "—"));
        var c = b.result || b.counts || {};
        tr.appendChild(el("td", null, Object.keys(c).filter(function (k) { return typeof c[k] === "number"; }).map(function (k) { return k + " " + c[k]; }).join(", ") || "—"));
        body.appendChild(tr);
      });
      text($("importsCount"), (res.batches || []).length + " recent");
      $("importsEmpty").hidden = (res.batches || []).length > 0;
    } catch (e) { notice(e.message, "error"); }
  }

  function openImport() {
    var body = el("div", "cm__plan");
    var fields = el("div", "cm__fields");
    function field(label, input, wide) { var f = el("div", "cm__field" + (wide ? " cm__field--wide" : "")); var l = el("label", null, label); l.htmlFor = input.id; f.appendChild(l); f.appendChild(input); fields.appendChild(f); return input; }
    var name = el("input"); name.type = "text"; name.id = "im_name"; name.maxLength = 255; name.placeholder = "e.g. State filings, October 2026"; field("Batch name", name, true);
    var door = el("select"); door.id = "im_door"; [["State filing", "State filing (a row with a website or email enters Qualified — ruling 53)"], ["List", "Purchased list (enters Unqualified — ruling 18)"], ["Partner file", "Partner file (enters Unqualified — ruling 18)"]].forEach(function (o) { var opt = el("option", null, o[1]); opt.value = o[0]; door.appendChild(opt); }); field("Lead Source", door);
    var qb = el("input"); qb.type = "text"; qb.id = "im_qb"; qb.placeholder = "The filter's name and version"; field("Qualified by (filings)", qb);
    var ls = el("input"); ls.type = "text"; ls.id = "im_ls"; ls.placeholder = "Vendor or partner"; field("List source (lists)", ls);
    var file = el("input"); file.type = "file"; file.id = "im_file"; file.accept = ".csv,text/csv"; field("CSV file", file, true);
    body.appendChild(fields);
    body.appendChild(el("p", "cm__hint", "Columns: business_name (required), mailing_street, mailing_city, mailing_state, mailing_zip (required as a set), and optionally external_reference, website, email, phone, contact_first_name, contact_last_name, qualified_by. Every row becomes a lead; no Company or Contact is created until first contact (ruling 43). A list or partner file names its vendor or partner in List source; its rows wait in the Review tab at Unqualified. Unknown columns ride along into the lead."));
    var planBox = el("div", "cm__plan"); body.appendChild(planBox);
    var planned = null;
    function readFile() { return new Promise(function (resolve, reject) { var f = file.files && file.files[0]; if (!f) { reject(new Error("Choose a CSV file.")); return; } var r = new FileReader(); r.onload = function () { resolve(String(r.result || "")); }; r.onerror = function () { reject(new Error("The file could not be read.")); }; r.readAsText(f); }); }
    openModal("Import leads", body, async function () {
      if (!planned) {
        if (!name.value.trim()) { modalMsg("Name the batch.", "error"); return; }
        var textContent = await readFile();
        planned = await api("/prospects/import/plan", { method: "POST", body: { name: name.value.trim(), source: door.value, text: textContent, qualifiedBy: qb.value, listSource: ls.value } });
        planBox.innerHTML = "";
        var c = planned.counts;
        tiles(planBox.appendChild(el("div", "cm__tiles")), [["Rows", c.rows], ["Leads to create", c.create], ["Enter Qualified", c.qualified], ["Enter Unqualified", c.unqualified], ["Duplicates", c.alreadyKnown], ["Repeat rows", c.knownRow + c.duplicate], ["Invalid", c.invalid]]);
        if (planned.priorBatch) planBox.appendChild(el("p", "cm__hint", "This exact file was applied before (" + fmtDate(planned.priorBatch.appliedAt) + ")."));
        if (planned.nothingToDo) planBox.appendChild(el("p", "cm__hint", "Nothing to do — every row is known or invalid."));
        var tbl = el("table", "cm__grid"); var tb = el("tbody");
        (planned.rows || []).forEach(function (r) { var tr = el("tr"); [r.name, r.postalCode, r.outcome === "already_known" ? "duplicate" : r.outcome.replace("_", " "), r.note || (r.status ? "enters " + r.status : "")].forEach(function (v) { tr.appendChild(el("td", null, v || "")); }); tb.appendChild(tr); });
        tbl.appendChild(tb); planBox.appendChild(tbl);
        modalMsg("Read the plan. Apply writes exactly this.", "ok");
        text($("modalSave"), planned.nothingToDo ? "Nothing to apply" : "Apply this plan");
        return;
      }
      if (planned.nothingToDo) { modalMsg("Nothing to apply.", "warn"); return; }
      var res = await api("/prospects/import/apply", { method: "POST", body: { batchId: planned.batchId } });
      var r = res.result;
      closeModal();
      notice("Imported: " + r.created + " leads (" + r.qualified + " Qualified, " + r.unqualified + " Unqualified), " + r.duplicates + " duplicates" + (r.errors ? ", " + r.errors + " errors (see the log)" : "") + ".", r.errors ? "warn" : "ok");
      loadProspects(); loadImports();
    }, "Plan");
  }

  // --- sections / boot ---------------------------------------------------------------------------------
  function showSection(name) {
    state.section = name;
    Array.prototype.forEach.call(document.querySelectorAll("#sectionNav .cm__navbtn"), function (b) { b.classList.toggle("is-active", b.getAttribute("data-section") === name); });
    $("campaignsPanel").hidden = name !== "campaigns"; $("prospectsPanel").hidden = name !== "prospects"; $("importsPanel").hidden = name !== "imports";
    $("reviewPanel").hidden = name !== "review";
    if (name === "prospects") loadProspects();
    if (name === "review") loadReview();
    if (name === "imports") loadImports();
  }
  Array.prototype.forEach.call(document.querySelectorAll("#sectionNav button.cm__navbtn"), function (b) { b.addEventListener("click", function () { showSection(b.getAttribute("data-section")); }); });
  $("callsNavLink").addEventListener("click", function (ev) {
    if (state.session && !state.session.callsOn) { ev.preventDefault(); notice("Campaign calls are switched off on this deployment (CAMPAIGNS_CALLS at /setup).", "warn"); }
  });

  function wireSort(tableId, sortState, render) {
    Array.prototype.forEach.call(document.querySelectorAll("#" + tableId + " th[data-sort]"), function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (sortState.key === key) sortState.dir = -sortState.dir; else { sortState.key = key; sortState.dir = 1; }
        Array.prototype.forEach.call(document.querySelectorAll("#" + tableId + " .cm__sortind"), function (s) { s.remove(); });
        th.appendChild(el("span", "cm__sortind", sortState.dir > 0 ? "▲" : "▼"));
        render();
      });
    });
  }

  $("newCampaignBtn").addEventListener("click", openNewCampaign);
  $("refreshBtn").addEventListener("click", loadCampaigns);
  $("campaignSearch").addEventListener("input", renderCampaigns);
  $("statusFilter").addEventListener("change", renderCampaigns);
  $("kindFilter").addEventListener("change", renderCampaigns);
  $("prospectSearch").addEventListener("input", renderProspects);
  ["stageFilter", "exitFilter", "doorFilter"].forEach(function (id) { $(id).addEventListener("change", loadProspects); });
  $("prospectRefreshBtn").addEventListener("click", loadProspects);
  $("reviewRefreshBtn").addEventListener("click", loadReview);
  $("reviewSearch").addEventListener("input", renderReview);
  $("importBtn").addEventListener("click", openImport); $("importBtn2").addEventListener("click", openImport);
  $("blockedReloadBtn").addEventListener("click", function () { location.reload(); });
  // The lock guards against editing one record in two tabs. When the other tab
  // is not where the person is, they decide: open here anyway (the other tab,
  // if real, keeps working; the last save wins).
  $("blockedOpenBtn").addEventListener("click", async function () {
    hide($("blockedView"));
    await loadRecord();
  });
  wireSort("campaignGrid", state.sort, renderCampaigns);
  wireSort("prospectGrid", state.psort, renderProspects);

  (async function init() {
    try {
      state.session = await api("/session");
    } catch (e) {
      if (e.status === 404) { text($("offReason"), "Campaign Management is switched off on this deployment (CAMPAIGNS_ENABLED at /setup)."); show($("offPanel")); }
      else if (e.status === 403) { text($("offReason"), e.message); show($("offPanel")); }
      else notice(e.message, "error");
      return;
    }
    text($("whoName"), state.session.name || state.session.userName); show($("userCorner"));
    if (!state.session.available) { text($("offReason"), state.session.reason); show($("offPanel")); return; }
    if (!state.session.storeAvailable) notice("The application database is not configured here, so links and imports are unavailable; campaigns themselves still work.", "warn");
    try {
      await ensureFields();
      fillSelect($("statusFilter"), state.fields.options.campaignStatus, 1); fillSelect($("kindFilter"), state.fields.options.campaignKind, 1);
      fillSelect($("stageFilter"), state.fields.prospectOptions.leadStatus, 1); fillSelect($("exitFilter"), state.fields.prospectOptions.sideExit, 2); fillSelect($("doorFilter"), state.fields.prospectOptions.leadSource, 1);
    } catch (e) { notice(e.message, "error"); }
    if (RECORD_ID) {
      $("sectionNav").hidden = true;
      var owner = await acquireRecordLock("campaigns:" + RECORD_ID);
      if (!owner) { show($("blockedView")); return; }
      await loadRecord();
    } else {
      show($("campaignsPanel"));
      await loadCampaigns();
      var hash = (location.hash || "").replace("#", "");
      if (hash === "prospects" || hash === "imports" || hash === "review") showSection(hash);
    }
  })();
})();
