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
  // The lead's own page, /campaigns/lead/{id} (build plan § 7e.4).
  var LEAD_ID = segs[2] === "lead" ? decodeURIComponent(segs[3] || "") : null;
  var API = "/campaigns/api";
  var HOST = (document.querySelector('meta[name="cbm-org"]') || {}).content || "";

  var state = {
    session: null, fields: null,
    campaigns: [], sort: { key: "createdAt", dir: -1 },
    record: null, links: null, responses: null,
    section: "prospects",
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
    var waitMs = opts.timeoutMs || 60000;
    var timer = setTimeout(function () { ctrl.abort(); }, waitMs);
    var init = { method: opts.method || "GET", headers: { Accept: "application/json" }, signal: ctrl.signal, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    var res;
    try { res = await fetch(API + path, init); }
    catch (e) {
      // The browser's own words ("signal is aborted without reason", "Failed
      // to fetch") say nothing a person can act on (Doug, 10-20-26).
      if (e && e.name === "AbortError") throw Object.assign(new Error("The server did not answer within " + Math.round(waitMs / 1000) + " seconds. It may still be working: wait a minute, then press Refresh to see whether it finished before trying again."), { status: 0 });
      throw Object.assign(new Error("The server could not be reached — check the connection, then try again."), { status: 0 });
    }
    finally { clearTimeout(timer); }
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
  function closeModal() {
    hide($("modal"));
    var cancelled = modal.onCancel;
    modal.onSave = null; modal.onCancel = null;
    if (cancelled) cancelled();
  }
  // A yes-or-no, or a one-line answer, as a promise — the page's own dialog,
  // never the browser's. Resolves true / the typed text, or null on Cancel.
  function ask(title, message, opts) {
    opts = opts || {};
    var body = el("div");
    if (message) body.appendChild(el("p", null, message));
    var input = null;
    if (opts.input) {
      var lab = el("label", "cm__field cm__field--wide"); lab.appendChild(el("span", null, opts.input));
      input = el("input"); input.type = "text"; input.maxLength = 500; input.value = opts.value || "";
      lab.appendChild(input); body.appendChild(lab);
    }
    return new Promise(function (resolve) {
      var settled = false;
      function settle(v) { if (settled) return; settled = true; modal.onCancel = null; resolve(v); }
      modal.onCancel = function () { settle(null); };
      openModal(title, body, function () {
        if (!input) { settle(true); closeModal(); return; }
        var v = input.value.trim();
        if (opts.required && !v) { modalMsg("This cannot be empty.", "error"); return; }
        settle(v); closeModal();
      }, opts.ok || "OK");
      if (input) {
        input.addEventListener("keydown", function (e) { if (e.key === "Enter") $("modalSave").click(); });
        setTimeout(function () { input.focus(); }, 0);
      }
    });
  }
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

  function campaignForm(record, chosenPartners, chosenEvents, chosenTeams, chosenFunders) {
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
    var rel = el("div", "cm__group"); rel.appendChild(el("h4", null, f.fundersAvailable ? "Partners, funders and events" : "Partners and events"));
    var partners = pickList("partners", "Partners", f.partnerOptions, chosenPartners, "The partners this campaign is for. A client who arrives through it is credited to every one.");
    // Ruling 57: funders a campaign names, shown once the CRM carries the link.
    var funders = f.fundersAvailable ? pickList("funders", "Funders", f.funderOptions, chosenFunders || [], "The funders paying for or sponsoring this campaign. It shows on each one's Campaigns tab; funders are not credited with the clients it brings in.") : null;
    var events = pickList("events", "Events", f.eventOptions, chosenEvents, "The events this campaign advertises.");
    rel.appendChild(partners); if (funders) rel.appendChild(funders); rel.appendChild(events); root.appendChild(rel);
    // Who calls: a call campaign's own teams. None named means the
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
               funderIds: funders && funders.getChosen ? funders.getChosen() : null,
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
      var res = await busyOver("campaignGrid", api("/campaigns"));
      state.campaigns = res.campaigns || [];
      if (gridListsOnly()) {
        fillRelationFilter($("eventFilter"), "events"); fillRelationFilter($("partnerFilter"), "partners"); fillRelationFilter($("funderFilter"), "funders");
      }
      renderCampaigns();
    } catch (e) { notice(e.message, "error"); }
  }

  // --- lists only: the flat grid --------------------------------------------------------
  var GRID_COLUMNS = [["Campaign", "name"], ["Channel", "campaignKind"], ["Stage", "stageOrder"], ["Event", "eventNames"],
    ["Partners", "partnerNames"], ["Funders", "funderNames"], ["Owner", "assignedUserName"], ["Dates", "startDate"],
    ["Reached", "reached", "num"], ["Responses", "submissions", "num"]];
  var GRID_STAGES = ["Draft", "Ready", "Signed off", "Sent", "Results"];
  function gridListsOnly() { return !!(state.session && state.session.listsOnlyOn); }

  // The shared grid (frontend/shared/grid.js; prds/shared-grid-plan.md § 8):
  // the Campaigns grid sorts here, on several columns, newest first by default.
  var campaignGrid = null;
  function sortCampaignRows(rows) {
    var keys = campaignGrid ? campaignGrid.keys() : [];
    if (!keys.length) keys = [{ col: "createdAt", dir: "desc" }];
    return window.CBMGrid ? CBMGrid.sortBy(rows, keys, function (c, col) { return c[col]; }) : rows;
  }
  function ensureCampaignGrid() {
    Array.prototype.forEach.call(document.querySelectorAll("#campaignGrid thead th"), function (th) {
      var k = th.getAttribute("data-sort");
      if (k) th.setAttribute("data-col", k); else th.setAttribute("data-sortable", "false");
    });
    if (!window.CBMGrid) return;
    if (!campaignGrid) campaignGrid = CBMGrid.enhance($("campaignGrid"), { key: "marketing.campaigns", onSort: function () { renderCampaigns(); } });
    else campaignGrid.refresh();
  }
  // A grid whose rows are drawn whole: the shared grid sorts the drawn rows.
  function gridify(id, key) {
    var t = $(id);
    if (!t || !window.CBMGrid) return;
    if (!t._cbmGrid) t._cbmGrid = CBMGrid.enhance(t, { key: key }); else t._cbmGrid.refresh();
  }
  function busyOver(id, promise) { return window.CBMBusy && CBMBusy.loading && $(id) ? CBMBusy.loading($(id), promise) : promise; }
  function setupListsOnlyGrid() {
    var tr = el("tr");
    GRID_COLUMNS.forEach(function (c) { var th = el("th", c[2] || null, c[0]); th.setAttribute("data-sort", c[1]); tr.appendChild(th); });
    var head = $("campaignHead"); head.innerHTML = ""; head.appendChild(tr);
    ensureCampaignGrid();
    hide($("statusFilterWrap")); text($("kindFilterText"), "Channel");
    ["stageFilterWrap", "eventFilterWrap", "partnerFilterWrap", "funderFilterWrap"].forEach(function (id) { show($(id)); });
    fillSelect($("stageFilter"), GRID_STAGES.concat(["Cancelled"]), 1);
    ["stageFilter", "eventFilter", "partnerFilter", "funderFilter"].forEach(function (id) { $(id).addEventListener("change", renderCampaigns); });
  }
  function names(items) { return (items || []).map(function (p) { return p.name; }).join(", "); }
  function fillRelationFilter(sel, key) {
    var keep = sel.value, seen = {}, opts = [];
    state.campaigns.forEach(function (c) { (c[key] || []).forEach(function (r) { if (!seen[r.id]) { seen[r.id] = 1; opts.push(r); } }); });
    opts.sort(function (a, b) { return a.name.localeCompare(b.name); });
    sel.innerHTML = ""; var all = el("option", null, "All"); all.value = ""; sel.appendChild(all);
    opts.forEach(function (r) { var o = el("option", null, r.name); o.value = r.id; sel.appendChild(o); });
    sel.value = keep && seen[keep] ? keep : "";
  }
  function hasRelation(c, key, id) { return !id || (c[key] || []).some(function (r) { return r.id === id; }); }
  function relationCell(items, link) {
    var td = el("td");
    if (items === null || items === undefined) { td.textContent = "—"; return td; }
    if (!items.length) { td.textContent = "none"; return td; }
    items.forEach(function (r, i) {
      if (i) td.appendChild(document.createTextNode(", "));
      if (link) { var a = el("a", "cm__link", r.name); a.href = link(r); a.target = "cbm-events"; td.appendChild(a); }
      else td.appendChild(document.createTextNode(r.name));
    });
    return td;
  }
  function renderCampaignsListsOnly() {
    var q = ($("campaignSearch").value || "").toLowerCase();
    var kind = $("kindFilter").value, stage = $("stageFilter").value;
    var ev = $("eventFilter").value, pa = $("partnerFilter").value, fu = $("funderFilter").value;
    state.campaigns.forEach(function (c) {
      c.stageWord = c.stage || (c.campaignKind === "Social media" ? (c.campaignStatus || "Draft") : "Cancelled");
      c.stageOrder = GRID_STAGES.indexOf(c.stage) >= 0 ? GRID_STAGES.indexOf(c.stage) : 9;
      c.eventNames = names(c.events); c.partnerNames = names(c.partners); c.funderNames = names(c.funders);
    });
    var rows = state.campaigns.filter(function (c) {
      if (kind && c.campaignKind !== kind) return false;
      if (stage && c.stageWord !== stage) return false;
      if (!hasRelation(c, "events", ev) || !hasRelation(c, "partners", pa) || !hasRelation(c, "funders", fu)) return false;
      if (!q) return true;
      return [c.name, c.campaignKind, c.stageWord, c.assignedUserName, c.eventNames, c.partnerNames, c.funderNames].join(" ").toLowerCase().indexOf(q) >= 0;
    });
    rows = sortCampaignRows(rows);
    var body = $("campaignRows"); body.innerHTML = "";
    rows.forEach(function (c) {
      var tr = el("tr");
      var nameTd = el("td"); var a = el("a", "cm__link", c.name || "(unnamed)");
      a.href = "/campaigns/record/" + encodeURIComponent(c.id);
      a.addEventListener("click", function (e) {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1) return;
        e.preventDefault(); window.open(a.href, "cbm-rec-campaigns-" + c.id);
      });
      nameTd.appendChild(a); tr.appendChild(nameTd);
      tr.appendChild(el("td", null, c.campaignKind || "—"));
      var stTd = el("td"); stTd.appendChild(el("span", statusClass(c.campaignStatus), c.stageWord)); tr.appendChild(stTd);
      // The event's own page; its campaigns roll-up arrives later.
      tr.appendChild(relationCell(c.events, function (r) { return "/events/?event=" + encodeURIComponent(r.id); }));
      tr.appendChild(relationCell(c.partners)); tr.appendChild(relationCell(c.funders));
      tr.appendChild(el("td", null, c.assignedUserName || "—"));
      tr.appendChild(el("td", null, (c.startDate || c.endDate) ? (fmtDate(c.startDate) + " – " + fmtDate(c.endDate)) : "—"));
      tr.appendChild(el("td", "num", c.reached == null ? "—" : c.reached)); tr.appendChild(el("td", "num", c.submissions));
      body.appendChild(tr);
    });
    text($("campaignCount"), rows.length + " of " + state.campaigns.length);
    $("campaignsEmpty").hidden = state.campaigns.length > 0;
  }

  function renderCampaigns() {
    if (gridListsOnly()) { renderCampaignsListsOnly(); return; }
    var q = ($("campaignSearch").value || "").toLowerCase();
    var st = $("statusFilter").value, kind = $("kindFilter").value;
    var rows = state.campaigns.filter(function (c) {
      if (st && c.campaignStatus !== st) return false;
      if (kind && c.campaignKind !== kind) return false;
      if (!q) return true;
      var hay = [c.name, c.campaignKind, c.campaignStatus, c.assignedUserName, (c.partners || []).map(function (p) { return p.name; }).join(" ")].join(" ").toLowerCase();
      return hay.indexOf(q) >= 0;
    });
    rows = sortCampaignRows(rows);
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

  // The short form: the essentials only — channel, name, owner (the creator by
  // default) and optionally events, partners and funders. Content, list and
  // dates are set on the campaign's page.
  async function openNewCampaignShort() {
    var f = state.fields, me = state.session.userId || "";
    var body = el("div", "cm__plan");
    var grid = el("div", "cm__fields"); body.appendChild(grid);
    function field(label, id, input) {
      var w = el("div", "cm__field"); var l = el("label", null, label); l.htmlFor = id; input.id = id;
      w.appendChild(l); w.appendChild(input); grid.appendChild(w); return input;
    }
    var kind = el("select"); kind.appendChild(el("option", null, "—")).value = "";
    (f.options.campaignKind || []).forEach(function (o) {
      var opt = el("option", null, o); opt.value = o;
      if (f.kindsBuilt.indexOf(o) < 0) { opt.disabled = true; opt.textContent = o + " (a later phase)"; }
      kind.appendChild(opt);
    });
    field("Channel *", "nc_kind", kind);
    var name = el("input"); name.type = "text"; name.maxLength = 255; field("Name *", "nc_name", name);
    var owner = el("select"); var mine = el("option", null, state.session.name || "Me"); mine.value = me; owner.appendChild(mine);
    field("Owner", "nc_owner", owner);
    loadOwnerOptions().then(function (opts) {
      owner.innerHTML = "";
      if (!opts.some(function (o) { return o.id === me; })) { var o0 = el("option", null, state.session.name || "Me"); o0.value = me; owner.appendChild(o0); }
      opts.forEach(function (o) { var op = el("option", null, o.name); op.value = o.id; owner.appendChild(op); });
      owner.value = me;
    }).catch(function () { /* the creator stays the owner */ });
    var rel = el("div", "cm__group"); rel.appendChild(el("h4", null, f.fundersAvailable ? "Events, partners and funders (optional)" : "Events and partners (optional)"));
    var events = pickList("events", "Events", f.eventOptions, [], "The events this campaign advertises.");
    var partners = pickList("partners", "Partners", f.partnerOptions, [], "The partners this campaign is for. A client who arrives through it is credited to every one.");
    var funders = f.fundersAvailable ? pickList("funders", "Funders", f.funderOptions, [], "The funders paying for or sponsoring this campaign.") : null;
    rel.appendChild(events); rel.appendChild(partners); if (funders) rel.appendChild(funders); body.appendChild(rel);
    body.appendChild(el("p", "cm__hint", "The list, the content and the dates are set on the campaign's page, which opens in its own tab."));
    openModal("New campaign", body, async function () {
      if (!kind.value) { modalMsg("Choose the campaign's channel.", "error"); return; }
      if (!name.value.trim()) { modalMsg("Give the campaign a name.", "error"); return; }
      var data = { changes: { name: name.value.trim(), campaignKind: kind.value },
        eventIds: f.eventOptions ? events.getChosen() : null, partnerIds: f.partnerOptions ? partners.getChosen() : null,
        funderIds: funders && f.funderOptions ? funders.getChosen() : null };
      var res = await api("/campaigns", { method: "POST", body: data });
      if (owner.value && owner.value !== me) {
        try { await api("/campaigns/" + encodeURIComponent(res.campaign.id) + "/owner", { method: "PUT", body: { userId: owner.value } }); }
        catch (e) { notice("Created \"" + res.campaign.name + "\", but the owner could not be changed: " + e.message, "warn"); }
      }
      closeModal();
      notice("Created \"" + res.campaign.name + "\" as a draft.", "ok");
      window.open("/campaigns/record/" + encodeURIComponent(res.campaign.id), "cbm-rec-campaigns-" + res.campaign.id);
      loadCampaigns();
    }, "Create");
    setTimeout(function () { kind.focus(); }, 50);
  }

  async function openNewCampaign() {
    try { await ensureFields(); } catch (e) { notice(e.message, "error"); return; }
    if (gridListsOnly()) { await openNewCampaignShort(); return; }
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
    var form = campaignForm(rec.campaign, (rec.partners || []).map(function (p) { return p.id; }), (rec.events || []).map(function (p) { return p.id; }), rec.callerTeamIds || [], (rec.funders || []).map(function (p) { return p.id; }));
    openModal("Edit campaign", form, async function () {
      var data = form.collect();
      if (!data.changes.name) { modalMsg("A campaign needs a name.", "error"); return; }
      var changes = {};
      Object.keys(data.changes).forEach(function (k) { if ((data.changes[k] || "") !== (rec.campaign[k] || "")) changes[k] = data.changes[k]; });
      if (Object.keys(changes).length) await api("/campaigns/" + encodeURIComponent(rec.campaign.id), { method: "PUT", body: { changes: changes } });
      var rel = {};
      if (data.partnerIds !== null) rel.partnerIds = data.partnerIds;
      if (data.funderIds !== null && rec.funders !== null) rel.funderIds = data.funderIds;
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

  // --- the owner picker: any team member may hand a campaign on ---
  var ownerOptions = null;
  async function loadOwnerOptions() {
    if (ownerOptions) return ownerOptions;
    var data = await api("/owner-options");
    ownerOptions = (data && data.options) || [];
    return ownerOptions;
  }

  function ownerCell(c) {
    var dd = el("dd", "cm__owner");
    var sel = el("select", "cm__owner-select"); sel.setAttribute("aria-label", "Owner");
    var cur = el("option", null, c.assignedUserName || "— nobody —"); cur.value = c.assignedUserId || ""; sel.appendChild(cur);
    var btn = el("button", "cbm-button cbm-button--secondary cm__owner-save", "Save owner"); btn.type = "button";
    dd.appendChild(sel); dd.appendChild(btn);
    loadOwnerOptions().then(function (opts) {
      sel.innerHTML = "";
      var listed = opts.some(function (o) { return o.id === c.assignedUserId; });
      if (!listed) {
        var o0 = el("option", null, c.assignedUserId ? (c.assignedUserName || "Current owner") + " (not on the team)" : "— nobody —");
        o0.value = c.assignedUserId || ""; sel.appendChild(o0);
      }
      opts.forEach(function (o) { var op = el("option", null, o.name); op.value = o.id; sel.appendChild(op); });
      sel.value = c.assignedUserId || "";
    }).catch(function (e) { notice("Could not list the people who may own a campaign: " + e.message, "error"); });
    btn.addEventListener("click", async function () {
      if (!sel.value) { notice("Choose the person who should own this campaign.", "error"); return; }
      if (sel.value === (c.assignedUserId || "")) { notice("The owner is unchanged — nothing to save.", "ok"); return; }
      try {
        var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/owner", { method: "PUT", body: { userId: sel.value } });
        notice(res && res.changed ? "Owner changed to " + sel.options[sel.selectedIndex].text + "." : "The owner is unchanged — nothing to save.", "ok");
        loadRecord();
      } catch (e) { notice(e.message, "error"); }
    });
    return dd;
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
      // The sign-off record and the run belong to every kind that
      // selects an audience; the mail-vendor facts to the postcard alone.
      var selecting = ["Postcard", "Call", "SMS", "Email"].indexOf(c.campaignKind) >= 0;
      if (c.campaignKind !== "Postcard" && ["Mail vendor template", "Postcard size", "Estimated cost"].indexOf(p[0]) >= 0) return;
      if (!selecting && ["Selection", "Pieces signed off", "People signed off", "People on the list", "Signed off by", "Signed off at", "Run started", "Run completed"].indexOf(p[0]) >= 0) return;
      if (c.campaignKind !== "Social media" && p[0] === "Platform") return;
      if (p[0] === "Owner") { facts.appendChild(el("dt", null, p[0])); facts.appendChild(ownerCell(c)); return; }
      facts.appendChild(el("dt", null, p[0])); facts.appendChild(el("dd", null, p[1] == null || p[1] === "" ? "—" : p[1]));
    });
    chips($("recPartners"), rec.partners, "No partner named."); chips($("recEvents"), rec.events, "No event linked.");
    $("recFundersCard").hidden = rec.funders === null || rec.funders === undefined;
    if (!$("recFundersCard").hidden) chips($("recFunders"), rec.funders, "No funder named.");
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
      else text(note, "Build the list, read the count and the cost, then sign off. Nothing is mailed until signed.");
    } else hide(pc);
    renderCallCard(rec);
    renderSmsCard(rec);
    renderEmailCard(rec);
    renderAudience(rec);
    renderListsOnly(rec);
    show($("recordPanel"));
  }

  // --- lists only: the strip and the Audience and content tab (build plan § 7e.9) ----------------
  function listsOnly() { return !!(state.record && state.record.listsOnly); }
  var RUN_CARDS = ["audienceCard", "postcardCard", "emailCard", "smsCard", "callCard"];
  var TAB_OF = { "Overview": "overview", "Audience and content": "audience", "Links": "links", "Responses": "responses", "Results": "analytics" };
  function placeCards(on) {
    var host = on ? $("audHost") : $("recNotesCard").parentNode;
    RUN_CARDS.forEach(function (id) {
      var card = $(id);
      if (on) host.appendChild(card); else host.insertBefore(card, $("recNotesCard"));
    });
  }
  function renderListsOnly(rec) {
    var on = !!rec.listsOnly;
    placeCards(on);
    $("audienceTabBtn").hidden = !on;
    $("recipientsTabBtn").hidden = !on;
    text($("resultsTabBtn"), on ? "Results" : "Analytics");
    // The rule boxes are gone: a campaign sends to its list.
    Array.prototype.forEach.call(document.querySelectorAll(".cm__rule"), function (box) { if (on) box.hidden = true; });
    var s = rec.strip, strip = $("recStrip");
    if (!on || !s) { hide(strip); return; }
    var ol = $("recStages"); ol.innerHTML = "";
    var at = s.current ? s.stages.indexOf(s.current) : -1;
    s.stages.forEach(function (name, i) {
      var li = el("li", "cm__stage" + (i < at ? " cm__stage--done" : i === at ? " cm__stage--now" : ""), name);
      if (i === at) li.setAttribute("aria-current", "step");
      ol.appendChild(li);
    });
    text($("recNext"), s.next || "");
    $("recNextGo").setAttribute("data-go", TAB_OF[s.tab] || "overview");
    text($("recNextGo"), "Go to " + (s.tab || "Overview"));
    show(strip);
  }
  $("recNextGo").addEventListener("click", function () {
    var tab = $("recNextGo").getAttribute("data-go") || "overview";
    var btn = document.querySelector('#recordTabs .cm__tab[data-tab="' + tab + '"]');
    if (btn) btn.click();
  });
  // A build sends no rule while lists only is on; a campaign must have its list.
  function buildBody(rule) { return listsOnly() ? {} : { rule: rule }; }
  function refuseWithoutList() {
    if (!listsOnly() || listChosen()) return false;
    notice("Choose a list first — on the Audience and content tab, then press Use this list.", "warn");
    return true;
  }

  // --- the campaign's list (build plan § 7c) ----------------------------------------------------
  state.audience = null;
  function listChosen() { return !!(state.audience && state.audience.listId); }
  function audienceNote(res) {
    var a = res && res.audience;
    if (!a) return "";
    var skipped = (a.skipped || []).map(function (x) { return x.count + " " + x.reason; }).join("; ");
    return "From the list \u201c" + a.list.name + "\u201d (version " + a.list.version + "): " + a.members + " members, " +
      a.reached + " reached" + (skipped ? " — skipped: " + skipped : "") + ". ";
  }
  async function renderAudience(rec) {
    var c = rec.campaign, card = $("audienceCard");
    var selecting = ["Postcard", "Call", "SMS", "Email"].indexOf(c.campaignKind) >= 0;
    if (!selecting || !state.session || !state.session.listsOn) { hide(card); state.audience = null; return; }
    show(card);
    var sel = $("audList");
    try {
      var both = await Promise.all([api("/campaigns/" + encodeURIComponent(c.id) + "/audience"), api("/lists")]);
      state.audience = both[0].audience;
      sel.innerHTML = "";
      var copyEmail = c.campaignKind === "Email" && emailCopyMode();
      var none = el("option", null, copyEmail || rec.listsOnly ? "No list chosen" : "No list — use this kind's own rule below"); none.value = ""; sel.appendChild(none);
      // The ready-made lists first, each named as such.
      var lists = (both[1].lists || []).slice().sort(function (x, y) { return (y.system ? 1 : 0) - (x.system ? 1 : 0); });
      lists.forEach(function (l) {
        if (l.status === "retired" && !(state.audience && state.audience.listId === l.id)) return;
        var o = el("option", null, l.name + " (" + (l.system ? "ready-made" : l.kind) + (l.status === "retired" ? ", retired" : "") + ")"); o.value = l.id; sel.appendChild(o);
      });
      sel.value = state.audience ? state.audience.listId : "";
      $("audEvery").checked = !!(state.audience && state.audience.includeEveryContact);
    } catch (e) { notice(e.message, "error"); return; }
    var a = state.audience, open = $("audOpen");
    open.href = "/campaigns/#lists" + (a ? "?list=" + encodeURIComponent(a.listId) : "");
    text($("audState"), a
      ? "Sends to the " + a.listKind + " list \u201c" + a.listName + "\u201d, now at version " + a.listVersion + "," +
        (a.includeEveryContact ? " every contact on each client, partner or funder." : " the primary contact of each client, partner or funder.") +
        (a.builtVersion ? " Last built from version " + a.builtVersion + " on " + fmtDate(a.builtAt) + "." : " Not built yet.") +
        (rec.listsOnly ? "" : " The rule ticks below are not used while a list is chosen.")
      : rec.listsOnly ? "No list chosen. Choose one above and press Use this list — every campaign sends to a list. The ready-made lists stand in for the old rules."
      : (c.campaignKind === "Email" && emailCopyMode()
        ? "No list chosen. An email goes to a list's copy in Constant Contact: choose a list that keeps one."
        : "No list chosen: Build the list uses this kind's own rule below."));
    if (rec.listsOnly) {
      text($("audHint"), "Every campaign sends to a list. The ready-made lists hold what each kind used to select; any list from the Lists tab will do. A client, partner or funder on the list reaches its primary contact, or every contact on the record when the box is ticked. Consent, exits, dead addresses and one card per business still apply to everyone on a list.");
      renderAudienceCounts(a);
    } else hide($("audCounts"));
    var skips = $("audSkips"); skips.innerHTML = "";
    ((a && a.build && a.build.skipped) || []).forEach(function (x) { skips.appendChild(el("li", null, x.count + " skipped — " + x.reason)); });
    Array.prototype.forEach.call(document.querySelectorAll(".cm__rule"), function (box) { box.classList.toggle("cm__rule--off", !!a); });
  }
  async function renderAudienceCounts(a) {
    var box = $("audCounts");
    if (!a) { hide(box); return; }
    try {
      var res = await api("/lists/" + encodeURIComponent(a.listId) + "/counts");
      if (res.neverRun) text(box, "Per channel: the list has not been run on the Lists tab yet, so only this campaign's own channel is counted (Build the list). Open the lists and press Run to count email, text and postcard.");
      else text(box, "Per channel, from the list's " + res.members + " members as last run: " +
        (res.counts || []).map(function (x) { return x.label + " " + x.count; }).join(" · ") + ".");
      show(box);
    } catch (e) { text(box, "The per-channel counts could not be read: " + e.message); show(box); }
  }
  $("audSave").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign;
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("The list cannot be changed once the campaign is " + c.campaignStatus + ".", "warn"); return; }
    try {
      await api("/campaigns/" + encodeURIComponent(c.id) + "/audience", { method: "PUT", body: { listId: $("audList").value || null, includeEveryContact: $("audEvery").checked } });
      notice($("audList").value ? "List chosen. Build the list to see who it reaches." : listsOnly() ? "List cleared — choose another before building." : "List cleared — the kind's own rule applies.", "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  // --- the email kind (§ 3.3; rulings 19, 25) ---------------------------------------------------
  var EMAIL_PUSHED = "pushed to the mailing list";
  // With copies on (build plan § 7e.9), an email campaign sends to its list's
  // copy in Constant Contact: build counts, sign-off syncs the copy, staff send
  // the notice there, then pick that email here.
  function emailCopyMode() { return !!(state.session && state.session.listSyncOn); }

  function renderEmailCopy(rec) {
    var c = rec.campaign, ec = rec.emailCopy || {}, built = ec.built || {};
    $("emailRuleBox").hidden = true;
    $("emailSentBtn").hidden = true;
    $("emailPickBtn").hidden = false;
    text($("emailSignoffBtn"), "Sign off and sync");
    var skipped = (built.skipped || []).reduce(function (n, x) { return n + (x.count || 0); }, 0);
    tiles($("emailTiles"), [["Reached", built.reached != null ? built.reached : "—"], ["Skipped", built.reached != null ? skipped : "—"],
      ["On the copy", c.pieceCount != null ? c.pieceCount : "—"], ["Email picked", ec.pickedEmailId ? "Yes" : "No"]]);
    var next = $("emailNext"), list = ec.listName ? "\u201c" + ec.listName + "\u201d" : "";
    var msg = "";
    if (!ec.listId) msg = "Next: choose a list (Audience and content). An email goes to a list's copy in Constant Contact.";
    else if (ec.problem) msg = "Next: " + ec.problem;
    else if (c.campaignStatus === "Signed off" && !ec.pickedEmailId) msg = "Next: send it in Constant Contact to " + list + ", then pick that email here.";
    else if (ec.pickedEmailId) msg = "Sent: the email picked here went to " + list + " from Constant Contact.";
    else if (!built.reached && built.reached !== 0) msg = "Next: build the list to count who " + list + " reaches.";
    else msg = "Next: sign off. Signing off brings the copy of " + list + " up to date in Constant Contact.";
    text(next, msg); next.hidden = false;
    var note = $("emailNote");
    if (!state.session.emailOn) text(note, "Campaign emails are switched off on this deployment (CAMPAIGNS_EMAIL at /setup).");
    else if (!state.session.mailingConnected) text(note, "The mailing service is not connected here (System Settings, Mailing).");
    else if (!ec.fieldAvailable) text(note, "This CRM has no place for the picked email yet, so Pick the email will refuse until the CRM change for the redesign is made.");
    else text(note, "The application never sends email: Constant Contact does. Design the notice there with this campaign's links (Links tab: the address to paste into a notice).");
  }

  function renderEmailCard(rec) {
    var c = rec.campaign, card = $("emailCard");
    if (c.campaignKind !== "Email") { hide(card); return; }
    show(card);
    if (emailCopyMode()) { renderEmailCopy(rec); return; }
    $("emailRuleBox").hidden = false; $("emailSentBtn").hidden = false; $("emailPickBtn").hidden = true; $("emailNext").hidden = true;
    text($("emailSignoffBtn"), "Sign off and push");
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
    if (refuseWithoutList()) return;
    var rule = emailRule();
    if (emailCopyMode() && !listChosen()) { notice("Choose a list for this email campaign first (Audience and content). An email goes to a list's copy in Constant Contact.", "warn"); return; }
    if (!listChosen() && !rule.stages.length && rule.dormantDays === null) { notice("Tick at least one stage, or the dormant clients.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: buildBody(rule) });
      if (res.copy) notice(audienceNote(res) + "The email will reach " + res.pieces + " " + (res.pieces === 1 ? "person" : "people") + ".", res.audience && res.audience.skipped.length ? "warn" : "ok");
      else notice(audienceNote(res) + "List built: " + res.pieces + " people (" + res.created + " new, " + res.cancelled + " dropped).", res.audience && res.audience.skipped.length ? "warn" : "ok");
      loadRecord();
    } catch (e) { notice(e.message, "error"); }
  });

  function emailSignoffToCopy() {
    var c = state.record.campaign, ec = state.record.emailCopy || {}, built = ec.built || {};
    if (!ec.listId) { notice("Choose a list for this email campaign first (Audience and content).", "warn"); return; }
    if (ec.problem) { notice(ec.problem, "warn"); return; }
    if (built.reached == null) { notice("Build the list first — it counts who the email will reach.", "warn"); return; }
    if (["Draft", "Awaiting sign-off", null, undefined, ""].indexOf(c.campaignStatus) < 0) { notice("A campaign at " + c.campaignStatus + " cannot be signed off.", "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "This brings the copy of \u201c" + ec.listName + "\u201d in Constant Contact up to date: " + built.reached + " " +
      (built.reached === 1 ? "person" : "people") + " when the list was built. Nobody is emailed until you send the notice from Constant Contact to that list."));
    body.appendChild(el("p", "cm__hint", "Type the number of people to confirm. The sync can take up to a minute."));
    var f = el("div", "cm__field"); var lab = el("label", null, "Number of people"); lab.htmlFor = "emailConfirm"; var inp = el("input"); inp.type = "text"; inp.id = "emailConfirm"; inp.autocomplete = "off";
    f.appendChild(lab); f.appendChild(inp); body.appendChild(f);
    openModal("Sign off and sync", body, async function () {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/signoff", { method: "POST", body: { confirm: inp.value }, timeoutMs: 70000 });
      var n = (res.campaign && res.campaign.pieceCount) || 0;
      closeModal(); notice("Signed off. The copy of \u201c" + ec.listName + "\u201d holds " + n + " " + (n === 1 ? "person" : "people") + ". Send the notice to it from Constant Contact, then pick that email here.", "ok"); loadRecord();
    }, "Sign off and sync");
    setTimeout(function () { inp.focus(); }, 50);
  }

  $("emailPickBtn").addEventListener("click", async function () {
    if (!state.record) return;
    var c = state.record.campaign, ec = state.record.emailCopy || {};
    if (ec.pickedEmailId) { notice("An email is already picked for this campaign.", "warn"); return; }
    if (c.campaignStatus !== "Signed off") { notice("Pick the email after the campaign is signed off and the email has gone out from Constant Contact.", "warn"); return; }
    var res;
    try { res = await api("/campaigns/" + encodeURIComponent(c.id) + "/emails", { timeoutMs: 70000 }); }
    catch (e) { notice(e.message, "error"); return; }
    var body = el("div", "cm__plan");
    var emails = res.emails || [];
    if (!emails.length) {
      body.appendChild(el("p", null, "No email has gone to \u201c" + res.listName + "\u201d from Constant Contact in the last 30 days. Send the notice there to that list, then come back and pick it."));
      openModal("Pick the email", body, async function () { closeModal(); }, "Close");
      return;
    }
    body.appendChild(el("p", null, "The emails sent from Constant Contact to \u201c" + res.listName + "\u201d in the last 30 days. Pick the one this campaign sent."));
    var group = el("div", "cm__pick");
    emails.forEach(function (m, i) {
      var lab = el("label", "cm__check"); var r = el("input"); r.type = "radio"; r.name = "emailPick"; r.value = m.id; r.id = "emailPick" + i;
      lab.appendChild(r); lab.appendChild(document.createTextNode(" " + (m.name || "(no name)") + (m.sentAt ? " — " + fmtDate(m.sentAt) : "") + (m.status ? " (" + m.status + ")" : "")));
      group.appendChild(lab);
    });
    body.appendChild(group);
    openModal("Pick the email", body, async function () {
      var picked = document.querySelector("input[name=emailPick]:checked");
      if (!picked) { modalMsg("Choose one of the emails first.", "warn"); return; }
      var out = await api("/campaigns/" + encodeURIComponent(c.id) + "/pick-email", { method: "POST", body: { emailId: picked.value }, timeoutMs: 70000 });
      closeModal(); notice("Picked \u201c" + out.email.name + "\u201d. The campaign is now Running.", "ok"); loadRecord();
    }, "Pick this email");
  });

  $("emailSignoffBtn").addEventListener("click", function () {
    if (!state.record) return;
    if (emailCopyMode()) { emailSignoffToCopy(); return; }
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
    if (chk.fieldAvailable === false) { prob.textContent = "This CRM has no Text message field on the campaign yet (the CRM change coutreach-entities-crm-handoff.md § 9 adds it)."; show(prob); }
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
    if (refuseWithoutList()) return;
    var stages = Array.prototype.filter.call(document.querySelectorAll("[data-smsstage]"), function (cb) { return cb.checked; }).map(function (cb) { return cb.value; });
    if (!listChosen() && !stages.length) { notice("Tick at least one stage to text.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: buildBody({ stages: stages }) });
      notice(audienceNote(res) + "List built: " + res.pieces + " to text (" + res.created + " new, " + res.cancelled + " dropped).", res.audience && res.audience.skipped.length ? "warn" : "ok");
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

  // --- the call kind (§ 3.4) ------------------------------------------------------
  function callsPageUrl() { return location.origin + "/campaigns/#calls"; }

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
    text($("callersLine"), rec.callerTeams ? "Who calls: members of " + rec.callerTeams.join(", ") + " (the teams named on this campaign; Edit to change them)." : "Who calls: the teams named on this campaign could not be read.");
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
    if (refuseWithoutList()) return;
    var callRule = chosenCallRule();
    if (!listChosen() && !callRule.statuses.length && !callRule.stages.length) { notice("Tick at least one lead status or stage to call.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: buildBody(callRule) });
      notice(audienceNote(res) + "List built: " + res.pieces + " to call (" + res.created + " new, " + res.cancelled + " dropped).", res.audience && res.audience.skipped.length ? "warn" : "ok");
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
    if (refuseWithoutList()) return;
    var postcardRule = currentRule();
    if (!listChosen() && !postcardRule.statuses.length && !postcardRule.stages.length) { notice("Tick at least one: Unqualified leads, Qualified leads, or Companies typed Prospect.", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/build", { method: "POST", body: buildBody(postcardRule) });
      notice(audienceNote(res) + "List built: " + res.pieces + " planned (" + res.created + " new, " + res.cancelled + " dropped). Estimated cost " + money(res.estimatedCost, res.currency) + ".", res.audience && res.audience.skipped.length ? "warn" : "ok");
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
    body.appendChild(el("p", "cm__hint", "Type the piece count to confirm. Nothing is mailed until you do."));
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

  var PASTE_TAG = "[[custom.cbm_lead_code]]";
  function pasteAddressShown() {
    return emailCopyMode() && !!(state.record && state.record.campaign && state.record.campaign.campaignKind === "Email");
  }

  function renderLinks() {
    var body = $("linkRows"); body.innerHTML = "";
    var links = (state.links || []).slice();
    // Lists only: the personal form (the landing page each person's code
    // opens) first, then the public forms, then the rest.
    if (listsOnly()) {
      var rank = function (l) { return l.destination_kind === "landing" ? 0 : l.destination_kind === "form" ? 1 : 2; };
      links.sort(function (x, y) { return rank(x) - rank(y); });
    }
    links.forEach(function (l) {
      var tr = el("tr");
      tr.appendChild(el("td", null, l.name));
      var sTd = el("td"); sTd.appendChild(el("span", "cm__short", l.shortUrl)); sTd.appendChild(document.createTextNode(" "));
      var copy = el("button", "cm__rowbtn", "Copy"); copy.type = "button"; copy.addEventListener("click", function () { copyText(l.shortUrl, copy); }); sTd.appendChild(copy);
      if (pasteAddressShown()) {
        // The address to paste into a notice (build plan § 7d.2): Constant
        // Contact fills in each person's own code. Nobody should type the tag.
        var paste = l.shortUrl.replace(/\/+$/, "") + "/" + PASTE_TAG;
        var pRow = el("div", "cm__paste"); pRow.appendChild(el("span", "cm__hint", "To paste into a notice: "));
        pRow.appendChild(el("span", "cm__short", paste)); pRow.appendChild(document.createTextNode(" "));
        var pCopy = el("button", "cm__rowbtn", "Copy"); pCopy.type = "button"; pCopy.addEventListener("click", function () { copyText(paste, pCopy); });
        pRow.appendChild(pCopy); sTd.appendChild(pRow);
      }
      tr.appendChild(sTd);
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
    gridify("linksGrid", "marketing.links");
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
    // Lists only: the Recipients tab replaces the Touches table.
    var ts = $("touchSection"); ts.hidden = !touches.length || listsOnly();
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
    gridify("responsesGrid", "marketing.responses");
    gridify("touchGrid", "marketing.touches");
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
      if (tab === "recipients") { rc.offset = 0; loadRecipients(); }
    });
  });

  // --- the Recipients tab (lists only): who the campaign reached ----------------------------
  var rc = { offset: 0, limit: 50, timer: null, grid: null };
  function rcQuery(extra) {
    var q = "q=" + encodeURIComponent($("rcSearch").value || "") + "&status=" + encodeURIComponent($("rcStatus").value || "");
    if (rc.grid && rc.grid.sortParam()) q += "&sort=" + encodeURIComponent(rc.grid.sortParam());
    return q + (extra || "");
  }
  async function loadRecipients() {
    var c = state.record && state.record.campaign; if (!c) return;
    // The shared grid, sorted by the server on several columns (§ 8).
    if (!rc.grid && window.CBMGrid) rc.grid = CBMGrid.enhance($("rcGrid"), { key: "marketing.recipients",
      onSort: function () { rc.offset = 0; loadRecipients(); } });
    var isEmail = c.campaignKind === "Email";
    $("rcReadBtn").hidden = !isEmail;
    text($("rcHint"), isEmail
      ? "Each person the email went to, from Constant Contact's report: delivered or bounced, opens and clicks. The report is read every night for 30 days after the email is picked; Read the report now reads it at once."
      : "Each person on the campaign's list as built, and what happened to each.");
    try {
      var res = await busyOver("rcGrid", api("/campaigns/" + encodeURIComponent(c.id) + "/recipients?" + rcQuery("&offset=" + rc.offset + "&limit=" + rc.limit)));
      var sel = $("rcStatus"), keep = sel.value;
      sel.innerHTML = ""; var all = el("option", null, "All"); all.value = ""; sel.appendChild(all);
      Object.keys(res.statusCounts || {}).sort().forEach(function (k) { var o = el("option", null, k + " (" + res.statusCounts[k] + ")"); o.value = k; sel.appendChild(o); });
      sel.value = keep;
      $("rcOpensHead").hidden = !res.opensRecorded;
      var body = $("rcRows"); body.innerHTML = "";
      res.recipients.forEach(function (r) {
        var tr = el("tr");
        tr.appendChild(el("td", null, r.who || "—")); tr.appendChild(el("td", null, r.reachedAt || "—"));
        var st = el("td"); st.appendChild(el("span", "cm__badge", r.status || "—")); if (r.vendorStatus && r.status === "Returned") st.appendChild(el("span", "cm__hint", " " + r.vendorStatus)); tr.appendChild(st);
        tr.appendChild(el("td", null, r.outcome || "—"));
        tr.appendChild(el("td", null, r.sentAt ? fmtDate(r.sentAt) : "—")); tr.appendChild(el("td", null, r.returnedAt ? fmtDate(r.returnedAt) : "—"));
        var op = el("td", "num", r.opens == null ? "—" : r.opens); op.hidden = !res.opensRecorded; tr.appendChild(op);
        tr.appendChild(el("td", "num", r.clicks || 0)); tr.appendChild(el("td", "num", r.scans || 0));
        body.appendChild(tr);
      });
      var shownTo = Math.min(res.offset + res.recipients.length, res.total);
      text($("rcCount"), res.total ? (res.offset + 1) + "–" + shownTo + " of " + res.total + (res.total !== res.all ? " (" + res.all + " in all)" : "") : "");
      $("rcEmpty").hidden = res.all > 0;
      rc.total = res.total;
    } catch (e) { notice(e.message, "error"); }
  }
  $("rcSearch").addEventListener("input", function () { clearTimeout(rc.timer); rc.timer = setTimeout(function () { rc.offset = 0; loadRecipients(); }, 300); });
  $("rcStatus").addEventListener("change", function () { rc.offset = 0; loadRecipients(); });
  $("rcPrev").addEventListener("click", function () {
    if (rc.offset === 0) { notice("This is the first page.", "ok"); return; }
    rc.offset = Math.max(0, rc.offset - rc.limit); loadRecipients();
  });
  $("rcNext").addEventListener("click", function () {
    if (rc.offset + rc.limit >= (rc.total || 0)) { notice("This is the last page.", "ok"); return; }
    rc.offset += rc.limit; loadRecipients();
  });
  $("rcExportBtn").addEventListener("click", function () {
    var c = state.record && state.record.campaign; if (!c) return;
    window.location.href = API + "/campaigns/" + encodeURIComponent(c.id) + "/recipients.csv?" + rcQuery();
  });
  $("rcReadBtn").addEventListener("click", async function () {
    var c = state.record && state.record.campaign; if (!c) return;
    if (!(state.session && state.session.sendReportOn)) { notice("The send report is switched off on this deployment (Campaign send report at /setup).", "warn"); return; }
    try {
      var res = await api("/campaigns/" + encodeURIComponent(c.id) + "/report", { method: "POST", timeoutMs: 70000 });
      notice(res.words, res.report && res.report.unmatched ? "warn" : "ok");
      rc.offset = 0; await loadRecord(); loadRecipients();
    } catch (e) { notice(e.message, "error"); }
  });

  // --- analytics tab: the campaign's dashboard (§ 6) -------------------------------------
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
  // --- the Leads and Review grids at volume (build plan § 7b) ---------------------------------
  // The CRM searches, sorts and counts; the grid asks for one page at a time.
  // The whole search rides the address (#prospects?q=… / #review?…), so it can
  // be bookmarked. Selection holds what the reviewer saw of each lead
  // (status and reason), which the server's guard compares before any write.
  var GRID_FILTERS = ["q", "status", "exit", "source", "batch", "place", "from", "to", "camp", "gate", "fit", "level", "replied", "assigned"];
  var GRID_PARAM = { q: "q", status: "status", exit: "exit", source: "source", batch: "batch", place: "place", from: "arrivedFrom", to: "arrivedTo", camp: "inCampaign", gate: "gate", fit: "minFit", level: "level", replied: "replied", assigned: "assigned" };
  // The filters the ladder folds behind "More filters" (build plan § 7e.4).
  var MORE_FILTERS = ["status", "exit", "from", "to", "camp", "gate", "fit"];
  var grids = {
    pf: { section: "prospects", review: false, offset: 0, limit: 50, total: 0, rows: [], sort: "createdAt:desc", dir: "", selected: {}, all: null, table: "prospectGrid", grid: null },
    rf: { section: "review", review: true, mode: "judge", offset: 0, limit: 50, total: 0, rows: [], sort: "createdAt:asc", dir: "", selected: {}, all: null, table: "reviewGrid", grid: null },
  };
  var REVIEW_MODES = ["judge", "contacts"];

  function gridQuery(px) {
    var g = grids[px], out = {};
    GRID_FILTERS.forEach(function (f) { var e = $(px + "_" + f); if (e && e.value.trim()) out[GRID_PARAM[f]] = e.value.trim(); });
    // The Review tab's mode rides the address like a filter (#review?mode=contacts).
    if (g.review && g.mode && g.mode !== "judge") out.mode = g.mode;
    out.sort = g.sort; if (g.dir) out.dir = g.dir;
    return out;
  }

  // The shared grid on Leads and Review (prds/shared-grid-plan.md § 8): the
  // server sorts, on several columns where the CRM has its sorted-list
  // endpoint, else on the first.
  function sortKeys(sort, dir) {
    var raw = String(sort || "");
    if (raw.indexOf(":") < 0 && raw.indexOf(",") < 0) return raw ? [{ col: raw, dir: dir === "asc" ? "asc" : "desc" }] : [];
    return raw.split(",").filter(Boolean).map(function (p) { var kv = p.split(":"); return { col: kv[0], dir: kv[1] === "desc" ? "desc" : "asc" }; });
  }
  function leadGridOn(px) {
    var g = grids[px];
    var ths = document.querySelectorAll("#" + g.table + " thead th");
    if (!window.CBMGrid) return;
    if (!g.grid) {
      g.grid = CBMGrid.enhance($(g.table), { key: "marketing." + g.section, onSort: function (keys) {
        g.sort = CBMGrid.sortParam(keys) || (g.review ? "createdAt:asc" : "createdAt:desc"); g.dir = ""; g.offset = 0; loadGrid(px);
      } });
    } else g.grid.refresh();
    g.grid.setSort(sortKeys(g.sort, g.dir), true);
    return ths;
  }
  function qs(obj) { return Object.keys(obj).filter(function (k) { return obj[k] !== "" && obj[k] != null; }).map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(obj[k]); }).join("&"); }

  function writeHash(px) {
    var g = grids[px], q = gridQuery(px);
    if (g.offset) q.offset = g.offset;
    var s = qs(q);
    try { history.replaceState(null, "", "#" + g.section + (s ? "?" + s : "")); } catch (_) {}
  }
  function readHash(px, params) {
    var g = grids[px];
    GRID_FILTERS.forEach(function (f) { var e = $(px + "_" + f); if (e && params[GRID_PARAM[f]] != null) e.value = params[GRID_PARAM[f]]; });
    if (g.review) g.mode = REVIEW_MODES.indexOf(params.mode) >= 0 ? params.mode : "judge";
    if (params.sort) { g.sort = params.sort; g.dir = params.dir || ""; }
    g.offset = Math.max(0, parseInt(params.offset || "0", 10) || 0);
  }
  function hashParams() {
    var h = (location.hash || "").replace(/^#/, ""), i = h.indexOf("?"), out = {};
    if (i < 0) return { section: h, params: out };
    h.slice(i + 1).split("&").forEach(function (kv) { if (!kv) return; var p = kv.split("="); out[decodeURIComponent(p[0])] = decodeURIComponent((p[1] || "").replace(/\+/g, " ")); });
    return { section: h.slice(0, i), params: out };
  }

  async function loadGrid(px) {
    var g = grids[px];
    g.lastKey = qs(gridQuery(px));
    var q = gridQuery(px); q.offset = g.offset; q.limit = g.limit; if (g.review) q.review = 1;
    writeHash(px);
    try {
      var res = await busyOver(g.table, api("/prospects?" + qs(q)));
      g.rows = res.prospects || []; g.total = res.total || 0;
      // A CRM without the sorted-list endpoint sorted by the first column only:
      // say so once, and show the sort that was used.
      if (res.multiSort === false && res.sort) {
        if (!g.toldOneColumn) { notice("This CRM sorts leads by one column at a time, so only the first column you chose was used.", "warn"); g.toldOneColumn = true; }
        g.sort = res.sort; g.dir = ""; writeHash(px);
        if (g.grid) g.grid.setSort(sortKeys(g.sort, ""), true);
      }
      // Lead enrichment's fit columns and filters: shown only when this CRM
      // carries the fit fields (the server says so on every page).
      g.fit = !!res.fit;
      Array.prototype.forEach.call(document.querySelectorAll("#" + (g.review ? "reviewPanel" : "prospectsPanel") + " .cm__fitonly"), function (e) { e.hidden = !g.fit; });
      // The ladder: the level and reach columns, Assigned to, the counts and
      // the shorter filter row — when the switch is on AND this CRM has the
      // fields (the server says so on every page).
      g.ladder = !!res.ladder;
      if (!g.review) { applyLadderLayout(); loadCounts(); } else applyReviewLayout();
      if (g.offset && !g.rows.length && g.total) { g.offset = Math.max(0, Math.floor((g.total - 1) / g.limit) * g.limit); return loadGrid(px); }
      (g.review ? renderReview : renderProspects)();
      renderPager(px); renderBulk(px);
    } catch (e) {
      // A contacts-mode address on a CRM without the ladder: say so, then
      // show the judge queue rather than an empty tab.
      if (g.review && g.mode === "contacts" && e.status === 400) { notice(e.message, "warn"); g.mode = "judge"; return loadGrid(px); }
      notice(e.message, "error");
    }
  }

  // --- the ladder on the Leads tab (build plan § 7e.4) ---------------------------------------
  function applyLadderLayout() {
    var g = grids.pf;
    Array.prototype.forEach.call(document.querySelectorAll("#prospectsPanel .cm__ladderonly"), function (e) { e.hidden = !g.ladder; });
    var anyMore = MORE_FILTERS.some(function (f) { var e = $("pf_" + f); return e && e.value.trim(); });
    var open = !g.ladder || g.moreOpen || anyMore;
    Array.prototype.forEach.call(document.querySelectorAll("#pf_filters .cm__morefilter"), function (e) {
      e.hidden = !open || (e.classList.contains("cm__fitonly") && !g.fit);
    });
    if ($("pf_more")) { text($("pf_more"), open ? "Fewer filters" : "More filters"); $("pf_more").setAttribute("aria-expanded", open ? "true" : "false"); }
    if (g.ladder) text($("pf_hint"), "Every lead, searched and counted by the CRM a page at a time. The counts across the top are filters: Unqualified, the three levels inside Qualified, replies waiting to be converted, Disqualified. Tick rows, or select everything the filters match, to Assign to a team member, Disqualify or mark Do Not Contact many at once. Open a lead to see what is known and reach them.");
    renderProspectHead();
  }
  var COUNT_CHIPS = [
    ["unqualified", "Unqualified", { status: "Unqualified", level: "", replied: "" }, true],
    ["identified", "Identified", { status: "Qualified", level: "Identified", replied: "" }, false],
    ["contactable", "Contactable", { status: "Qualified", level: "Contactable", replied: "" }, false],
    ["referred", "Referred", { status: "Qualified", level: "Referred", replied: "" }, false],
    ["replied", "Replied, not yet converted", { status: "", level: "", replied: "1" }, false],
    ["disqualified", "Disqualified", { status: "Disqualified", level: "", replied: "" }, true],
    // Mine (personal outreach): the Assigned-to filter preset to the signed-in
    // user, one chip. It leaves status, level and replied as they are.
    ["mine", "Mine", { assigned: "me" }, false],
  ];
  function chipKeys(c) { return Object.keys(c[2]); }
  function chipActive(c) {
    var want = c[2];
    return chipKeys(c).every(function (k) { var e = $("pf_" + k); return (e ? e.value.trim() : "") === (want[k] || ""); });
  }
  async function loadCounts() {
    var g = grids.pf, host = $("pf_counts");
    if (!g.ladder) { hide(host); return; }
    try {
      var q = gridQuery("pf"); delete q.sort; delete q.dir; delete q.status; delete q.level; delete q.replied;
      var res = await api("/prospects/counts" + (qs(q) ? "?" + qs(q) : ""));
      host.innerHTML = "";
      COUNT_CHIPS.forEach(function (c) {
        if (res[c[0]] == null) return;
        var b = el("button", "cm__countchip" + (c[3] ? " cm__countchip--muted" : "") + (chipActive(c) ? " is-active" : "")); b.type = "button";
        b.appendChild(el("strong", null, Number(res[c[0]]).toLocaleString())); b.appendChild(el("span", null, c[1]));
        b.title = chipActive(c) ? "Showing these leads — click to show every lead again." : "Show only these leads.";
        b.addEventListener("click", function () {
          var on = chipActive(c);
          chipKeys(c).forEach(function (k) { var e = $("pf_" + k); if (e) e.value = on ? "" : (c[2][k] || ""); });
          g.offset = 0; clearSelection("pf"); loadGrid("pf");
        });
        host.appendChild(b);
      });
      show(host);
    } catch (e) { hide(host); }
  }
  // The Leads grid's columns: the ladder's set when this CRM has the fields,
  // else the columns the tab always had.
  function levelCell(p) {
    var td = el("td");
    var status = p.leadStatus || "Unqualified";
    if (status === "Qualified") { td.textContent = p.qualificationLevel || "Qualified"; td.title = p.levelSetAt ? ("Set by hand" + (p.levelSetByHandName ? " by " + p.levelSetByHandName : "") + " " + fmtDate(p.levelSetAt)) : "Placed by the system from what the lead holds."; }
    else { td.textContent = status; td.className = "cm__level--unq"; }
    if (p.sideExit) { td.appendChild(el("span", "cm__level--stopped", " · " + p.sideExit)); }
    return td;
  }
  function reachCell(p) {
    var td = el("td"); var box = el("span", "cm__reach");
    var card = !!(p.mailingAddressStreet && p.addressStatus !== "Dead");
    var phone = !!p.phone;
    var mailable = p.leadStatus === "Qualified" && (p.qualificationLevel === "Contactable" || p.qualificationLevel === "Referred");
    var email = !!p.email && mailable;
    [["Card", card, card ? "A postcard can reach this address." : (p.addressStatus === "Dead" ? "The address is dead." : "No street address.")],
     ["Phone", phone, phone ? p.phone : "No phone number."],
     ["Email", email, !p.email ? "No email address." : (email ? p.email : "Has an email, but only a Contactable or Referred lead may be emailed personally.")]
    ].forEach(function (r) { var s = el("span", r[1] ? "" : "cm__reach--off", r[0]); s.title = r[2]; box.appendChild(s); });
    td.appendChild(box); return td;
  }
  function personCell(p) { return el("td", null, [p.firstName, p.lastName].filter(Boolean).join(" ") || "—"); }
  var LADDER_COLUMNS = [
    { label: "Business", sort: "name" },
    { label: "Level", sort: "qualificationLevel", title: "Unqualified, the level inside Qualified, or Disqualified." },
    { label: "Contact person", sort: "lastName" },
    { label: "Reach", title: "How the lead can be reached: a postcard, a phone call, a personal email." },
    { label: "Fit", sort: "fitScore", cls: "cm__fitonly", title: "The free pass's fit score, 0 to 100. Click a score for its reasons." },
    { label: "Assigned to", sort: "assignedUserName" },
    { label: "Lead Source", sort: "leadSource" },
    { label: "Last activity", sort: "modifiedAt" },
  ];
  var CLASSIC_COLUMNS = [
    { label: "Business", sort: "name" },
    { label: "Fit", sort: "fitScore", cls: "cm__fitonly", title: "The free pass's fit score, 0 to 100. Click a score for its reasons." },
    { label: "Service area", cls: "cm__fitonly" }, { label: "County", cls: "cm__fitonly" },
    { label: "Lead status", sort: "leadStatus" }, { label: "Stopped because", sort: "sideExit" }, { label: "Lead Source", sort: "leadSource" },
    { label: "City", sort: "mailingAddressCity" }, { label: "ZIP", sort: "mailingAddressPostalCode" }, { label: "Address", sort: "addressStatus" },
    { label: "Batch", sort: "importBatch" }, { label: "Arrived", sort: "createdAt" },
  ];
  function renderProspectHead() {
    var g = grids.pf, tr = $("prospectHead").querySelector("tr");
    Array.prototype.slice.call(tr.children, 1).forEach(function (c) { c.remove(); });
    (g.ladder ? LADDER_COLUMNS : CLASSIC_COLUMNS).forEach(function (c) {
      var th = el("th", c.cls || null, c.label);
      if (c.sort) th.setAttribute("data-col", c.sort); else th.setAttribute("data-sortable", "false");
      if (c.title) th.title = c.title;
      if (c.cls === "cm__fitonly") th.hidden = !g.fit;
      tr.appendChild(th);
    });
    leadGridOn("pf");
  }
  function openLead(id) {
    // Either grid's answer says whether this CRM has the ladder: a page opened
    // straight on the Review tab has never loaded the Leads grid (10-25-26).
    if (grids.pf.ladder || grids.rf.ladder) { window.open("/campaigns/lead/" + encodeURIComponent(id), "cbm-lead-" + id); return; }
    openProspect(id);
  }
  // The names the rest of the page already calls.
  function loadProspects() { return loadGrid("pf"); }
  function loadReview() { return loadGrid("rf"); }

  function renderPager(px) {
    var g = grids[px];
    var from = g.total ? g.offset + 1 : 0, to = Math.min(g.offset + g.rows.length, g.total);
    text($(px + "_count"), g.total ? (from.toLocaleString() + "–" + to.toLocaleString() + " of " + g.total.toLocaleString() + (g.review ? " waiting" : " leads")) : (g.review ? "0 waiting" : "0 leads"));
    $(px === "pf" ? "prospectsEmpty" : "reviewEmpty").hidden = g.total > 0;
  }
  function page(px, step) {
    var g = grids[px];
    var next = g.offset + step * g.limit;
    if (next < 0 || next >= g.total) { notice(step < 0 ? "This is the first page." : "This is the last page.", "warn"); return; }
    g.offset = next; loadGrid(px);
  }

  function tickCell(px, p) {
    var g = grids[px], td = el("td", "cm__tick"), box = el("input"); box.type = "checkbox";
    box.setAttribute("aria-label", "Select " + (p.businessName || p.name || "lead"));
    box.checked = !!g.all || !!g.selected[p.id];
    box.addEventListener("change", function () {
      if (g.all) { g.all = null; }
      if (box.checked) g.selected[p.id] = { id: p.id, leadStatus: p.leadStatus || "", sideExit: p.sideExit || "", qualificationLevel: p.qualificationLevel || "" };
      else delete g.selected[p.id];
      renderBulk(px);
    });
    td.appendChild(box); return td;
  }
  function selectedCount(px) { var g = grids[px]; return g.all ? g.all.length : Object.keys(g.selected).length; }
  function renderBulk(px) {
    var g = grids[px], n = selectedCount(px), bar = $(px + "_bulk");
    bar.hidden = n === 0;
    $(px + "_page").checked = g.rows.length > 0 && g.rows.every(function (p) { return g.all || g.selected[p.id]; });
    if (!n) return;
    text($(px + "_bulkcount"), g.all ? ("All " + n.toLocaleString() + " matching leads selected.") : (n.toLocaleString() + " selected."));
    var allBtn = $(px + "_all");
    allBtn.hidden = !!g.all || g.total <= n;
    text(allBtn, "Select all " + g.total.toLocaleString() + " matching");
  }
  function selectPage(px, on) {
    var g = grids[px]; g.all = null;
    g.rows.forEach(function (p) { if (on) g.selected[p.id] = { id: p.id, leadStatus: p.leadStatus || "", sideExit: p.sideExit || "" }; else delete g.selected[p.id]; });
    (g.review ? renderReview : renderProspects)(); renderBulk(px);
  }
  async function selectAllMatching(px) {
    var g = grids[px];
    try {
      var res = await api("/prospects/bulk/resolve", { method: "POST", body: { query: gridQuery(px), review: g.review } });
      g.all = res.items || []; g.selected = {};
      (g.review ? renderReview : renderProspects)(); renderBulk(px);
    } catch (e) { notice(e.message, "error"); }
  }
  function clearSelection(px) { var g = grids[px]; g.all = null; g.selected = {}; (g.review ? renderReview : renderProspects)(); renderBulk(px); }

  var BULK = {
    disqualify: ["Disqualify", "Why will these leads never be a client, partner or funder? (required)", true],
    "do-not-contact": ["Do Not Contact", "Note (optional)", false],
  };
  function openBulk(px, action) {
    var g = grids[px], items = g.all ? g.all.slice() : Object.keys(g.selected).map(function (k) { return g.selected[k]; });
    var b = BULK[action];
    if (!items.length) { notice("Tick at least one lead first.", "warn"); return; }
    var n = items.length;
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, b[0] + " " + n.toLocaleString() + " lead" + (n === 1 ? "" : "s") + "? Each lead is checked again first; one someone else has changed since you saw it is skipped, never overwritten."));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, b[1]); lab.htmlFor = "bk_note";
    var ta = el("textarea"); ta.id = "bk_note"; ta.rows = 3; ta.maxLength = 4000; f.appendChild(lab); f.appendChild(ta); body.appendChild(f);
    var prog = el("p", "cm__hint"); body.appendChild(prog);
    var running = false;
    openModal(b[0] + " " + n.toLocaleString() + " lead" + (n === 1 ? "" : "s"), body, async function () {
      if (running) return;
      if (b[2] && !ta.value.trim()) { modalMsg("Say why — the reason is required.", "error"); return; }
      running = true;
      var done = 0, skipped = [], failed = [];
      try {
        for (var i = 0; i < items.length; i += 50) {
          text(prog, "Working… " + Math.min(i, n).toLocaleString() + " of " + n.toLocaleString() + ".");
          var res = await api("/prospects/bulk", { method: "POST", body: { action: action, note: ta.value, items: items.slice(i, i + 50) } });
          done += (res.done || []).length; skipped = skipped.concat(res.skipped || []); failed = failed.concat(res.failed || []);
        }
      } catch (e) {
        failed.push({ name: "the remaining leads", why: e.message });
      }
      running = false;
      var summary = b[0] + ": " + done.toLocaleString() + " done, " + skipped.length + " skipped (changed meanwhile or not applicable), " + failed.length + " failed.";
      var detail = skipped.concat(failed).slice(0, 12).map(function (s) { return (s.name || s.id) + " — " + s.why; });
      text(prog, summary + (detail.length ? " " + detail.join(" · ") : ""));
      $("modalSave").hidden = true;
      notice(summary, failed.length ? "warn" : "ok");
      clearSelection(px); loadGrid(px);
    }, b[0]);
    setTimeout(function () { ta.focus(); }, 50);
  }

  // The fit score as a link that opens its reasons (prds/lead-enrichment/).
  function fitCell(p, withGate) {
    var td = el("td", "cm__fit");
    if (p.fitScore == null || p.fitScore === "") { td.textContent = "—"; td.title = "Not scored yet."; return td; }
    var a = el("a", "cm__link", String(p.fitScore) + (withGate && p.fitGate && p.fitGate !== "Passed" ? " · " + p.fitGate : ""));
    a.href = "#"; a.title = "Why this score";
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      var body = el("div");
      body.appendChild(el("p", null, "Fit score " + p.fitScore + " of 100 — service area: " + (p.fitGate || "—") + (p.fitCounty ? " (" + p.fitCounty + " County)" : "") + "."));
      var pre = el("p", "cm__fitreasons", p.fitReasons || "No reasons recorded."); pre.style.whiteSpace = "pre-line";
      body.appendChild(pre);
      openModal("Fit — " + (p.businessName || p.name || "lead"), body, null);
    });
    td.appendChild(a); return td;
  }
  function renderProspects() {
    var g = grids.pf, body = $("prospectRows"); body.innerHTML = "";
    g.rows.forEach(function (p) {
      var tr = el("tr");
      tr.appendChild(tickCell("pf", p));
      var nTd = el("td"); var a = el("a", "cm__link", p.businessName || p.name || "(unnamed)"); a.href = g.ladder ? ("/campaigns/lead/" + encodeURIComponent(p.id)) : "#"; a.addEventListener("click", function (ev) { ev.preventDefault(); openLead(p.id); }); nTd.appendChild(a); tr.appendChild(nTd);
      if (g.ladder) {
        tr.appendChild(levelCell(p)); tr.appendChild(personCell(p)); tr.appendChild(reachCell(p));
        if (g.fit) tr.appendChild(fitCell(p, true));
        tr.appendChild(el("td", null, p.assignedUserName || "—")); tr.appendChild(el("td", null, p.leadSource || "—"));
        tr.appendChild(el("td", null, fmtDate(p.modifiedAt || p.createdAt)));
      } else {
        if (g.fit) { tr.appendChild(fitCell(p, false)); tr.appendChild(el("td", null, p.fitGate || "—")); tr.appendChild(el("td", null, p.fitCounty || "—")); }
        tr.appendChild(el("td", null, p.leadStatus || "—")); tr.appendChild(el("td", null, p.sideExit || "—")); tr.appendChild(el("td", null, p.leadSource || "—"));
        tr.appendChild(el("td", null, p.mailingAddressCity || "—")); tr.appendChild(el("td", null, p.mailingAddressPostalCode || "—")); tr.appendChild(el("td", null, p.addressStatus || "—"));
        tr.appendChild(el("td", null, p.importBatch || "—")); tr.appendChild(el("td", null, fmtDate(p.createdAt)));
      }
      body.appendChild(tr);
    });
  }

  // Assign to…: the ticked leads, or all matching, go to one
  // member of the Marketing Admin Team, written as the signed-in user.
  async function openAssign(px) {
    var g = grids[px], items = g.all ? g.all.slice() : Object.keys(g.selected).map(function (k) { return g.selected[k]; });
    if (!items.length) { notice("Tick at least one lead first.", "warn"); return; }
    var options;
    try { options = await loadOwnerOptions(); } catch (e) { notice(e.message, "error"); return; }
    var n = items.length;
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "Assign " + n.toLocaleString() + " lead" + (n === 1 ? "" : "s") + " to one team member. A lead that is Converted, Disqualified or has stopped being worked is skipped, and says so."));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, "Team member"); lab.htmlFor = "as_user";
    var sel = el("select"); sel.id = "as_user"; var none = el("option", null, "Choose…"); none.value = ""; sel.appendChild(none);
    options.forEach(function (o) { var opt = el("option", null, o.name); opt.value = o.id; if (state.session && o.id === state.session.userId) opt.textContent = o.name + " (me)"; sel.appendChild(opt); });
    f.appendChild(lab); f.appendChild(sel); body.appendChild(f);
    var prog = el("p", "cm__hint"); body.appendChild(prog);
    var running = false;
    openModal("Assign " + n.toLocaleString() + " lead" + (n === 1 ? "" : "s"), body, async function () {
      if (running) return;
      if (!sel.value) { modalMsg("Choose the team member the leads go to.", "error"); return; }
      running = true;
      var done = 0, skipped = [], failed = [];
      try {
        for (var i = 0; i < items.length; i += 50) {
          text(prog, "Working… " + Math.min(i, n).toLocaleString() + " of " + n.toLocaleString() + ".");
          var res = await api("/prospects/bulk", { method: "POST", body: { action: "assign", assignee: sel.value, items: items.slice(i, i + 50) } });
          done += (res.done || []).length; skipped = skipped.concat(res.skipped || []); failed = failed.concat(res.failed || []);
        }
      } catch (e) { failed.push({ name: "the remaining leads", why: e.message }); }
      running = false;
      var who = sel.options[sel.selectedIndex].textContent;
      var summary = "Assigned to " + who + ": " + done.toLocaleString() + " done, " + skipped.length + " skipped, " + failed.length + " failed.";
      var detail = skipped.concat(failed).slice(0, 12).map(function (s) { return (s.name || s.id) + " — " + s.why; });
      text(prog, summary + (detail.length ? " " + detail.join(" · ") : ""));
      $("modalSave").hidden = true;
      notice(summary, failed.length ? "warn" : "ok");
      clearSelection(px); loadGrid(px);
    }, "Assign");
  }

  // --- the Review queue — the research queue in two modes (build plan § 7e.6) -----------------
  // Judge: Unqualified leads, decided on a website or an email. Contacts:
  // Qualified leads still at Identified, given a named person and a phone or
  // an email. The mode rides the address; the thead is drawn from it.
  var REVIEW_HINTS = {
    judge: "Leads waiting at Unqualified, oldest first. A lead needs a website or an email before it can be Qualified: Look it up, type what you find into the row and press Enter to Qualify — the cursor moves to the next lead. AI research fills the boxes from what the model found; Enter accepts them. Disqualify the obvious no's many at once by ticking them. Two reviewers can split the queue with the filters (one batch or ZIP each); a lead someone else has already decided is refused, naming who.",
    contacts: "Qualified leads still at Identified, oldest first: a real business with no named person and no direct line. Look it up, type the person's first and last name and a phone or an email, and press Enter — the lead becomes Contactable, leaves this queue and the cursor moves to the next. AI research fills the boxes from what the model found; Enter accepts them. A lead given only a name stays here until a phone or an email arrives. A lead someone else has already moved is refused, naming who."
  };
  var REVIEW_COLUMNS = {
    judge: [{ label: "Business", sort: "name" }, { label: "Fit", cls: "cm__fitonly", sort: "fitScore" }, { label: "Person", sort: "lastName" }, { label: "City", sort: "mailingAddressCity" }, { label: "Phone" }, { label: "Look it up" },
            { label: "Website" }, { label: "Email" }, { label: "AI research", title: "Fill the boxes from the AI model's findings, or start research on this lead." }, { label: "Decide" }, { label: "Batch", sort: "importBatch" }],
    contacts: [{ label: "Business", sort: "name" }, { label: "Fit", cls: "cm__fitonly", sort: "fitScore" }, { label: "City", sort: "mailingAddressCity" }, { label: "Look it up" }, { label: "First name" }, { label: "Last name" },
               { label: "Phone" }, { label: "Email" }, { label: "AI research", title: "Fill the boxes from the AI model's findings, or start research on this lead." }, { label: "Save" }, { label: "Batch", sort: "importBatch" }]
  };
  function renderReviewHead() {
    var g = grids.rf, tr = $("reviewHead").querySelector("tr");
    Array.prototype.slice.call(tr.children, 1).forEach(function (c) { c.remove(); });
    (REVIEW_COLUMNS[g.mode] || REVIEW_COLUMNS.judge).forEach(function (c) {
      var th = el("th", c.cls || null, c.label);
      if (c.sort) th.setAttribute("data-col", c.sort); else th.setAttribute("data-sortable", "false");
      if (c.title) th.title = c.title;
      if (c.cls === "cm__fitonly") th.hidden = !g.fit;
      tr.appendChild(th);
    });
    leadGridOn("rf");
  }
  function applyReviewLayout() {
    var g = grids.rf;
    // The contacts switch is offered only when this CRM carries the level;
    // with the ladder off, Review is exactly the judge queue.
    if ($("rf_mode_contacts")) $("rf_mode_contacts").hidden = !g.ladder;
    if (!g.ladder) g.mode = "judge";
    REVIEW_MODES.forEach(function (m) { var b = $("rf_mode_" + m); if (b) b.classList.toggle("is-active", g.mode === m); });
    text($("rf_hint"), REVIEW_HINTS[g.mode] || REVIEW_HINTS.judge);
    $("reviewEmpty").textContent = g.mode === "contacts" ? "No Identified lead is waiting for a contact." : "Nothing waiting for review.";
    renderReviewHead();
  }
  function setReviewMode(mode) {
    var g = grids.rf;
    if (g.mode === mode) return;
    g.mode = mode; g.offset = 0; clearSelection("rf"); loadGrid("rf");
  }
  function webSearchUrl(p) {
    var who = p.businessName || [p.firstName, p.lastName].filter(Boolean).join(" ") || p.name || "";
    var where = [p.mailingAddressCity, p.mailingAddressState].filter(Boolean).join(" ");
    return "https://www.google.com/search?q=" + encodeURIComponent((who + " " + where).trim());
  }
  function focusRow(i) {
    var rows = document.querySelectorAll("#reviewRows tr");
    var tr = rows[Math.min(i, rows.length - 1)];
    if (tr) { var inp = tr.querySelector("input.cm__rvbox"); if (inp) { inp.focus(); inp.select(); } }
  }
  function dropReviewRow(p, i) {
    var g = grids.rf;
    g.rows = g.rows.filter(function (r) { return r.id !== p.id; });
    delete g.selected[p.id];
    g.total = Math.max(0, g.total - 1);
    renderReview(); renderPager("rf"); renderBulk("rf");
    if (!g.rows.length && g.total) loadGrid("rf"); else focusRow(i);
  }
  function rowBox(cls, type, id, placeholder, value, label, short) {
    var td = el("td"), inp = el("input", "cm__rvbox " + cls + (short ? " cm__rvbox--short" : ""));
    inp.type = type; inp.id = id; inp.placeholder = placeholder; inp.value = value || ""; inp.autocomplete = "off";
    inp.setAttribute("aria-label", label);
    td.appendChild(inp); return { td: td, input: inp };
  }
  function seenOf(p) { return { seenStatus: p.leadStatus || "Unqualified", seenExit: p.sideExit || "", seenLevel: p.qualificationLevel || "" }; }

  // --- AI research on a row: fill the boxes from the lead's findings, or start a run -----------
  var aiStatus = null;
  function aiStatusCheck() {
    if (!aiStatus) aiStatus = fetch("/enrichment/api/status?targetType=lead", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { available: false, ready: false, reason: "AI research could not be checked (HTTP " + r.status + ")." }; })
      .catch(function () { return { available: false, ready: false, reason: "AI research could not be checked — the server did not answer." }; });
    return aiStatus;
  }
  function aiResearchButton(p, boxes, row) {
    // ``boxes`` maps a suggestion key (website, email, phone, firstName,
    // lastName) to the row's input for it; ``row.findingIds`` remembers which
    // findings filled the boxes, so Enter can close them Accepted.
    var btn = el("button", "cm__rowbtn", "AI research"); btn.type = "button";
    btn.title = "With findings on this lead: fill the empty boxes from them. Without: start AI research on this lead.";
    btn.addEventListener("click", async function () {
      var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
      try {
        var sug = await api("/prospects/" + encodeURIComponent(p.id) + "/suggestions");
        if (!sug.available) { notice("This CRM does not have the Enrichment Finding record type yet, so AI research cannot run here.", "warn"); return; }
        if (sug.findingIds && sug.findingIds.length) {
          var filled = [], WORDS = { website: "website", email: "email", phone: "phone", firstName: "first name", lastName: "last name" };
          Object.keys(boxes).forEach(function (k) {
            if (sug[k] && !boxes[k].value.trim()) { boxes[k].value = sug[k]; filled.push(k); }
          });
          row.findingIds = sug.findingIds;
          if (filled.length) { notice("Filled from AI research: " + filled.map(function (k) { return WORDS[k] || k; }).join(", ") + ". Check them, then press Enter to save and accept the findings.", "ok"); boxes[filled[0]].focus(); }
          else notice("The findings match what the row already holds. Press Enter to save and accept them, or edit a box first.", "ok");
          return;
        }
        if (sug.researching) { notice("AI research is still running for " + (p.businessName || p.name) + " — this usually takes one to three minutes. Press the button again when it finishes.", "warn"); return; }
        var st = await aiStatusCheck();
        if (!st.available || !st.ready) { notice(st.reason || "AI research is not available on this deployment.", "warn"); return; }
        if (!window.CBMEnrichment) { notice("The AI research script did not load — reload the page and try again.", "error"); return; }
        window.CBMEnrichment.startRun({ targetType: "lead", ids: [p.id],
          onStarted: function (r) { notice("AI research started on " + (p.businessName || p.name) + " (estimated $" + Number(r.estimate).toFixed(2) + "). Press AI research again in a minute or two to fill the boxes from what it found.", "ok"); } });
      } catch (e) { notice(e.message, "error"); }
      finally { done(); }
    });
    return btn;
  }

  async function qualifyRow(p, web, mail, i, btn, row) {
    if (!web.value.trim() && !mail.value.trim()) {
      notice("Type the website or email you found first. A lead without either can never be Qualified.", "warn");
      web.focus(); return;
    }
    if (row.saving) return;
    row.saving = true;
    var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
    try {
      await api("/prospects/" + encodeURIComponent(p.id) + "/review", { method: "POST", body: {
        action: "qualify", note: "", website: web.value.trim(), email: mail.value.trim(),
        seenStatus: p.leadStatus || "Unqualified", seenExit: p.sideExit || "" } });
      if (row.findingIds && row.findingIds.length) {
        // The boxes came from findings: close them Accepted (best-effort; the qualify stands).
        // The lead is Qualified now and placement may have given it a level,
        // so what was seen is the status alone — never the old (empty) level.
        try { await api("/prospects/" + encodeURIComponent(p.id) + "/contacts", { method: "POST", body: { findingIds: row.findingIds, seenStatus: "Qualified", seenExit: p.sideExit || "" } }); }
        catch (e2) { notice("Qualified, but the AI findings could not be marked accepted: " + e2.message, "warn"); }
      }
      notice("Qualified: " + (p.businessName || p.name) + ".", "ok");
      dropReviewRow(p, i);
    } catch (e) {
      notice(e.message, e.status === 409 ? "warn" : "error");
      if (e.status === 409) dropReviewRow(p, i);
    } finally { row.saving = false; done(); }
  }
  function disqualifyRow(p, i) {
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, (p.businessName || p.name) + " — Disqualify"));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, "Why will it never be a client, partner or funder? (required)"); lab.htmlFor = "rv_note";
    var ta = el("textarea"); ta.id = "rv_note"; ta.rows = 3; ta.maxLength = 4000; f.appendChild(lab); f.appendChild(ta); body.appendChild(f);
    openModal("Disqualify", body, async function () {
      if (!ta.value.trim()) { modalMsg("Say why — the note is required.", "error"); return; }
      try {
        await api("/prospects/" + encodeURIComponent(p.id) + "/review", { method: "POST", body: {
          action: "disqualify", note: ta.value, seenStatus: p.leadStatus || "Unqualified", seenExit: p.sideExit || "" } });
        closeModal(); notice("Disqualified: " + (p.businessName || p.name) + ".", "ok");
        dropReviewRow(p, i);
      } catch (e) {
        if (e.status === 409) { closeModal(); notice(e.message, "warn"); dropReviewRow(p, i); return; }
        throw e;
      }
    }, "Disqualify");
    setTimeout(function () { ta.focus(); }, 50);
  }

  // The contacts row's save: Enter in any box, or the Save button. The row
  // leaves the queue when the lead becomes Contactable or Referred; with only
  // a name it stays, and the notice says what is still needed. Like the lead
  // page's gap(), a save in flight or of what was just saved is not repeated.
  async function saveContactsRow(p, boxes, i, btn, row) {
    var typed = {};
    Object.keys(boxes).forEach(function (k) { typed[k] = boxes[k].value.trim(); });
    var key = JSON.stringify(typed) + "|" + (row.findingIds || []).join(",");
    if (row.saving || key === row.savedKey) return;
    var anyTyped = Object.keys(typed).some(function (k) { return typed[k] && typed[k] !== (p[k] || ""); });
    if (!anyTyped && !(row.findingIds && row.findingIds.length)) {
      notice("Type the person's first and last name and a phone or an email first.", "warn");
      boxes.firstName.focus(); return;
    }
    row.saving = true;
    var done = window.CBMBusy ? CBMBusy.start(btn) : function () {};
    try {
      var res = await api("/prospects/" + encodeURIComponent(p.id) + "/contacts", { method: "POST",
        body: Object.assign({}, typed, seenOf(p), { findingIds: row.findingIds || [] }) });
      row.savedKey = key; row.findingIds = [];
      var closed = (res.findings && res.findings.closed) ? res.findings.closed.length : 0;
      var skipped = (res.findings && res.findings.skipped) ? res.findings.skipped : [];
      var tail = (closed ? " " + closed + " AI finding" + (closed === 1 ? "" : "s") + " accepted." : "")
        + (skipped.length ? " Not accepted: " + skipped.map(function (s) { return s.why; }).join(" ") : "");
      if (res.stays) {
        Object.assign(p, res.prospect || {});
        notice("Saved for " + (p.businessName || p.name) + " — still Identified; it still needs " + (res.needs || "a phone or an email") + "." + tail, "warn");
        focusRow(i);
      } else {
        notice("Contact found for " + (p.businessName || p.name) + " — now " + (res.level || "Contactable") + "." + tail, "ok");
        dropReviewRow(p, i);
      }
    } catch (e) {
      notice(e.message, e.status === 409 ? "warn" : "error");
      if (e.status === 409) dropReviewRow(p, i);
    } finally { row.saving = false; done(); }
  }

  function businessCell(p) {
    var g = grids.rf, nTd = el("td"); var a = el("a", "cm__link", p.businessName || p.name || "(unnamed)");
    a.href = g.ladder ? ("/campaigns/lead/" + encodeURIComponent(p.id)) : "#";
    a.addEventListener("click", function (ev) { ev.preventDefault(); openLead(p.id); });
    if (g.ladder) a.target = "cbm-lead-" + p.id;
    nTd.appendChild(a); return nTd;
  }
  function lookupCell(p) {
    var sTd = el("td"); var s = el("a", "cm__link", "Look it up"); s.href = webSearchUrl(p); s.target = "cbm-lead-lookup"; s.rel = "noopener"; sTd.appendChild(s); return sTd;
  }
  function renderJudgeRow(p, i) {
    var tr = el("tr"), row = { findingIds: [], saving: false }, who = p.businessName || p.name;
    tr.appendChild(tickCell("rf", p));
    tr.appendChild(businessCell(p));
    if (grids.rf.fit) tr.appendChild(fitCell(p, true));
    tr.appendChild(el("td", null, [p.firstName, p.lastName].filter(Boolean).join(" ") || "—"));
    tr.appendChild(el("td", null, [p.mailingAddressCity, p.mailingAddressPostalCode].filter(Boolean).join(" ") || "—"));
    tr.appendChild(el("td", null, p.phone || "—"));
    tr.appendChild(lookupCell(p));
    var web = rowBox("cm__rvweb", "url", "rv_web_" + p.id, "https://…", p.website, "Website for " + who);
    var mail = rowBox("cm__rvmail", "email", "rv_mail_" + p.id, "name@…", p.email, "Email for " + who);
    tr.appendChild(web.td); tr.appendChild(mail.td);
    var aiTd = el("td"); aiTd.appendChild(aiResearchButton(p, { website: web.input, email: mail.input }, row)); tr.appendChild(aiTd);
    var dTd = el("td");
    var qb = el("button", "cm__rowbtn", "Qualify"); qb.type = "button"; qb.addEventListener("click", function () { qualifyRow(p, web.input, mail.input, i, qb, row); }); dTd.appendChild(qb);
    var db = el("button", "cm__rowbtn", "Disqualify…"); db.type = "button"; db.addEventListener("click", function () { disqualifyRow(p, i); }); dTd.appendChild(db);
    tr.appendChild(dTd);
    [web.input, mail.input].forEach(function (inp) { inp.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); qualifyRow(p, web.input, mail.input, i, qb, row); } }); });
    tr.appendChild(el("td", null, p.importBatch || "—"));
    return tr;
  }
  function renderContactsRow(p, i) {
    var tr = el("tr"), row = { findingIds: [], saving: false, savedKey: null }, who = p.businessName || p.name;
    tr.appendChild(tickCell("rf", p));
    tr.appendChild(businessCell(p));
    if (grids.rf.fit) tr.appendChild(fitCell(p, true));
    tr.appendChild(el("td", null, [p.mailingAddressCity, p.mailingAddressPostalCode].filter(Boolean).join(" ") || "—"));
    tr.appendChild(lookupCell(p));
    var first = rowBox("cm__rvfirst", "text", "rv_first_" + p.id, "First", p.firstName, "First name for " + who, true);
    var last = rowBox("cm__rvlast", "text", "rv_last_" + p.id, "Last", p.lastName, "Last name for " + who, true);
    var phone = rowBox("cm__rvphone", "tel", "rv_phone_" + p.id, "216 555 0100", p.phone, "Phone for " + who, true);
    var mail = rowBox("cm__rvmail", "email", "rv_mail_" + p.id, "name@…", p.email, "Email for " + who);
    var boxes = { firstName: first.input, lastName: last.input, phone: phone.input, email: mail.input };
    tr.appendChild(first.td); tr.appendChild(last.td); tr.appendChild(phone.td); tr.appendChild(mail.td);
    var aiTd = el("td"); aiTd.appendChild(aiResearchButton(p, boxes, row)); tr.appendChild(aiTd);
    var sTd = el("td"); var sb = el("button", "cm__rowbtn", "Save"); sb.type = "button"; sb.addEventListener("click", function () { saveContactsRow(p, boxes, i, sb, row); }); sTd.appendChild(sb); tr.appendChild(sTd);
    Object.keys(boxes).forEach(function (k) { boxes[k].addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); saveContactsRow(p, boxes, i, sb, row); } }); });
    tr.appendChild(el("td", null, p.importBatch || "—"));
    return tr;
  }
  function renderReview() {
    var g = grids.rf, body = $("reviewRows"); body.innerHTML = "";
    g.rows.forEach(function (p, i) { body.appendChild(g.mode === "contacts" ? renderContactsRow(p, i) : renderJudgeRow(p, i)); });
  }

  function markSort(tableId, g) {
    Array.prototype.forEach.call(document.querySelectorAll("#" + tableId + " .cm__sortind"), function (s) { s.remove(); });
    var th = document.querySelector("#" + tableId + ' th[data-sort="' + g.sort + '"]');
    if (th) th.appendChild(el("span", "cm__sortind", g.dir === "asc" ? "▲" : "▼"));
  }

  function wireGrid(px) {
    var g = grids[px], timer = null;
    // A typed filter applies half a second after the last key, and at once on
    // Enter or on leaving the box (Tab). The same query is never asked twice.
    var go = function () {
      clearTimeout(timer);
      var key = qs(gridQuery(px));
      if (key === g.lastKey) return;
      g.offset = 0; clearSelection(px); loadGrid(px);
    };
    GRID_FILTERS.forEach(function (f) {
      var e = $(px + "_" + f); if (!e) return;
      if (f === "q" || f === "place" || f === "batch" || f === "fit") {
        e.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(go, 500); });
        e.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); go(); } });
      }
      e.addEventListener("change", go);
    });
    $(px + "_clear").addEventListener("click", function () {
      GRID_FILTERS.forEach(function (f) { var e = $(px + "_" + f); if (e) e.value = ""; });
      g.offset = 0; clearSelection(px); loadGrid(px);
    });
    $(px + "_prev").addEventListener("click", function () { page(px, -1); });
    $(px + "_next").addEventListener("click", function () { page(px, 1); });
    $(px + "_page").addEventListener("change", function () { selectPage(px, $(px + "_page").checked); });
    $(px + "_all").addEventListener("click", function () { selectAllMatching(px); });
    $(px + "_bulkclear").addEventListener("click", function () { clearSelection(px); });
    $(px + "_bulkdq").addEventListener("click", function () { openBulk(px, "disqualify"); });
    $(px + "_bulkdnc").addEventListener("click", function () { openBulk(px, "do-not-contact"); });
    // Lead enrichment phase 2 (ruling E18): AI research over the ticked leads
    // or all matching. Offered only when the feature is live on this CRM.
    if ($(px + "_bulkai") && window.CBMEnrichment) {
      $(px + "_bulkai").addEventListener("click", function () {
        var g2 = grids[px], items = g2.all ? g2.all.slice() : Object.keys(g2.selected).map(function (k) { return g2.selected[k]; });
        if (!items.length) { notice("Tick at least one lead first.", "warn"); return; }
        window.CBMEnrichment.startRun({ targetType: "lead", ids: items.map(function (i) { return i.id; }),
          onStarted: function (r) { notice("AI research started on " + r.records.toLocaleString() + " lead" + (r.records === 1 ? "" : "s") + " (estimated $" + Number(r.estimate).toFixed(2) + "). Findings appear on each lead as they finish.", "ok"); clearSelection(px); } });
      });
      fetch("/enrichment/api/status?targetType=lead", { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (s) { if (s && s.available && s.ready) $(px + "_bulkai").hidden = false; })
        .catch(function () {});
    }
  }
  wireGrid("pf"); wireGrid("rf");
  if ($("pf_bulkassign")) $("pf_bulkassign").addEventListener("click", function () { openAssign("pf"); });
  if ($("pf_more")) $("pf_more").addEventListener("click", function () { grids.pf.moreOpen = !grids.pf.moreOpen; applyLadderLayout(); });
  $("pf_export").addEventListener("click", function () {
    var s = qs(gridQuery("pf"));
    var a = document.createElement("a"); a.href = API + "/prospects/export" + (s ? "?" + s : ""); a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
    notice("Exporting the " + grids.pf.total.toLocaleString() + " matching leads as a CSV file — your browser saves it.", "ok");
  });

  function fillGridOptions() {
    ["pf", "rf"].forEach(function (px) {
      if ($(px + "_status")) fillSelect($(px + "_status"), state.fields.prospectOptions.leadStatus, 1);
      if ($(px + "_exit")) fillSelect($(px + "_exit"), state.fields.prospectOptions.sideExit, 2);
      fillSelect($(px + "_source"), state.fields.prospectOptions.leadSource, 1);
    });
  }
  function fillCampaignOptions() {
    ["pf", "rf"].forEach(function (px) {
      var sel = $(px + "_camp"), keep = sel.value;
      Array.prototype.slice.call(sel.options, 3).forEach(function (o) { o.remove(); });
      (state.campaigns || []).forEach(function (c) { var o = el("option", null, "In " + c.name); o.value = c.id; sel.appendChild(o); });
      sel.value = keep;
    });
  }
  function fillBatchOptions(batches) {
    ["pf", "rf"].forEach(function (px) {
      var dl = $(px + "_batches"); dl.innerHTML = "";
      (batches || []).forEach(function (b) { var o = el("option"); o.value = b.name; dl.appendChild(o); });
    });
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
      // The lead's notes: where Qualify and Disqualify write who, when and why.
      facts.appendChild(el("dt", null, "Notes"));
      var notesDd = el("dd", "cm__notes", p.description || "—");
      notesDd.style.whiteSpace = "pre-wrap";
      facts.appendChild(notesDd);
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
      // Lead enrichment phase 2: the lead's AI research findings (hidden while
      // the feature is dark — frontend/shared/enrichment.js).
      if (window.CBMEnrichment) window.CBMEnrichment.panel(body, { targetType: "lead", recordId: p.id, onChange: function () { loadProspects(); } });
      openModal(p.businessName || p.name, body, null);
    } catch (e) { notice(e.message, "error"); }
  }

  // --- the lead's page (build plan § 7e.4) -----------------------------------------------------------
  // The header: level, assignee, how we can reach them, the actions. What we
  // know in three groups, with every empty field an inline gap written as the
  // user (placement runs after each). Where it came from. One Activity
  // timeline. Every action button stays visible; one that does not apply says
  // why on click.
  var lead = { data: null, partners: null };
  var LEVEL_WORDS = {
    Identified: "a real business, no named person or direct line yet",
    Contactable: "a named person and a phone or an email",
    Referred: "introduced by a partner or someone trusted, with a phone or an email",
  };
  async function loadLead() {
    try {
      lead.data = await api("/prospects/" + encodeURIComponent(LEAD_ID));
      renderLead();
    } catch (e) {
      if (e.status === 404) notice("This lead was not found.", "error"); else notice(e.message, "error");
    }
  }
  function leadLevelWord(p) {
    var status = p.leadStatus || "Unqualified";
    if (status === "Qualified") return p.qualificationLevel || "Qualified";
    return status;
  }
  function leadBadgeClass(p) {
    var w = leadLevelWord(p).toLowerCase();
    return "cm__badge" + (["identified", "contactable", "referred", "disqualified", "converted"].indexOf(w) >= 0 ? " cm__badge--" + w : "");
  }
  function gap(p, field, opts) {
    // One fact: a filled value shown plainly (click to edit), an empty one as a
    // dashed box. Enter or leaving the box saves a change.
    opts = opts || {};
    var dd = el("dd");
    var input = el(opts.select ? "select" : "input", "cm__gap" + (p[field] ? " cm__gap--filled" : ""));
    if (opts.select) {
      var none = el("option", null, "—"); none.value = ""; input.appendChild(none);
      (opts.select || []).forEach(function (o) { var op = el("option", null, o.name); op.value = o.id; input.appendChild(op); });
      input.value = p[field] || "";
    } else {
      input.type = opts.type || "text"; input.value = p[field] || ""; input.placeholder = opts.placeholder || "Add…"; input.autocomplete = "off";
      if (opts.readonly) { input.readOnly = true; input.title = opts.readonly; }
    }
    input.setAttribute("aria-label", opts.label || field);
    var was = input.value, saving = false;
    async function save() {
      // Enter saves and the page redraws, which blurs the box: the blur must
      // not save the same value again (found on the live pass, 10-25-26).
      if (saving || input.value === was) return;
      var before = was, value = input.value;
      was = value; saving = true;
      var changes = {}; changes[field] = value;
      var done = window.CBMBusy ? CBMBusy.start(input) : function () {};
      try {
        var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/facts", { method: "PATCH", body: { changes: changes } });
        notice("Saved" + (res.level ? " — level now " + res.level : "") + ".", "ok");
        await loadLead();
      } catch (e) { notice(e.message, "error"); was = before; input.value = before; }
      finally { saving = false; done(); }
    }
    if (!opts.readonly) {
      input.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); save(); } if (ev.key === "Escape") { input.value = was; input.blur(); } });
      input.addEventListener("blur", save);
      if (opts.select) input.addEventListener("change", save);
    }
    dd.appendChild(input); return dd;
  }
  function factRow(host, label, node) { host.appendChild(el("dt", null, label)); host.appendChild(node); }
  function plain(v) { return el("dd", null, v == null || v === "" ? "—" : String(v)); }
  function reachSentence(p) {
    var ways = [];
    if (p.mailingAddressStreet && p.addressStatus !== "Dead") ways.push("a postcard to " + [p.mailingAddressStreet, p.mailingAddressCity].filter(Boolean).join(", "));
    if (p.phone) ways.push("a call to " + p.phone);
    var mailable = p.leadStatus === "Qualified" && (p.qualificationLevel === "Contactable" || p.qualificationLevel === "Referred");
    if (p.email) ways.push(mailable ? "a personal email to " + p.email : "an email to " + p.email + " once the lead is Contactable or Referred");
    return ways.length ? "How we can reach them: " + ways.join("; ") + "." : "How we can reach them: no address, phone or email yet — the gaps below are where to put what you find.";
  }
  async function renderLead() {
    var d = lead.data, p = d.prospect;
    document.title = HOST + " — " + (p.businessName || p.name || "Lead");
    text($("ld_name"), p.businessName || p.name || "(unnamed)");
    var lv = $("ld_level"); lv.textContent = leadLevelWord(p) + (p.sideExit ? " · " + p.sideExit : ""); lv.className = leadBadgeClass(p) + (p.sideExit ? " cm__badge--stopped" : "");
    lv.title = p.leadStatus === "Qualified" ? (p.levelSetAt ? "Set by hand" + (p.levelSetByHandName ? " by " + p.levelSetByHandName : "") + " " + fmtDate(p.levelSetAt) + (d.manualLevel ? "; it moves up only when a new fact arrives" : "") : (LEVEL_WORDS[p.qualificationLevel] ? "Placed by the system: " + LEVEL_WORDS[p.qualificationLevel] + "." : "The system places the level from what the lead holds.")) : "";
    text($("ld_assignee"), d.ladder ? (p.assignedUserName ? "· assigned to " + p.assignedUserName : "· not assigned yet") : "");
    text($("ld_reach"), reachSentence(p));
    Object.keys(PANELS).forEach(function (k) { $(PANELS[k]).hidden = true; });
    show($("leadPanel"));
    if (d.ladder && !lead.partners) {
      try { lead.partners = (await api("/prospects/partner-options")).options || []; } catch (_) { lead.partners = []; }
    }
    var b = $("ld_business"); b.innerHTML = "";
    factRow(b, "Business", gap(p, "businessName", { label: "Business name" }));
    factRow(b, "Website", gap(p, "website", { label: "Website", placeholder: "Add a web address…" }));
    factRow(b, "Street", gap(p, "mailingAddressStreet", { label: "Street" }));
    factRow(b, "City", gap(p, "mailingAddressCity", { label: "City" }));
    factRow(b, "State", gap(p, "mailingAddressState", { label: "State" }));
    factRow(b, "ZIP", gap(p, "mailingAddressPostalCode", { label: "ZIP" }));
    factRow(b, "Address status", plain(p.addressStatus));
    var s = $("ld_person"); s.innerHTML = "";
    factRow(s, "First name", gap(p, "firstName", { label: "First name" }));
    factRow(s, "Last name", gap(p, "lastName", { label: "Last name" }));
    factRow(s, "Phone", gap(p, "phone", { label: "Phone", type: "tel", placeholder: "Add a phone number…" }));
    factRow(s, "Email", gap(p, "email", { label: "Email", type: "email", placeholder: "Add an email address…" }));
    if (d.ladder) {
      factRow(s, "Referred by (partner)", gap(p, "referredByPartnerId", { label: "Referred by (partner)", select: lead.partners || [] }));
      factRow(s, "Referred by (name)", gap(p, "referredByName", { label: "Referred by (name)", placeholder: "Someone trusted who is not a partner…" }));
    }
    var f = $("ld_fit"); f.innerHTML = "";
    if (p.fitScore != null && p.fitScore !== "") {
      factRow(f, "Fit score", plain(p.fitScore + " of 100")); factRow(f, "Service area", plain(p.fitGate)); factRow(f, "County", plain(p.fitCounty));
      var reasons = el("dd", null, p.fitReasons || "—"); reasons.style.whiteSpace = "pre-line"; factRow(f, "Why", reasons);
    } else { factRow(f, "Fit score", plain("Not scored yet")); }
    var o = $("ld_origin"); o.innerHTML = "";
    factRow(o, "Lead Source", plain(p.leadSource)); factRow(o, "Batch", plain(p.importBatch)); factRow(o, "Reference", plain(p.externalReference));
    factRow(o, "Arrived", plain(fmtDate(p.createdAt))); factRow(o, "Status", plain((p.leadStatus || "Unqualified") + (p.leadStatusChangedAt ? " since " + fmtDate(p.leadStatusChangedAt) : "")));
    if (p.qualifiedBy) factRow(o, "Qualified by", plain(p.qualifiedBy + (p.qualifiedAt ? ", " + fmtDate(p.qualifiedAt) : "")));
    if (p.sideExit) { factRow(o, "Stopped because", plain(p.sideExit)); factRow(o, "Reason note", plain(p.sideExitNote)); }
    if (p.promotedCompanyName) factRow(o, "Converted to company", plain(p.promotedCompanyName));
    if (p.promotedContactName) factRow(o, "Converted to contact", plain(p.promotedContactName));
    if (p.alreadyKnownCompanyName) factRow(o, "Duplicate of company", plain(p.alreadyKnownCompanyName));
    if (d.ladder && p.replied) factRow(o, "Replied", plain("Yes — convert the lead, or answer first"));
    var bar = $("ld_repliedBar"); if (bar) bar.hidden = !(d.ladder && p.replied && p.leadStatus !== "Converted");
    if (p.leadCode !== undefined) factRow(o, "Link code", plain(p.leadCode ? p.leadCode + " (the end of every personal link; New code replaces it)" : "None yet — minted the first time a campaign needs it, or by New code"));
    var rv = $("ld_review"); rv.innerHTML = ""; rv.appendChild(reviewActions(p, loadLead));
    text($("ld_notes"), p.description || "—");
    var tl = $("ld_activity"); tl.innerHTML = "";
    (d.activity || []).forEach(function (r) {
      var li = el("li", "cm__tl--" + r.kind);
      li.appendChild(el("div", "cm__tl-when", fmtDate(r.at) + (r.by ? " · " + r.by : "")));
      li.appendChild(el("div", null, r.title));
      if (r.detail) li.appendChild(el("div", "cm__tl-detail", r.detail));
      tl.appendChild(li);
    });
    $("ld_activityEmpty").hidden = (d.activity || []).length > 0;
    loadLeadConversations(p);
    var en = $("ld_enrichment"); en.innerHTML = "";
    if (window.CBMEnrichment) window.CBMEnrichment.panel(en, { targetType: "lead", recordId: p.id, onChange: loadLead });
  }
  function leadWhyNot(p, action) {
    if (action === "level") {
      if (!(lead.data && lead.data.ladder)) return "The qualification ladder is not switched on here, or this CRM does not carry its fields yet.";
      if (p.leadStatus !== "Qualified") return "Only a Qualified lead has a level; this one is " + (p.leadStatus || "Unqualified") + ". Qualify it first (under Review).";
      if (p.sideExit) return "This lead stopped being worked (" + p.sideExit + "); its level stays as it is.";
    }
    if (action === "assign") {
      if (!(lead.data && lead.data.ladder)) return "This CRM does not carry the lead's Assigned to field yet.";
      if (p.leadStatus === "Converted") return "This lead is Converted; its Company or Contact is the record to work now.";
      if (p.leadStatus === "Disqualified") return "A Disqualified lead is not worked, so it is not assigned.";
      if (p.sideExit) return "This lead stopped being worked (" + p.sideExit + "), so it is not assigned.";
    }
    if (action === "convert") {
      if (p.leadStatus === "Converted") return "This lead is already Converted" + (p.promotedCompanyName || p.promotedContactName ? " — to " + [p.promotedCompanyName, p.promotedContactName].filter(Boolean).join(" and ") : "") + ".";
      if (p.sideExit) return "This lead stopped being worked (" + p.sideExit + "); clear that first if it should be converted.";
      if (!p.email && !(p.website && p.businessName)) return "A lead converts from an email, or a website for a business. Fill one in under What we know first.";
    }
    return "";
  }
  function openSetLevel(p) {
    var why = leadWhyNot(p, "level"); if (why) { notice(why, "warn"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "The system places the level from what the lead holds; set it by hand when you know better. It never moves backwards on its own, and after a hand setting it moves up only when a new fact arrives — a phone, an email, a named person or a referrer."));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, "Level"); lab.htmlFor = "lv_pick";
    var sel = el("select"); sel.id = "lv_pick";
    (lead.data.levels || []).forEach(function (l) { var op = el("option", null, l + " — " + (LEVEL_WORDS[l] || "")); op.value = l; sel.appendChild(op); });
    sel.value = p.qualificationLevel || (lead.data.levels || [])[0];
    f.appendChild(lab); f.appendChild(sel); body.appendChild(f);
    openModal("Set level — " + (p.businessName || p.name), body, async function () {
      var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/level", { method: "PUT", body: { level: sel.value } });
      closeModal(); notice("Level set to " + sel.value + (res.was ? " (was " + res.was + ")" : "") + ".", "ok"); loadLead();
    }, "Set level");
  }
  async function openAssignOne(p) {
    var why = leadWhyNot(p, "assign"); if (why) { notice(why, "warn"); return; }
    var options;
    try { options = await loadOwnerOptions(); } catch (e) { notice(e.message, "error"); return; }
    var body = el("div", "cm__plan");
    body.appendChild(el("p", null, "The team member who makes contact personally. Only members of the Marketing Management team are offered."));
    var f = el("div", "cm__field cm__field--wide"); var lab = el("label", null, "Assign to"); lab.htmlFor = "as_one";
    var sel = el("select"); sel.id = "as_one"; var none = el("option", null, "Choose…"); none.value = ""; sel.appendChild(none);
    options.forEach(function (o) { var op = el("option", null, o.name + (state.session && o.id === state.session.userId ? " (me)" : "")); op.value = o.id; sel.appendChild(op); });
    sel.value = p.assignedUserId || "";
    f.appendChild(lab); f.appendChild(sel); body.appendChild(f);
    openModal("Assign — " + (p.businessName || p.name), body, async function () {
      if (!sel.value) { modalMsg("Choose the team member the lead goes to.", "error"); return; }
      var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/assignee", { method: "PUT", body: { userId: sel.value } });
      closeModal(); notice("Assigned to " + res.assignee.name + ".", "ok"); loadLead();
    }, "Assign");
  }
  function convertLead(p) {
    var why = leadWhyNot(p, "convert"); if (why) { notice(why, "warn"); return; }
    var from = p.email ? "its email " + p.email : "its website " + p.website;
    ask("Convert this lead?", "Convert " + (p.businessName || p.name) + " from " + from + ": " + (p.businessName ? "a Company" + (p.email ? " and a Contact" : "") : "a Contact") + " typed Prospect is created (or matched), and the lead is marked Converted.", { ok: "Convert" }).then(async function (ok) {
      if (!ok) return;
      try {
        var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/convert", { method: "POST" });
        var c = res.converted || {};
        notice("Converted" + (c.companyId ? (c.companyCreated ? " — a new Company" : " — matched an existing Company") : "") + (c.contactId ? (c.contactCreated ? ", a new Contact" : ", an existing Contact") : "") + ".", "ok");
        loadLead();
      } catch (e) { notice(e.message, e.status === 409 ? "warn" : "error"); }
    });
  }
  // --- personal outreach from the lead's page (build plan § 7e.5) ------------------------------
  // Email opens the shared composer (frontend/shared/compose.js) to the lead's
  // own address from the sender's own chapter mailbox; Log a call records a
  // campaign-less call with one of three outcomes; Conversations lists the
  // lead's threads and opens each with the shared renderer. The server holds
  // the same guardrails; the screen says why in words before a round trip.
  function outreachOff() {
    return !(state.session && state.session.leadOutreachOn)
      ? "Personal outreach is not switched on here (Personal outreach to leads at /setup)." : "";
  }
  function leadWhyNotEmail(p) {
    var off = outreachOff(); if (off) return off;
    if (!(lead.data && lead.data.ladder)) return "This CRM does not carry the lead's Assigned to field yet, so personal outreach is not available here.";
    var mailable = p.leadStatus === "Qualified" && (p.qualificationLevel === "Contactable" || p.qualificationLevel === "Referred");
    if (!mailable) return "Only a Contactable or Referred lead may be emailed personally; this one is " + leadLevelWord(p) + ". A named person and a phone or an email make a lead Contactable.";
    if (p.sideExit) return "This lead stopped being worked (" + p.sideExit + "), so it is not emailed.";
    if (!p.email) return "This lead has no email address. Add one under What we know first.";
    return leadWhyNotMine(p);
  }
  function leadWhyNotMine(p) {
    var me = state.session && state.session.userId;
    if (p.assignedUserId && p.assignedUserId === me) return "";
    if (p.assignedUserId) return "This lead is assigned to " + (p.assignedUserName || "someone else") + ". Assign the lead to yourself first.";
    return "Assign the lead to yourself first.";
  }
  function leadWhyNotCall(p) {
    var off = outreachOff(); if (off) return off;
    if (!(lead.data && lead.data.ladder)) return "This CRM does not carry the lead's Assigned to field yet, so personal outreach is not available here.";
    if (p.leadStatus === "Disqualified") return "A Disqualified lead is not worked, so a call on it is not logged.";
    return leadWhyNotMine(p);
  }
  lead.mailbox = undefined;   // the sender's own mailbox and signature, fetched once per page
  function openCompose(p) {
    var why = leadWhyNotEmail(p); if (why) { notice(why, "warn"); return; }
    if (!window.CBMCompose) { notice("The email composer did not load — reload the page and try again.", "error"); return; }
    var base = "/prospects/" + encodeURIComponent(LEAD_ID);
    var person = [p.firstName, p.lastName].filter(Boolean).join(" ");
    CBMCompose.open({
      apiBase: API,
      api: function (path, opts) { opts = opts || {}; return api(path, { method: opts.method || "GET", body: opts.body }); },
      endpoints: {
        mailbox: "/mailbox",
        templates: "/emailtemplates",
        parse: function (tid) { return base + "/emailtemplates/" + encodeURIComponent(tid) + "/parse"; },
        messages: base + "/messages",
        writeBack: "/emailwriteback",
      },
      // One person to one person: no Cc/Bcc, no Documents folder, no reply from here.
      features: { cc: false, templates: true, attachments: true, documents: false, drafts: true, reply: false, addressBook: false },
      record: { entity: "CProspect", id: p.id, name: p.businessName || p.name || "", fixedRecipient: true,
                contacts: [{ name: person || (p.businessName || ""), email: p.email }] },
      sendingEnabled: true,
      mailbox: {
        get: function () { return lead.mailbox; },
        set: function (mb, sig) { lead.mailbox = { mailbox: mb, signature: sig || "" }; },
      },
      fmtWhen: fmtDate,
      onSent: function (res) {
        if (res && (res.warnings || []).length) notice("Email sent. " + res.warnings.join(" "), "warn");
        loadLead();
      },
      onUnauthorized: function () { location.assign("/?next=" + encodeURIComponent("/campaigns/")); },
      notice: function (t, k) { notice(t, k === "error" ? "error" : "ok"); },
    }, { to: p.email });
  }
  var CALL_OUTCOMES = [
    ["Interested", "converts the lead from its email or website; with neither, the call is recorded and the lead stays a lead"],
    ["Not interested", "stops the lead, with your note as the reason"],
    ["No reply yet", "records the attempt only"],
  ];
  function openLogCall(p) {
    var why = leadWhyNotCall(p); if (why) { notice(why, "warn"); return; }
    var body = el("div", "cm__callform");
    body.appendChild(el("p", null, "A call you made yourself, outside any campaign. It goes on the lead's Activity like a campaign call."));
    var fs = el("fieldset"); fs.appendChild(el("legend", null, "What came of it"));
    var picked = "";
    CALL_OUTCOMES.forEach(function (o) {
      var lab = el("label", "cm__radio"); var r = el("input"); r.type = "radio"; r.name = "ld_callOutcome"; r.value = o[0];
      r.addEventListener("change", function () { picked = o[0]; });
      lab.appendChild(r); var t = el("span", null, o[0] + " "); t.appendChild(el("small", null, "— " + o[1])); lab.appendChild(t); fs.appendChild(lab);
    });
    body.appendChild(fs);
    var f1 = el("label", "cm__field cm__field--wide"); f1.appendChild(el("span", null, "Number called"));
    var phone = el("input"); phone.type = "tel"; phone.value = p.phone || ""; phone.id = "ld_callPhone"; f1.appendChild(phone); body.appendChild(f1);
    var f2 = el("label", "cm__field cm__field--wide"); f2.appendChild(el("span", null, "Notes (required for Not interested)"));
    var notes = el("textarea"); notes.rows = 4; notes.maxLength = 4000; notes.id = "ld_callNotes"; f2.appendChild(notes); body.appendChild(f2);
    openModal("Log a call — " + (p.businessName || p.name), body, async function () {
      if (!picked) { modalMsg("Choose what came of the call.", "error"); return; }
      if (picked === "Not interested" && !notes.value.trim()) { modalMsg("Say why the lead is not interested — the note is required.", "error"); return; }
      var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/calls", { method: "POST", body: { outcome: picked, notes: notes.value.trim(), calledPhone: phone.value.trim() } });
      closeModal();
      var parts = ["Call logged: " + picked + "."];
      if (res.notConverted) parts.push(res.notConverted);
      else if ((res.consequences || []).indexOf("lead converted") >= 0) parts.push("The lead is Converted.");
      else if ((res.consequences || []).indexOf("stopped by Declined") >= 0) parts.push("The lead stopped being worked.");
      if ((res.warnings || []).length) parts.push(res.warnings.join(" "));
      notice(parts.join(" "), (res.warnings || []).length ? "warn" : "ok");
      loadLead();
    }, "Log the call");
  }
  async function loadLeadConversations(p) {
    var list = $("ld_conversations"), empty = $("ld_conversationsEmpty"), hint = $("ld_convHint");
    if (!list) return;
    list.innerHTML = ""; empty.hidden = true;
    var off = outreachOff();
    if (off) { text(hint, off + " Email with this lead is not shown."); return; }
    var res;
    try { res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/conversations"); }
    catch (e) { text(hint, e.message); return; }
    if (!res.available) { text(hint, res.reason || "Conversations are not available here."); return; }
    var rows = res.conversations || [];
    empty.hidden = rows.length > 0;
    rows.forEach(function (c) {
      var li = el("li"); var b = el("button", "cm__convrow" + (c.unread ? " is-unread" : "")); b.type = "button";
      b.appendChild(el("span", "cm__conv-subject", c.subject || "(no subject)"));
      var when = el("span", "cm__conv-when", (c.messageCount ? c.messageCount + (c.messageCount === 1 ? " message · " : " messages · ") : "") + fmtDate(c.lastMessageAt));
      b.appendChild(when);
      var who = el("span", "cm__conv-who", c.participants || "");
      if (c.awaiting) { who.appendChild(document.createTextNode(" ")); who.appendChild(el("span", "cm__conv-awaiting", "Their last message is unanswered")); }
      b.appendChild(who);
      b.addEventListener("click", function () { openConversation(c.id, c.subject); });
      li.appendChild(b); list.appendChild(li);
    });
  }
  function sanitizeHtml(html) {
    var tmp = document.createElement("div");
    tmp.innerHTML = html || "";
    Array.prototype.forEach.call(tmp.querySelectorAll("script,style,iframe,object,embed,link,meta"), function (n) { n.remove(); });
    Array.prototype.forEach.call(tmp.querySelectorAll("*"), function (n) {
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var name = a.name.toLowerCase(), val = (a.value || "").replace(/\s/g, "").toLowerCase();
        if (name.indexOf("on") === 0) n.removeAttribute(a.name);
        else if ((name === "href" || name === "src") && val.indexOf("javascript:") === 0) n.removeAttribute(a.name);
      });
    });
    return tmp.innerHTML;
  }
  async function openConversation(convId, subject) {
    var body = el("div", "cm__thread");
    body.appendChild(el("p", "cm__muted", "Loading…"));
    openModal(subject || "Conversation", body, null);
    var c;
    try { c = await api("/conversations/" + encodeURIComponent(convId)); }
    catch (e) { body.innerHTML = ""; body.appendChild(el("p", "cm__notice cm__notice--error", e.message)); return; }
    body.innerHTML = "";
    var msgs = c.messages || [];
    if (!window.CBMConversation) { body.appendChild(el("p", null, "The conversation renderer did not load — reload the page.")); return; }
    msgs.forEach(function (m, i) {
      if (i === 0) body.appendChild(CBMConversation.startedDivider(m, { fmtWhen: fmtDate }));
      body.appendChild(CBMConversation.messageCard(m, { sanitizeHtml: sanitizeHtml, fmtWhen: fmtDate, gmailMailbox: lead.mailbox ? lead.mailbox.mailbox : null }));
    });
    if (!msgs.length) body.appendChild(el("p", "cm__muted", "No messages stored for this conversation."));
    body.appendChild(el("p", "cm__hint", "To answer, use the Email button on the lead's page; the reply joins this conversation through your mailbox."));
    // The server stamped the thread read; the row loses its bold without a round trip.
    Array.prototype.forEach.call(document.querySelectorAll("#ld_conversations .cm__convrow.is-unread"), function (r) {
      if (r.querySelector(".cm__conv-subject") && r.querySelector(".cm__conv-subject").textContent === (subject || "(no subject)")) r.classList.remove("is-unread");
    });
  }
  // New code: a fresh personal-link code. The old one stops resolving at
  // once; a notice already sent carries it until the next push rewrites the
  // vendor's field, so the confirmation says so.
  function newCode(p) {
    var had = !!p.leadCode;
    ask("New code for " + (p.businessName || p.name) + "?",
        (had ? "The code at the end of this lead's personal links is replaced. A link printed or sent with the old code opens the campaign with no lead on it from now on, and the email service's field keeps the old code until the next push that includes this person."
             : "This lead has no code yet; one is minted now and every personal link made for them will carry it."),
        { ok: had ? "Replace the code" : "Mint a code" }).then(async function (ok) {
      if (!ok) return;
      try {
        var res = await api("/prospects/" + encodeURIComponent(LEAD_ID) + "/code", { method: "POST" });
        notice((res.replaced ? "Code replaced." : "Code minted.") + " New links for this lead end in " + res.code + ".", "ok");
        loadLead();
      } catch (e) { notice(e.message, e.status === 409 ? "warn" : "error"); }
    });
  }
  if ($("ld_setlevel")) {
    $("ld_setlevel").addEventListener("click", function () { if (lead.data) openSetLevel(lead.data.prospect); });
    $("ld_assign").addEventListener("click", function () { if (lead.data) openAssignOne(lead.data.prospect); });
    $("ld_convert").addEventListener("click", function () { if (lead.data) convertLead(lead.data.prospect); });
    $("ld_newcode").addEventListener("click", function () { if (lead.data) newCode(lead.data.prospect); });
    $("ld_email").addEventListener("click", function () { if (lead.data) openCompose(lead.data.prospect); });
    $("ld_call").addEventListener("click", function () { if (lead.data) openLogCall(lead.data.prospect); });
    $("ld_repliedConvert").addEventListener("click", function () { if (lead.data) convertLead(lead.data.prospect); });
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
    if (action === "qualify" && !p.website && !p.email) return "A lead without a website or an email can never be Qualified. Type the one you found into its row on the Review tab, or leave it Unqualified — campaigns may still reach it.";
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

  function importToolOn() { return !!(state.session && state.session.importTemplatesOn && window.CBMImports); }
  async function loadImports() {
    // The import tool (build plan § 7e.7) owns the tab when its switch is on.
    if (importToolOn()) return window.CBMImports.load();
    try {
      var res = await busyOver("importsGrid", api("/prospects/imports"));
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
      gridify("importsGrid", "marketing.imports");
      fillBatchOptions(res.batches);
      $("importsEmpty").hidden = (res.batches || []).length > 0;
    } catch (e) { notice(e.message, "error"); }
  }

  function openImport() {
    if (importToolOn()) return window.CBMImports.openImport();
    var body = el("div", "cm__plan");
    var fields = el("div", "cm__fields");
    function field(label, input, wide) { var f = el("div", "cm__field" + (wide ? " cm__field--wide" : "")); var l = el("label", null, label); l.htmlFor = input.id; f.appendChild(l); f.appendChild(input); fields.appendChild(f); return input; }
    var name = el("input"); name.type = "text"; name.id = "im_name"; name.maxLength = 255; name.placeholder = "e.g. State filings, October 2026"; field("Batch name", name, true);
    var door = el("select"); door.id = "im_door"; [["State filing", "State filing (a row with a website or email enters Qualified)"], ["List", "Purchased list (enters Unqualified)"], ["Partner file", "Partner file (enters Unqualified)"]].forEach(function (o) { var opt = el("option", null, o[1]); opt.value = o[0]; door.appendChild(opt); }); field("Lead Source", door);
    var qb = el("input"); qb.type = "text"; qb.id = "im_qb"; qb.placeholder = "The filter's name and version"; field("Qualified by (filings)", qb);
    var ls = el("input"); ls.type = "text"; ls.id = "im_ls"; ls.placeholder = "Vendor or partner"; field("List source (lists)", ls);
    var file = el("input"); file.type = "file"; file.id = "im_file"; file.accept = ".csv,text/csv"; field("CSV file", file, true);
    body.appendChild(fields);
    body.appendChild(el("p", "cm__hint", "Columns: business_name (required), mailing_street, mailing_city, mailing_state, mailing_zip (required as a set), and optionally external_reference, website, email, phone, contact_first_name, contact_last_name, qualified_by. Every row becomes a lead; no Company or Contact is created until first contact. A list or partner file names its vendor or partner in List source; its rows wait in the Review tab at Unqualified. Unknown columns ride along into the lead."));
    var planBox = el("div", "cm__plan"); body.appendChild(planBox);
    var planned = null;
    function readFile() { return new Promise(function (resolve, reject) { var f = file.files && file.files[0]; if (!f) { reject(new Error("Choose a CSV file.")); return; } var r = new FileReader(); r.onload = function () { resolve(String(r.result || "")); }; r.onerror = function () { reject(new Error("The file could not be read.")); }; r.readAsText(f); }); }
    openModal("Import leads", body, async function () {
      if (!planned) {
        if (!name.value.trim()) { modalMsg("Name the batch.", "error"); return; }
        var textContent = await readFile();
        modalMsg("Planning — checking every row against the companies and contacts the CRM already holds…", "ok");
        planned = await api("/prospects/import/plan", { method: "POST", timeoutMs: 300000, body: { name: name.value.trim(), source: door.value, text: textContent, qualifiedBy: qb.value, listSource: ls.value } });
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
      // In parts of 100 rows, so no single request outlasts a timeout; the
      // ledger makes every part resumable (10-20-26).
      var r = { created: 0, qualified: 0, unqualified: 0, duplicates: 0, errors: 0 };
      var toWrite = (planned.counts.create || 0) + (planned.counts.alreadyKnown || 0);
      while (true) {
        modalMsg("Applying — " + (r.created + r.duplicates).toLocaleString() + " of " + toWrite.toLocaleString() + " written…", "ok");
        var part = (await api("/prospects/import/apply", { method: "POST", timeoutMs: 180000, body: { batchId: planned.batchId, maxRows: 100 } })).result;
        ["created", "qualified", "unqualified", "duplicates", "errors"].forEach(function (k) { r[k] += part[k] || 0; });
        if (part.errors) break;
        if (!part.remaining) break;
      }
      if (r.errors) { modalMsg(r.errors + " row(s) could not be written; the rest are saved. Press Apply this plan again to retry them — nothing is written twice.", "error"); loadImports(); return; }
      closeModal();
      notice("Imported: " + r.created + " leads (" + r.qualified + " Qualified, " + r.unqualified + " Unqualified), " + r.duplicates + " duplicates" + (r.errors ? ", " + r.errors + " errors (see the log)" : "") + ".", r.errors ? "warn" : "ok");
      loadProspects(); loadImports();
    }, "Plan");
  }

  // --- sections / boot ---------------------------------------------------------------------------------
  // One page, six tabs. Lists and Calls are drawn by lists.js and calls.js,
  // which register here; a tab's onLeave may refuse the switch (an unsaved
  // list), and its onShow gets the hash's parameters (#lists?list=<id>).
  var SECTIONS = ["prospects", "lists", "campaigns", "review", "calls", "imports"];
  var PANELS = { prospects: "prospectsPanel", lists: "listsPanel", campaigns: "campaignsPanel", review: "reviewPanel", calls: "callsPanel", imports: "importsPanel" };
  // The lead's page is not a tab: it is hidden with the tabs and shown by loadLead alone.
  var sections = {};
  function markNav(name) {
    Array.prototype.forEach.call(document.querySelectorAll("#sectionNav .cm__navbtn"), function (b) { b.classList.toggle("is-active", b.getAttribute("data-section") === name); });
  }
  async function showSection(name, params) {
    if (SECTIONS.indexOf(name) < 0) return false;
    var leaving = state.section;
    if (leaving && leaving !== name && sections[leaving] && sections[leaving].onLeave) {
      var ok = await sections[leaving].onLeave();
      if (ok === false) { markNav(leaving); return false; }
    }
    if (name === "lists" && state.session && !state.session.listsOn) { notice("Campaign lists are switched off on this deployment (Campaign lists at /setup).", "warn"); markNav(leaving); return false; }
    if (name === "calls" && state.session && !state.session.callsOn) { notice("Campaign calls are switched off on this deployment (CAMPAIGNS_CALLS at /setup).", "warn"); markNav(leaving); return false; }
    state.section = name;
    markNav(name);
    Object.keys(PANELS).forEach(function (k) { $(PANELS[k]).hidden = k !== name; });
    if (name === "prospects") loadProspects();
    if (name === "review") loadReview();
    if (name === "imports") loadImports();
    // Leads and Review write their own hash (filters ride it), Lists writes
    // its own (the open list rides it); the other three record theirs here,
    // so a reload stays on the tab that was open.
    if (name === "campaigns" || name === "imports" || name === "calls") { try { history.replaceState(null, "", "#" + name); } catch (_) {} }
    if (sections[name] && sections[name].onShow) await sections[name].onShow(params || {});
    return true;
  }
  Array.prototype.forEach.call(document.querySelectorAll("#sectionNav button.cm__navbtn"), function (b) { b.addEventListener("click", function () { showSection(b.getAttribute("data-section")); }); });
  // A record page's links open this page by its tab name. When this page is
  // already open in that browser tab only the hash changes, so switch here.
  window.addEventListener("hashchange", function () {
    if (RECORD_ID || LEAD_ID || !state.session || state.session.callerOnly || !state.session.available) return;
    var h = hashParams();
    if (SECTIONS.indexOf(h.section) < 0) return;
    if (h.section === "prospects") readHash("pf", h.params);
    if (h.section === "review") readHash("rf", h.params);
    showSection(h.section, h.params);
  });
  // What the Lists and Calls scripts share with this one (build plan § 7e.2):
  // one api, one notice, one modal, one session, and the tab registry.
  window.CBMMarketing = {
    api: api, notice: notice, el: el, text: text, show: show, hide: hide, esc: esc, fmtDate: fmtDate,
    openModal: openModal, closeModal: closeModal, modalMsg: modalMsg, ask: ask,
    onModalCancel: function (fn) { modal.onCancel = fn; },
    batchOptions: fillBatchOptions,
    register: function (name, hooks) { sections[name] = hooks || {}; },
    showSection: showSection,
    session: function () { return state.session; },
    recordId: RECORD_ID
  };

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
  $("prospectRefreshBtn").addEventListener("click", loadProspects);
  $("reviewRefreshBtn").addEventListener("click", loadReview);
  REVIEW_MODES.forEach(function (m) { if ($("rf_mode_" + m)) $("rf_mode_" + m).addEventListener("click", function () { setReviewMode(m); }); });
  $("importBtn2").addEventListener("click", openImport);
  $("blockedReloadBtn").addEventListener("click", function () { location.reload(); });
  // The lock guards against editing one record in two tabs. When the other tab
  // is not where the person is, they decide: open here anyway (the other tab,
  // if real, keeps working; the last save wins).
  $("blockedOpenBtn").addEventListener("click", async function () {
    hide($("blockedView"));
    if (LEAD_ID) await loadLead(); else await loadRecord();
  });
  ensureCampaignGrid();

  (async function init() {
    try {
      state.session = await api("/session");
    } catch (e) {
      if (e.status === 404) { text($("offReason"), "Marketing Management is switched off on this deployment (CAMPAIGNS_ENABLED at /setup)."); show($("offPanel")); }
      else if (e.status === 403) { text($("offReason"), e.message); show($("offPanel")); }
      else notice(e.message, "error");
      return;
    }
    text($("whoName"), state.session.name || state.session.userName); show($("userCorner"));
    if (state.session.callerOnly) {
      // A caller from another team: only the Calls tab, listing only the calls
      // they make. The server keeps every other door shut regardless.
      Array.prototype.forEach.call(document.querySelectorAll("#sectionNav .cm__navbtn"), function (b) { b.hidden = b.getAttribute("data-section") !== "calls"; });
      text($("pageSub"), "The calls you make for the call campaigns that name your team.");
      if (RECORD_ID || LEAD_ID) { text($("offReason"), "Your account is not authorized to open campaigns or leads here. Campaign calls are on the Calls tab."); show($("offPanel")); return; }
      if (!state.session.callsOn) { text($("offReason"), "Campaign calls are switched off on this deployment (CAMPAIGNS_CALLS at /setup)."); show($("offPanel")); return; }
      await showSection("calls");
      return;
    }
    if (!state.session.available) { text($("offReason"), state.session.reason); show($("offPanel")); return; }
    if (state.session.listsOnlyOn) setupListsOnlyGrid();
    if (!state.session.storeAvailable) notice("The application database is not configured here, so links and imports are unavailable; campaigns themselves still work.", "warn");
    try {
      await ensureFields();
      fillSelect($("statusFilter"), state.fields.options.campaignStatus, 1); fillSelect($("kindFilter"), state.fields.options.campaignKind, 1);
      fillGridOptions();
    } catch (e) { notice(e.message, "error"); }
    if (RECORD_ID) {
      $("sectionNav").hidden = true;
      var owner = await acquireRecordLock("campaigns:" + RECORD_ID);
      if (!owner) { show($("blockedView")); return; }
      await loadRecord();
    } else if (LEAD_ID) {
      $("sectionNav").hidden = true;
      var leadOwner = await acquireRecordLock("lead:" + LEAD_ID);
      if (!leadOwner) { show($("blockedView")); return; }
      await loadLead();
    } else {
      // Leads is the opening tab; a hash naming another tab wins. The
      // campaigns load first either way — the lead filters list them.
      await loadCampaigns();
      fillCampaignOptions();
      var h = hashParams();
      var start = SECTIONS.indexOf(h.section) >= 0 ? h.section : "prospects";
      if (start === "prospects") readHash("pf", h.params);
      if (start === "review") readHash("rf", h.params);
      if (!(await showSection(start, h.params))) await showSection("prospects");
      if (start !== "imports") loadImports();
    }
  })();
})();
