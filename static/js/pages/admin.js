"use strict";
(async () => {
  await boot("");
  await guard("admin");
  const TABS = ADMIN_TABS;
  const view = $("#view");
  let tab = "stats";

  function route() {
    const [h, sub] = location.hash.slice(1).split("/");
    if (h === "user" && +sub) { tab = "users"; markActive(); view.onclick = null; view.onsubmit = null; return userPage(+sub).catch((e) => (view.innerHTML = `<div class="empty card">${esc(e.message)}</div>`)); }
    tab = TABS.find(([k]) => k === h)?.[0] || "stats";
    route.sub = sub || "";
    markActive();
    $("#viewTitle").textContent = t(TABS.find(([k]) => k === tab)[1]);
    $("#viewSub").textContent = "";
    view.onclick = null; view.onsubmit = null;
    view.innerHTML = `<div class="skeleton" style="height:240px"></div>`;
    const arg = { users: () => new URLSearchParams(route.sub ? { kind: route.sub } : {}), bookings: () => route.sub, cars: () => new URLSearchParams(route.sub ? { state: route.sub } : {}) }[tab]?.();
    ({ stats, users, cars, bookings, payments, reports, reviews, finance, audit, disputes, channels, analytics: () => Reports.render(view, "admin") })[tab](arg).catch((e) => (view.innerHTML = `<div class="empty card">${esc(e.message)}</div>`));
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("langchange", route);
  route();

  const searchBox = (phKey, extra = "") => `<form class="row" id="search" style="margin-bottom:12px">
    <input class="input" name="q" placeholder="${esc(t(phKey))}" aria-label="${esc(t(phKey))}" style="max-width:320px">${extra}<button class="btn btn-outline">${esc(t("common.search"))}</button></form>`;
  const onSearch = (fn) => $("#search").addEventListener("submit", (e) => { e.preventDefault(); fn(new URLSearchParams(formData(e.target))); });

  const A = (entity, title, extra = {}) => ({ scope: "admin", entity, title, ...extra });

  async function stats() {
    const s = await api("/api/admin/stats");
    $("#viewSub").textContent = t("admin.real_data");
    const total = Object.values(s.bookings).reduce((a, x) => a + x, 0);
    view.innerHTML = `<p class="drill-note">${icon("info", 14)} ${esc(t("drill.note"))}</p><div class="stats">
        ${stat(t("admin.users_total"), s.users.total, esc(t("admin.users_sub", { a: s.users.owners, b: s.users.renters, c: s.users.new_week })), A("users", t("admin.users_total"), { kind: "all" }), t("hint.users_total"))}
        ${stat(t("admin.active_30"), s.users.active_30d, esc(t("admin.active_sub")), A("users", t("admin.active_30"), { kind: "active" }), t("hint.active_30"))}
        ${stat(t("admin.cars_active"), s.cars.active, esc(t("admin.cars_sub", { n: s.cars.total, h: s.cars.hidden })), A("cars", t("admin.cars_active"), { state: "active" }), t("hint.cars_active"))}
        ${stat(t("admin.bookings_total"), total, esc(t("admin.pending_n", { n: s.bookings.pending })), A("bookings", t("admin.bookings_total")), t("hint.bookings_total"))}
        ${stat(t("admin.gmv"), money(s.revenue_total), esc(t("admin.gmv_sub")), A("bookings", t("admin.gmv"), { status: "done" }), t("hint.gmv"))}
        ${stat(t("admin.commission_income"), money(s.commission_total), esc(t("admin.commission_rate", { pct: s.commission_bps / 100 })), A("bookings", t("admin.commission_income"), { status: "done" }), t("hint.commission"))}
        ${stat(t("admin.reviews_total"), s.reviews.cnt, s.reviews.avg ? `★ ${s.reviews.avg}` : "", A("reviews", t("admin.reviews_total")), t("hint.reviews"))}
        ${stat(t("admin.blocked"), s.users.blocked, esc(t("admin.blocked_sub")), A("users", t("admin.blocked"), { kind: "blocked" }), t("hint.blocked"))}
        ${stat(t("admin.reports_new"), s.reports_new, esc(s.reports_new ? t("dash.open") : t("owner.all_done")), "#reports", t("hint.reports_new"))}
        ${stat(t("admin.paid_online"), money(s.paid_online), s.refunds_pending ? esc(t("admin.refunds_n", { n: s.refunds_pending })) : "", A("payments", t("admin.paid_online")), t("hint.paid_online"))}
      </div>
      <div class="two-col">
        <div class="card card-pad"><h3>${esc(t("admin.monthly"))}</h3>${revenueChart(s.monthly, { drill: (m) => A("bookings", `${t("admin.monthly")}: ${m.month}`, { status: "done", month: m.month }) })}</div>
        <div class="card card-pad"><h3>${esc(t("owner.statuses"))}</h3>${statusBars(s.bookings, (k) => A("bookings", `${t("owner.statuses")}: ${t("status." + k)}`, { status: k }))}</div>
      </div>
      <div class="two-col" style="margin-top:18px">
        <div class="card card-pad"><h3>${esc(t("admin.by_city"))}</h3>${hbars(s.by_city, { label: (r) => r.city, value: (r) => r.bookings, drill: (r) => A("bookings", `${t("admin.by_city")}: ${r.city}`, { city: r.city }) })}</div>
        <div class="card card-pad"><h3>${esc(t("admin.by_body"))}</h3>${hbars(s.by_body, { label: (r) => t("body." + r.body_type), value: (r) => r.bookings, drill: (r) => A("bookings", `${t("admin.by_body")}: ${t("body." + r.body_type)}`, { body: r.body_type }) })}
          <h3 style="margin-top:18px">${esc(t("admin.growth"))}</h3>${hbars(s.user_growth.slice(-6), { label: (r) => r.month, value: (r) => r.count, color: "var(--success)", drill: (r) => A("users", `${t("admin.growth")}: ${r.month}`, { month: r.month }) })}</div>
      </div>`;
  }

  async function users(p = new URLSearchParams()) {
    const { items, counts } = await api("/api/admin/users?" + p);
    const kind = p.get("kind") || "";
    const KINDS = [["", "common.all"], ["renters", "admin.renters"], ["owners", "admin.owners"], ["active", "admin.active_30"], ["new", "admin.new_week"],
      ["blocked", "admin.blocked"], ["admins", "admin.admins"]];
    view.innerHTML = `<div class="stats mini-stats">${KINDS.map(([k, key]) => `<a class="card stat stat-link ${k === kind ? "on" : ""}" href="#users${k ? "/" + k : ""}" title="${esc(t("uk.h_" + (k || "all")))}">
        <div class="k">${esc(t(key))}</div><div class="v">${numFmt().format(counts[k || "all"] || 0)}</div><div class="stat-hint">${esc(t("uk.h_" + (k || "all")))}</div></a>`).join("")}</div>`
      + searchBox("admin.search_users", `<input type="hidden" name="kind" value="${esc(kind)}">`) +
      `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.user"))}</th><th>${esc(t("col.role"))}</th><th>${esc(t("col.activity"))}</th>
        <th>${esc(t("col.registered"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
      ${items.map((u) => `<tr><td data-label="#">${u.id}</td><td data-label="${esc(t("col.user"))}"><a href="#user/${u.id}"><b>${esc(u.full_name)}</b></a><div class="small muted">${esc(u.email)} · ${esc(u.phone ? fmtPhone(u.phone) : "")}</div></td>
        <td data-label="${esc(t("col.role"))}">${esc(t("role." + u.role))}</td>
        <td data-label="${esc(t("col.activity"))}" class="small">${esc(t("admin.activity", { c: u.cars, b: u.bookings }))}</td>
        <td data-label="${esc(t("col.registered"))}" class="small">${fmtDate(u.created_at)}</td>
        <td data-label="${esc(t("col.status"))}">${u.is_active ? `<span class="tag tag-ok">${esc(t("admin.active"))}</span>` : `<span class="tag tag-bad">${esc(t("admin.blocked_one"))}</span>`}</td>
        <td><a class="btn btn-sm" href="#user/${u.id}">${esc(t("uadm.manage"))}</a></td></tr>`).join("")}
      </tbody></table></div>`;
    for (const [k, v] of p) { const el = $(`#search [name=${k}]`); if (el) el.value = v; }
    onSearch(users);
    if (!items.length) view.insertAdjacentHTML("beforeend", `<div class="empty card">${esc(t("admin.no_users"))}</div>`);
  }

  // ---------------- Bitta foydalanuvchi: to'liq ma'lumot va boshqaruv ----------------
  function reasonModal({ title, label, required = true, danger = false, okText, extra = "" }) {
    return new Promise((resolve) => {
      const bg = document.createElement("div"); bg.className = "modal-bg";
      bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true" novalidate><h3>${esc(title)}</h3>
        <div class="field"><label for="rmR">${esc(label)}</label><textarea class="input" id="rmR" name="reason" maxlength="1000" ${required ? "required minlength=\"3\"" : ""}></textarea></div>
        ${extra}
        <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button>
          <button class="btn ${danger ? "btn-danger" : ""}">${esc(okText || t("common.save"))}</button></div></form>`;
      document.body.append(bg);
      $("#rmR", bg).focus();
      const done = (v) => { bg.remove(); resolve(v); };
      bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) done(null); });
      $("form", bg).addEventListener("submit", (e) => {
        e.preventDefault();
        const f = formData(e.target);
        if (required && (f.reason || "").trim().length < 3) { toast(t("uadm.reason_need"), "error"); return; }
        done({ ...f, reason: (f.reason || "").trim(), full_refund: !!$("[name=full_refund]", bg)?.checked });
      });
    });
  }

  async function userPage(id) {
    const d = await api(`/api/admin/users/${id}`);
    const u = d.user, R = d.renter, O = d.owner;
    $("#viewTitle").textContent = u.full_name;
    $("#viewSub").innerHTML = `<a href="#users">← ${esc(t("admin.users"))}</a>`;
    const tabs = [["overview", "uadm.t_overview"], ["bookings", "admin.bookings", d.bookings.length], ["cars", "uadm.t_cars", d.cars.length],
      ["payments", "admin.payments", d.payments.length], ["complaints", "uadm.t_complaints", d.counts.complaints_new || ""],
      ["disputes", "admin.disputes", d.counts.disputes_open || ""], ["reviews", "admin.reviews", d.reviews.length],
      ["security", "uadm.t_security"], ["history", "uadm.t_history"]];
    let cur = userPage.tab && userPage.id === id ? userPage.tab : "overview";
    userPage.id = id;
    const verified = (on, key) => `<span class="tag ${on ? "tag-ok" : "tag-hidden"}">${icon(on ? "check" : "close", 12)} ${esc(t(key))}</span>`;
    const blocked = !u.is_active, isAdmin = u.role === "admin";
    const btn = (act, key, cls = "btn-outline", ico = "") => `<button class="btn btn-sm ${cls}" data-act="${act}">${ico ? icon(ico, 16) + " " : ""}${esc(t(key))}</button>`;
    view.innerHTML = `<div class="card card-pad uadm-head">
        <div class="uadm-id">${avatarHtml(u, "xl")}
          <div><h2>${esc(u.full_name)} <span class="muted small">#${u.id}</span></h2>
            <div class="row" style="gap:6px;flex-wrap:wrap">${blocked ? `<span class="tag tag-bad">${esc(t("admin.blocked_one"))}</span>` : `<span class="tag tag-ok">${esc(t("admin.active"))}</span>`}
              <span class="tag tag-info">${esc(t("role." + u.role))}</span>${O ? `<span class="tag tag-info">${esc(t("uadm.is_owner"))}</span>` : ""}${R.trips ? `<span class="tag tag-info">${esc(t("uadm.is_renter"))}</span>` : ""}
              ${verified(u.email_verified, "uadm.email_ok")} ${verified(u.phone_verified, "uadm.phone_ok")}</div>
            <div class="small muted" style="margin-top:6px">${icon("mail", 14)} ${esc(u.email)} ${u.phone ? `· ${icon("phone", 14)} ${esc(fmtPhone(u.phone))}` : ""}
              ${u.region ? `· ${esc(Places.label(u.region, u.district))}` : ""}</div>
            <div class="small muted">${esc(t("uadm.registered", { d: fmtDate(u.created_at) }))} · ${esc(u.last_seen ? t("uadm.last_seen", { d: timeAgo(u.last_seen) }) : t("uadm.never_seen"))}${u.deleted_at ? ` · <b>${esc(t("uadm.deleted"))}</b>` : ""}</div></div></div>
        ${isAdmin ? "" : `<div class="uadm-actions">
          ${blocked ? btn("unblock", "admin.unblock", "btn-ok", "check") : btn("block", "admin.block", "btn-danger", "lock")}
          ${btn("warn", "uadm.warn", "btn-outline", "flag")} ${btn("note", "uadm.note", "btn-outline", "log")}
          <a class="btn btn-sm btn-outline" href="/messages.html?user=${u.id}">${icon("chat", 16)} ${esc(t("uadm.message"))}</a>
          ${btn("logout_all", "uadm.logout_all", "btn-outline", "logout")}
          ${btn(u.email_verified ? "unverify_email" : "verify_email", u.email_verified ? "uadm.unverify_email" : "uadm.verify_email")}
          ${btn(u.phone_verified ? "unverify_phone" : "verify_phone", u.phone_verified ? "uadm.unverify_phone" : "uadm.verify_phone")}
          ${O ? btn(O.cars_active ? "hide_cars" : "restore_cars", O.cars_active ? "uadm.hide_cars" : "uadm.restore_cars", "btn-outline", "car") : ""}</div>`}
      </div>
      ${d.flags.length ? `<div class="uadm-flags">${d.flags.map((f) => `<span class="uflag f-${f.code}">${icon("flag", 14)} ${esc(t("uadm.f_" + f.code, { n: f.code === "fee_owed" ? money(f.n) : f.n }))}</span>`).join("")}</div>` : ""}
      <div class="stats">
        ${stat(t("uadm.r_trips"), R.trips, esc(t("uadm.r_trips_sub", { sum: money(R.spent), d: R.days })), R.trips ? A("bookings", `${u.full_name}: ${t("uadm.r_trips")}`, { renter_id: u.id, status: "done" }) : "", t("uadm.h_r_trips"))}
        ${stat(t("uadm.r_cancel"), R.statuses.cancelled + R.statuses.rejected, esc(t("uadm.r_cancel_sub", { c: R.statuses.cancelled, r: R.statuses.rejected })), R.statuses.cancelled + R.statuses.rejected ? A("bookings", `${u.full_name}: ${t("uadm.r_cancel")}`, { renter_id: u.id, status: "cancelled,rejected" }) : "", t("uadm.h_r_cancel"))}
        ${stat(t("uadm.r_rating"), R.rating ? `★ ${R.rating}` : "—", esc(t("car.reviews_n", { n: R.rating_cnt })), "", t("uadm.h_r_rating"))}
        ${O ? `${stat(t("uadm.o_cars"), `${O.cars_active} / ${O.cars_total}`, esc(t("uadm.o_cars_sub")), A("cars", `${u.full_name}: ${t("uadm.o_cars")}`, { owner_id: u.id }), t("uadm.h_o_cars"))}
          ${stat(t("uadm.o_trips"), O.trips, esc(t("uadm.o_trips_sub", { sum: money(O.gross) })), O.trips ? A("bookings", `${u.full_name}: ${t("uadm.o_trips")}`, { owner_id: u.id, status: "done" }) : "", t("uadm.h_o_trips"))}
          ${stat(t("uadm.o_payout"), money(O.payout), esc(t("uadm.o_payout_sub", { fee: money(O.commission) })), O.trips ? A("bookings", `${u.full_name}: ${t("uadm.o_payout")}`, { owner_id: u.id, status: "done" }) : "", t("uadm.h_o_payout"))}
          ${stat(t("earn.balance"), money(O.balance.balance), esc(t("uadm.o_balance_sub", { out: money(O.balance.paid_out), req: money(O.balance.requested) })), A("payouts", `${u.full_name}: ${t("earn.paid_out")}`, { owner_id: u.id }), t("uadm.h_o_balance"))}
          ${stat(t("earn.fee_debt"), O.balance.fee_owed ? money(O.balance.fee_owed) : "—", esc(t("uadm.o_fee_sub")), O.balance.fee_owed ? "#payments" : "", t("uadm.h_o_fee"))}
          ${stat(t("uadm.o_rating"), O.rating ? `★ ${O.rating}` : "—", esc(t("car.reviews_n", { n: O.rating_cnt })), "", t("uadm.h_o_rating"))}` : ""}
        ${stat(t("uadm.t_complaints"), d.counts.complaints, esc(t("uadm.complaints_sub", { n: d.counts.complaints_new })), "", t("uadm.h_complaints"))}
        ${stat(t("uadm.warnings"), d.counts.warnings, esc(t("uadm.warnings_sub")), "", t("uadm.h_warnings"))}
      </div>
      <div class="chips uadm-tabs" role="tablist">${tabs.map(([k, key, n]) => `<button type="button" class="chip-btn ${k === cur ? "on" : ""}" data-ut="${k}" role="tab">${esc(t(key))}${n ? ` <span class="cnt">${n}</span>` : ""}</button>`).join("")}</div>
      <div id="uTab"></div>`;

    const bookingTable = (list) => list.length ? `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("uadm.role_in"))}</th>
        <th>${esc(t("col.dates"))}</th><th>${esc(t("booking.total"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
        ${list.map((b) => { const asRenter = b.renter_id === u.id; return `<tr><td data-label="#">${b.id}</td>
          <td data-label="${esc(t("col.car"))}"><div class="row" style="gap:10px;flex-wrap:nowrap"><span class="mini-thumb">${carImage(b)}</span><div><a href="/car.html?id=${b.car_id}">${esc(b.brand)} ${esc(b.model)} ${b.year}</a>
            <div class="small muted">${esc(asRenter ? t("col.owner") : t("booking.renter"))}: <a href="#user/${asRenter ? b.owner_id : b.renter_id}">${esc(asRenter ? b.owner_name : b.renter_name)}</a></div></div></div></td>
          <td data-label="${esc(t("uadm.role_in"))}"><span class="tag ${asRenter ? "tag-info" : "tag-pending"}">${esc(t(asRenter ? "notif.for_renter" : "notif.for_owner"))}</span></td>
          <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)}</td>
          <td data-label="${esc(t("booking.total"))}">${money(b.total_price)}<div class="small muted">${esc(t("pay.st_" + b.payment_status))}</div></td>
          <td data-label="${esc(t("col.status"))}">${statusTag(b.status)}</td>
          <td>${["pending", "approved"].includes(b.status) ? `<button class="btn btn-sm btn-danger" data-bcancel="${b.id}" data-paid="${b.payment_status === "paid" ? 1 : 0}">${esc(t("uadm.cancel_booking"))}</button>` : ""}</td></tr>`; }).join("")}
        </tbody></table></div>` : `<div class="empty card">${esc(t("dash.no_bookings"))}</div>`;

    const complaintItem = (r, against) => `<div class="list-item" style="grid-template-columns:auto 1fr auto">
        ${r.cover ? `<span class="mini-thumb">${carImage({ cover: r.cover, brand: "", model: "" })}</span>` : `<span class="avatar ico">${icon("flag", 16)}</span>`}
        <div><div class="row" style="gap:6px"><span class="tag tag-bad">${esc(t("report.reason_" + r.reason))}</span><span class="tag tag-info">${esc(t("report.type_" + r.target_type))}</span>
          <span class="tag ${r.status === "new" ? "tag-pending" : "tag-hidden"}">${esc(t("report.st_" + r.status))}</span>
          <span class="small muted">${against ? `${esc(t("uadm.from"))}: <a href="#user/${r.reporter_id}">${esc(r.reporter_name)}</a>` : `→ ${r.target_user_id ? `<a href="#user/${r.target_user_id}">${esc(r.target_user_name || "")}</a>` : ""}`} · ${fmtDate(r.created_at)}</span></div>
          <div style="margin-top:4px">${r.link ? `<a href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r.target_label)}</a>` : esc(r.target_label)}</div>
          ${r.comment ? `<div class="small muted">“${esc(r.comment)}”</div>` : ""}</div>
        <div class="actions">${r.status === "new" ? `<a class="btn btn-sm btn-outline" href="#reports">${esc(t("uadm.to_reports"))}</a>` : ""}</div></div>`;

    const tab = {
      overview: () => `<div class="two-col">
          <div class="card card-pad"><h3>${icon("log", 18)} ${esc(t("uadm.notes"))}</h3>
            <form id="noteForm" class="row" style="gap:8px;margin-bottom:12px;flex-wrap:nowrap"><input class="input" name="reason" maxlength="1000" placeholder="${esc(t("uadm.note_ph"))}"><button class="btn btn-sm">${esc(t("common.save"))}</button></form>
            ${d.notes.length ? `<div class="timeline">${d.notes.map((n) => `<div class="tl n-${n.kind}"><span class="tag ${n.kind === "warning" ? "tag-pending" : n.kind === "block" ? "tag-bad" : n.kind === "unblock" ? "tag-ok" : "tag-hidden"}">${esc(t("uadm.k_" + n.kind))}</span>
              <div>${esc(n.body)}</div><div class="small muted">${esc(n.author_name || "—")} · ${esc(n.created_at)}</div></div>`).join("")}</div>` : `<p class="muted small">${esc(t("uadm.no_notes"))}</p>`}</div>
          <div class="card card-pad"><h3>${icon("bulb", 18)} ${esc(t("uadm.guide"))}</h3><ul class="uadm-guide">${["g1", "g2", "g3", "g4", "g5"].map((k) => `<li>${esc(t("uadm." + k))}</li>`).join("")}</ul>
            ${O ? `<h3 style="margin-top:16px">${esc(t("owner.statuses"))}</h3>${statusBars(O.statuses, (k) => A("bookings", `${u.full_name} (${t("notif.for_owner")}): ${t("status." + k)}`, { owner_id: u.id, status: k }))}` : ""}
            <h3 style="margin-top:16px">${esc(t("uadm.as_renter"))}</h3>${statusBars(R.statuses, (k) => A("bookings", `${u.full_name} (${t("notif.for_renter")}): ${t("status." + k)}`, { renter_id: u.id, status: k }))}</div>
        </div>`,
      bookings: () => bookingTable(d.bookings),
      cars: () => d.cars.length ? `<div class="uadm-cars">${d.cars.map((c) => `<div class="card uadm-car"><a class="car-thumb" href="/car.html?id=${c.id}" target="_blank" rel="noopener">${carImage(c)}</a>
          <div class="card-pad"><b>${esc(c.brand)} ${esc(c.model)} ${c.year}</b><div class="small muted">${esc(Places.label(c.city, c.district))} · ${money(c.price_per_day)} ${esc(t("car.per_day"))}</div>
            <div class="small">${esc(t("drill.trips_n", { n: c.trips }))} · ${esc(t("drill.views_n", { n: c.views }))}${c.rating ? ` · ★ ${c.rating}` : ""}</div>
            <div class="row" style="gap:6px;margin-top:8px;justify-content:space-between">${!c.is_approved ? `<span class="tag tag-bad">${esc(t("car.state_moderated"))}</span>` : c.is_active ? `<span class="tag tag-ok">${esc(t("car.state_active"))}</span>` : `<span class="tag tag-hidden">${esc(t("car.state_hidden"))}</span>`}
              <span class="row" style="gap:6px"><button class="btn btn-sm btn-outline" ${drillAttr(A("bookings", `${c.brand} ${c.model} ${c.year}`, { car_id: c.id }))}>${esc(t("admin.bookings"))}</button>
              <button class="btn btn-sm btn-outline" data-car="${c.id}" data-approve="${c.is_approved ? 0 : 1}">${esc(t(c.is_approved ? "admin.hide" : "admin.restore"))}</button></span></div></div></div>`).join("")}</div>`
        : `<div class="empty card">${esc(t("uadm.no_cars"))}</div>`,
      payments: () => d.payments.length ? `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("uadm.role_in"))}</th><th>${esc(t("pay.method"))}</th>
          <th>${esc(t("pay.amount"))}</th><th>${esc(t("col.status"))}</th><th>${esc(t("col.time"))}</th><th></th></tr></thead><tbody>
          ${d.payments.map((p) => `<tr><td data-label="#">${p.id}</td><td data-label="${esc(t("col.car"))}">${esc(p.brand)} ${esc(p.model)} <span class="muted small">${esc(t("drill.booking_n", { n: p.booking_id }))}</span></td>
            <td data-label="${esc(t("uadm.role_in"))}">${esc(t(p.user_id === u.id ? "drill.payer" : "uadm.receiver"))}</td>
            <td data-label="${esc(t("pay.method"))}">${esc(p.provider === "test" ? t("pay.test_name") : p.provider === "click" ? "Click" : "Payme")}</td>
            <td data-label="${esc(t("pay.amount"))}">${money(p.amount)}${p.refund_amount ? `<div class="small" style="color:var(--success-ink)">↩ ${money(p.refund_amount)}</div>` : ""}</td>
            <td data-label="${esc(t("col.status"))}">${payStatusTag(p.status)}</td><td data-label="${esc(t("col.time"))}" class="small">${esc(p.paid_at || p.created_at)}</td>
            <td><a class="btn btn-sm btn-outline" href="/receipt.html?payment=${p.id}" target="_blank" rel="noopener">${esc(t("pay.receipt"))}</a></td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty card">${esc(t("admin.no_payments"))}</div>`,
      complaints: () => `<h3>${esc(t("uadm.c_against"))}</h3><div class="card" style="margin-bottom:18px">${d.complaints_against.length ? d.complaints_against.map((r) => complaintItem(r, true)).join("") : `<div class="empty">${esc(t("report.none"))}</div>`}</div>
        <h3>${esc(t("uadm.c_by"))}</h3><div class="card">${d.complaints_by.length ? d.complaints_by.map((r) => complaintItem(r, false)).join("") : `<div class="empty">${esc(t("report.none"))}</div>`}</div>`,
      disputes: () => d.disputes.length ? `<div class="card">${d.disputes.map((x) => `<div class="list-item" style="grid-template-columns:1fr auto">
          <div><div class="row" style="gap:6px"><b>${esc(t("disp.t_" + x.type))}</b><span class="tag ${["open", "in_review"].includes(x.status) ? "tag-pending" : x.status === "resolved" ? "tag-ok" : "tag-hidden"}">${esc(t("disp.st_" + x.status))}</span>
            ${x.outcome ? `<span class="tag tag-info">${esc(t("disp.o_" + x.outcome))}</span>` : ""}</div>
            <div class="small muted">${esc(t("drill.booking_n", { n: x.booking_id }))} · ${esc(x.brand)} ${esc(x.model)} · ${fmtDate(x.created_at)}</div>
            <div class="small"><a href="#user/${x.opened_by}">${esc(x.opener_name)}</a> → <a href="#user/${x.against_id}">${esc(x.against_name)}</a>${x.amount ? ` · ${money(x.amount)}` : ""}</div></div>
          <div class="actions"><a class="btn btn-sm btn-outline" href="#disputes">${esc(t("uadm.to_disputes"))}</a></div></div>`).join("")}</div>`
        : `<div class="empty card">${esc(t("disp.none"))}</div>`,
      reviews: () => d.reviews.length ? `<div class="card">${d.reviews.map((r) => `<div class="list-item" style="grid-template-columns:1fr auto">
          <div><div class="row" style="gap:8px"><span class="stars">${stars(r.rating)}</span><span class="tag ${r.author_id === u.id ? "tag-info" : "tag-pending"}">${esc(t(r.author_id === u.id ? "uadm.rev_by" : "uadm.rev_about"))}</span>
            <span class="small muted">${r.author_id === u.id ? "" : `<a href="#user/${r.author_id}">${esc(r.author_name)}</a> · `}<a href="/car.html?id=${r.car_id}">${esc(r.brand)} ${esc(r.model)}</a> · ${fmtDate(r.created_at)}</span></div>
            ${r.comment ? `<div style="margin-top:4px">${esc(r.comment)}</div>` : ""}</div>
          <div class="actions"><button class="btn btn-sm btn-danger" data-rev="${r.id}">${esc(t("common.delete"))}</button></div></div>`).join("")}</div>`
        : `<div class="empty card">${esc(t("car.reviews_empty"))}</div>`,
      security: () => `<div class="card card-pad"><h3>${esc(t("uadm.sessions"))}</h3>
          ${d.sessions.length ? d.sessions.map((x) => `<div class="sum-row"><span>${esc((x.user_agent || "—").slice(0, 80))}<div class="small muted">${esc(x.ip || "")}</div></span><span class="small muted">${timeAgo(x.last_seen)}</span></div>`).join("")
            : `<p class="muted small">${esc(t("uadm.no_sessions"))}</p>`}
          ${d.sessions.length && !isAdmin ? `<button class="btn btn-sm btn-outline" data-act="logout_all" style="margin-top:12px">${icon("logout", 16)} ${esc(t("uadm.logout_all"))}</button>` : ""}
          <p class="small muted" style="margin-top:12px">${esc(t("uadm.sec_hint"))}</p></div>`,
      history: () => d.history.length ? `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.time"))}</th><th>${esc(t("col.actor"))}</th><th>${esc(t("col.action"))}</th><th>${esc(t("col.target"))}</th></tr></thead><tbody>
          ${d.history.map((a) => `<tr><td data-label="${esc(t("col.time"))}" class="small">${esc(a.created_at)}</td><td data-label="${esc(t("col.actor"))}">${esc(a.actor_name || "—")}</td>
            <td data-label="${esc(t("col.action"))}">${esc(t("audit." + a.action) || a.action)}</td><td data-label="${esc(t("col.target"))}" class="small">${esc(a.target_type || "")} ${a.target_id ?? ""} <span class="muted">${esc(a.details || "")}</span></td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty card">${esc(t("admin.audit_empty"))}</div>`,
    };
    const showTab = (k) => { cur = userPage.tab = k; $$("[data-ut]").forEach((b) => b.classList.toggle("on", b.dataset.ut === k)); $("#uTab").innerHTML = tab[k](); };
    showTab(cur);

    const reload = () => userPage(id);
    view.onclick = async (e) => {
      const ut = e.target.closest("[data-ut]"); if (ut) return showTab(ut.dataset.ut);
      const act = e.target.closest("[data-act]"), bc = e.target.closest("[data-bcancel]"), car = e.target.closest("[data-approve]"), rev = e.target.closest("[data-rev]");
      try {
        if (act) {
          const a = act.dataset.act;
          let body = { action: a };
          if (["block", "warn", "note", "hide_cars"].includes(a)) {
            const r = await reasonModal({ title: t("uadm.m_" + a, { name: u.full_name }), label: t("uadm.l_" + a), required: a !== "hide_cars", danger: a === "block" || a === "hide_cars",
              okText: t("uadm.ok_" + a) });
            if (!r) return;
            body.reason = r.reason || null;
          } else if (a === "unblock" || a === "restore_cars") {
            const r = await reasonModal({ title: t("uadm.m_" + a, { name: u.full_name }), label: t("uadm.l_optional"), required: false, okText: t("common.yes") });
            if (!r) return;
            body.reason = r.reason || null;
          } else if (!(await confirmBox(t("uadm.c_" + a, { name: u.full_name }), t("common.yes")))) return;
          await api(`/api/admin/users/${id}/action`, { method: "POST", body });
          toast(t("common.done"), "ok"); reload();
        }
        if (bc) {
          const r = await reasonModal({ title: t("uadm.cancel_t", { n: bc.dataset.bcancel }), label: t("uadm.cancel_reason"), danger: true, okText: t("uadm.cancel_booking"),
            extra: bc.dataset.paid === "1" ? `<label class="check"><input type="checkbox" name="full_refund"><span>${esc(t("uadm.full_refund"))}</span></label><p class="small muted">${esc(t("uadm.refund_hint"))}</p>` : "" });
          if (!r) return;
          await api(`/api/admin/bookings/${bc.dataset.bcancel}/cancel`, { method: "POST", body: { reason: r.reason, full_refund: r.full_refund } });
          toast(t("common.done"), "ok"); reload();
        }
        if (car) { await api(`/api/admin/cars/${car.dataset.car}`, { method: "PATCH", body: { is_approved: car.dataset.approve === "1" } }); toast(t("common.done"), "ok"); reload(); }
        if (rev && await confirmBox(t("admin.delete_review_confirm"), t("common.delete"), true)) { await api(`/api/admin/reviews/${rev.dataset.rev}`, { method: "DELETE" }); toast(t("common.done"), "ok"); reload(); }
      } catch (err) { toast(err.message, "error"); }
    };
    view.onsubmit = async (e) => {
      if (e.target.id !== "noteForm") return;
      e.preventDefault();
      const v = e.target.reason.value.trim();
      if (v.length < 3) { toast(t("uadm.reason_need"), "error"); return; }
      try { await api(`/api/admin/users/${id}/action`, { method: "POST", body: { action: "note", reason: v } }); toast(t("common.saved"), "ok"); userPage.tab = "overview"; reload(); }
      catch (err) { toast(err.message, "error"); }
    };
  }

  async function cars(p = new URLSearchParams()) {
    const { items } = await api("/api/admin/cars?" + p);
    view.innerHTML = searchBox("admin.search_cars") + `<div class="card table-wrap"><table class="table responsive"><thead><tr>
      <th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("col.owner"))}</th><th>${esc(t("col.price"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
      ${items.map((c) => `<tr><td data-label="#">${c.id}</td><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${c.id}"><b>${esc(c.brand)} ${esc(c.model)} ${c.year}</b></a><div class="small muted">${esc(Places.label(c.city, c.district))} · ${fmtDate(c.created_at)}</div></td>
        <td data-label="${esc(t("col.owner"))}"><a href="#user/${c.owner_id}">${esc(c.owner_name)}</a></td><td data-label="${esc(t("col.price"))}">${money(c.price_per_day)}</td>
        <td data-label="${esc(t("col.status"))}">${!c.is_approved ? `<span class="tag tag-bad">${esc(t("car.state_moderated"))}</span>` : c.is_active ? `<span class="tag tag-ok">${esc(t("car.state_active"))}</span>` : `<span class="tag tag-hidden">${esc(t("car.state_hidden"))}</span>`}</td>
        <td><div class="row" style="gap:6px;flex-wrap:nowrap"><button class="btn btn-sm btn-outline" data-car="${c.id}" data-approve="${c.is_approved ? 0 : 1}">${esc(t(c.is_approved ? "admin.hide" : "admin.restore"))}</button>
          <button class="btn btn-sm btn-danger" data-del="${c.id}">${esc(t("common.delete"))}</button></div></td></tr>`).join("")}
      </tbody></table></div>`;
    if (p.get("q")) $("#search [name=q]").value = p.get("q");
    onSearch(cars);
    view.onclick = async (e) => {
      const a = e.target.closest("[data-approve]"), d = e.target.closest("[data-del]");
      try {
        if (a) { await api(`/api/admin/cars/${a.dataset.car}`, { method: "PATCH", body: { is_approved: a.dataset.approve === "1" } }); toast(t("common.done"), "ok"); cars(p); }
        if (d && await confirmBox(t("admin.delete_car_confirm"), t("common.delete"), true)) { await api(`/api/cars/${d.dataset.del}`, { method: "DELETE" }); toast(t("common.done"), "ok"); cars(p); }
      } catch (err) { toast(err.message, "error"); }
    };
  }

  async function bookings(status = "") {
    const { items } = await api("/api/admin/bookings" + (status ? "?status=" + status : ""));
    const opts = ["", "pending", "approved", "completed", "rejected", "cancelled"];
    view.innerHTML = `<div class="row" style="gap:6px;margin-bottom:12px">${opts.map((k) => `<button class="btn btn-sm ${k === status ? "" : "btn-outline"}" data-st="${k}">${esc(k ? t("status." + k) : t("common.all"))}</button>`).join("")}</div>
      <div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("booking.renter"))}</th><th>${esc(t("col.owner"))}</th>
        <th>${esc(t("col.dates"))}</th><th>${esc(t("booking.total"))}</th><th>${esc(t("col.commission"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
      ${items.map((b) => `<tr><td data-label="#">${b.id}</td><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${b.car_id}">${esc(b.brand)} ${esc(b.model)}</a></td>
        <td data-label="${esc(t("booking.renter"))}"><a href="#user/${b.renter_id}">${esc(b.renter_name)}</a></td><td data-label="${esc(t("col.owner"))}"><a href="#user/${b.owner_id}">${esc(b.owner_name)}</a></td>
        <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)}</td>
        <td data-label="${esc(t("booking.total"))}">${money(b.total_price)}</td><td data-label="${esc(t("col.commission"))}">${money(b.commission)} <span class="muted small">(${b.commission_bps / 100}%)</span></td>
        <td data-label="${esc(t("col.status"))}">${statusTag(b.status)}</td>
        <td>${["pending", "approved"].includes(b.status) ? `<button class="btn btn-sm btn-outline" data-bcancel="${b.id}" data-paid="${b.payment_status === "paid" ? 1 : 0}">${esc(t("uadm.cancel_booking"))}</button>` : ""}</td></tr>`).join("")}
      </tbody></table>${items.length ? "" : `<div class="empty">${esc(t("dash.no_bookings"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const b = e.target.closest("[data-st]"); if (b) return bookings(b.dataset.st);
      const bc = e.target.closest("[data-bcancel]"); if (!bc) return;
      const r = await reasonModal({ title: t("uadm.cancel_t", { n: bc.dataset.bcancel }), label: t("uadm.cancel_reason"), danger: true, okText: t("uadm.cancel_booking"),
        extra: bc.dataset.paid === "1" ? `<label class="check"><input type="checkbox" name="full_refund"><span>${esc(t("uadm.full_refund"))}</span></label><p class="small muted">${esc(t("uadm.refund_hint"))}</p>` : "" });
      if (!r) return;
      try { await api(`/api/admin/bookings/${bc.dataset.bcancel}/cancel`, { method: "POST", body: { reason: r.reason, full_refund: r.full_refund } }); toast(t("common.done"), "ok"); bookings(status); }
      catch (err) { toast(err.message, "error"); }
    };
  }

  async function reviews() {
    const { items } = await api("/api/admin/reviews");
    view.innerHTML = `<div class="card">${items.length ? items.map((r) => `<div class="list-item" style="grid-template-columns:1fr auto">
        <div><div class="row" style="gap:8px"><span class="stars">${stars(r.rating)}</span><b><a href="#user/${r.author_id}">${esc(r.author)}</a></b>
          <span class="tag ${r.kind === "car" ? "tag-info" : "tag-pending"}">${esc(t("review.kind_" + r.kind))}</span>
          <span class="muted small">→ ${r.kind === "car" ? `<a href="/car.html?id=${r.car_id}">${esc(r.brand)} ${esc(r.model)}</a>` : esc(r.target)} · ${fmtDate(r.created_at)}</span></div>
        ${r.comment ? `<div style="margin-top:4px">${esc(r.comment)}</div>` : ""}</div>
        <div class="actions"><button class="btn btn-sm btn-danger" data-rev="${r.id}">${esc(t("common.delete"))}</button></div></div>`).join("") : `<div class="empty">${esc(t("car.reviews_empty"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const b = e.target.closest("[data-rev]"); if (!b) return;
      if (!(await confirmBox(t("admin.delete_review_confirm"), t("common.delete"), true))) return;
      try { await api(`/api/admin/reviews/${b.dataset.rev}`, { method: "DELETE" }); toast(t("common.done"), "ok"); reviews(); } catch (err) { toast(err.message, "error"); }
    };
  }

  async function finance() {
    const [s, cfg, rq] = await Promise.all([api("/api/admin/stats"), api("/api/admin/settings"), api("/api/admin/payout-requests")]);
    const pend = rq.items.filter((r) => r.status === "pending");
    const method = (r) => r.method === "card" ? `${t("payreq.m_card")} •••• ${esc(r.card_last4)}` : esc(t("payreq.m_" + r.method));
    const reqTag = (st) => `<span class="tag ${st === "paid" ? "tag-ok" : st === "pending" ? "tag-pending" : st === "rejected" ? "tag-bad" : "tag-hidden"}">${esc(t("payreq.st_" + st))}</span>`;
    view.innerHTML = `<div class="card" style="margin-bottom:18px"><div class="card-pad" style="padding-bottom:0">
        <h3>${icon("wallet", 18)} ${esc(t("payreq.admin_title"))} ${pend.length ? `<span class="tag tag-pending">${pend.length}</span>` : ""}</h3>
        <p class="small muted">${esc(t("payreq.admin_sub"))}</p></div>
        ${rq.items.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.owner"))}</th><th>${esc(t("pay.amount"))}</th>
          <th>${esc(t("payreq.method"))}</th><th>${esc(t("col.time"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
          ${rq.items.map((r) => `<tr><td data-label="${esc(t("col.owner"))}"><a href="#user/${r.owner_id}"><b>${esc(r.full_name)}</b></a><div class="small muted">${esc(r.phone ? fmtPhone(r.phone) : r.email)}</div></td>
            <td data-label="${esc(t("pay.amount"))}"><b>${money(r.amount)}</b>${r.balance !== undefined ? `<div class="small muted">${esc(t("earn.balance"))}: ${money(r.balance)}</div>` : ""}</td>
            <td data-label="${esc(t("payreq.method"))}">${method(r)}${r.note ? `<div class="small muted">${esc(r.note)}</div>` : ""}</td>
            <td data-label="${esc(t("col.time"))}" class="small">${fmtDate(r.created_at)}</td>
            <td data-label="${esc(t("col.status"))}">${reqTag(r.status)}${r.admin_note ? `<div class="small muted">${esc(r.admin_note)}</div>` : ""}</td>
            <td>${r.status === "pending" ? `<div class="row" style="gap:6px;flex-wrap:nowrap"><button class="btn btn-sm btn-ok" data-req-ok="${r.id}" data-sum="${r.amount}" data-name="${esc(r.full_name)}">✓ ${esc(t("payreq.approve"))}</button>
              <button class="btn btn-sm btn-danger" data-req-no="${r.id}">${esc(t("payreq.reject"))}</button>
              <a class="btn btn-sm btn-outline" href="/messages.html?user=${r.owner_id}" title="${esc(t("nav.messages"))}" aria-label="${esc(t("nav.messages"))}">${icon("chat", 16)}</a></div>` : ""}</td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">${esc(t("payreq.admin_empty"))}</div>`}</div>
      <div class="stats">
        ${stat(t("admin.gmv"), money(s.revenue_total), esc(t("admin.gmv_sub")))}
        ${stat(t("admin.commission_income"), money(s.commission_total), "")}
        ${stat(t("admin.owner_share"), money(s.revenue_total - s.commission_total), "")}
      </div>
      <div class="two-col">
        <div class="card card-pad"><h3>${esc(t("admin.monthly"))}</h3>${revenueChart(s.monthly)}
          <a class="btn btn-outline" style="margin-top:14px" href="/api/admin/finance.csv" download>${esc(t("admin.export_csv"))}</a></div>
        <form class="card card-pad" id="cfgForm"><h3>${esc(t("admin.commission_settings"))}</h3>
          <div class="field"><label for="pct">${esc(t("admin.commission_pct"))}</label><input class="input" type="number" id="pct" name="commission_percent" min="0" max="30" step="0.5" value="${cfg.commission_percent}"></div>
          <p class="small muted">${esc(t("admin.commission_hint"))}</p>
          <div class="notice info" style="margin-bottom:12px">${esc(t("admin.payment_note"))}</div>
          <button class="btn">${esc(t("common.save"))}</button></form>
      </div>`;
    $("#cfgForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("/api/admin/settings", { method: "PUT", body: { commission_percent: Number($("#pct").value) } }); toast(t("common.saved"), "ok"); finance(); }
      catch (err) { toast(err.message, "error"); }
    });
    view.onclick = async (e) => {
      const okB = e.target.closest("[data-req-ok]"), noB = e.target.closest("[data-req-no]");
      try {
        if (okB && await confirmBox(t("payreq.approve_confirm", { sum: money(okB.dataset.sum), name: okB.dataset.name }), t("payreq.approve"))) {
          await api(`/api/admin/payout-requests/${okB.dataset.reqOk}/approve`, { method: "POST", body: {} }); toast(t("common.done"), "ok"); finance();
        }
        if (noB) {
          const note = prompt(t("payreq.reject_reason"));
          if (note === null) return;
          await api(`/api/admin/payout-requests/${noB.dataset.reqNo}/reject`, { method: "POST", body: { note: note.trim() } }); toast(t("common.done"), "ok"); finance();
        }
      } catch (err) { toast(err.message, "error"); }
    };
  }

  async function payments() {
    const d = await api("/api/admin/payments");
    const prov = d.providers;
    const provName = (k) => (k === "test" ? t("pay.test_name") : k === "click" ? "Click" : "Payme");
    view.innerHTML = `<div class="row" style="gap:8px;margin-bottom:14px">${["click", "payme", "test"].map((k) =>
        `<span class="tag ${prov[k] ? "tag-ok" : "tag-hidden"}">${esc(provName(k))}: ${esc(t(prov[k] ? "pay.connected" : "pay.not_connected"))}</span>`).join("")}</div>
      <div class="card" style="margin-bottom:18px"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("admin.balances"))}</h3>
        <p class="small muted">${esc(t("admin.balances_sub"))}</p></div>
        ${d.balances.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.owner"))}</th><th>${esc(t("earn.online"))}</th>
          <th>${esc(t("earn.paid_out"))}</th><th>${esc(t("earn.balance"))}</th><th>${esc(t("earn.fee_debt"))}</th><th></th></tr></thead><tbody>
          ${d.balances.map((b) => `<tr><td data-label="${esc(t("col.owner"))}"><a href="#user/${b.id}"><b>${esc(b.full_name)}</b></a></td><td data-label="${esc(t("earn.online"))}">${money(b.earned_online)}</td>
            <td data-label="${esc(t("earn.paid_out"))}">${money(b.paid_out)}</td><td data-label="${esc(t("earn.balance"))}"><b>${money(b.balance)}</b></td>
            <td data-label="${esc(t("earn.fee_debt"))}">${b.fee_owed ? `<b style="color:var(--warning-ink)">${money(b.fee_owed)}</b>` : "—"}</td>
            <td><div class="row" style="gap:6px">${b.available > 0 ? `<button class="btn btn-sm" data-payout="${b.id}" data-max="${b.available}" data-name="${esc(b.full_name)}">${esc(t("admin.payout"))}</button>` : ""}
              ${b.fee_owed && b.balance - b.requested > 0 ? `<button class="btn btn-sm btn-outline" data-fee-net="${b.id}" data-sum="${Math.min(b.fee_owed, b.balance - b.requested)}" data-name="${esc(b.full_name)}">${esc(t("fee.net"))}</button>` : ""}
              ${b.fee_owed ? `<button class="btn btn-sm btn-outline" data-fee-cash="${b.id}" data-sum="${b.fee_owed}" data-name="${esc(b.full_name)}">${esc(t("fee.cash"))}</button>` : ""}</div></td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">${esc(t("admin.no_balances"))}</div>`}</div>
      <div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("booking.renter"))}</th>
        <th>${esc(t("pay.method"))}</th><th>${esc(t("pay.amount"))}</th><th>${esc(t("col.status"))}</th><th>${esc(t("col.time"))}</th><th></th></tr></thead><tbody>
        ${d.items.map((p) => `<tr><td data-label="#">${p.id}</td><td data-label="${esc(t("col.car"))}">${esc(p.brand)} ${esc(p.model)}</td>
          <td data-label="${esc(t("booking.renter"))}"><a href="#user/${p.user_id}">${esc(p.renter_name)}</a></td><td data-label="${esc(t("pay.method"))}">${esc(provName(p.provider))}</td>
          <td data-label="${esc(t("pay.amount"))}">${money(p.amount)}${p.refund_amount ? `<div class="small" style="color:var(--success-ink)">↩ ${money(p.refund_amount)}</div>` : ""}</td>
          <td data-label="${esc(t("col.status"))}">${payStatusTag(p.status)}</td>
          <td data-label="${esc(t("col.time"))}" class="small">${esc(p.paid_at || p.created_at)}</td>
          <td>${p.status === "refund_pending" ? `<button class="btn btn-sm btn-outline" data-refunded="${p.id}">${esc(t("admin.mark_refunded"))}</button>` : `<a class="btn btn-sm btn-outline" href="/receipt.html?payment=${p.id}">${esc(t("pay.receipt"))}</a>`}</td></tr>`).join("")}
      </tbody></table>${d.items.length ? "" : `<div class="empty">${esc(t("admin.no_payments"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const r = e.target.closest("[data-refunded]"), po = e.target.closest("[data-payout]");
      const net = e.target.closest("[data-fee-net]"), cash = e.target.closest("[data-fee-cash]");
      try {
        if (net && await confirmBox(t("fee.net_confirm", { sum: money(net.dataset.sum), name: net.dataset.name }), t("common.yes"))) {
          await api("/api/admin/fee-settlements", { method: "POST", body: { owner_id: +net.dataset.feeNet, amount: +net.dataset.sum, from_balance: true } });
          toast(t("common.done"), "ok"); payments();
        }
        if (cash && await confirmBox(t("fee.cash_confirm", { sum: money(cash.dataset.sum), name: cash.dataset.name }), t("common.yes"))) {
          await api("/api/admin/fee-settlements", { method: "POST", body: { owner_id: +cash.dataset.feeCash, amount: +cash.dataset.sum, from_balance: false } });
          toast(t("common.done"), "ok"); payments();
        }
        if (r && await confirmBox(t("admin.refund_confirm"), t("common.yes"))) { await api(`/api/admin/payments/${r.dataset.refunded}/refunded`, { method: "POST" }); toast(t("common.done"), "ok"); payments(); }
        if (po) payoutModal(+po.dataset.payout, +po.dataset.max, po.dataset.name);
      } catch (err) { toast(err.message, "error"); }
    };
  }

  function payoutModal(ownerId, max, name) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true"><h3>${esc(t("admin.payout"))}: ${esc(name)}</h3>
      <div class="field"><label for="poA">${esc(t("pay.amount"))}</label><input class="input" id="poA" type="text" data-money value="${fmtMoneyInput(max)}" required>
        <div class="hint">${esc(t("admin.payout_hint", { max: money(max) }))}</div></div>
      <div class="field"><label for="poN">${esc(t("block.note"))}</label><input class="input" id="poN" maxlength="200" placeholder="${esc(t("admin.payout_note_ph"))}"></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button><button class="btn">${esc(t("common.save"))}</button></div></form>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("/api/admin/payouts", { method: "POST", body: { owner_id: ownerId, amount: moneyVal($("#poA").value) || 0, note: $("#poN").value.trim() || null } }); bg.remove(); toast(t("common.done"), "ok"); payments(); }
      catch (err) { toast(err.message, "error"); }
    });
  }

  // ---------------- Nizolar ----------------
  async function disputes(status = "active") {
    $("#viewSub").textContent = t("disp.admin_sub");
    const d = await api("/api/admin/disputes?status=" + status);
    const filters = [["active", t("disp.filter_active")], ["resolved", t("disp.st_resolved")], ["rejected", t("disp.st_rejected")],
      ["cancelled", t("disp.st_cancelled")], ["all", t("common.all")]];
    view.innerHTML = `<div class="row" style="gap:6px;margin-bottom:12px">${filters.map(([k, l]) =>
        `<button class="btn btn-sm ${k === status ? "" : "btn-outline"}" data-f="${k}">${esc(l)}${k === "active" && (d.counts.open || d.counts.in_review) ? ` (${(d.counts.open || 0) + (d.counts.in_review || 0)})` : ""}</button>`).join("")}</div>
      ${d.items.length ? `<div class="disp-list">${d.items.map((x) => disputeCard(x, null, true)).join("")}</div>` : `<div class="empty card">${esc(t("disp.none"))}</div>`}`;
    view.onclick = async (e) => {
      const f = e.target.closest("[data-f]"), take = e.target.closest("[data-take]"), res = e.target.closest("[data-resolve]");
      try {
        if (f) disputes(f.dataset.f);
        if (take) { await api(`/api/admin/disputes/${take.dataset.take}/take`, { method: "POST" }); toast(t("common.done"), "ok"); disputes(status); }
        if (res) resolveModal(res.dataset, () => disputes(status));
      } catch (err) { toast(err.message, "error"); }
    };
  }

  function resolveModal(ds, reload) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true" novalidate><h3>${icon("shield", 20)} ${esc(t("disp.resolve_t"))}</h3>
      <div class="field"><label>${esc(t("disp.outcome"))}</label><div class="stack">${["favor_opener", "favor_other", "split", "rejected"].map((o, i) =>
        `<label class="check"><input type="radio" name="outcome" value="${o}" ${i ? "" : "checked"}><span>${esc(t("disp.o_" + o))}${o === "favor_opener" ? ` — ${esc(ds.an)}` : o === "favor_other" ? ` — ${esc(ds.bn)}` : ""}</span></label>`).join("")}</div></div>
      <div class="field"><label for="rsN">${esc(t("disp.note"))}</label><textarea class="input" id="rsN" name="note" minlength="5" maxlength="2000" required></textarea></div>
      <div class="field"><label for="rsC">${esc(t("disp.comp"))}</label><input class="input" type="text" data-money id="rsC" name="compensation" placeholder="0">
        <div class="hint show">${esc(t("disp.comp_hint"))}</div></div>
      <div class="field"><label for="rsB">${esc(t("disp.block_user"))}</label><select class="input" id="rsB" name="block_user_id">
        <option value="">—</option><option value="${ds.a}">${esc(ds.an)}</option><option value="${ds.b}">${esc(ds.bn)}</option></select></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button>
        <button class="btn">${esc(t("disp.resolve"))}</button></div></form>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = formData(e.target);
      try {
        await api(`/api/admin/disputes/${ds.resolve}/resolve`, { method: "POST", body: { outcome: f.outcome, note: f.note,
          compensation: f.compensation ? +f.compensation : null, block_user_id: f.block_user_id ? +f.block_user_id : null } });
        bg.remove(); toast(t("common.done"), "ok"); reload();
      } catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
    });
  }

  // ---------------- SMS va email kanallari ----------------
  async function channels() {
    $("#viewSub").textContent = t("chan.sub");
    const c = await api("/api/admin/channels");
    const state = (on) => `<span class="chan-dot ${on ? "on" : ""}"></span>${esc(on ? t("chan.on") : c.dev_inbox ? t("chan.off_dev") : t("chan.off_prod"))}`;
    const stTag = (st) => `<span class="tag ${st === "sent" || st === "delivered" ? "tag-ok" : st === "failed" ? "tag-bad" : st === "dev" ? "tag-hidden" : "tag-pending"}">${esc(t("chan.st_" + st) || st)}</span>`;
    view.innerHTML = `<div class="chan-grid">
        <div class="card card-pad chan-card"><h3>${icon("phone", 18)} ${esc(t("chan.sms"))}</h3><p>${state(c.sms.enabled)}</p>
          ${c.sms.enabled ? `<p class="small muted">${esc(c.sms.account || "")} · from: ${esc(c.sms.from)}</p>` : `<p class="small muted">${esc(t("chan.setup_sms"))}</p>`}</div>
        <div class="card card-pad chan-card"><h3>${icon("mail", 18)} ${esc(t("chan.email"))}</h3><p>${state(c.email.enabled)}</p>
          ${c.email.enabled ? `<p class="small muted">${esc(c.email.host || "")} · ${esc(c.email.from)}</p>` : `<p class="small muted">${esc(t("chan.setup_email"))}</p>`}</div>
      </div>
      <div class="two-col" style="margin-bottom:18px">
        <form class="card card-pad" id="chanTest"><h3>${esc(t("chan.test_t"))}</h3>
          <div class="seg" id="chanSeg" role="radiogroup"><button type="button" class="on" data-ch="sms">SMS</button><button type="button" data-ch="email">Email</button></div>
          <div class="field" style="margin-top:12px"><label for="chanTo" id="chanToL">${esc(t("chan.test_to_sms"))}</label>
            <input class="input" id="chanTo" type="tel" required placeholder="+998 90 123 45 67"></div>
          <button class="btn">${esc(t("chan.test_send"))}</button><div id="chanRes" class="small" style="margin-top:10px"></div></form>
        <div class="card card-pad"><h3>${esc(t("chan.templates"))}</h3><p class="small muted">${esc(t("chan.templates_sub"))}</p>
          ${c.templates.map((x) => `<div class="tpl">${esc(x.text)}</div>`).join("")}</div>
      </div>
      <div class="card"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t("chan.last"))}</h3></div>
        ${c.log.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.time"))}</th><th>${esc(t("chan.col_channel"))}</th><th>${esc(t("chan.test_to_sms"))}</th><th>${esc(t("chan.col_template"))}</th><th>${esc(t("col.status"))}</th></tr></thead><tbody>
          ${c.log.map((l) => `<tr><td class="small" data-label="${esc(t("col.time"))}">${esc(l.created_at)}</td><td data-label="${esc(t("chan.col_channel"))}">${esc(l.channel.toUpperCase())}</td>
            <td data-label="${esc(t("chan.test_to_sms"))}" class="mono">${esc(l.to_masked)}</td><td data-label="${esc(t("chan.col_template"))}">${esc(l.template)}</td>
            <td data-label="${esc(t("col.status"))}">${stTag(l.status)}${l.error ? `<div class="small muted">${esc(l.error)}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>`
          : `<div class="empty">${esc(t("chan.log_none"))}</div>`}</div>`;
    let ch = "sms";
    $$("#chanSeg [data-ch]").forEach((b) => b.addEventListener("click", () => {
      ch = b.dataset.ch; $$("#chanSeg [data-ch]").forEach((x) => x.classList.toggle("on", x === b));
      const to = $("#chanTo"); to.value = ""; to.type = ch === "sms" ? "tel" : "email"; to.placeholder = ch === "sms" ? "+998 90 123 45 67" : "you@gmail.com";
      $("#chanToL").textContent = t(ch === "sms" ? "chan.test_to_sms" : "chan.test_to_email");
    }));
    $("#chanTest").addEventListener("submit", async (e) => {
      e.preventDefault();
      await withLoading($("#chanTest .btn:not([data-ch])"), async () => {
        try {
          const r = await api("/api/admin/channels/test", { method: "POST", body: { channel: ch, to: $("#chanTo").value.trim() } });
          $("#chanRes").innerHTML = r.status === "sent" ? `<span class="tag tag-ok">${esc(t("chan.test_ok", { to: r.to }))}</span>`
            : r.status === "dev_inbox" ? `<span class="tag tag-hidden">${esc(t("chan.test_dev"))}</span> <a href="/dev-inbox.html" target="_blank" rel="noopener">${esc(t("dev.inbox_short"))}</a>`
            : `<span class="tag tag-bad">${esc(t("chan.st_failed"))}</span> ${esc(r.error || "")}`;
          setTimeout(channels, 2500);
        } catch (err) { toast(err.message, "error"); }
      });
    });
  }

  async function reports(status = "new") {
    const { items } = await api("/api/admin/reports?status=" + status);
    $("#viewSub").textContent = t("uadm.reports_sub");
    const actionFor = { car: "hide_car", review: "delete_review" };
    view.innerHTML = `<div class="row" style="gap:6px;margin-bottom:12px">${["new", "resolved", "dismissed"].map((k) =>
        `<button class="btn btn-sm ${k === status ? "" : "btn-outline"}" data-rst="${k}">${esc(t("report.st_" + k))}</button>`).join("")}</div>
      <div class="rep-list">${items.length ? items.map((r) => `<article class="card rep-item">
        <div class="rep-main">
          <div class="row" style="gap:8px"><span class="tag tag-bad">${esc(t("report.reason_" + r.reason))}</span><span class="tag tag-info">${esc(t("report.type_" + r.target_type))}</span>
            <span class="small muted">${esc(t("uadm.from"))}: <a href="#user/${r.reporter_id}">${esc(r.reporter_name)}</a> · ${fmtDate(r.created_at)}</span></div>
          <div class="row" style="gap:12px;margin-top:8px;flex-wrap:nowrap">${r.cover ? `<a class="mini-thumb lg" href="${esc(r.link)}" target="_blank" rel="noopener">${carImage({ cover: r.cover, brand: "", model: "" })}</a>` : ""}
            <div><div>${r.link ? `<a href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r.target_label)}</a>` : esc(r.target_label)}</div>
            ${r.comment ? `<div class="small muted">“${esc(r.comment)}”</div>` : ""}</div></div>
        </div>
        ${r.target_user_id ? `<a class="rep-who" href="#user/${r.target_user_id}" title="${esc(t("uadm.open_page"))}">
            <span class="small muted">${esc(t("uadm.against"))}</span>
            <span class="row" style="gap:8px;flex-wrap:nowrap">${avatarHtml({ full_name: r.target_user_name, avatar: r.target_user_avatar })}<b>${esc(r.target_user_name || "")}</b></span>
            <span class="row" style="gap:4px">${r.target_user_active ? `<span class="tag tag-ok">${esc(t("admin.active"))}</span>` : `<span class="tag tag-bad">${esc(t("admin.blocked_one"))}</span>`}
              ${r.target_user_warnings ? `<span class="tag tag-pending">${esc(t("uadm.warn_n", { n: r.target_user_warnings }))}</span>` : ""}</span>
            <span class="small" style="color:var(--primary)">${esc(t("uadm.open_page"))} →</span></a>` : ""}
        ${status === "new" ? `<div class="rep-acts">
          ${actionFor[r.target_type] ? `<button class="btn btn-sm btn-outline" data-rep="${r.id}" data-ract="${actionFor[r.target_type]}">${esc(t("report.act_" + actionFor[r.target_type]))}</button>` : ""}
          ${r.target_user_id ? `<button class="btn btn-sm btn-outline" data-rep="${r.id}" data-ract="warn_user">${icon("flag", 14)} ${esc(t("uadm.warn"))}</button>
            ${r.target_user_active ? `<button class="btn btn-sm btn-danger" data-rep="${r.id}" data-ract="block_user">${icon("lock", 14)} ${esc(t("admin.block"))}</button>` : ""}` : ""}
          <button class="btn btn-sm btn-ok" data-rep="${r.id}" data-ract="">${esc(t("report.resolve"))}</button>
          <button class="btn btn-sm btn-outline" data-rep="${r.id}" data-rdismiss="1">${esc(t("report.dismiss"))}</button></div>` : ""}
      </article>`).join("") : `<div class="empty card">${esc(t("report.none"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const st = e.target.closest("[data-rst]"); if (st) return reports(st.dataset.rst);
      const b = e.target.closest("[data-rep]"); if (!b) return;
      const body = b.dataset.rdismiss ? { status: "dismissed" } : { status: "resolved", action: b.dataset.ract || null };
      if (body.action === "warn_user" || body.action === "block_user") {
        const r = await reasonModal({ title: t(body.action === "warn_user" ? "uadm.warn" : "admin.block"), label: t(body.action === "warn_user" ? "uadm.l_warn" : "uadm.l_block"),
          danger: body.action === "block_user", okText: t(body.action === "warn_user" ? "uadm.ok_warn" : "uadm.ok_block") });
        if (!r) return;
        body.note = r.reason;
      } else if (body.action && !(await confirmBox(t("report.act_confirm"), t("common.yes"), true))) return;
      try { await api(`/api/admin/reports/${b.dataset.rep}`, { method: "PATCH", body }); toast(t("common.done"), "ok"); pollSummary(); reports(status); }
      catch (err) { toast(err.message, "error"); }
    };
  }

  async function audit() {
    const { items } = await api("/api/admin/audit");
    view.innerHTML = `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>${esc(t("col.time"))}</th><th>${esc(t("col.actor"))}</th>
      <th>${esc(t("col.action"))}</th><th>${esc(t("col.target"))}</th><th>IP</th></tr></thead><tbody>
      ${items.map((a) => `<tr><td data-label="${esc(t("col.time"))}" class="small">${esc(a.created_at)}</td><td data-label="${esc(t("col.actor"))}">${esc(a.actor_name || "—")}</td>
        <td data-label="${esc(t("col.action"))}">${esc(t("audit." + a.action) || a.action)}</td>
        <td data-label="${esc(t("col.target"))}" class="small">${esc(a.target_type || "")} ${a.target_id ?? ""} ${a.details ? `<span class="muted">${esc(a.details)}</span>` : ""}</td>
        <td data-label="IP" class="small">${esc(a.ip || "")}</td></tr>`).join("")}</tbody></table>
      ${items.length ? "" : `<div class="empty">${esc(t("admin.audit_empty"))}</div>`}</div>`;
  }
})();
