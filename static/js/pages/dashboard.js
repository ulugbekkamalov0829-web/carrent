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
      favorites, cars: ownerCars, calendar: ownerCalendar, reviews: ownerReviews, earnings: ownerEarnings, notifications,
      payments: renterPayments, disputes: myDisputes, analytics: () => { head("rep.title", mode() === "owner" ? "rep.sub_owner" : "rep.sub_renter"); return Reports.render(view, mode()); } }[tab];
    fn().catch((e) => (view.innerHTML = `<div class="empty card">${esc(e.message)}</div>`));
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("langchange", route);
  document.addEventListener("modeview", route);
  route();

  // ===================== IJARACHI =====================
  const DR = (scope, entity, title, extra = {}) => ({ scope, entity, title, ...extra });
  const periodRange = (k) => {
    const d = new Date(), iso = isoDate;
    return { today: [iso(d), iso(d)], week: [iso(new Date(d.getFullYear(), d.getMonth(), d.getDate() - 6)), iso(d)],
      month: [iso(new Date(d.getFullYear(), d.getMonth(), 1)), iso(d)], year: [iso(new Date(d.getFullYear(), 0, 1)), iso(d)] }[k];
  };

  async function renterOverview() {
    head("dash.hello", "dash.renter_sub");
    const [s, mine, reco] = await Promise.all([api("/api/dashboard/renter"), api("/api/bookings/mine"), api("/api/recommendations?limit=4")]);
    const active = s.bookings.approved;
    view.innerHTML = `<div class="stats">
        ${stat(t("dash.active"), active, s.upcoming ? esc(t("dash.next_trip", { car: s.upcoming.title, d: fmtDate(s.upcoming.start_date) })) : `<a href="/cars.html">${esc(t("dash.find_car"))}</a>`,
          active ? DR("renter", "bookings", t("dash.active"), { status: "approved" }) : "", t("hint.r_active"))}
        ${stat(t("dash.pending"), s.bookings.pending, esc(t("dash.pending_sub")), s.bookings.pending ? DR("renter", "bookings", t("dash.pending"), { status: "pending" }) : "", t("hint.r_pending"))}
        ${stat(t("dash.completed"), s.bookings.completed, s.to_review ? `<a href="#bookings">${esc(t("dash.to_review", { n: s.to_review }))}</a>` : esc(t("dash.days_total", { n: s.days_total })),
          s.bookings.completed ? DR("renter", "bookings", t("dash.completed"), { status: "completed" }) : "", t("hint.r_completed"))}
        ${stat(t("dash.favorites"), s.favorites, `<span class="link-like">${esc(t("dash.open"))}</span>`, "#favorites", t("hint.r_favorites"))}
      </div>
      <div class="two-col">
        <div class="card"><div class="card-pad" style="padding-bottom:6px"><h3>${esc(t("dash.recent"))}</h3></div>
          ${mine.items.slice(0, 4).map((b) => bookingRow(b, false)).join("") || `<div class="empty">${esc(t("dash.no_bookings"))}</div>`}</div>
        <div class="card card-pad"><h3>${esc(t("dash.my_profile"))}</h3>
          <div class="sum-row" ${s.spent_total ? drillAttr(DR("renter", "bookings", t("dash.spent"), { status: "done" })) : ""}><span class="muted">${esc(t("dash.spent"))}</span><b>${money(s.spent_total)}</b></div>
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

  async function renterPayments() {
    head("dash.my_payments", "mypay.sub");
    const d = await api("/api/my/payments");
    const provName = (k) => (k === "test" ? t("pay.test_name") : k === "click" ? "Click" : "Payme");
    view.innerHTML = `<div class="stats">
        ${stat(t("mypay.paid"), money(d.paid_total), esc(t("mypay.paid_sub")), d.paid_total ? DR("renter", "payments", t("mypay.paid")) : "")}
        ${stat(t("mypay.refunded"), money(d.refunded_total), esc(t("mypay.refunded_sub")), d.refunded_total ? DR("renter", "payments", t("mypay.refunded"), { status: "refunded" }) : "")}
        ${stat(t("mypay.waiting"), money(d.refund_waiting), esc(t("mypay.waiting_sub")), d.refund_waiting ? DR("renter", "payments", t("mypay.waiting"), { status: "refund_pending" }) : "")}
      </div>
      <div class="two-col wide-left">
        <div class="card"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("mypay.history"))}</h3></div>
          ${d.items.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>№</th><th>${esc(t("col.car"))}</th><th>${esc(t("col.dates"))}</th>
            <th>${esc(t("pay.method"))}</th><th>${esc(t("pay.amount"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
            ${d.items.map((p) => `<tr><td data-label="№">${p.id}</td><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${p.car_id}">${esc(p.brand)} ${esc(p.model)} ${p.year}</a></td>
              <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</td>
              <td data-label="${esc(t("pay.method"))}">${esc(provName(p.provider))}</td>
              <td data-label="${esc(t("pay.amount"))}"><b>${money(p.amount)}</b>${p.refund_amount ? `<div class="small" style="color:var(--success-ink)">↩ ${money(p.refund_amount)}</div>` : ""}</td>
              <td data-label="${esc(t("col.status"))}">${payStatusTag(p.status)}</td>
              <td>${["paid", "refunded", "refund_pending"].includes(p.status) ? `<a class="btn btn-sm btn-outline" href="/receipt.html?payment=${p.id}">${icon("receipt", 16)} ${esc(t("pay.receipt"))}</a>` : ""}</td></tr>`).join("")}
            </tbody></table></div>` : `<div class="empty">${esc(t("mypay.empty"))}</div>`}</div>
        <div class="card card-pad"><h3>${icon("shield", 18)} ${esc(t("policy.title"))}</h3>
          ${policyList(d.policy)}
          <p class="small muted" style="margin-top:10px">${esc(t("policy.on_site"))}</p>
          <p class="small muted">${esc(t("policy.real_providers"))}</p></div>
      </div>`;
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
    const [s, inc] = await Promise.all([api("/api/dashboard/owner"), api("/api/bookings/incoming")]);
    if (!s.cars_total) {
      view.innerHTML = `<div class="empty card"><h3>${esc(t("owner.empty"))}</h3><p>${esc(t("owner.empty_hint", { pct: s.commission_bps / 100 }))}</p>
        <a class="btn btn-lg" href="/car-form.html">+ ${esc(t("nav.add_car"))}</a></div>`;
      return;
    }
    const p = s.periods, today = isoDate(new Date());
    const months = t("cal.months_short").split(",");
    const pay = s.monthly.map((m) => m.payout), cnt = s.monthly.map((m) => m.count);
    const rentedNow = new Set(inc.items.filter((b) => b.status === "approved" && b.start_date <= today && b.end_date >= today).map((b) => b.car_id)).size;
    const pending = inc.items.filter((b) => b.status === "pending");
    const series = {
      month: s.daily.map((d) => ({ k: d.day, v: d.payout, n: d.count, label: fmtDate(d.day).slice(0, 5) })),
      year: s.monthly.map((m) => ({ k: m.month, v: m.payout, n: m.count, label: months[+m.month.slice(5) - 1] })),
    };
    let period = "year";
    const chartDrill = (pt) => DR("owner", "bookings", `${t("owner.monthly")}: ${pt.label}`, { status: "done", ...(pt.k.length === 7 ? { month: pt.k } : { day: pt.k }) });
    view.innerHTML = `<p class="drill-note">${icon("info", 14)} ${esc(t("drill.note"))}</p>
      <div class="owner-dash">
        <div class="od-main">
          <div class="kpi-row three">
            ${kpiCard({ label: t("owner.month_income"), value: money(p.month.payout), icon: "trend", tone: "green", trend: trendPct(pay), spark: sparkline(pay.slice(-8)),
              href: p.month.revenue ? DR("owner", "bookings", t("owner.month_income"), { status: "done", from: periodRange("month")[0], to: periodRange("month")[1] }) : "", hint: t("hint.o_payout") })}
            ${kpiCard({ label: t("owner.active_cars"), value: `${s.cars_active} <small>/ ${s.cars_total}</small>`, icon: "car", tone: "blue",
              sub: esc(t("owner.rented_free", { a: rentedNow, b: Math.max(0, s.cars_active - rentedNow) })), spark: donut(rentedNow, Math.max(1, s.cars_active)),
              href: DR("owner", "cars", t("owner.active_cars"), { sort: "occupancy" }), hint: t("hint.o_cars") })}
            ${kpiCard({ label: t("owner.orders_n"), value: cnt[cnt.length - 1] || 0, icon: "list", tone: "orange", sub: esc(t("owner.this_month")), spark: miniBars(cnt.slice(-10)),
              href: DR("owner", "bookings", t("owner.orders_n"), { from: periodRange("month")[0], to: periodRange("month")[1] }) })}
          </div>
          <div class="card card-pad"><div class="card-head"><h3>${esc(t("owner.monthly"))}</h3>
            <div class="seg small-seg" id="perSeg">${["month", "year"].map((k) => `<button type="button" data-per="${k}" class="${k === period ? "on" : ""}">${esc(t("per." + k))}</button>`).join("")}</div></div>
            <div id="areaBox"></div></div>
        </div>
        <div class="card card-pad od-cal"><h3>${esc(t("owner.occ_calendar"))}</h3><div id="occCal"></div></div>
      </div>
      <div class="card" style="margin-top:18px"><div class="card-pad card-head" style="padding-bottom:4px"><h3>${esc(t("owner.pending_orders"))} ${pending.length ? `<span class="cnt-badge">${pending.length}</span>` : ""}</h3><a class="small" href="#bookings">${esc(t("admin.see_all"))} →</a></div>
        ${pending.length ? `<div class="po-list">${pending.slice(0, 6).map((b) => `<div class="po-row">
            <span class="avatar">${esc(initials(b.renter_name))}</span>
            <div class="po-who"><b>${esc(b.renter_name)}</b>${b.renter_docs_verified ? ` <span class="verified docs">${icon("idcard", 12)}</span>` : ""}<div class="small muted">${b.renter_rating ? `★ ${b.renter_rating}` : esc(t("booking.new_renter"))}</div></div>
            <div class="po-car"><b>${esc(b.brand)} ${esc(b.model)}</b><div class="small muted">${b.year}</div></div>
            <div class="po-when"><span class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)}</span><b>${money(b.total_price)}</b></div>
            <div class="po-acts"><button class="btn btn-sm btn-ok" data-act="approve" data-id="${b.id}">${esc(t("booking.approve"))}</button>
              <button class="btn btn-sm btn-outline danger-outline" data-act="reject" data-id="${b.id}">${esc(t("booking.reject"))}</button></div></div>`).join("")}</div>`
          : `<div class="empty small">${icon("check", 18)} ${esc(t("owner.all_done"))}</div>`}</div>
      <div class="stats small-stats" style="margin-top:18px">
        ${stat(t("owner.revenue"), money(s.revenue_total), esc(t("owner.revenue_sub")), s.revenue_total ? DR("owner", "bookings", t("owner.revenue"), { status: "done" }) : "", t("hint.o_revenue"))}
        ${stat(t("owner.commission", { pct: s.commission_bps / 100 }), money(s.commission_total), esc(t("owner.commission_sub")), s.commission_total ? DR("owner", "bookings", t("owner.commission", { pct: s.commission_bps / 100 }), { status: "done" }) : "", t("hint.o_commission"))}
        ${stat(t("owner.payout"), money(s.payout_total), esc(t("owner.payout_sub")), s.payout_total ? DR("owner", "bookings", t("owner.payout"), { status: "done" }) : "", t("hint.o_payout"))}
        ${stat(t("owner.occupancy"), `${s.occupancy}%`, esc(t("owner.occupancy_sub")), DR("owner", "cars", t("owner.occupancy"), { sort: "occupancy" }), t("hint.o_occupancy"))}
        ${stat(t("owner.rating"), s.rating_avg ? `★ ${s.rating_avg}` : "—", esc(t("car.reviews_n", { n: s.reviews_count })), s.reviews_count ? DR("owner", "reviews", t("owner.rating")) : "", t("hint.o_rating"))}
        ${stat(t("owner.conversion"), `${s.conversion}%`, esc(t("owner.conversion_sub", { n: s.views_total })), DR("owner", "cars", t("owner.conversion")), t("hint.o_conversion"))}
      </div>
      <div class="card card-pad" style="margin-bottom:18px"><h3>${esc(t("owner.periods"))}</h3>
        <div class="stats" style="margin:0">${["today", "week", "month", "year"].map((k) => `<div class="period-cell" ${p[k].revenue ? drillAttr(DR("owner", "bookings", `${t("owner.periods")}: ${t("period." + k)}`, { status: "done", from: periodRange(k)[0], to: periodRange(k)[1] })) : ""}><div class="small muted">${esc(t("period." + k))}</div>
          <b>${money(p[k].payout)}</b><div class="small muted">${esc(t("owner.gross"))}: ${money(p[k].revenue)}</div></div>`).join("")}</div></div>
      <div class="two-col">
        <div class="card card-pad"><h3>${esc(t("owner.statuses"))}</h3>${statusBars(s.bookings, (k) => DR("owner", "bookings", `${t("owner.statuses")}: ${t("status." + k)}`, { status: k }))}</div>
        <div class="card"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("owner.per_car"))}</h3></div>
          <div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.car"))}</th><th>${esc(t("col.bookings"))}</th><th>${esc(t("col.occupancy"))}</th><th>${esc(t("col.payout"))}</th></tr></thead><tbody>
          ${s.per_car.map((c) => `<tr ${c.bookings ? drillAttr(DR("owner", "bookings", `${c.brand} ${c.model} ${c.year}`, { car_id: c.id })) : ""}><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${c.id}">${esc(c.brand)} ${esc(c.model)} ${c.year}</a></td>
            <td data-label="${esc(t("col.bookings"))}">${c.bookings}</td><td data-label="${esc(t("col.occupancy"))}">${c.occupancy}%</td>
            <td data-label="${esc(t("col.payout"))}"><b>${money(c.payout)}</b></td></tr>`).join("")}</tbody></table></div></div>
      </div>`;
    const drawArea = () => { $("#areaBox").innerHTML = areaChart(series[period], { drill: chartDrill, color: "var(--primary)" }); };
    drawArea();
    $("#perSeg").addEventListener("click", (e) => { const b = e.target.closest("[data-per]"); if (!b) return; period = b.dataset.per; $$("#perSeg button").forEach((x) => x.classList.toggle("on", x === b)); drawArea(); });
    occCalendar($("#occCal"), inc.items, { cars: s.per_car });
    bindBookingActions(ownerOverview);
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
          <div class="small muted">${esc(Places.label(c.city, c.district))} · ${money(c.price_per_day)} ${esc(t("car.per_day"))} · ${c.rating ? `★ ${c.rating} (${c.reviews_count})` : esc(t("car.no_reviews"))} · ${esc(t("car.views_n", { n: c.views }))}</div>
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
          fuel: c.fuel, engine_l: c.engine_l, mileage_km: c.mileage_km, drive: c.drive, features: c.features, city: c.city, district: c.district, description: c.description,
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
      <select class="input" id="calCar">${items.map((c) => `<option value="${c.id}" ${String(c.id) === pre ? "selected" : ""}>${esc(carName(c))} ${c.year} · ${esc(Places.label(c.city, c.district))}</option>`).join("")}</select></div>
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
    const [e, prov] = await Promise.all([api("/api/my/earnings"), api("/api/payments/providers")]);
    const realOnline = prov.click || prov.payme;
    const pending = e.requests.find((r) => r.status === "pending");
    const reqTag = (st) => `<span class="tag ${st === "paid" ? "tag-ok" : st === "pending" ? "tag-pending" : st === "rejected" ? "tag-bad" : "tag-hidden"}">${esc(t("payreq.st_" + st))}</span>`;
    const method = (r) => r.method === "card" ? `${t("payreq.m_card")} •••• ${r.card_last4}` : t("payreq.m_" + r.method);
    view.innerHTML = `<div class="stats">
        ${stat(t("earn.online"), money(e.earned_online), esc(e.compensation ? t("earn.online_sub_comp", { sum: money(e.compensation) }) : t("earn.online_sub")), e.earned_online ? DR("owner", "payments", t("earn.online")) : "")}
        ${stat(t("earn.paid_out"), money(e.paid_out), esc(t("earn.paid_out_sub")), e.paid_out ? DR("owner", "payouts", t("earn.paid_out")) : "")}
        ${stat(t("payreq.available"), money(e.available), esc(e.requested ? t("payreq.available_sub_req", { sum: money(e.requested) }) : t("earn.balance_sub")))}
        ${stat(t("earn.site_collected"), money(e.site_collected), `${esc(t("earn.site_collected_sub"))}<br>${e.fee_owed
          ? `<span class="tag tag-pending">${esc(t("earn.fee_debt"))}: ${money(e.fee_owed)}</span>` : `<span class="tag tag-ok">${esc(t("earn.fee_debt"))}: ${esc(t("earn.fee_debt_none"))}</span>`}`,
          e.site_collected ? DR("owner", "bookings", t("earn.site_collected"), { pay: "on_site", status: "completed" }) : "")}
      </div>
      <details class="card card-pad earn-how" ${e.earned_online || e.paid_out ? "" : "open"}><summary><b>${icon("info", 18)} ${esc(t("earn.how_t"))}</b></summary>
        <div class="how-grid"><div class="how-step"><span class="how-ico">${icon("card", 20)}</span><p>${esc(t("earn.how_online"))}</p></div>
          <div class="how-step"><span class="how-ico">${icon("wallet", 20)}</span><p>${esc(t("earn.how_site"))}</p></div></div>
        ${realOnline ? "" : `<div class="notice" style="margin-top:12px">${esc(t("earn.providers_off"))}</div>`}</details>
      <div class="two-col" style="margin-bottom:18px">
        <form class="card card-pad" id="payReqForm" novalidate><h3>${icon("wallet", 18)} ${esc(t("payreq.title"))}</h3>
          ${pending ? `<div class="notice info">${esc(t("payreq.pending_note", { sum: money(pending.amount), d: fmtDate(pending.created_at) }))}</div>
              <button type="button" class="btn btn-outline btn-sm" style="margin-top:10px" data-cancel-req="${pending.id}">${esc(t("payreq.cancel"))}</button>`
          : e.available > 0 ? `<p class="small muted">${esc(t("payreq.sub"))}</p>
            <div class="field"><label for="prA">${esc(t("pay.amount"))}</label>
              <input class="input" type="text" data-money id="prA" name="amount" value="${e.available}" required data-hint="payreq.amount_hint">
              <div class="row" style="gap:6px;margin-top:6px">${[0.25, 0.5, 1].map((k) => `<button type="button" class="btn btn-sm btn-soft" data-part="${Math.floor(e.available * k)}">${k === 1 ? esc(t("common.all")) : k * 100 + "%"}</button>`).join("")}</div></div>
            <div class="field"><label>${esc(t("payreq.method"))}</label><div class="seg" id="prM" role="radiogroup">
              ${["card", "bank", "cash"].map((m, i) => `<button type="button" role="radio" data-m="${m}" class="${i ? "" : "on"}" aria-checked="${!i}">${esc(t("payreq.m_" + m))}</button>`).join("")}</div></div>
            <div class="field" id="prCardF"><label for="prC">${esc(t("payreq.card_last4"))}</label>
              <input class="input" id="prC" name="card_last4" inputmode="numeric" maxlength="4" pattern="[0-9]{4}" placeholder="1234" data-hint="payreq.card_hint"></div>
            <div class="field"><label for="prN">${esc(t("block.note"))} <span class="muted small">(${esc(t("common.optional"))})</span></label>
              <input class="input" id="prN" name="note" maxlength="300" placeholder="${esc(t("payreq.note_ph"))}"></div>
            <button class="btn btn-block">${esc(t("payreq.send"))}</button>
            <p class="small muted" style="margin:10px 0 0">${icon("lock", 14)} ${esc(t("payreq.privacy"))}</p>`
          : `<p class="muted">${esc(t("payreq.nothing"))}</p>`}
        </form>
        <div class="card card-pad"><h3>${esc(t("payreq.history"))}</h3>
          ${e.requests.length ? e.requests.map((r) => `<div class="sum-row" style="align-items:flex-start"><span><b>${money(r.amount)}</b>
              <span class="small muted"> · ${esc(method(r))} · ${fmtDate(r.created_at)}</span>
              ${r.admin_note ? `<div class="small muted">${esc(t("payreq.admin_note"))}: ${esc(r.admin_note)}</div>` : ""}</span>${reqTag(r.status)}</div>`).join("")
            : `<p class="muted small">${esc(t("payreq.none"))}</p>`}</div>
      </div>
      <div class="two-col">
        <div class="card"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("earn.payments"))}</h3></div>
          ${e.payments.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.car"))}</th><th>${esc(t("col.dates"))}</th>
            <th>${esc(t("pay.method"))}</th><th>${esc(t("col.status"))}</th><th>${esc(t("booking.yours"))}</th></tr></thead><tbody>
            ${e.payments.map((p) => { const cancelled = p.booking_status === "cancelled"; const yours = cancelled ? p.kept_payout : p.owner_payout;
              return `<tr><td data-label="${esc(t("col.car"))}">${esc(p.brand)} ${esc(p.model)} ${p.year}</td>
              <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</td>
              <td data-label="${esc(t("pay.method"))}">${esc(p.provider === "test" ? t("pay.test_name") : p.provider === "click" ? "Click" : "Payme")}</td>
              <td data-label="${esc(t("col.status"))}">${cancelled ? `<span class="tag tag-hidden">${esc(t("earn.cancelled_comp"))}</span>` : payStatusTag(p.status)}</td>
              <td data-label="${esc(t("booking.yours"))}"><b>${money(yours)}</b></td></tr>`; }).join("")}</tbody></table></div>`
            : `<div class="empty"><b>${esc(t("earn.no_online_t"))}</b><p class="small muted" style="max-width:460px;margin:6px auto 0">${esc(t("earn.no_online_b"))}</p></div>`}</div>
        <div class="card card-pad"><h3>${esc(t("earn.payouts"))}</h3>
          ${e.payouts.length ? e.payouts.map((x) => `<div class="sum-row"><span>${fmtDate(x.created_at)}${x.note ? ` <span class="muted small">· ${esc(x.note)}</span>` : ""}</span><b>${money(x.amount)}</b></div>`).join("")
            : `<p class="muted small">${esc(t("earn.no_payouts"))}</p>`}</div>
      </div>`;
    applyHints(view); applyMasks(view);
    let methodSel = "card";
    $$("#prM [data-m]", view).forEach((b) => b.addEventListener("click", () => {
      methodSel = b.dataset.m;
      $$("#prM [data-m]", view).forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); });
      $("#prCardF").classList.toggle("hidden", methodSel !== "card");
    }));
    $("#prC")?.addEventListener("input", (ev) => { ev.target.value = ev.target.value.replace(/\D/g, "").slice(0, 4); });
    view.onclick = async (ev) => {
      const part = ev.target.closest("[data-part]"), cancel = ev.target.closest("[data-cancel-req]");
      if (part) $("#prA").value = fmtMoneyInput(part.dataset.part);
      if (cancel && await confirmBox(t("payreq.cancel_confirm"), t("common.yes"))) {
        try { await api(`/api/my/payout-requests/${cancel.dataset.cancelReq}/cancel`, { method: "POST" }); toast(t("common.done"), "ok"); ownerEarnings(); }
        catch (err) { toast(err.message, "error"); }
      }
    };
    $("#payReqForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!$("#prA")) return;
      const body = { amount: moneyVal($("#prA").value) || 0, method: methodSel, card_last4: methodSel === "card" ? $("#prC").value.trim() || null : null, note: $("#prN").value.trim() || null };
      await withLoading($("button.btn-block", ev.target), async () => {
        try { await api("/api/my/payout-requests", { method: "POST", body }); toast(t("payreq.sent"), "ok"); ownerEarnings(); }
        catch (err) { showFieldErrors(ev.target, err); toast(err.message, "error"); }
      });
    });
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

  const payTag = (b) => b.payment_status && b.payment_status !== "on_site" ? payStatusTag(b.payment_status) : "";

  function bookingRow(b, owner) {
    const today = isoDate(new Date());
    let actions = "";
    if (owner && b.status === "pending") actions = `<button class="btn btn-sm btn-ok" data-act="approve" data-id="${b.id}">✓ ${esc(t("booking.approve"))}</button>
      <button class="btn btn-sm btn-danger" data-act="reject" data-id="${b.id}">${esc(t("booking.reject"))}</button>`;
    if (!owner && b.status === "approved" && b.payment_status === "on_site" && b.end_date >= today)
      actions += `<button class="btn btn-sm" data-pay="${b.id}" data-total="${b.total_price}">${icon("card", 16)} ${esc(t("pay.online"))}</button>`;
    if (!owner && (b.status === "pending" || (b.status === "approved" && b.start_date > today)))
      actions += `<button class="btn btn-sm btn-danger" data-act="cancel" data-id="${b.id}">${esc(t("booking.cancel"))}</button>`;
    if (["approved", "completed"].includes(b.status)) {
      const cs = b.contract_status || "pending";
      actions += `<a class="btn btn-sm ${cs === "approved" ? "btn-outline" : "btn-soft"}" href="/contract.html?booking=${b.id}">${icon("doc", 16)} ${esc(t("ctr.btn"))}${cs === "pending" ? ` <i class="dot-warn"></i>` : ""}</a>
        <a class="btn btn-sm btn-outline" href="/handover.html?booking=${b.id}">${icon("key", 16)} ${esc(t("ho.btn"))}</a>`;
    }
    if (b.payment_id) actions += `<a class="btn btn-sm btn-outline" href="/receipt.html?payment=${b.payment_id}">${icon("receipt", 16)} ${esc(t("pay.receipt"))}</a>`;
    if (b.status === "completed" && (owner ? !b.renter_review_id : !b.car_review_id))
      actions += `<button class="btn btn-sm btn-soft" data-review="${b.id}" data-title="${esc(owner ? b.renter_name : `${b.brand} ${b.model}`)}" data-owner="${owner ? 1 : 0}">★ ${esc(t(owner ? "review.rate_renter" : "review.leave"))}</button>`;
    if (!owner && ["completed", "cancelled", "rejected"].includes(b.status))
      actions += `<a class="btn btn-sm btn-outline" href="/car.html?id=${b.car_id}#book">${esc(t("booking.rebook"))}</a>`;
    if (["approved", "completed", "cancelled"].includes(b.status) && daysBetween(b.end_date, today) <= 31)
      actions += `<button class="btn btn-sm btn-outline" data-dispute="${b.id}" title="${esc(t("disp.title"))}">${icon("shield", 16)} ${esc(t("disp.open_btn"))}</button>`;
    const partnerId = owner ? b.renter_id : b.owner_id, partner = owner ? b.renter_name : b.owner_name;
    const phone = owner ? b.renter_phone : (["approved", "completed"].includes(b.status) ? b.owner_phone : null);
    actions += `<a class="btn btn-sm btn-outline" href="/messages.html?user=${partnerId}&car=${b.car_id}" aria-label="${esc(t("nav.messages"))}" title="${esc(t("nav.messages"))}">${icon("chat", 16)}</a>`;
    const where = b.payment_status === "on_site" ? ` · ${esc(t("terms.on_site"))}` : "";
    const money_line = owner
      ? `${esc(t("booking.total"))}: <b>${money(b.total_price)}</b> · ${esc(t("booking.fee", { pct: b.commission_bps / 100 }))}: ${money(b.commission)} · ${esc(t("booking.yours"))}: <b>${money(b.owner_payout)}</b>`
      : `${esc(t("booking.total"))}: <b>${money(b.total_price)}</b>${b.deposit ? ` · ${esc(t("book.deposit"))}: ${money(b.deposit)}` : ""}${where}`;
    const verified = (owner && (b.renter_phone_verified || b.renter_email_verified)
      ? ` <span class="verified" title="${esc(t("verify.badge"))}">${icon("check", 13)} ${esc(t("verify.badge"))}</span>` : "")
      + (owner ? (b.renter_docs_verified ? ` <span class="verified docs" title="${esc(t("docs.badge_t"))}">${icon("idcard", 13)} ${esc(t("docs.badge"))}</span>`
        : ` <span class="tag tag-pending" title="${esc(t("docs.no_badge_t"))}">${esc(t("docs.no_badge"))}</span>`) : "");
    return `<div class="list-item">
      <a class="thumb" href="/car.html?id=${b.car_id}">${carImage({ id: b.car_id, brand: b.brand, model: b.model, cover: b.cover })}</a>
      <div><div class="row" style="gap:8px"><a href="/car.html?id=${b.car_id}"><b>${esc(b.brand)} ${esc(b.model)} ${b.year}</b></a>${statusTag(b.status)}${payTag(b)}</div>
        <div class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)} · ${esc(t("car.days_n", { n: b.days }))}${b.delivery ? ` · ${esc(t("book.delivery_fee"))}` : ""}</div>
        <div class="small">${money_line}</div>
        <div class="small muted">${esc(t(owner ? "booking.renter" : "booking.owner"))}: ${esc(partner)}${verified}
          ${owner && b.renter_rating ? ` · ★ ${b.renter_rating} (${b.renter_reviews})` : owner ? ` · ${esc(t("booking.new_renter"))}` : ""}
          ${phone ? ` · <a href="tel:${esc(phone.replace(/[^+\d]/g, ""))}">${esc(fmtPhone(phone))}</a>` : ""}</div>
        ${b.note ? `<div class="small muted">${esc(t("booking.note"))}: “${esc(b.note)}”</div>` : ""}
      </div>
      <div class="actions">${actions}</div></div>`;
  }

  function bindBookingActions(reload) {
    view.onclick = async (e) => {
      const act = e.target.closest("[data-act]"), rev = e.target.closest("[data-review]"), pay = e.target.closest("[data-pay]");
      const dsp = e.target.closest("[data-dispute]");
      if (dsp) disputeModal(+dsp.dataset.dispute);
      if (act) {
        let text = t("booking.confirm_" + act.dataset.act);
        if (act.dataset.act === "cancel") {
          const pv = await api(`/api/bookings/${act.dataset.id}/cancel-preview`).catch(() => null);
          if (pv?.paid) text += "\n\n" + (pv.refund === pv.amount ? t("policy.preview_full", { sum: money(pv.refund) })
            : t("policy.preview_part", { pct: pv.pct, sum: money(pv.refund), kept: money(pv.kept), n: pv.days_before }));
        }
        if (!(await confirmBox(text, t("common.yes"), act.dataset.act !== "approve"))) return;
        try {
          const r = await api(`/api/bookings/${act.dataset.id}/${act.dataset.act}`, { method: "POST" });
          toast(r.refund?.refund ? t("policy.refund_done", { sum: money(r.refund.refund) }) : t("booking.done_" + act.dataset.act), "ok"); reload();
        } catch (err) { toast(err.message, "error"); }
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

  // ===================== NIZOLAR =====================
  const DISPUTE_TYPES = ["damage", "no_show", "late_return", "deposit", "not_as_described", "payment", "fuel_mileage", "other"];
  function disputeModal(bookingId) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true" aria-labelledby="dspT" novalidate>
      <h3 id="dspT">${icon("shield", 20)} ${esc(t("disp.title"))}</h3><p class="small muted">${esc(t("disp.sub"))}</p>
      <div class="field"><label for="dspType">${esc(t("disp.type"))}</label><select class="input" id="dspType" name="type">
        ${DISPUTE_TYPES.map((k) => `<option value="${k}">${esc(t("disp.t_" + k))}</option>`).join("")}</select></div>
      <div class="field"><label for="dspDesc">${esc(t("disp.desc"))}</label><textarea class="input" id="dspDesc" name="description" minlength="20" maxlength="2000" required placeholder="${esc(t("disp.desc_ph"))}"></textarea></div>
      <div class="field"><label for="dspAmt">${esc(t("disp.amount"))} <span class="muted small">(${esc(t("common.optional"))})</span></label>
        <input class="input" type="text" data-money id="dspAmt" name="amount" placeholder="0"><div class="hint show">${esc(t("disp.amount_hint"))}</div></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button>
        <button class="btn">${esc(t("disp.send"))}</button></div></form>`;
    document.body.append(bg);
    bg.addEventListener("click", (ev) => { if (ev.target === bg || ev.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const f = formData(ev.target);
      await withLoading($("button.btn:not(.btn-outline)", bg), async () => {
        try {
          await api("/api/disputes", { method: "POST", body: { booking_id: bookingId, type: f.type, description: f.description, amount: f.amount ? +f.amount : null } });
          bg.remove(); toast(t("disp.sent"), "ok"); location.hash = "#disputes";
        } catch (err) { showFieldErrors(ev.target, err); toast(err.message, "error"); }
      });
    });
    setTimeout(() => $("#dspDesc", bg).focus(), 50);
  }

  async function myDisputes() {
    head("disp.my_title", "disp.sub");
    const { items } = await api("/api/disputes/mine");
    const me = Auth.user.id;
    view.innerHTML = items.length ? `<div class="disp-list">${items.map((d) => disputeCard(d, me)).join("")}</div>`
      : `<div class="empty card"><h3>${esc(t("disp.none"))}</h3><p class="muted">${esc(t("disp.sub"))}</p></div>`;
    view.onclick = async (e) => {
      const w = e.target.closest("[data-withdraw]");
      if (w && await confirmBox(t("disp.withdraw_confirm"), t("common.yes"))) {
        try { await api(`/api/disputes/${w.dataset.withdraw}/withdraw`, { method: "POST" }); toast(t("common.done"), "ok"); myDisputes(); } catch (err) { toast(err.message, "error"); }
      }
    };
    $$(".disp-reply", view).forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api(`/api/disputes/${f.dataset.id}/reply`, { method: "POST", body: { text: f.text.value.trim() } }); toast(t("common.done"), "ok"); myDisputes(); }
      catch (err) { toast(err.message, "error"); }
    }));
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
    const showAll = new URLSearchParams(location.search).get("all") === "1";
    const list = showAll ? data.items : data.items.filter(inMode);
    const hidden = data.items.length - data.items.filter(inMode).length;
    view.innerHTML = `<div class="row" style="margin-bottom:12px;gap:6px">
        <a class="btn btn-sm ${showAll ? "btn-outline" : ""}" href="?#notifications">${esc(modeLabel(curMode()))}</a>
        <a class="btn btn-sm ${showAll ? "" : "btn-outline"}" href="?all=1#notifications">${esc(t("common.all"))}${hidden ? ` (+${hidden})` : ""}</a>
        <span class="spacer"></span><button class="btn btn-sm btn-outline" id="readAllBtn">${esc(t("notif.read_all"))}</button></div>
      <div class="card notif-page">${list.length ? list.map(notifRow).join("") : `<div class="empty">${esc(t("notif.empty_mode", { mode: modeLabel(curMode()) }))}</div>`}</div>`;
    $("#readAllBtn").addEventListener("click", async () => { await api("/api/notifications/read-all", { method: "POST" }); pollSummary(); notifications(); });
    $$(".notif", view).forEach((a) => a.addEventListener("click", (e) => openNotif(data.items.find((n) => n.id == a.dataset.id), e)));
  }

})();
