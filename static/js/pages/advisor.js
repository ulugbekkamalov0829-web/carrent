"use strict";
/* Maslahatchi: 4 qadamli savolnoma -> server har bir avtomobilga moslik foizi va sabablarini qaytaradi.
   Javoblar shu brauzerda eslab qolinadi (keyingi safar qaytadan to'ldirish shart emas). */
(async () => {
  await boot("");
  const box = $("#advisor"), out = $("#advResults");
  const meta = await api("/api/meta").catch(() => ({ cities: [] }));
  // 3D realistik ikonkalar (Microsoft Fluent Emoji, MIT) — /img/adv/
  const PURPOSES = ["city", "family", "trip", "mountain", "business", "event", "cargo"].map((k) => [k, `/img/adv/${k}.png`]);
  const LUGGAGE = ["none", "small", "medium", "large"].map((k) => [k, `/img/adv/lug_${k}.png`]);
  const PRIOS = ["economy", "comfort", "safety", "prestige", "price"];
  const FEATS = ["child_seat", "isofix", "ac", "climate", "camera", "bluetooth", "carplay", "cruise", "heated_seats", "navigation", "roof_rack", "pets_ok"];
  const BUDGETS = [250000, 400000, 600000, 1000000];
  const DEFAULTS = { purpose: "city", passengers: 2, luggage: "small", budget_max: null, city: Auth.user?.region || "", district: Auth.user?.district || "", start_date: "", end_date: "",
    transmission: "", experience: "normal", priorities: [], features: [], delivery: false };
  let ans = { ...DEFAULTS };
  try { ans = { ...DEFAULTS, ...(JSON.parse(localStorage.getItem("adv.answers") || "{}")) }; } catch {}
  if (ans.start_date && ans.start_date < isoDate(new Date())) { ans.start_date = ""; ans.end_date = ""; }
  let step = 0;
  const STEPS = ["purpose", "people", "budget", "prefs"];

  const tile = (group, value, emoji, on, sub = "") => `<button type="button" class="adv-tile ${on ? "on" : ""}" data-g="${group}" data-v="${value}" aria-pressed="${on}">
    <img class="em" src="${emoji}" alt="" width="56" height="56" loading="lazy"><b>${esc(t(`adv.${group}_${value}`))}</b>${sub ? `<span class="small muted">${esc(sub)}</span>` : ""}</button>`;
  const chip = (group, value, label, on) => `<button type="button" class="chip-btn ${on ? "on" : ""}" data-g="${group}" data-v="${value}" aria-pressed="${on}">${esc(label)}</button>`;

  function stepHtml() {
    if (step === 0) return `<h2>${esc(t("adv.q_purpose"))}</h2><div class="adv-grid">
      ${PURPOSES.map(([k, e]) => tile("purpose", k, e, ans.purpose === k, t(`adv.purpose_${k}_d`))).join("")}</div>`;
    if (step === 1) return `<h2>${esc(t("adv.q_people"))}</h2>
      <div class="adv-stepper"><button type="button" class="icon-btn" data-pass="-1" aria-label="−">−</button>
        <div><b id="passN">${ans.passengers}</b><span class="muted">${esc(t("adv.people_unit"))}</span></div>
        <button type="button" class="icon-btn" data-pass="1" aria-label="+">+</button></div>
      <p class="small muted center">${esc(t("adv.people_hint"))}</p>
      <h3 style="margin-top:22px">${esc(t("adv.q_luggage"))}</h3>
      <div class="adv-grid four">${LUGGAGE.map(([k, e]) => tile("luggage", k, e, ans.luggage === k)).join("")}</div>`;
    if (step === 2) return `<h2>${esc(t("adv.q_budget"))}</h2>
      <div class="chips">${BUDGETS.map((b) => chip("budget", b, t("adv.upto", { sum: shortMoney(b) }), ans.budget_max === b)).join("")}
        ${chip("budget", "", t("common.any"), !ans.budget_max)}</div>
      <div class="field" style="max-width:280px;margin-top:12px"><label for="advBudget">${esc(t("adv.budget_own"))}</label>
        <input class="input" type="text" data-money id="advBudget" value="${ans.budget_max || ""}" placeholder="350 000"></div>
      <div class="grid-2" style="margin-top:6px">
        <div class="field"><label for="advCity">${esc(t("adv.q_city"))}</label><select class="input" id="advCity"></select></div>
        <div class="field"><label for="advDist">${esc(t("place.district"))} <span class="muted small">(${esc(t("common.optional"))})</span></label><select class="input" id="advDist"></select></div>
        <div class="field"><label for="advS">${esc(t("adv.from"))} <span class="muted small">(${esc(t("common.optional"))})</span></label><input class="input" type="date" id="advS" value="${esc(ans.start_date)}"></div>
        <div class="field"><label for="advE">${esc(t("adv.to"))}</label><input class="input" type="date" id="advE" value="${esc(ans.end_date)}"></div>
      </div><p class="small muted">${esc(t("adv.dates_hint"))}</p>`;
    return `<h2>${esc(t("adv.q_prefs"))}</h2>
      <h3>${esc(t("adv.q_prio"))} <span class="muted small">${esc(t("adv.max3"))}</span></h3>
      <div class="chips">${PRIOS.map((k) => chip("prio", k, t("adv.prio_" + k), ans.priorities.includes(k))).join("")}</div>
      <div class="grid-2" style="margin-top:18px">
        <div><h3>${esc(t("adv.q_trans"))}</h3><div class="chips">${chip("trans", "", t("common.any"), !ans.transmission)}
          ${["automatic", "manual"].map((k) => chip("trans", k, t("trans." + k), ans.transmission === k)).join("")}</div></div>
        <div><h3>${esc(t("adv.q_exp"))}</h3><div class="chips">${["new", "normal"].map((k) => chip("exp", k, t("adv.exp_" + k), ans.experience === k)).join("")}</div></div>
      </div>
      <h3 style="margin-top:18px">${esc(t("adv.q_feats"))}</h3>
      <div class="chips">${FEATS.map((k) => chip("feat", k, t("feature." + k), ans.features.includes(k))).join("")}</div>
      <label class="check" style="margin-top:16px"><input type="checkbox" id="advDel" ${ans.delivery ? "checked" : ""}> <span>${esc(t("adv.delivery"))}</span></label>`;
  }

  function draw() {
    box.innerHTML = `<div class="card adv-card">
      <div class="adv-progress" aria-hidden="true">${STEPS.map((s, i) => `<div class="${i < step ? "done" : i === step ? "on" : ""}"><i>${i < step ? "✓" : i + 1}</i><span>${esc(t("adv.s_" + s))}</span></div>`).join("")}</div>
      <div class="card-pad adv-body">${stepHtml()}</div>
      <div class="card-pad adv-nav">
        <button type="button" class="btn btn-outline" id="advBack" ${step ? "" : "disabled"}>← ${esc(t("common.back"))}</button>
        <span class="small muted">${esc(t("adv.step_of", { a: step + 1, b: STEPS.length }))}</span>
        ${step < STEPS.length - 1 ? `<button type="button" class="btn" id="advNext">${esc(t("common.next"))} →</button>`
          : `<button type="button" class="btn btn-lg" id="advGo">${icon("spark", 18)} ${esc(t("adv.go"))}</button>`}
      </div></div>`;
    bind();
  }

  function readInputs() {
    if ($("#advBudget")) { const v = moneyVal($("#advBudget").value); ans.budget_max = v >= 50000 ? v : null; }
    if ($("#advCity")) { ans.city = $("#advCity").value; ans.district = $("#advDist").value; }
    if ($("#advS")) { ans.start_date = $("#advS").value; ans.end_date = $("#advE").value; }
    if ($("#advDel")) ans.delivery = $("#advDel").checked;
    try { localStorage.setItem("adv.answers", JSON.stringify(ans)); } catch {}
  }

  function bind() {
    $$("[data-g]", box).forEach((b) => b.addEventListener("click", () => {
      const g = b.dataset.g, v = b.dataset.v;
      if (g === "purpose") ans.purpose = v;
      if (g === "luggage") ans.luggage = v;
      if (g === "budget") { ans.budget_max = v ? +v : null; }
      if (g === "trans") ans.transmission = v;
      if (g === "exp") ans.experience = v;
      if (g === "prio") {
        if (ans.priorities.includes(v)) ans.priorities = ans.priorities.filter((x) => x !== v);
        else if (ans.priorities.length < 3) ans.priorities.push(v);
        else { toast(t("adv.max3_toast"), "error"); return; }
      }
      if (g === "feat") ans.features = ans.features.includes(v) ? ans.features.filter((x) => x !== v) : [...ans.features, v].slice(0, 8);
      if (g === "budget" && $("#advBudget")) $("#advBudget").value = fmtMoneyInput(ans.budget_max || "");
      readInputs();
      if (g === "purpose") { step++; draw(); return; }      // bitta bosish bilan keyingi savolga
      draw();
    }));
    $$("[data-pass]", box).forEach((b) => b.addEventListener("click", () => {
      ans.passengers = Math.max(1, Math.min(15, ans.passengers + +b.dataset.pass)); $("#passN").textContent = ans.passengers; readInputs();
    }));
    if ($("#advCity")) {
      Places.bind($("#advCity"), $("#advDist"), { region: ans.city, district: ans.district, any: true });
      $("#advDist").addEventListener("change", readInputs); $("#advCity").addEventListener("change", readInputs);
    }
    applyMasks(box);
    $("#advBudget")?.addEventListener("input", () => {   // yozilgan summa tayyor variantga teng bo'lsa — o'sha tugma belgilanadi
      const v = moneyVal($("#advBudget").value);
      $$("[data-g=budget]", box).forEach((c) => c.classList.toggle("on", c.dataset.v ? +c.dataset.v === v : !v));
    });
    const today = isoDate(new Date());
    if ($("#advS")) {
      $("#advS").min = today; $("#advE").min = ans.start_date || today;
      $("#advS").addEventListener("change", () => { $("#advE").min = $("#advS").value || today; if (!$("#advE").value || $("#advE").value < $("#advS").value) $("#advE").value = $("#advS").value; });
      DateField.enhance(box);
    }
    $("#advBack").addEventListener("click", () => { readInputs(); step = Math.max(0, step - 1); draw(); });
    $("#advNext")?.addEventListener("click", () => {
      readInputs();
      if (step === 2 && Boolean(ans.start_date) !== Boolean(ans.end_date)) { toast(t("adv.both_dates"), "error"); return; }
      step++; draw();
    });
    $("#advGo")?.addEventListener("click", (e) => withLoading(e.currentTarget, run));
  }

  async function run() {
    readInputs();
    const body = { ...ans, budget_max: ans.budget_max || null, city: ans.city || null, district: (ans.city && ans.district) || null, transmission: ans.transmission || null,
      start_date: ans.start_date || null, end_date: ans.end_date || null };
    try {
      const r = await api("/api/advisor", { method: "POST", body });
      results(r);
      out.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) { toast(err.message, "error"); }
  }

  function reasonText(x) {
    const p = { ...(x.p || {}) };
    for (const k of ["price", "left", "over", "deposit"]) if (typeof p[k] === "number") p[k] = money(p[k]);
    if (p.body) p.body = t("body." + p.body);
    if (p.purpose) p.purpose = t(`adv.purpose_${p.purpose}`).toLowerCase();
    if (p.fuel) p.fuel = t("fuel." + p.fuel);
    if (p.list) p.list = p.list.map((f) => t("feature." + f)).join(", ");
    return t("adv.r_" + x.code, p);
  }

  function results(r) {
    const qs = ans.start_date ? `&start=${ans.start_date}&end=${ans.end_date}` : "";
    const summary = [t(`adv.purpose_${ans.purpose}`), t("adv.n_people", { n: ans.passengers }), ans.budget_max ? t("adv.upto", { sum: money(ans.budget_max) }) : null,
      ans.city ? Places.label(ans.city, ans.district) : null, ans.transmission ? t("trans." + ans.transmission) : null].filter(Boolean).join(" · ");
    if (!r.items.length) {
      out.innerHTML = `<div class="empty card" style="margin-top:18px"><h3>${esc(t("adv.none"))}</h3><p>${esc(t("adv.none_hint"))}</p>
        <a class="btn btn-outline" href="/cars.html">${esc(t("nav.cars"))}</a></div>`;
      return;
    }
    out.innerHTML = `<section class="adv-results">
      <div class="row" style="justify-content:space-between;align-items:flex-end;margin:26px 0 10px"><div><h2 style="margin:0">${esc(t("adv.results", { n: r.items.length }))}</h2>
        <div class="small muted">${esc(summary)}</div></div>
        <button class="btn btn-sm btn-outline" id="advEdit">${esc(t("adv.change"))}</button></div>
      ${r.relaxed.length ? `<div class="notice" style="margin-bottom:14px">${esc(t("adv.relaxed", { what: r.relaxed.map((k) => t("adv.rel_" + k)).join(", ") }))}</div>` : ""}
      <div class="adv-list">${r.items.map((c, i) => `<article class="card adv-item ${i === 0 ? "first" : ""}">
        <a class="adv-thumb" href="/car.html?id=${c.id}${qs}">${carImage(c)}${c.badge ? `<span class="adv-badge b-${c.badge}">${esc(t("adv.badge_" + c.badge))}</span>` : ""}</a>
        <div class="adv-main">
          <div class="row" style="justify-content:space-between;gap:8px;flex-wrap:nowrap;align-items:flex-start">
            <div><a class="car-title" href="/car.html?id=${c.id}${qs}">${esc(carName(c))} <span class="muted small">${c.year}</span></a>
              <div class="small muted">📍 ${esc(Places.label(c.city, c.district))} · ${esc(t("body." + c.body_type))} · ${esc(t("trans." + c.transmission))} · ${esc(t("fuel." + c.fuel))} · ${esc(t("car.seats_n", { n: c.seats }))}</div></div>
            <div class="match" style="--m:${c.match}" title="${esc(t("adv.match_hint"))}"><b>${c.match}%</b><span>${esc(t("adv.match"))}</span></div>
          </div>
          <ul class="why">${c.pros.map((x) => `<li class="pro">${icon("check", 15)} ${esc(reasonText(x))}</li>`).join("")}
            ${c.cons.map((x) => `<li class="con">${icon("flag", 15)} ${esc(reasonText(x))}</li>`).join("")}</ul>
          <div class="adv-foot"><div class="price">${money(c.price_per_day)} <small>${esc(t("car.per_day"))}</small>
            ${c.total ? `<div class="small muted">${esc(t("adv.total_for", { n: r.days }))}: <b>${money(c.total)}</b></div>` : ""}</div>
            <div class="row" style="gap:6px"><a class="btn btn-sm btn-outline" href="/car.html?id=${c.id}${qs}">${esc(t("car.details"))}</a>
              <a class="btn btn-sm" href="/car.html?id=${c.id}${qs}#book">${esc(t("car.book"))}</a></div></div>
        </div></article>`).join("")}</div>
      <div class="card card-pad adv-tips"><h3>${icon("bulb", 18)} ${esc(t("adv.tips"))}</h3><ul>${r.tips.map((k) => `<li>${esc(t("adv." + k))}</li>`).join("")}</ul>
        <p class="small muted" style="margin:8px 0 0">${esc(t("adv.how"))}</p></div>
    </section>`;
    $("#advEdit").addEventListener("click", () => { step = 0; draw(); box.scrollIntoView({ behavior: "smooth" }); });
  }

  draw();
  document.addEventListener("langchange", () => { draw(); if (out.innerHTML) run(); });
})();
