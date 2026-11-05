"use strict";
/** Mehmonlar uchun kirish sahifasi: qorong'i "showroom", mashinalar almashinib turadigan sahna, kolleksiya, texnologiyalar. */
const Landing = {
  CARS: [
    { img: "/img/auth/camry.png", name: "Toyota Camry", tag: "lp.tag_business" },
    { img: "/img/auth/malibu_black.png", name: "Chevrolet Malibu", tag: "lp.tag_comfort" },
    { img: "/img/auth/tracker.png", name: "Chevrolet Tracker", tag: "lp.tag_family" },
    { img: "/img/auth/sonata.png", name: "Hyundai Sonata", tag: "lp.tag_trip" },
  ],
  TECH: [["shield", "lp.t1", "lp.t1d"], ["doc", "lp.t2", "lp.t2d"], ["finger", "lp.t3", "lp.t3d"], ["spark", "lp.t4", "lp.t4d"]],
  i: 0, timer: null, meta: null, reco: [],

  async start() {
    document.body.classList.add("landing");
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
    $("#lpLang").addEventListener("click", () => { const l = I18N.langs[(I18N.langs.indexOf(I18N.lang) + 1) % 3]; setLang(l); });
    $("#lpCars").innerHTML = this.CARS.map((c, i) => `<figure class="lp-car ${i ? "" : "on"}"><img src="${c.img}" alt="" ${i ? 'loading="lazy"' : ""}>
      <figcaption><b>${esc(c.name)}</b><span data-k="${c.tag}"></span></figcaption></figure>`).join("");
    $("#lpDots").innerHTML = this.CARS.map((_, i) => `<button type="button" class="${i ? "" : "on"}" data-i="${i}" aria-label="${i + 1}"></button>`).join("");
    $("#lpDots").addEventListener("click", (e) => { const b = e.target.closest("[data-i]"); if (b) this.go(+b.dataset.i, true); });
    swipe($("#lpHero"), (d) => this.go(this.i + d, true));
    this.auto();
    $("#lpPrev").addEventListener("click", () => $("#lpRail").scrollBy({ left: -$("#lpRail").clientWidth * .8, behavior: "smooth" }));
    $("#lpNext").addEventListener("click", () => $("#lpRail").scrollBy({ left: $("#lpRail").clientWidth * .8, behavior: "smooth" }));
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .12 });
    $$(".reveal", $("#landing")).forEach((el) => io.observe(el));
    [this.meta, this.reco] = await Promise.all([api("/api/meta").catch(() => null), api("/api/recommendations?limit=8").then((r) => r.items).catch(() => [])]);
    this.draw();
    document.addEventListener("langchange", () => this.draw());
  },

  go(n, user = false) {
    const N = this.CARS.length;
    this.i = (n + N) % N;
    $$(".lp-car").forEach((f, k) => { f.classList.toggle("on", k === this.i); f.classList.toggle("off", k !== this.i); });
    $$("#lpDots button").forEach((b, k) => b.classList.toggle("on", k === this.i));
    if (user) this.auto();
  },
  auto() {
    clearInterval(this.timer);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    this.timer = setInterval(() => { if (!document.hidden) this.go(this.i + 1); }, 4800);
  },

  draw() {
    $("#lpLang").textContent = I18N.lang.toUpperCase();
    $$("#lpCars [data-k]").forEach((s) => (s.textContent = t(s.dataset.k)));
    const m = this.meta;
    if (m) {
      $("#lpStats").innerHTML = [[m.cars_total, "home.stat_cars"], [m.cities.length, "home.stat_cities"], [m.completed_total, "home.stat_trips"],
        [shortMoney(m.price_min), "home.stat_from"]].map(([v, k]) => `<div><b>${esc(v)}</b><span>${esc(t(k))}</span></div>`).join("");
      const counts = Object.fromEntries(m.cities.map((c) => [c.city, c.count]));
      const v = $("#lpCity").value;
      $("#lpCity").innerHTML = `<option value="">${esc(t("search.any_city"))}</option>` + (Places.data?.regions || []).map((r) =>
        `<option value="${esc(r.key)}">${esc(Places.regionName(r.key))}${counts[r.key] ? ` · ${counts[r.key]}` : ""}</option>`).join("");
      $("#lpCity").value = v;
    }
    $("#lpRail").innerHTML = this.reco.length ? this.reco.map((c) => `<a class="lp-card" href="/car.html?id=${c.id}">
        <div class="lp-card-img">${carImage(c)}</div>
        <div class="lp-card-body"><b>${esc(carName(c))} <small>${esc(c.year)}</small></b>
          <span>${esc(t("body." + c.body_type))} · ${esc(t("trans." + c.transmission))} · ${esc(Places.regionName(c.city))}</span>
          <div class="lp-card-foot"><strong>${esc(money(c.price_per_day))}<small> ${esc(t("car.per_day"))}</small></strong><span class="lp-btn sm">${esc(t("car.details"))}</span></div></div></a>`).join("")
      : `<p class="lp-muted">${esc(t("cars.empty"))}</p>`;
    $("#lpTechCards").innerHTML = this.TECH.map(([ico, h, d], k) => `<div class="lp-tcard reveal in" style="--d:${k * 90}ms">
      <span class="lp-tico">${icon(ico, 28)}</span><b>${esc(t(h))}</b><p>${esc(t(d))}</p></div>`).join("");
  },
};
