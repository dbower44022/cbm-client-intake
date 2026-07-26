/* Birthday celebration overlay — shown on the portal when a mentor signs in on
   their birthday, before their screen.

   Self-contained: `CBMBirthday.celebrate({ name, onDone })` builds the overlay,
   runs a canvas fireworks display, and calls `onDone` exactly once when the
   user (or the auto-dismiss) closes it. The caller carries on from there, so a
   failure here can never strand someone at sign-in.

   Respects `prefers-reduced-motion`: the same greeting, no animation. */
(function () {
  "use strict";

  var SHOW_MS = 9000;          // auto-dismiss; any click or key closes sooner
  var FADE_MS = 450;
  var COLORS = [
    "#FFD36E", "#CB963B", "#FFFFFF", "#7CC6FF",
    "#FF7FA3", "#6FE7C0", "#C7A2FF", "#FFB05C",
  ];

  var GRAVITY = 0.16;          // px per frame², for the rising shells

  function reducedMotion() {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch (e) { return false; }
  }

  function rand(min, max) { return min + Math.random() * (max - min); }
  function pick(a) { return a[(Math.random() * a.length) | 0]; }

  /* --- the fireworks ------------------------------------------------------
     Particles keep their previous position and are drawn as short additive
     line segments, so the canvas itself stays transparent (the overlay's
     gradient shows through) and each spark leaves a comet trail. */
  function Fireworks(canvas) {
    var ctx = canvas.getContext("2d");
    var rockets = [], sparks = [], raf = null, launching = true, last = 0, nextLaunch = 0;
    var w = 0, h = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    // Launch speed is DERIVED from where the shell should burst (apex ≈ burstY,
    // from v² = 2·g·rise) — a fixed speed only climbs ~300px, which on a tall
    // window means every burst happens down by the taskbar.
    function launch(x) {
      var burstY = rand(h * 0.08, h * 0.44);
      var vy = -Math.sqrt(2 * GRAVITY * Math.max(60, h - burstY)) * rand(1, 1.06);
      rockets.push({
        x: x === undefined ? rand(w * 0.1, w * 0.9) : x,
        y: h + 8, px: h + 8,
        vx: rand(-0.5, 0.5),
        vy: vy,
        color: pick(COLORS),
        burstY: burstY,
      });
    }

    function burst(r) {
      // Bursts scale with the window so a big monitor gets a big display.
      var n = (rand(52, 84) | 0);
      var spread = rand(2.6, 4.6) * Math.max(0.85, Math.min(1.7, Math.min(w, h) / 900));
      for (var i = 0; i < n; i++) {
        var a = Math.random() * Math.PI * 2;
        var sp = spread * Math.sqrt(Math.random()) * (Math.random() < 0.08 ? 1.7 : 1);
        sparks.push({
          x: r.x, y: r.y, px: r.x, py: r.y,
          vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
          color: Math.random() < 0.22 ? pick(COLORS) : r.color,
          life: 1, decay: rand(0.008, 0.018),
        });
      }
    }

    function step(now) {
      raf = window.requestAnimationFrame(step);
      var dt = last ? Math.min((now - last) / 16.67, 3) : 1;   // frames, capped
      last = now;

      if (launching && now >= nextLaunch) {
        launch();
        if (Math.random() < 0.35) launch();                     // occasional pair
        nextLaunch = now + rand(280, 620);
      }

      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";

      var i, r, s;
      for (i = rockets.length - 1; i >= 0; i--) {
        r = rockets[i];
        r.px = r.y;
        r.x += r.vx * dt;
        r.y += r.vy * dt;
        r.vy += GRAVITY * dt;
        ctx.strokeStyle = r.color;
        ctx.globalAlpha = 0.9;
        ctx.lineWidth = 2.4;
        ctx.beginPath(); ctx.moveTo(r.x, r.px); ctx.lineTo(r.x, r.y); ctx.stroke();
        if (r.vy >= -1.6 || r.y <= r.burstY) { burst(r); rockets.splice(i, 1); }
      }

      for (i = sparks.length - 1; i >= 0; i--) {
        s = sparks[i];
        s.px = s.x; s.py = s.y;
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        s.vy += 0.055 * dt;                                     // gravity
        s.vx *= Math.pow(0.985, dt);                            // drag
        s.vy *= Math.pow(0.985, dt);
        s.life -= s.decay * dt;
        if (s.life <= 0) { sparks.splice(i, 1); continue; }
        // Twinkle as they fade out.
        var a = s.life > 0.35 ? s.life : s.life * (0.55 + 0.45 * Math.random());
        ctx.globalAlpha = Math.max(0, Math.min(1, a));
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 1 + 1.6 * s.life;
        ctx.beginPath(); ctx.moveTo(s.px, s.py); ctx.lineTo(s.x, s.y); ctx.stroke();
      }

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    }

    return {
      start: function () {
        resize();
        window.addEventListener("resize", resize);
        // Open with a small volley so the display is alive immediately.
        launch(w * rand(0.2, 0.4));
        launch(w * rand(0.55, 0.8));
        nextLaunch = 0;
        raf = window.requestAnimationFrame(step);
      },
      stop: function () {
        launching = false;
        window.removeEventListener("resize", resize);
        if (raf) window.cancelAnimationFrame(raf);
        raf = null;
      },
    };
  }

  /* --- the overlay -------------------------------------------------------- */
  function build(name) {
    var el = document.createElement("div");
    el.className = "bday";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "Happy birthday");

    var canvas = document.createElement("canvas");
    canvas.className = "bday__sky";
    canvas.setAttribute("aria-hidden", "true");

    var card = document.createElement("div");
    card.className = "bday__card";

    var eyebrow = document.createElement("p");
    eyebrow.className = "bday__eyebrow";
    eyebrow.textContent = "Cleveland Business Mentors";

    var title = document.createElement("h2");
    title.className = "bday__title";
    title.textContent = "Happy Birthday";

    var who = document.createElement("p");
    who.className = "bday__name";
    who.textContent = name ? name + "!" : "!";

    var msg = document.createElement("p");
    msg.className = "bday__msg";
    msg.textContent =
      "Thank you for all you do for our clients and mentors. Have a wonderful day.";

    var go = document.createElement("button");
    go.type = "button";
    go.className = "bday__go";
    go.textContent = "Continue →";

    card.appendChild(eyebrow);
    card.appendChild(title);
    card.appendChild(who);
    card.appendChild(msg);
    card.appendChild(go);
    el.appendChild(canvas);
    el.appendChild(card);
    return { el: el, canvas: canvas, button: go };
  }

  function celebrate(opts) {
    opts = opts || {};
    var finished = false;
    function done() {
      if (finished) return;
      finished = true;
      try { if (typeof opts.onDone === "function") opts.onDone(); } catch (e) {}
    }

    var parts, show, timer = null, fw = null;
    try {
      parts = build(opts.name);
      document.body.appendChild(parts.el);
    } catch (e) {
      done();                       // the greeting is never worth a broken login
      return;
    }

    function close() {
      if (timer) { window.clearTimeout(timer); timer = null; }
      document.removeEventListener("keydown", onKey, true);
      if (fw) { try { fw.stop(); } catch (e) {} }
      parts.el.classList.add("bday--out");
      window.setTimeout(function () {
        if (parts.el.parentNode) parts.el.parentNode.removeChild(parts.el);
      }, FADE_MS);
      done();                       // hand over as the overlay fades
    }

    function onKey(ev) {
      if (ev.key === "Escape" || ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        close();
      }
    }

    parts.button.addEventListener("click", function (ev) { ev.stopPropagation(); close(); });
    parts.el.addEventListener("click", close);
    document.addEventListener("keydown", onKey, true);

    if (!reducedMotion()) {
      try { fw = Fireworks(parts.canvas); fw.start(); } catch (e) { fw = null; }
    }

    // Let the element land before the entrance transition.
    window.requestAnimationFrame(function () { parts.el.classList.add("bday--in"); });
    try { parts.button.focus({ preventScroll: true }); } catch (e) {}

    show = typeof opts.duration === "number" ? opts.duration : SHOW_MS;
    timer = window.setTimeout(close, show);
  }

  window.CBMBirthday = { celebrate: celebrate };
})();
