"use strict";
/** Mehmonlar uchun kirish sahifasi — videodagi effektlar:
 *  faralar yonishi va poldagi aks, mashina almashganda tezlik chiziqlari va "harakat xiraligi",
 *  sarlavhalarning "shifr" bilan paydo bo'lishi, neon chegarali faol kartalar (o'zi aylanadi),
 *  "rentgen" skaneri (mashina chizmaga aylanadi, energiya oqimi), tungi yo'l va ko'k tezlik izlari,
 *  yakuniy sahnada faralar yonadi, sahifa bo'limlari ekranga "yopishadi", tepada aylantirish chizig'i. */
const Landing = {
  // hx/hy — yaqin fara, fx/fy — uzoq fara (rasm ichidagi % koordinata)
  CARS: [
    { img: "/img/auth/camry.png", name: "Toyota Camry", tag: "lp.tag_business", hx: 36, hy: 44, fx: 4, fy: 45 },
    { img: "/img/auth/malibu_black.png", name: "Chevrolet Malibu", tag: "lp.tag_comfort", hx: 31, hy: 46, fx: 3, fy: 44 },
    { img: "/img/auth/tracker.png", name: "Chevrolet Tracker", tag: "lp.tag_family", hx: 32, hy: 43, fx: 3, fy: 42 },
    { img: "/img/auth/sonata.png", name: "Hyundai Sonata", tag: "lp.tag_trip", hx: 31, hy: 43, fx: 2, fy: 45 },
  ],
  TECH: [["shield", "lp.t1", "lp.t1d"], ["doc", "lp.t2", "lp.t2d"], ["finger", "lp.t3", "lp.t3d"], ["spark", "lp.t4", "lp.t4d"]],
  i: 0, ri: 0, timer: null, railTimer: null, techTimer: null, meta: null, reco: [],
  calm: matchMedia("(prefers-reduced-motion: reduce)").matches,

  async start() {
    document.body.classList.add("landing");
    document.documentElement.classList.add("lp-snapping");
    $("#landing").classList.remove("hidden");
    $("#homeMain").remove();
    $(".topbar")?.remove();
    $(".site-footer")?.remove();
    const today = isoDate(new Date());
    $("#lpStart").min = today; $("#lpEnd").min = today;
    $("#lpStart").addEventListener("change", () => { $("#lpEnd").min = $("#lpStart").value; if ($("#lpEnd").value && $("#lpEnd").value < $("#lpStart").value) $("#lpEnd").value = $("#lpStart").value; });
    $("#lpSearch").addEventListener("submit", (e) => {
      e.preventDefault();
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
      location.href = "/cars.html" + (p.toString() ? "?" + p : "");
    });
    $("#lpLang").addEventListener("click", () => setLang(I18N.langs[(I18N.langs.indexOf(I18N.lang) + 1) % 3]));

    // ---- 1. Bosh sahna ----
    $("#lpCars").innerHTML = this.CARS.map((c, i) => `<figure class="lp-car car-lit ${i ? "" : "on"}" style="--hx:${c.hx}%;--hy:${c.hy}%;--fx:${c.fx}%;--fy:${c.fy}%">
      <div class="car-box"><img src="${c.img}" alt="" ${i ? 'loading="lazy"' : ""}><img class="refl" src="${c.img}" alt="" ${i ? 'loading="lazy"' : ""}>
        <i class="hl near"></i><i class="hl far"></i><i class="beam"></i><i class="pool"></i></div>
      <figcaption><b>${esc(c.name)}</b><span data-k="${c.tag}"></span></figcaption></figure>`).join("");
    $("#lpDots").innerHTML = this.CARS.map((_, i) => `<button type="button" class="${i ? "" : "on"}" data-i="${i}" aria-label="${i + 1}"><i></i></button>`).join("");
    $("#lpDots").addEventListener("click", (e) => { const b = e.target.closest("[data-i]"); if (b) this.go(+b.dataset.i, true); });
    swipe($("#lpHero"), (d) => this.go(this.i + d, true));
    setTimeout(() => $(".lp-car.on")?.classList.add("lit"), 700);
    this.auto();
    // Sichqoncha bilan sahna biroz egiladi (parallaks)
    $("#lpHero").addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse" || this.calm) return;
      const r = e.currentTarget.getBoundingClientRect();
      e.currentTarget.style.setProperty("--px", ((e.clientX - r.left) / r.width - .5).toFixed(3));
      e.currentTarget.style.setProperty("--py", ((e.clientY - r.top) / r.height - .5).toFixed(3));
    });

    // ---- 2. Kolleksiya karuseli ----
    $("#lpPrev").addEventListener("click", () => this.rail(-1, true));
    $("#lpNext").addEventListener("click", () => this.rail(1, true));
    $("#lpRailDots").addEventListener("click", (e) => { const b = e.target.closest("[data-r]"); if (b) this.railTo(+b.dataset.r, true); });

    // ---- Paydo bo'lish, "shifr" sarlavhalar, faralar yonishi ----
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      $$("[data-scramble]", e.target).forEach((h) => this.scramble(h));
      if (e.target.id === "lpFinal") setTimeout(() => $("#lpFinalCar").classList.add("lit"), 500);
      io.unobserve(e.target);
    }), { threshold: .18 });
    $$(".reveal, #lpFinal", $("#landing")).forEach((el) => io.observe(el));
    this.scrollFx();

    [this.meta, this.reco] = await Promise.all([api("/api/meta").catch(() => null), api("/api/recommendations?limit=8").then((r) => r.items).catch(() => [])]);
    this.draw();
    $$("#lpHero [data-scramble]").forEach((h) => this.scramble(h));
    document.addEventListener("langchange", () => { this.draw(); $$("[data-scramble]").forEach((h) => this.scramble(h)); });
  },

  /** Mashina almashishi: eskisi chapga "uchib" ketadi (xiralik + tezlik chiziqlari), yangisi kirib, faralari yonadi */
  go(n, user = false) {
    const N = this.CARS.length, prev = this.i;
    this.i = (n + N) % N;
    if (prev === this.i) return;
    const stage = $(".lp-stage");
    stage.classList.remove("swoosh"); void stage.offsetWidth; stage.classList.add("swoosh");
    $$(".lp-car").forEach((f, k) => {
      f.classList.toggle("on", k === this.i); f.classList.toggle("off", k === prev); f.classList.remove("lit");
    });
    setTimeout(() => $$(".lp-car")[this.i]?.classList.add("lit"), 900);
    $$("#lpDots button").forEach((b, k) => b.classList.toggle("on", k === this.i));
    if (user) this.auto();
  },
  auto() {
    clearInterval(this.timer);
    if (this.calm) return;
    this.timer = setInterval(() => { if (!document.hidden) this.go(this.i + 1); }, 5600);
  },

  /** Kolleksiya: faol karta neon chegarada, 3,5 soniyada keyingisiga o'tadi */
  railTo(k, user = false) {
    const cards = $$(".lp-card"); if (!cards.length) return;
    this.ri = (k + cards.length) % cards.length;
    cards.forEach((c, j) => c.classList.toggle("active", j === this.ri));
    const rail = $("#lpRail"), c = cards[this.ri];
    rail.scrollTo({ left: c.offsetLeft - rail.offsetLeft - 2, behavior: "smooth" });
    $$("#lpRailDots button").forEach((b, j) => b.classList.toggle("on", j === this.ri));
    if (user) this.railAuto();
  },
  rail(d, user) { this.railTo(this.ri + d, user); },
  railAuto() { clearInterval(this.railTimer); if (!this.calm) this.railTimer = setInterval(() => { if (!document.hidden) this.rail(1); }, 3500); },
  techAuto() {
    clearInterval(this.techTimer);
    let k = 0;
    const step = () => { $$(".lp-tcard").forEach((c, j) => c.classList.toggle("active", j === k % this.TECH.length)); k++; };
    step(); if (!this.calm) this.techTimer = setInterval(step, 2400);
  },

  /** Sarlavha harflari tasodifiy belgilardan "ochilib" chiqadi (videodagi shifr effekti) */
  scramble(el) {
    const final = el.dataset.final || el.textContent;
    el.dataset.final = final;
    if (!final.trim() || this.calm) return;
    if (el._scr) cancelAnimationFrame(el._scr);
    const chars = "ABCDEFGHJKLMNOPRSTUVXYZ0123456789#%&*+<>/=";
    const len = final.length, start = performance.now(), dur = 700 + len * 22;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur), done = Math.floor(p * len);
      el.textContent = final.slice(0, done) + [...final.slice(done)].map((ch) => (ch === " " ? " " : chars[(Math.random() * chars.length) | 0])).join("");
      if (p < 1) el._scr = requestAnimationFrame(tick); else { el.textContent = final; el._scr = null; }
    };
    el._scr = requestAnimationFrame(tick);
  },

  /** Aylantirish: tepadagi chiziq va bo'limlardagi parallaks */
  scrollFx() {
    const bar = $("#lpProgress");
    let raf = null;
    const run = () => {
      raf = null;
      const max = document.documentElement.scrollHeight - innerHeight;
      bar.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
      $$(".lp-exp, .lp-xray").forEach((s) => {
        const r = s.getBoundingClientRect(), p = Math.max(-1, Math.min(1, (r.top + r.height / 2 - innerHeight / 2) / innerHeight));
        s.style.setProperty("--sp", p.toFixed(3));
      });
    };
    addEventListener("scroll", () => { if (!raf) raf = requestAnimationFrame(run); }, { passive: true });
    run();
  },

  draw() {
    $("#lpLang").textContent = I18N.lang.toUpperCase();
    $$("#lpCars [data-k]").forEach((s) => (s.textContent = t(s.dataset.k)));
    $$("[data-scramble]").forEach((h) => { delete h.dataset.final; });
    const m = this.meta;
    if (m) {
      $("#lpStats").innerHTML = [[m.cars_total, "home.stat_cars"], [m.cities.length, "home.stat_cities"], [m.completed_total, "home.stat_trips"],
        [shortMoney(m.price_min), "home.stat_from"]].map(([v, k]) => `<div><b>${esc(v)}</b><span>${esc(t(k))}</span></div>`).join("");
      const counts = Object.fromEntries(m.cities.map((c) => [c.city, c.count]));
      const v = $("#lpCity").value;
      $("#lpCity").innerHTML = `<option value="">${esc(t("search.any_city"))}</option>` + (Places.data?.regions || []).map((r) =>
        `<option value="${esc(r.key)}" data-n="${counts[r.key] || 0}">${esc(Places.regionName(r.key))}${counts[r.key] ? ` · ${esc(t("place.n_cars", { n: counts[r.key] }))}` : ""}</option>`).join("");
      $("#lpCity").value = v;
      SheetSelect.attach($("#lpCity"));
    }
    $("#lpRail").innerHTML = this.reco.length ? this.reco.map((c, k) => `<a class="lp-card ${k ? "" : "active"}" href="/car.html?id=${c.id}">
        <div class="lp-card-img">${carImage(c)}${maxDisc(c) ? `<span class="lp-disc">−${maxDisc(c)}%</span>` : ""}</div>
        <div class="lp-card-body"><b>${esc(carName(c))} <small>${esc(c.year)}</small></b>
          <span>${esc(t("body." + c.body_type))} · ${esc(t("trans." + c.transmission))} · ${esc(Places.regionName(c.city))}</span>
          <div class="lp-card-foot"><strong>${esc(money(c.price_per_day))}<small> ${esc(t("car.per_day"))}</small></strong><span class="lp-btn sm">${esc(t("car.details"))}</span></div></div></a>`).join("")
      : `<p class="lp-muted">${esc(t("cars.empty"))}</p>`;
    $("#lpRailDots").innerHTML = this.reco.map((_, k) => `<button type="button" data-r="${k}" class="${k ? "" : "on"}" aria-label="${k + 1}"></button>`).join("");
    this.ri = 0; this.railAuto();
    $("#lpTechCards").innerHTML = this.TECH.map(([ico, h, d], k) => `<div class="lp-tcard reveal in" style="--d:${k * 90}ms">
      <span class="lp-tico">${icon(ico, 28)}</span><b>${esc(t(h))}</b><p>${esc(t(d))}</p><i class="lp-tline"></i></div>`).join("");
    this.techAuto();
  },
};
