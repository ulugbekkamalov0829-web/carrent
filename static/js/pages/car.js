"use strict";
(async () => {
  const user = await boot("cars");
  const params = new URLSearchParams(location.search);
  const id = Number(params.get("id"));
  const root = $("#root");
  let car, reviews = { items: [] }, cal = null, prov = {};
  try { [car, reviews, prov] = await Promise.all([api(`/api/cars/${id}`), api(`/api/cars/${id}/reviews`), api("/api/payments/providers").catch(() => ({}))]); }
  catch (e) { root.innerHTML = `<div class="empty card"><h2>${esc(t("car.not_found"))}</h2><p>${esc(e.message)}</p><a class="btn" href="/cars.html">${esc(t("nav.cars"))}</a></div>`; return; }

  const canBook = user && user.role !== "admin" && !car.is_mine;
  const form = { start: params.get("start") || "", end: params.get("end") || "", delivery: false, note: "" };
  let imgIndex = 0;

  function spec(k, v, ico) {
    return v === null || v === undefined || v === "" ? "" : `<div class="spec-tile"><span class="sp-ico">${icon(ico, 22)}</span><div><div class="k">${esc(t(k))}</div><div class="v">${esc(v)}</div></div></div>`;
  }
  const hasLoc = () => car.lat != null && car.lng != null;      // aniq nuqta faqat egasi/bron qilganlarga (loc_exact)

  function reviewsBlock() {
    if (!reviews.items.length) return `<p class="muted">${esc(t("car.reviews_empty"))}</p>`;
    const dist = [5, 4, 3, 2, 1].map((n) => ({ n, c: reviews.items.filter((r) => r.rating === n).length }));
    return `<div class="rev-sum"><div class="rev-big"><b>${car.rating ?? "—"}</b><div><span class="stars">${stars(car.rating)}</span><div class="small muted">${esc(t("car.reviews_n", { n: car.reviews_count }))}</div></div></div>
        <div class="rev-dist">${dist.map((d) => `<div><span>${d.n}★</span><i><b style="width:${reviews.items.length ? (d.c / reviews.items.length) * 100 : 0}%"></b></i><span>${d.c}</span></div>`).join("")}</div></div>
      <div class="rev-grid">${reviews.items.map((r) => `<div class="review card">
        <div class="row"><span class="avatar">${esc(initials(r.author))}</span><div><b>${esc(r.author)}</b><div class="small muted">${fmtDate(r.created_at)}</div></div>
        <span class="spacer"></span><span class="stars">${stars(r.rating)}</span></div>
        ${r.comment ? `<p style="margin:8px 0 0">${esc(r.comment)}</p>` : ""}
        ${r.reply ? `<div class="reply"><b>${esc(t("review.owner_reply"))}:</b> ${esc(r.reply)}</div>` : ""}</div>`).join("")}</div>`;
  }

  /** Uzoq muddat chegirmasi: har pog'ona uchun kunlik narx */
  function discountBlock() {
    const d = Object.entries(car.discounts || {}).sort((a, b) => a[0] - b[0]);
    if (!d.length) return "";
    const rows = [[1, 0], ...d.map(([k, p]) => [+k, p])];
    return `<div class="card card-pad disc-card" style="margin-bottom:18px"><h3>${icon("tag", 18)} ${esc(t("disc.title"))}</h3><p class="small muted">${esc(t("disc.sub"))}</p>
      <div class="disc-grid">${rows.map(([k, p], i) => `<div class="${p ? "on" : ""}"><small>${esc(i ? t("disc.from_days", { d: k }) : t("disc.base"))}</small>
        <b>${money(Math.round(car.price_per_day * (100 - p) / 100))}</b><span>${p ? `−${p}%` : esc(t("car.per_day"))}</span></div>`).join("")}</div></div>`;
  }

  function render() {
    // Formadagi qiymatlarni saqlab qolamiz (til almashganda yo'qolmasin)
    if ($("#bStart")) Object.assign(form, { start: $("#bStart").value, end: $("#bEnd").value, delivery: $("#bDelivery")?.checked || false, note: $("#bNote").value });
    document.title = `${carName(car)} ${car.year} — CarRent`;
    const hidden = !car.is_active || !car.is_approved;
    const images = car.images.length ? car.images : [null];
    const place = car.address ? `${car.address}, ${Places.label(car.city, car.district)}` : Places.label(car.city, car.district);
    root.innerHTML = `
      ${hidden ? `<div class="notice" style="margin-bottom:16px">${esc(t(!car.is_approved ? "car.hidden_admin" : "car.hidden_owner"))}</div>` : ""}
      <nav class="small muted" style="margin-bottom:10px" aria-label="breadcrumb"><a href="/cars.html">${esc(t("nav.cars"))}</a> › <a href="/cars.html?city=${encodeURIComponent(car.city)}">${esc(Places.regionName(car.city))}</a> › ${esc(car.brand)}</nav>
      <section class="car-hero" id="mainImg">${carImage(car, images[imgIndex]?.path)}
        <div class="hero-shade"></div>
        <div class="hero-title"><h1>${esc(carName(car))} ${esc(car.year)}</h1><div>${esc(t("body." + car.body_type))} · ${esc(t("trans." + car.transmission))}</div></div>
        ${car.images.length > 1 ? `<div class="hero-dots" id="thumbs">${car.images.map((im, i) => `<button class="${i === imgIndex ? "active" : ""}" data-i="${i}" aria-label="${esc(t("car.photo_n", { n: i + 1 }))}">${i + 1}</button>`).join("")}</div>` : ""}
        ${car.images.length ? `<button class="gal-zoom" id="openLb" aria-label="${esc(t("gallery.open"))}">${icon("search", 18)} ${imgIndex + 1} / ${car.images.length}</button>` : ""}
        <span class="gal-label ${images[imgIndex]?.label ? "" : "hidden"}">${images[imgIndex]?.label ? esc(t("img.label_" + images[imgIndex].label)) : ""}</span>
        ${car.images.length > 1 ? `<button class="gal-nav prev" data-step="-1" aria-label="${esc(t("cal.prev"))}">${icon("arrowl")}</button><button class="gal-nav next" data-step="1" aria-label="${esc(t("cal.next"))}">${icon("arrowr")}</button>` : ""}
        ${car.is_mine ? "" : `<button class="fav-btn ${car.is_favorite ? "on" : ""}" data-fav="${car.id}" aria-pressed="${!!car.is_favorite}" aria-label="${esc(t(car.is_favorite ? "fav.remove" : "fav.add"))}">${car.is_favorite ? HEART : HEART_O}</button>`}
      </section>
      <div class="detail detail-v7">
        <div>
          <div class="car-headline">
            <div><h2 style="margin:0">${esc(carName(car))} ${esc(car.year)}</h2>
              <div class="small muted">${icon("pin", 14)} ${esc(place)}</div>
              ${car.ownership_status === "verified" ? `<span class="verified own-badge">${icon("idcard", 13)} ${esc(t("own.verified"))}</span>` : ""}</div>
            <div class="owner-chip">${avatarHtml(car.owner)}<div><b>${esc(car.owner.full_name)}</b>${car.owner.phone_verified ? ` <span class="verified" title="${esc(t("verify.phone_ok"))}">${icon("check", 13)}</span>` : ""}
              <div class="small"><span class="star-y">★</span> ${car.rating ?? "—"} <span class="muted">(${esc(t("car.reviews_n", { n: car.reviews_count }))})</span></div></div></div>
          </div>
          ${discountBlock()}
          <details class="card card-pad fold" data-fold open><summary><h3>${esc(t("car.specs"))}</h3>${icon("chevron", 18)}</summary>
            <div class="spec-grid">
              ${spec("field.year", car.year, "calendar")}${spec("spec.trans", t("trans." + car.transmission), "gear")}${spec("spec.fuel", t("fuel." + car.fuel), "fuel")}${spec("spec.seats", t("car.seats_n", { n: car.seats }), "seat")}
              ${spec("spec.engine", car.engine_l ? `${car.engine_l} ${t("unit.l")}` : null, "engine")}${spec("spec.mileage", car.mileage_km !== null ? `${numFmt().format(car.mileage_km)} ${t("unit.km")}` : null, "gauge")}
              ${spec("spec.drive", car.drive ? t("drive." + car.drive) : null, "road")}${spec("spec.color", car.color, "palette")}
              ${spec("spec.per100", car.fuel_per_100 ? t(car.fuel === "electric" ? "spec.per100_kwh" : "spec.per100_v", { n: car.fuel_per_100 }) : null, "drop")}
            </div></details>
          ${car.features.length ? `<details class="card card-pad fold" data-fold open style="margin-top:18px"><summary><h3>${esc(t("car.features"))} <span class="fold-n">${car.features.length}</span></h3>${icon("chevron", 18)}</summary><div class="amenities">${car.features.map((f) => `<span><i>${icon("check", 13)}</i>${esc(t("feature." + f))}</span>`).join("")}</div></details>` : ""}
          ${car.description ? `<div class="card card-pad" style="margin-top:18px"><h3>${esc(t("car.description"))}</h3><p style="margin:0;white-space:pre-line">${esc(car.description)}</p></div>` : ""}
          <div class="two-col loc-rev" style="margin-top:18px">
            <div class="card card-pad"><h3>${icon("pin", 18)} ${esc(t("map.location"))}</h3>
              <div class="map-box" id="carMap"></div>
              <div class="small" style="margin:8px 0">${esc(place)}${car.loc_exact ? "" : ` <span class="muted">· ${esc(t("map.approx"))}</span>`}</div>
              ${hasLoc() ? MapKit.links(car.lat, car.lng, `${carName(car)} — CarRent`) : ""}
              ${car.loc_exact ? "" : `<p class="small muted" style="margin:8px 0 0">${esc(t("map.exact_after"))}</p>`}</div>
            <div class="card card-pad"><h3>${esc(t("car.terms"))}</h3><div class="terms-list">
              <div><span class="muted">${esc(t("terms.deposit"))}</span><b>${car.deposit ? money(car.deposit) : esc(t("terms.none"))}</b></div>
              <div><span class="muted">${esc(t("terms.period"))}</span><b>${esc(t("terms.days_range", { a: car.min_days, b: car.max_days }))}</b></div>
              <div><span class="muted">${esc(t("terms.km"))}</span><b>${car.km_limit ? `${car.km_limit} ${esc(t("unit.km_day"))}` : esc(t("terms.unlimited"))}</b></div>
              <div><span class="muted">${esc(t("field.fuel_policy"))}</span><b>${esc(t("fuel_policy." + (car.fuel_policy || "same")))}</b></div>
              <div><span class="muted">${esc(t("terms.delivery"))}</span><b>${car.delivery_price !== null ? money(car.delivery_price) : esc(t("terms.no_delivery"))}</b></div>
              <div><span class="muted">${esc(t("terms.cancel"))}</span><b>${esc(t("terms.cancel_rule"))}</b></div>
              <div><span class="muted">${esc(t("terms.owner_cancel"))}</span><b>${esc(t("terms.owner_cancel_rule"))}</b></div>
              <div><span class="muted">${esc(t("terms.early"))}</span><b>${esc(t("terms.early_rule"))}</b></div>
              <div><span class="muted">${esc(t("terms.breakdown"))}</span><b>${esc(t("terms.breakdown_rule"))}</b></div>
              <div><span class="muted">${esc(t("terms.check"))}</span><b>${esc(t("terms.check_rule"))}</b></div>
              <div><span class="muted">${esc(t("terms.payment"))}</span><b>${esc(t(prov.click || prov.payme || prov.test ? "terms.on_site_or_online" : "terms.on_site"))}</b></div>
              ${car.require_docs ? `<div><span class="muted">${esc(t("terms.docs"))}</span><b>${esc(t("terms.docs_required"))}</b></div>` : ""}
              <div><span class="muted">${esc(t("terms.contract"))}</span><b>${esc(t("terms.contract_e"))}</b></div>
            </div></div>
          </div>
          ${canBook ? "" : `<div class="card card-pad" style="margin-top:18px"><h3>${esc(t("car.calendar"))}</h3><p class="small muted" style="margin-top:-4px">${esc(t("car.calendar_legend"))}</p><div id="calendar"></div></div>`}
          <div class="card card-pad" style="margin-top:18px" id="reviews"><h3>${esc(t("car.reviews"))}</h3>${reviewsBlock()}</div>
        </div>
        <aside class="stack book-box" id="book">
          <div class="card card-pad book-card">
            <div class="price-big">${money(car.price_per_day)} <span class="muted small">${esc(t("car.per_day"))}</span></div>
            ${Object.keys(car.discounts || {}).length ? `<div class="disc-chips">${Object.entries(car.discounts).map(([d, p]) => `<span>${icon("tag", 13)} ${esc(t("disc.chip", { d, p }))}</span>`).join("")}</div>` : ""}
            ${canBook ? `<div class="date-guide"><div class="dg-step ${form.start ? "done" : "on"}"><b>1</b><span>${esc(t("book.step1"))}</span></div><i></i>
              <div class="dg-step ${form.end ? "done" : form.start ? "on" : ""}"><b>2</b><span>${esc(t("book.step2"))}</span></div></div>
              <p class="small muted dg-hint">${esc(t("book.dates_hint"))}</p><div id="calendar"></div>` : ""}
            <div id="bookArea" style="margin-top:14px"></div>
          </div>
          <div class="card card-pad">
            <div class="owner-box">${avatarHtml(car.owner)}
              <div><b>${esc(car.owner.full_name)}</b>${car.owner.phone_verified ? ` <span class="verified" title="${esc(t("verify.phone_ok"))}">${icon("check", 13)} ${esc(t("verify.badge"))}</span>` : ""}<div class="small muted">${esc(t("owner.cars_n", { n: car.owner.cars_count }))} · ${esc(t("owner.trips_n", { n: car.owner.trips }))}</div>
              <div class="small muted">${car.owner.rating ? `★ ${car.owner.rating} · ` : ""}${esc(t("owner.since", { d: fmtDate(car.owner.created_at) }))}</div></div></div>
            <div class="stack" style="margin-top:14px" id="contactArea"></div>
          </div>
          ${user && !car.is_mine && user.role !== "admin" ? `<button class="linkbtn muted report-link" id="reportBtn">${icon("flag", 16)} ${esc(t("report.car"))}</button>` : ""}
        </aside>
      </div>
      ${car.similar.length ? `<section style="margin-top:40px"><h2>${esc(t("car.similar"))}</h2><div class="cars-grid">${car.similar.map((c) => carCard(c)).join("")}</div></section>` : ""}
      ${canBook ? `<div class="mobile-book"><div><b>${money(car.price_per_day)}</b> <span class="muted small">${esc(t("car.per_day"))}</span></div><a class="btn" href="#book">${esc(t("car.book"))}</a></div>` : ""}`;
    MapKit.show($("#carMap"), car.loc_exact ? { lat: car.lat, lng: car.lng, label: `${carName(car)} ${car.year}` }
      : { region: car.city, approx: hasLoc() ? [car.lat, car.lng] : null }).catch((e) => { $("#carMap").innerHTML = `<div class="empty small">${esc(e.message)}</div>`; });
    document.body.classList.toggle("has-mobile-book", !!canBook);
    // Telefonda "Xususiyatlar" va "Qulayliklar" yig'ilgan holda — bosilganda ochiladi
    if (innerWidth < 760) $$("[data-fold]").forEach((d) => d.removeAttribute("open"));

    const go = (i) => {
      if (!car.images.length) return;
      imgIndex = (i + car.images.length) % car.images.length;
      $$("#thumbs button").forEach((x, k) => x.classList.toggle("active", k === imgIndex));
      $("#mainImg").firstElementChild.outerHTML = carImage(car, car.images[imgIndex].path);
      const lab = $("#mainImg .gal-label"), im = car.images[imgIndex];
      if (lab) lab.textContent = im.label ? t("img.label_" + im.label) : ""; if (lab) lab.classList.toggle("hidden", !im.label);
      if ($("#openLb")) $("#openLb").lastChild.textContent = ` ${imgIndex + 1} / ${car.images.length}`;
    };
    $("#thumbs")?.addEventListener("click", (e) => { const b = e.target.closest("[data-i]"); if (b) go(+b.dataset.i); });
    $("#mainImg").addEventListener("click", (e) => {
      const st = e.target.closest("[data-step]"); if (st) { go(imgIndex + +st.dataset.step); return; }
      if (e.target.closest(".fav-btn") || e.target.closest("#thumbs")) return;
      if (car.images.length) lightbox(car.images, imgIndex, (i) => go(i));
    });
    swipe($("#mainImg"), (d) => go(imgIndex + d));
    $("#reportBtn")?.addEventListener("click", () => reportModal("car", car.id));
    renderContact();
    renderBooking();
    const old = cal;
    cal = new BookingCalendar($("#calendar"), car.id, { selectable: canBook, onSelect: (s, e) => { if ($("#bStart")) { $("#bStart").value = s; $("#bEnd").value = e; updateQuote(); guide(); } } });
    if (old) { cal.ranges = old.ranges; cal.month = old.month; cal.today = old.today; cal.setRange(form.start, form.end); cal.render(); }
    else cal.load().then(() => form.start && cal.setRange(form.start, form.end));
    if (location.hash === "#book" && !old) setTimeout(() => $("#book").scrollIntoView({ behavior: "smooth" }), 50);
  }

  function renderContact() {
    const box = $("#contactArea");
    const next = encodeURIComponent(location.pathname + location.search);
    if (!user) box.innerHTML = `<a class="btn btn-outline btn-block" href="/auth.html?next=${next}#login">${esc(t("owner.login_to_contact"))}</a>`;
    else if (car.is_mine) box.innerHTML = `<a class="btn btn-outline btn-block" href="/car-form.html?id=${car.id}">${esc(t("car.edit"))}</a>
      <div class="small muted">${esc(t("car.views_n", { n: car.views }))}</div>`;
    else box.innerHTML = `${car.owner.phone ? `<a class="btn btn-outline btn-block" href="tel:${esc(car.owner.phone.replace(/[^+\d]/g, ""))}">📞 ${esc(fmtPhone(car.owner.phone))}</a>` : ""}
      <a class="btn btn-soft btn-block" href="/messages.html?user=${car.owner_id}&car=${car.id}">💬 ${esc(t("owner.message"))}</a>`;
  }

  function renderBooking() {
    const area = $("#bookArea");
    const next = encodeURIComponent(location.pathname + location.search);
    if (!user) { area.innerHTML = `<p class="small muted">${esc(t("book.login_hint"))}</p><a class="btn btn-block btn-lg" href="/auth.html?next=${next}#login">${esc(t("book.login_btn"))}</a>`; return; }
    if (!canBook) {
      area.innerHTML = `<p class="small muted" style="margin:0">${esc(t(car.is_mine ? "book.own_car" : "book.admin"))}</p>
        ${car.is_mine ? `<a class="btn btn-outline btn-block" style="margin-top:10px" href="/dashboard.html?mode=owner#bookings">${esc(t("book.requests"))}</a>` : ""}`;
      return;
    }
    const today = isoDate(new Date());
    area.innerHTML = `<div id="ready"></div><form id="bookForm" novalidate>
      <div class="grid-2"><div class="field"><label for="bStart">${esc(t("book.start"))}</label><input class="input" type="date" id="bStart" min="${today}" value="${esc(form.start)}" required></div>
      <div class="field"><label for="bEnd">${esc(t("book.end"))}</label><input class="input" type="date" id="bEnd" min="${esc(form.start || today)}" value="${esc(form.end)}" required></div></div>
      ${car.delivery_price !== null ? `<label class="check field"><input type="checkbox" id="bDelivery" ${form.delivery ? "checked" : ""}><span>${esc(t("book.delivery", { price: money(car.delivery_price) }))}</span></label>` : ""}
      <div class="field"><label for="bNote">${esc(t("book.note"))}</label><input class="input" id="bNote" maxlength="500" value="${esc(form.note)}" placeholder="${esc(t("book.note_ph"))}" data-hint="hint.book_note"></div>
      <div id="quote" class="small" aria-live="polite"></div>
      <button class="btn btn-block btn-lg" type="submit" style="margin-top:10px">${esc(t("book.submit"))}</button>
      <p class="small muted" style="margin-bottom:0">${esc(t(prov.click || prov.payme || prov.test ? "book.disclaimer_online" : "book.disclaimer"))}</p></form>`;
    const f = $("#bookForm");
    DateField.enhance(f); applyHints(f);
    f.addEventListener("input", (e) => {
      if (e.target.id === "bStart") { $("#bEnd").min = $("#bStart").value; if ($("#bEnd").value < $("#bStart").value) $("#bEnd").value = $("#bStart").value; }
      cal?.setRange($("#bStart").value, $("#bEnd").value); updateQuote(); guide();
    });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("button[type=submit]", f);
      if (readyState && !readyState.ready) { readyModal(readyState); return; }
      if (!$("#bStart").value || !$("#bEnd").value) { toast(t("book.pick_dates"), "error"); return; }
      await withLoading(btn, async () => {
        try {
          await api("/api/bookings", { method: "POST", body: { car_id: car.id, start_date: $("#bStart").value, end_date: $("#bEnd").value,
            delivery: !!$("#bDelivery")?.checked, note: $("#bNote").value || null } });
          toast(t("book.sent"), "ok");
          setTimeout(() => (location.href = "/dashboard.html?mode=renter#bookings"), 900);
        } catch (err) { toast(err.message, "error"); await cal.load(); updateQuote(); }
      });
    });
    updateQuote();
    loadReadiness();
  }

  // ---------- Bron oldidan profil tayyorligi: nima yetishmaydi va qayerda to'ldiriladi ----------
  let readyState = null;
  const withBack = (link) => link.replace("#", `?back=${encodeURIComponent(location.pathname + location.search + "#book")}#`);
  const readyItem = (i) => `<li class="${i.ok ? "ok" : i.required ? "need" : "tip"}">${icon(i.ok ? "check" : i.required ? "close" : "info", 15)}
    <span>${esc(t("ready." + i.code + (i.code === "docs" && !i.ok && i.state === "pending" ? "_pending" : "")))}</span>
    ${i.ok || (i.code === "docs" && i.state === "pending") ? "" : `<a href="${esc(withBack(i.link))}">${esc(t("ready.fix"))} →</a>`}</li>`;
  async function loadReadiness() {
    try { readyState = await api(`/api/bookings/readiness?car_id=${car.id}`); } catch { return; }
    const r = readyState, box = $("#ready");
    if (!box) return;
    const need = r.items.filter((i) => i.required && !i.ok), tips = r.items.filter((i) => !i.required && !i.ok);
    box.innerHTML = need.length ? `<div class="ready-box bad" role="alert"><b>${icon("flag", 16)} ${esc(t("ready.title_need"))}</b>
        <p class="small">${esc(t("ready.need_sub"))}</p><ul class="ready-list">${need.map(readyItem).join("")}</ul></div>`
      : tips.length ? `<details class="ready-box tip"><summary>${icon("bulb", 15)} ${esc(t("ready.title_tip", { p: r.percent }))}</summary>
        <ul class="ready-list">${tips.map(readyItem).join("")}</ul></details>` : "";
    const btn = $("#bookForm button[type=submit]");
    if (btn) btn.classList.toggle("btn-muted", !r.ready);
  }
  function readyModal(r) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal card card-pad" role="dialog" aria-modal="true"><h3>${icon("flag", 18)} ${esc(t("ready.title_need"))}</h3>
      <p class="muted small">${esc(t("ready.modal_sub"))}</p><ul class="ready-list">${r.items.filter((i) => i.required).map(readyItem).join("")}</ul>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button type="button" class="btn btn-outline" data-close>${esc(t("common.close"))}</button>
      <a class="btn" href="${esc(withBack(r.items.find((i) => i.required && !i.ok)?.link || "/settings.html#profile"))}">${esc(t("ready.go_fill"))}</a></div></div>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
  }

  /** Keyingi chegirma pog'onasigacha necha kun qolgani — "yana 2 kun olsangiz 10% arzon" */
  function nextTierHint(days) {
    const next = Object.entries(car.discounts || {}).map(([k, p]) => [+k, p]).filter(([k]) => k > days).sort((a, b) => a[0] - b[0])[0];
    return next ? `<div class="disc-next">${icon("bulb", 14)} ${esc(t("disc.next", { n: next[0] - days, p: next[1] }))}</div>` : "";
  }
  function guide() {
    const s = $("#bStart")?.value, e = cal?.start ? cal.end : $("#bEnd")?.value, st = $$(".dg-step");
    if (!st.length) return;
    st[0].className = "dg-step " + (s ? "done" : "on"); st[1].className = "dg-step " + (e && s ? "done" : s ? "on" : "");
  }

  let qTimer;
  function updateQuote() {
    clearTimeout(qTimer);
    qTimer = setTimeout(async () => {
      const box = $("#quote"); if (!box) return;
      const s = $("#bStart").value, e = $("#bEnd").value;
      if (!s || !e || e < s) { box.innerHTML = ""; return; }
      try {
        // Narx serverda hisoblanadi — frontend faqat ko'rsatadi
        const q = await api(`/api/cars/${car.id}/quote?start=${s}&end=${e}&delivery=${$("#bDelivery")?.checked ? 1 : 0}`);
        box.innerHTML = `${!q.available ? `<div class="notice" style="margin-bottom:8px">${esc(t("book.busy"))}</div>` : ""}
          ${!q.within_limits ? `<div class="notice" style="margin-bottom:8px">${esc(t("terms.days_range", { a: car.min_days, b: car.max_days }))}</div>` : ""}
          <div class="sum-row"><span>${money(q.price_per_day)} × ${esc(t("car.days_n", { n: q.days }))}</span><span>${money(q.rent_full ?? q.rent)}</span></div>
          ${q.discount ? `<div class="sum-row disc"><span>${icon("tag", 13)} ${esc(t("disc.applied", { p: q.discount_pct, d: q.days }))}</span><span>−${money(q.discount)}</span></div>` : ""}
          ${q.delivery ? `<div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(q.delivery)}</span></div>` : ""}
          <div class="sum-row total"><span>${esc(t("book.total"))}</span><span>${money(q.total)}</span></div>
          ${q.deposit ? `<div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${money(q.deposit)}</span></div>` : ""}
          <div class="sum-row sub"><span>${esc(t("book.pay_on_site"))}</span><span>${money(q.pay_on_site)}</span></div>
          ${q.discount ? `<div class="disc-save">${esc(t("disc.you_save", { sum: money(q.discount) }))}</div>` : nextTierHint(q.days)}`;
      } catch (err) { box.innerHTML = `<div class="notice">${esc(err.message)}</div>`; }
    }, 200);
  }

  render();
  document.addEventListener("langchange", render);
})();
