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

  function spec(k, v) { return v === null || v === undefined || v === "" ? "" : `<div class="spec"><div class="k">${esc(t(k))}</div><div class="v">${esc(v)}</div></div>`; }

  function render() {
    // Formadagi qiymatlarni saqlab qolamiz (til almashganda yo'qolmasin)
    if ($("#bStart")) Object.assign(form, { start: $("#bStart").value, end: $("#bEnd").value, delivery: $("#bDelivery")?.checked || false, note: $("#bNote").value });
    document.title = `${carName(car)} ${car.year} — CarRent`;
    const hidden = !car.is_active || !car.is_approved;
    const images = car.images.length ? car.images : [null];
    root.innerHTML = `
      ${hidden ? `<div class="notice" style="margin-bottom:16px">${esc(t(!car.is_approved ? "car.hidden_admin" : "car.hidden_owner"))}</div>` : ""}
      <nav class="small muted" style="margin-bottom:10px" aria-label="breadcrumb"><a href="/cars.html">${esc(t("nav.cars"))}</a> › <a href="/cars.html?city=${encodeURIComponent(car.city)}">${esc(car.city)}</a> › ${esc(car.brand)}</nav>
      <div class="detail">
        <div>
          <div class="gallery-main" id="mainImg">${carImage(car, images[imgIndex]?.path)}
            ${car.images.length ? `<button class="gal-zoom" id="openLb" aria-label="${esc(t("gallery.open"))}">${icon("search", 18)} ${imgIndex + 1} / ${car.images.length}</button>` : ""}
            <span class="gal-label ${images[imgIndex]?.label ? "" : "hidden"}">${images[imgIndex]?.label ? esc(t("img.label_" + images[imgIndex].label)) : ""}</span>
            ${car.images.length > 1 ? `<button class="gal-nav prev" data-step="-1" aria-label="${esc(t("cal.prev"))}">${icon("arrowl")}</button><button class="gal-nav next" data-step="1" aria-label="${esc(t("cal.next"))}">${icon("arrowr")}</button>` : ""}
            ${car.is_mine ? "" : `<button class="fav-btn ${car.is_favorite ? "on" : ""}" data-fav="${car.id}" aria-pressed="${!!car.is_favorite}" aria-label="${esc(t(car.is_favorite ? "fav.remove" : "fav.add"))}">${car.is_favorite ? HEART : HEART_O}</button>`}</div>
          ${car.images.length > 1 ? `<div class="thumbs" id="thumbs">${car.images.map((im, i) => `<button class="${i === imgIndex ? "active" : ""}" data-i="${i}" aria-label="${esc(t("car.photo_n", { n: i + 1 }))}"><img src="${esc(im.path)}" alt="" loading="lazy"></button>`).join("")}</div>` : ""}
          <div class="row" style="margin-top:18px;gap:8px">${car.is_demo ? `<span class="tag tag-demo">${esc(t("car.demo"))}</span>` : ""}<span class="tag tag-info">${esc(t("body." + car.body_type))}</span></div>
          <h1 style="margin-top:8px">${esc(carName(car))} <span class="muted" style="font-weight:600">${esc(car.year)}</span></h1>
          <div class="row small">
            ${car.rating ? `<span class="stars">${stars(car.rating)}</span><b>${car.rating}</b><a href="#reviews">${esc(t("car.reviews_n", { n: car.reviews_count }))}</a>` : `<span class="muted">${esc(t("car.no_reviews"))}</span>`}
            <span class="muted">· 📍 ${esc(car.city)}</span>
          </div>
          <div class="specs">
            ${spec("spec.trans", t("trans." + car.transmission))}${spec("spec.fuel", t("fuel." + car.fuel))}${spec("spec.seats", car.seats)}
            ${spec("spec.engine", car.engine_l ? `${car.engine_l} ${t("unit.l")}` : null)}${spec("spec.mileage", car.mileage_km !== null ? `${numFmt().format(car.mileage_km)} ${t("unit.km")}` : null)}
            ${spec("spec.drive", car.drive ? t("drive." + car.drive) : null)}${spec("spec.color", car.color)}${spec("spec.body", t("body." + car.body_type))}
          </div>
          ${car.features.length ? `<div class="card card-pad"><h3>${esc(t("car.features"))}</h3><div class="features-list">${car.features.map((f) => `<span>${esc(t("feature." + f))}</span>`).join("")}</div></div>` : ""}
          ${car.description ? `<div class="card card-pad" style="margin-top:18px"><h3>${esc(t("car.description"))}</h3><p style="margin:0;white-space:pre-line">${esc(car.description)}</p></div>` : ""}
          <div class="card card-pad" style="margin-top:18px"><h3>${esc(t("car.terms"))}</h3><div class="terms-list">
            <div><span class="muted">${esc(t("terms.deposit"))}</span><b>${car.deposit ? money(car.deposit) : esc(t("terms.none"))}</b></div>
            <div><span class="muted">${esc(t("terms.period"))}</span><b>${esc(t("terms.days_range", { a: car.min_days, b: car.max_days }))}</b></div>
            <div><span class="muted">${esc(t("terms.km"))}</span><b>${car.km_limit ? `${car.km_limit} ${esc(t("unit.km_day"))}` : esc(t("terms.unlimited"))}</b></div>
            <div><span class="muted">${esc(t("terms.delivery"))}</span><b>${car.delivery_price !== null ? money(car.delivery_price) : esc(t("terms.no_delivery"))}</b></div>
            <div><span class="muted">${esc(t("terms.cancel"))}</span><b>${esc(t("terms.cancel_rule"))}</b></div>
            <div><span class="muted">${esc(t("terms.payment"))}</span><b>${esc(t(prov.click || prov.payme || prov.test ? "terms.on_site_or_online" : "terms.on_site"))}</b></div>
          </div></div>
          <div class="card card-pad" style="margin-top:18px">
            <h3>${esc(t("car.calendar"))}</h3><p class="small muted" style="margin-top:-4px">${esc(t(canBook ? "car.calendar_hint" : "car.calendar_legend"))}</p>
            <div id="calendar"></div>
          </div>
          <div class="card card-pad" style="margin-top:18px" id="reviews"><h3>${esc(t("car.reviews"))}</h3>
            ${reviews.items.length ? reviews.items.map((r) => `<div class="review">
              <div class="row"><span class="avatar">${esc(initials(r.author))}</span><div><b>${esc(r.author)}</b><div class="small muted">${fmtDate(r.created_at)}</div></div>
              <span class="spacer"></span><span class="stars">${stars(r.rating)}</span></div>
              ${r.comment ? `<p style="margin:8px 0 0">${esc(r.comment)}</p>` : ""}
              ${r.reply ? `<div class="reply"><b>${esc(t("review.owner_reply"))}:</b> ${esc(r.reply)}</div>` : ""}</div>`).join("")
              : `<p class="muted">${esc(t("car.reviews_empty"))}</p>`}
          </div>
        </div>
        <aside class="stack book-box" id="book">
          <div class="card card-pad">
            <div class="price-big">${money(car.price_per_day)} <span class="muted small">${esc(t("car.per_day"))}</span></div>
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
    document.body.classList.toggle("has-mobile-book", !!canBook);

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
      if (e.target.closest(".fav-btn")) return;
      if (car.images.length) lightbox(car.images, imgIndex, (i) => go(i));
    });
    swipe($("#mainImg"), (d) => go(imgIndex + d));
    $("#reportBtn")?.addEventListener("click", () => reportModal("car", car.id));
    renderContact();
    renderBooking();
    const old = cal;
    cal = new BookingCalendar($("#calendar"), car.id, { selectable: canBook, onSelect: (s, e) => { if ($("#bStart")) { $("#bStart").value = s; $("#bEnd").value = e; updateQuote(); } } });
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
    else box.innerHTML = `${car.owner.phone ? `<a class="btn btn-outline btn-block" href="tel:${esc(car.owner.phone.replace(/[^+\d]/g, ""))}">📞 ${esc(car.owner.phone)}</a>` : ""}
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
    area.innerHTML = `<form id="bookForm" novalidate>
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
      cal?.setRange($("#bStart").value, $("#bEnd").value); updateQuote();
    });
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("button[type=submit]", f);
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
          <div class="sum-row"><span>${money(q.price_per_day)} × ${esc(t("car.days_n", { n: q.days }))}</span><span>${money(q.rent)}</span></div>
          ${q.delivery ? `<div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(q.delivery)}</span></div>` : ""}
          <div class="sum-row total"><span>${esc(t("book.total"))}</span><span>${money(q.total)}</span></div>
          ${q.deposit ? `<div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${money(q.deposit)}</span></div>` : ""}
          <div class="sum-row sub"><span>${esc(t("book.pay_on_site"))}</span><span>${money(q.pay_on_site)}</span></div>`;
      } catch (err) { box.innerHTML = `<div class="notice">${esc(err.message)}</div>`; }
    }, 200);
  }

  render();
  document.addEventListener("langchange", render);
})();
