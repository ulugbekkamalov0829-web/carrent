"use strict";
(async () => {
  await boot("");
  const user = await guard("user", "admin");
  if (user.role === "admin") { location.replace("/admin.html"); return; }

  // Bildirishnoma havolasidagi ?mode=... rejimni moslaydi (idempotent)
  const wanted = new URLSearchParams(location.search).get("mode");
  if (wanted && wanted !== user.active_mode && ["renter", "owner"].includes(wanted)) await Auth.setMode(wanted);

  // Profil va xavfsizlik endi "Sozlamalar" sahifasida
  if (["#profile", "#security"].includes(location.hash)) { location.replace("/settings.html" + location.hash); return; }
  const EXTRA = [["notifications", "dash.notifications"]];
  const tabsOf = (m) => [...CABINET[m], ...EXTRA];
  const view = $("#view");
  const mode = () => Auth.user.active_mode;

  function head(titleKey, subKey = "", actions = "") {
    $("#viewTitle").textContent = t(titleKey);
    $("#viewSub").textContent = subKey ? t(subKey, { name: Auth.user.full_name.split(" ")[0] }) : "";
    $("#viewActions").innerHTML = actions;
  }

  let current = null;
  function route() {
    const tab = tabsOf(mode()).find(([k]) => "#" + k === location.hash)?.[0] || "overview";
    current = tab;
    markActive();
    view.onclick = null;
    view.innerHTML = `<div class="skeleton" style="height:240px"></div>`;
    const fn = { overview: mode() === "owner" ? ownerOverview : renterOverview, bookings: mode() === "owner" ? ownerBookings : renterBookings,
      favorites, cars: ownerCars, calendar: ownerCalendar, reviews: ownerReviews, earnings: ownerEarnings, notifications }[tab];
    fn().catch((e) => (view.innerHTML = `<div class="empty card">${esc(e.message)}</div>`));
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("langchange", route);
  document.addEventListener("modeview", route);
  route();

  // ===================== IJARACHI =====================
  async function renterOverview() {
    head("dash.hello", "dash.renter_sub");
    const [s, mine, reco] = await Promise.all([api("/api/dashboard/renter"), api("/api/bookings/mine"), api("/api/recommendations?limit=4")]);
    const active = s.bookings.approved;
    view.innerHTML = `<div class="stats">
        ${stat(t("dash.active"), active, s.upcoming ? esc(t("dash.next_trip", { car: s.upcoming.title, d: fmtDate(s.upcoming.start_date) })) : `<a href="/cars.html">${esc(t("dash.find_car"))}</a>`)}
        ${stat(t("dash.pending"), s.bookings.pending, esc(t("dash.pending_sub")))}
        ${stat(t("dash.completed"), s.bookings.completed, s.to_review ? `<a href="#bookings">${esc(t("dash.to_review", { n: s.to_review }))}</a>` : esc(t("dash.days_total", { n: s.days_total })))}
        ${stat(t("dash.favorites"), s.favorites, `<a href="#favorites">${esc(t("dash.open"))}</a>`)}
      </div>
      <div class="two-col">
        <div class="card"><div class="card-pad" style="padding-bottom:6px"><h3>${esc(t("dash.recent"))}</h3></div>
          ${mine.items.slice(0, 4).map((b) => bookingRow(b, false)).join("") || `<div class="empty">${esc(t("dash.no_bookings"))}</div>`}</div>
        <div class="card card-pad"><h3>${esc(t("dash.my_profile"))}</h3>
          <div class="sum-row"><span class="muted">${esc(t("dash.spent"))}</span><b>${money(s.spent_total)}</b></div>
          <div class="sum-row"><span class="muted">${esc(t("dash.my_rating"))}</span><b>${s.my_rating.avg ? `★ ${s.my_rating.avg} (${s.my_rating.cnt})` : "—"}</b></div>
          <p class="small muted" style="margin-top:10px">${esc(t("dash.rating_hint"))}</p></div>
      </div>
      <h2 style="margin-top:28px">${esc(t("home.for_you"))}</h2>
      <div class="cars-grid">${reco.items.map((c) => carCard(c, { reason: true })).join("")}</div>`;
    bindBookingActions(renterOverview);
  }

  async function renterBookings() {
    head("dash.my_bookings");
    const filter = new URLSearchParams(location.search).get("status") || "";
    const { items } = await api("/api/bookings/mine" + (filter ? "?status=" + filter : ""));
    view.innerHTML = filterBar(filter) + (items.length ? `<div class="card">${items.map((b) => bookingRow(b, false)).join("")}</div>`
      : `<div class="empty card"><h3>${esc(t("dash.no_bookings"))}</h3><p>${esc(t("dash.no_bookings_hint"))}</p><a class="btn" href="/cars.html">${esc(t("nav.cars"))}</a></div>`);
    bindBookingActions(renterBookings);
  }

  async function favorites() {
    head("dash.favorites");
    const { items } = await api("/api/favorites");
    view.innerHTML = items.length ? `<div class="cars-grid">${items.map((c) => carCard(c)).join("")}</div>`
      : `<div class="empty card"><h3>${esc(t("fav.empty"))}</h3><p>${esc(t("fav.empty_hint"))}</p><a class="btn" href="/cars.html">${esc(t("nav.cars"))}</a></div>`;
  }
  document.addEventListener("favchange", () => { if (current === "favorites") favorites(); });

  // ===================== OWNER =====================
  async function ownerOverview() {
    head("dash.owner_overview", "dash.owner_sub", `<a class="btn" href="/car-form.html">+ ${esc(t("nav.add_car"))}</a>`);
    const s = await api("/api/dashboard/owner");
    if (!s.cars_total) {
      view.innerHTML = `<div class="empty card"><h3>${esc(t("owner.empty"))}</h3><p>${esc(t("owner.empty_hint", { pct: s.commission_bps / 100 }))}</p>
        <a class="btn btn-lg" href="/car-form.html">+ ${esc(t("nav.add_car"))}</a></div>`;
      return;
    }
    const p = s.periods;
    view.innerHTML = `<div class="stats">
        ${stat(t("owner.revenue"), money(s.revenue_total), esc(t("owner.revenue_sub")))}
        ${stat(t("owner.commission", { pct: s.commission_bps / 100 }), money(s.commission_total), esc(t("owner.commission_sub")))}
        ${stat(t("owner.payout"), money(s.payout_total), esc(t("owner.payout_sub")))}
        ${stat(t("owner.occupancy"), `${s.occupancy}%`, esc(t("owner.occupancy_sub")))}
        ${stat(t("owner.cars"), `${s.cars_active} / ${s.cars_total}`, esc(t("owner.cars_sub")))}
        ${stat(t("dash.pending"), s.bookings.pending, s.bookings.pending ? `<a href="#bookings">${esc(t("owner.review_now"))}</a>` : esc(t("owner.all_done")))}
        ${stat(t("owner.rating"), s.rating_avg ? `★ ${s.rating_avg}` : "—", esc(t("car.reviews_n", { n: s.reviews_count })))}
        ${stat(t("owner.conversion"), `${s.conversion}%`, esc(t("owner.conversion_sub", { n: s.views_total })))}
      </div>
      <div class="card card-pad" style="margin-bottom:18px"><h3>${esc(t("owner.periods"))}</h3>
        <div class="stats" style="margin:0">${["today", "week", "month", "year"].map((k) => `<div><div class="small muted">${esc(t("period." + k))}</div>
          <b>${money(p[k].payout)}</b><div class="small muted">${esc(t("owner.gross"))}: ${money(p[k].revenue)}</div></div>`).join("")}</div></div>
      <div class="two-col">
        <div class="card card-pad"><h3>${esc(t("owner.monthly"))}</h3>${revenueChart(s.monthly)}</div>
        <div class="card card-pad"><h3>${esc(t("owner.statuses"))}</h3>${statusBars(s.bookings)}</div>
      </div>
      <div class="card" style="margin-top:18px"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("owner.per_car"))}</h3></div>
        <div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.car"))}</th><th>${esc(t("col.bookings"))}</th><th>${esc(t("col.occupancy"))}</th>
          <th>${esc(t("col.views"))}</th><th>${esc(t("col.revenue"))}</th><th>${esc(t("col.payout"))}</th></tr></thead><tbody>
          ${s.per_car.map((c) => `<tr><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${c.id}">${esc(c.brand)} ${esc(c.model)} ${c.year}</a></td>
            <td data-label="${esc(t("col.bookings"))}">${c.bookings}</td><td data-label="${esc(t("col.occupancy"))}">${c.occupancy}%</td>
            <td data-label="${esc(t("col.views"))}">${c.views}</td><td data-label="${esc(t("col.revenue"))}">${money(c.revenue)}</td>
            <td data-label="${esc(t("col.payout"))}"><b>${money(c.payout)}</b></td></tr>`).join("")}</tbody></table></div></div>`;
  }

  async function ownerCars() {
    head("dash.my_cars", "", `<a class="btn" href="/car-form.html">+ ${esc(t("nav.add_car"))}</a>`);
    const { items } = await api("/api/my/cars");
    if (!items.length) {
      view.innerHTML = `<div class="empty card"><h3>${esc(t("owner.empty"))}</h3><a class="btn" href="/car-form.html">+ ${esc(t("nav.add_car"))}</a></div>`;
      return;
    }
    view.innerHTML = `<div class="card">${items.map((c) => `
      <div class="list-item">
        <a class="thumb" href="/car.html?id=${c.id}">${carImage(c)}</a>
        <div><a href="/car.html?id=${c.id}"><b>${esc(carName(c))} ${c.year}</b></a>
          <div class="small muted">${esc(c.city)} · ${money(c.price_per_day)} ${esc(t("car.per_day"))} · ${c.rating ? `★ ${c.rating} (${c.reviews_count})` : esc(t("car.no_reviews"))} · ${esc(t("car.views_n", { n: c.views }))}</div>
          <div class="row" style="gap:6px;margin-top:4px">
            ${c.is_approved ? (c.is_active ? `<span class="tag tag-ok">${esc(t("car.state_active"))}</span>` : `<span class="tag tag-hidden">${esc(t("car.state_hidden"))}</span>`) : `<span class="tag tag-bad">${esc(t("car.state_moderated"))}</span>`}
            ${c.pending_count ? `<a href="#bookings" class="tag tag-pending">${esc(t("owner.new_requests", { n: c.pending_count }))}</a>` : ""}
          </div></div>
        <div class="actions">
          <button class="btn btn-sm btn-outline" data-toggle="${c.id}">${esc(t(c.is_active ? "car.hide" : "car.show"))}</button>
          <a class="btn btn-sm btn-outline" href="/car-form.html?id=${c.id}">${esc(t("common.edit"))}</a>
          <button class="btn btn-sm btn-danger" data-del="${c.id}">${esc(t("common.delete"))}</button>
        </div></div>`).join("")}</div>`;
    view.onclick = async (e) => {
      const del = e.target.closest("[data-del]"), tog = e.target.closest("[data-toggle]");
      if (del && await confirmBox(t("car.delete_confirm"), t("common.delete"), true)) {
        try { await api(`/api/cars/${del.dataset.del}`, { method: "DELETE" }); toast(t("car.deleted"), "ok"); ownerCars(); } catch (err) { toast(err.message, "error"); }
      }
      if (tog) {
        const c = items.find((x) => x.id == tog.dataset.toggle);
        const body = { brand: c.brand, model: c.model, year: c.year, color: c.color, body_type: c.body_type, seats: c.seats, transmission: c.transmission,
          fuel: c.fuel, engine_l: c.engine_l, mileage_km: c.mileage_km, drive: c.drive, features: c.features, city: c.city, description: c.description,
          price_per_day: c.price_per_day, deposit: c.deposit, min_days: c.min_days, max_days: c.max_days, km_limit: c.km_limit,
          delivery_price: c.delivery_price, is_active: !c.is_active };
        try { await api(`/api/cars/${c.id}`, { method: "PUT", body }); toast(t(body.is_active ? "car.shown" : "car.hidden"), "ok"); ownerCars(); } catch (err) { toast(err.message, "error"); }
      }
    };
  }

  async function ownerBookings() {
    head("dash.requests");
    const filter = new URLSearchParams(location.search).get("status") || "";
    const { items } = await api("/api/bookings/incoming" + (filter ? "?status=" + filter : ""));
    view.innerHTML = filterBar(filter) + (items.length ? `<div class="card">${items.map((b) => bookingRow(b, true)).join("")}</div>`
      : `<div class="empty card"><h3>${esc(t("owner.no_requests"))}</h3><p>${esc(t("owner.no_requests_hint"))}</p></div>`);
    bindBookingActions(ownerBookings);
  }

  async function ownerCalendar() {
    head("dash.calendar", "owner.calendar_sub");
    const { items } = await api("/api/my/cars");
    if (!items.length) { view.innerHTML = `<div class="empty card">${esc(t("owner.empty"))}</div>`; return; }
    const pre = new URLSearchParams(location.search).get("car");
    view.innerHTML = `<div class="two-col"><div class="card card-pad"><div class="field" style="max-width:420px"><label for="calCar">${esc(t("col.car"))}</label>
      <select class="input" id="calCar">${items.map((c) => `<option value="${c.id}" ${String(c.id) === pre ? "selected" : ""}>${esc(carName(c))} ${c.year} · ${esc(c.city)}</option>`).join("")}</select></div>
      <div id="calendar"></div></div>
      <div class="card card-pad"><h3>${esc(t("block.title"))}</h3><p class="small muted">${esc(t("block.sub"))}</p>
        <form id="blockForm" novalidate><div class="grid-2">
          <div class="field"><label for="blS">${esc(t("block.from"))}</label><input class="input" type="date" id="blS" required></div>
          <div class="field"><label for="blE">${esc(t("block.to"))}</label><input class="input" type="date" id="blE" required></div></div>
          <div class="field"><label for="blN">${esc(t("block.note"))}</label><input class="input" id="blN" maxlength="200" data-hint="block.note_hint" placeholder="${esc(t("block.note_ph"))}"></div>
          <button class="btn btn-block">${esc(t("block.add"))}</button></form>
        <div id="blockList" style="margin-top:14px"></div></div></div>`;
    const today = isoDate(new Date());
    DateField.enhance(view); applyHints(view);
    $("#blS").min = today; $("#blE").min = today;
    $("#blS").addEventListener("change", () => { $("#blE").min = $("#blS").value || today; if (!$("#blE").value) $("#blE").value = $("#blS").value; });
    const carId = () => +$("#calCar").value;
    let cal;
    const drawBlocks = async () => {
      const { items: bl } = await api(`/api/cars/${carId()}/blocks`);
      $("#blockList").innerHTML = bl.length ? bl.map((x) => `<div class="block-row"><div><b>${fmtDate(x.start_date)} → ${fmtDate(x.end_date)}</b>
        ${x.note ? `<div class="small muted">${esc(x.note)}</div>` : ""}</div><button class="btn btn-sm btn-danger" data-unblock="${x.id}">${esc(t("block.remove"))}</button></div>`).join("")
        : `<p class="small muted">${esc(t("block.none"))}</p>`;
    };
    const draw = () => { cal = new BookingCalendar($("#calendar"), carId()); cal.load(); drawBlocks(); };
    $("#calCar").addEventListener("change", draw);
    $("#blockForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!$("#blS").value || !$("#blE").value) { toast(t("date.invalid"), "error"); return; }
      try {
        await api(`/api/cars/${carId()}/blocks`, { method: "POST", body: { start_date: $("#blS").value, end_date: $("#blE").value, note: $("#blN").value.trim() || null } });
        toast(t("block.added"), "ok"); $("#blS").value = ""; $("#blE").value = ""; $("#blN").value = ""; draw();
      } catch (err) { toast(err.message, "error"); }
    });
    view.onclick = async (e) => {
      const b = e.target.closest("[data-unblock]"); if (!b) return;
      try { await api(`/api/cars/${carId()}/blocks/${b.dataset.unblock}`, { method: "DELETE" }); toast(t("block.removed"), "ok"); draw(); }
      catch (err) { toast(err.message, "error"); }
    };
    draw();
  }

  async function ownerEarnings() {
    head("dash.earnings", "earn.sub");
    const e = await api("/api/my/earnings");
    view.innerHTML = `<div class="stats">
        ${stat(t("earn.online"), money(e.earned_online), esc(t("earn.online_sub")))}
        ${stat(t("earn.paid_out"), money(e.paid_out), esc(t("earn.paid_out_sub")))}
        ${stat(t("earn.balance"), money(e.balance), esc(t("earn.balance_sub")))}
        ${stat(t("earn.on_site"), money(e.on_site), esc(t("earn.on_site_sub")))}
      </div>
      <div class="notice info" style="margin-bottom:16px">${esc(t("earn.note"))}</div>
      <div class="two-col">
        <div class="card"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("earn.payments"))}</h3></div>
          ${e.payments.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.car"))}</th><th>${esc(t("col.dates"))}</th>
            <th>${esc(t("pay.method"))}</th><th>${esc(t("col.status"))}</th><th>${esc(t("booking.yours"))}</th></tr></thead><tbody>
            ${e.payments.map((p) => `<tr><td data-label="${esc(t("col.car"))}">${esc(p.brand)} ${esc(p.model)} ${p.year}</td>
              <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</td>
              <td data-label="${esc(t("pay.method"))}">${esc(p.provider === "test" ? t("pay.test_name") : p.provider === "click" ? "Click" : "Payme")}</td>
              <td data-label="${esc(t("col.status"))}"><span class="tag ${p.status === "paid" ? "tag-ok" : "tag-pending"}">${esc(t("pay.st_" + p.status))}</span></td>
              <td data-label="${esc(t("booking.yours"))}"><b>${money(p.owner_payout)}</b></td></tr>`).join("")}</tbody></table></div>`
            : `<div class="empty">${esc(t("earn.no_payments"))}</div>`}</div>
        <div class="card card-pad"><h3>${esc(t("earn.payouts"))}</h3>
          ${e.payouts.length ? e.payouts.map((x) => `<div class="sum-row"><span>${fmtDate(x.created_at)}${x.note ? ` <span class="muted small">· ${esc(x.note)}</span>` : ""}</span><b>${money(x.amount)}</b></div>`).join("")
            : `<p class="muted small">${esc(t("earn.no_payouts"))}</p>`}</div>
      </div>`;
  }

  async function ownerReviews() {
    head("dash.reviews", "owner.reviews_sub");
    const { items } = await api("/api/my/car-reviews");
    view.innerHTML = items.length ? `<div class="card card-pad">${items.map((r) => `<div class="review">
      <div class="row"><span class="avatar">${esc(initials(r.author))}</span><div><b>${esc(r.author)}</b>
        <div class="small muted"><a href="/car.html?id=${r.car_id}">${esc(r.brand)} ${esc(r.model)} ${r.year}</a> · ${fmtDate(r.created_at)}</div></div>
        <span class="spacer"></span><span class="stars">${stars(r.rating)}</span></div>
      ${r.comment ? `<p style="margin:8px 0 0">${esc(r.comment)}</p>` : ""}
      ${r.reply ? `<div class="reply"><b>${esc(t("review.owner_reply"))}:</b> ${esc(r.reply)}</div>` : `<form class="row reply-form" data-rid="${r.id}" style="margin:8px 0 0 44px">
        <input class="input" name="reply" maxlength="1000" placeholder="${esc(t("review.reply_ph"))}" style="flex:1" aria-label="${esc(t("review.reply_ph"))}" required>
        <button class="btn btn-sm">${esc(t("review.reply"))}</button></form>`}</div>`).join("")}</div>`
      : `<div class="empty card">${esc(t("car.reviews_empty"))}</div>`;
    $$(".reply-form", view).forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api(`/api/reviews/${f.dataset.rid}/reply`, { method: "POST", body: { reply: f.reply.value.trim() } }); toast(t("review.replied"), "ok"); ownerReviews(); }
      catch (err) { toast(err.message, "error"); }
    }));
  }

  // ===================== UMUMIY =====================
  function filterBar(active) {
    const opts = ["", "pending", "approved", "completed", "rejected", "cancelled"];
    return `<div class="row" style="margin-bottom:12px;gap:6px">${opts.map((k) =>
      `<a class="btn btn-sm ${k === active ? "" : "btn-outline"}" href="?status=${k}#bookings">${esc(k ? t("status." + k) : t("common.all"))}</a>`).join("")}</div>`;
  }

  const payTag = (b) => b.payment_status && b.payment_status !== "on_site"
    ? `<span class="tag ${b.payment_status === "paid" ? "tag-ok" : "tag-pending"}">${esc(t("pay.st_" + b.payment_status))}</span>` : "";

  function bookingRow(b, owner) {
    const today = isoDate(new Date());
    let actions = "";
    if (owner && b.status === "pending") actions = `<button class="btn btn-sm btn-ok" data-act="approve" data-id="${b.id}">✓ ${esc(t("booking.approve"))}</button>
      <button class="btn btn-sm btn-danger" data-act="reject" data-id="${b.id}">${esc(t("booking.reject"))}</button>`;
    if (!owner && b.status === "approved" && b.payment_status === "on_site" && b.end_date >= today)
      actions += `<button class="btn btn-sm" data-pay="${b.id}" data-total="${b.total_price}">${icon("card", 16)} ${esc(t("pay.online"))}</button>`;
    if (!owner && (b.status === "pending" || (b.status === "approved" && b.start_date > today)))
      actions += `<button class="btn btn-sm btn-danger" data-act="cancel" data-id="${b.id}">${esc(t("booking.cancel"))}</button>`;
    if (b.payment_id) actions += `<a class="btn btn-sm btn-outline" href="/receipt.html?payment=${b.payment_id}">${icon("receipt", 16)} ${esc(t("pay.receipt"))}</a>`;
    if (b.status === "completed" && (owner ? !b.renter_review_id : !b.car_review_id))
      actions += `<button class="btn btn-sm btn-soft" data-review="${b.id}" data-title="${esc(owner ? b.renter_name : `${b.brand} ${b.model}`)}" data-owner="${owner ? 1 : 0}">★ ${esc(t(owner ? "review.rate_renter" : "review.leave"))}</button>`;
    if (!owner && ["completed", "cancelled", "rejected"].includes(b.status))
      actions += `<a class="btn btn-sm btn-outline" href="/car.html?id=${b.car_id}#book">${esc(t("booking.rebook"))}</a>`;
    const partnerId = owner ? b.renter_id : b.owner_id, partner = owner ? b.renter_name : b.owner_name;
    const phone = owner ? b.renter_phone : (["approved", "completed"].includes(b.status) ? b.owner_phone : null);
    actions += `<a class="btn btn-sm btn-outline" href="/messages.html?user=${partnerId}&car=${b.car_id}" aria-label="${esc(t("nav.messages"))}" title="${esc(t("nav.messages"))}">${icon("chat", 16)}</a>`;
    const where = b.payment_status === "on_site" ? ` · ${esc(t("terms.on_site"))}` : "";
    const money_line = owner
      ? `${esc(t("booking.total"))}: <b>${money(b.total_price)}</b> · ${esc(t("booking.fee", { pct: b.commission_bps / 100 }))}: ${money(b.commission)} · ${esc(t("booking.yours"))}: <b>${money(b.owner_payout)}</b>`
      : `${esc(t("booking.total"))}: <b>${money(b.total_price)}</b>${b.deposit ? ` · ${esc(t("book.deposit"))}: ${money(b.deposit)}` : ""}${where}`;
    const verified = owner && (b.renter_phone_verified || b.renter_email_verified)
      ? ` <span class="verified" title="${esc(t("verify.badge"))}">${icon("check", 13)} ${esc(t("verify.badge"))}</span>` : "";
    return `<div class="list-item">
      <a class="thumb" href="/car.html?id=${b.car_id}">${carImage({ id: b.car_id, brand: b.brand, model: b.model, cover: b.cover })}</a>
      <div><div class="row" style="gap:8px"><a href="/car.html?id=${b.car_id}"><b>${esc(b.brand)} ${esc(b.model)} ${b.year}</b></a>${statusTag(b.status)}${payTag(b)}</div>
        <div class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)} · ${esc(t("car.days_n", { n: b.days }))}${b.delivery ? ` · ${esc(t("book.delivery_fee"))}` : ""}</div>
        <div class="small">${money_line}</div>
        <div class="small muted">${esc(t(owner ? "booking.renter" : "booking.owner"))}: ${esc(partner)}${verified}
          ${owner && b.renter_rating ? ` · ★ ${b.renter_rating} (${b.renter_reviews})` : owner ? ` · ${esc(t("booking.new_renter"))}` : ""}
          ${phone ? ` · <a href="tel:${esc(phone)}">${esc(phone)}</a>` : ""}</div>
        ${b.note ? `<div class="small muted">${esc(t("booking.note"))}: “${esc(b.note)}”</div>` : ""}
      </div>
      <div class="actions">${actions}</div></div>`;
  }

  function bindBookingActions(reload) {
    view.onclick = async (e) => {
      const act = e.target.closest("[data-act]"), rev = e.target.closest("[data-review]"), pay = e.target.closest("[data-pay]");
      if (act) {
        if (!(await confirmBox(t("booking.confirm_" + act.dataset.act), t("common.yes"), act.dataset.act !== "approve"))) return;
        try { await api(`/api/bookings/${act.dataset.id}/${act.dataset.act}`, { method: "POST" }); toast(t("booking.done_" + act.dataset.act), "ok"); reload(); }
        catch (err) { toast(err.message, "error"); }
      }
      if (rev) reviewModal(rev.dataset.review, rev.dataset.title, rev.dataset.owner === "1", reload);
      if (pay) payModal(+pay.dataset.pay, +pay.dataset.total);
    };
  }

  /** To'lov usulini tanlash. Faqat haqiqatan sozlangan provayderlar faol bo'ladi. */
  async function payModal(bookingId, total) {
    const prov = await api("/api/payments/providers");
    const opts = [["click", "Click", "pay.click_d"], ["payme", "Payme", "pay.payme_d"], ["test", t("pay.test_name"), "pay.test_d"]];
    const any = opts.some(([k]) => prov[k]);
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true" aria-labelledby="payT"><h3 id="payT">${esc(t("pay.choose"))}</h3>
      <p class="muted">${esc(t("pay.amount"))}: <b>${money(total)}</b></p>
      <div class="pay-options">${opts.map(([k, name, d]) => `<label class="pay-opt ${prov[k] ? "" : "off"}">
        <input type="radio" name="provider" value="${k}" ${prov[k] ? "" : "disabled"}>
        <span class="pay-logo pay-${k}">${esc(k === "test" ? "TEST" : name)}</span>
        <span><b>${esc(name)}</b><span class="small muted">${esc(prov[k] ? t(d) : t("pay.not_connected"))}</span></span></label>`).join("")}</div>
      ${any ? "" : `<div class="notice" style="margin-top:12px">${esc(t("pay.none"))}</div>`}
      <p class="small muted" style="margin:12px 0">${icon("lock", 14)} ${esc(t("pay.secure_note"))}</p>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button>
        <button class="btn" ${any ? "" : "disabled"}>${esc(t("pay.continue"))}</button></div></form>`;
    document.body.append(bg);
    const first = $("input:not(:disabled)", bg); if (first) first.checked = true;
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (e) => {
      e.preventDefault();
      const provider = new FormData(e.target).get("provider");
      if (!provider) return;
      await withLoading($("button.btn:not(.btn-outline)", bg), async () => {
        try { const r = await api("/api/payments", { method: "POST", body: { booking_id: bookingId, provider } }); location.href = r.redirect_url; }
        catch (err) { toast(err.message, "error"); }
      });
    });
  }

  function reviewModal(bookingId, title, aboutRenter, reload) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true"><h3>${esc(t(aboutRenter ? "review.rate_renter" : "review.leave"))}: ${esc(title)}</h3>
      <div class="field"><label>${esc(t("review.rating"))}</label><div class="rating-input">
        ${[5, 4, 3, 2, 1].map((n) => `<input type="radio" name="rating" id="st${n}" value="${n}" ${n === 5 ? "checked" : ""}><label for="st${n}" title="${n}">★</label>`).join("")}</div></div>
      <div class="field"><label for="rvc">${esc(t("review.comment"))}</label><textarea class="input" id="rvc" name="comment" maxlength="1000"
        placeholder="${esc(t(aboutRenter ? "review.ph_renter" : "review.ph_car"))}"></textarea></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button><button class="btn">${esc(t("common.send"))}</button></div></form>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = formData(e.target);
      try { await api("/api/reviews", { method: "POST", body: { booking_id: +bookingId, rating: +f.rating, comment: f.comment || null } }); bg.remove(); toast(t("review.thanks"), "ok"); reload(); }
      catch (err) { toast(err.message, "error"); }
    });
  }

  async function notifications() {
    head("dash.notifications");
    const data = await api("/api/notifications");
    view.innerHTML = `<div class="row" style="margin-bottom:12px"><button class="btn btn-sm btn-outline" id="readAllBtn">${esc(t("notif.read_all"))}</button></div>
      <div class="card">${data.items.length ? data.items.map((n) => { const x = notifText(n); return `<a class="notif ${n.is_read ? "" : "unread"}" href="${esc(n.link || "#")}" data-id="${n.id}">
        <div class="t">${esc(x.title)}</div><div class="b">${esc(x.body)}</div><div class="small muted">${timeAgo(n.created_at)}</div></a>`; }).join("")
        : `<div class="empty">${esc(t("notif.empty"))}</div>`}</div>`;
    $("#readAllBtn").addEventListener("click", async () => { await api("/api/notifications/read-all", { method: "POST" }); pollSummary(); notifications(); });
    $$(".notif", view).forEach((a) => a.addEventListener("click", () => api(`/api/notifications/${a.dataset.id}/read`, { method: "POST" }).catch(() => {})));
  }

})();
