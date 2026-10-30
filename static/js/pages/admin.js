"use strict";
(async () => {
  await boot("");
  await guard("admin");
  const TABS = ADMIN_TABS;
  const view = $("#view");
  let tab = "stats";

  function route() {
    tab = TABS.find(([k]) => "#" + k === location.hash)?.[0] || "stats";
    markActive();
    $("#viewTitle").textContent = t(TABS.find(([k]) => k === tab)[1]);
    $("#viewSub").textContent = "";
    view.onclick = null;
    view.innerHTML = `<div class="skeleton" style="height:240px"></div>`;
    ({ stats, users, cars, bookings, payments, reports, reviews, finance, audit, analytics: () => Reports.render(view, "admin") })[tab]().catch((e) => (view.innerHTML = `<div class="empty card">${esc(e.message)}</div>`));
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("langchange", route);
  route();

  const searchBox = (phKey, extra = "") => `<form class="row" id="search" style="margin-bottom:12px">
    <input class="input" name="q" placeholder="${esc(t(phKey))}" aria-label="${esc(t(phKey))}" style="max-width:320px">${extra}<button class="btn btn-outline">${esc(t("common.search"))}</button></form>`;
  const onSearch = (fn) => $("#search").addEventListener("submit", (e) => { e.preventDefault(); fn(new URLSearchParams(formData(e.target))); });

  async function stats() {
    const s = await api("/api/admin/stats");
    $("#viewSub").textContent = t("admin.real_data");
    view.innerHTML = `<div class="stats">
        ${stat(t("admin.users_total"), s.users.total, esc(t("admin.users_sub", { a: s.users.owners, b: s.users.renters, c: s.users.new_week })))}
        ${stat(t("admin.active_30"), s.users.active_30d, esc(t("admin.active_sub")))}
        ${stat(t("admin.cars_active"), s.cars.active, esc(t("admin.cars_sub", { n: s.cars.total, h: s.cars.hidden })))}
        ${stat(t("admin.bookings_total"), Object.values(s.bookings).reduce((a, x) => a + x, 0), esc(t("admin.pending_n", { n: s.bookings.pending })))}
        ${stat(t("admin.gmv"), money(s.revenue_total), esc(t("admin.gmv_sub")))}
        ${stat(t("admin.commission_income"), money(s.commission_total), esc(t("admin.commission_rate", { pct: s.commission_bps / 100 })))}
        ${stat(t("admin.reviews_total"), s.reviews.cnt, s.reviews.avg ? `★ ${s.reviews.avg}` : "")}
        ${stat(t("admin.blocked"), s.users.blocked, esc(t("admin.blocked_sub")))}
        ${stat(t("admin.reports_new"), s.reports_new, s.reports_new ? `<a href="#reports">${esc(t("dash.open"))}</a>` : esc(t("owner.all_done")))}
        ${stat(t("admin.paid_online"), money(s.paid_online), s.refunds_pending ? `<a href="#payments">${esc(t("admin.refunds_n", { n: s.refunds_pending }))}</a>` : "")}
      </div>
      <div class="two-col">
        <div class="card card-pad"><h3>${esc(t("admin.monthly"))}</h3>${revenueChart(s.monthly)}</div>
        <div class="card card-pad"><h3>${esc(t("owner.statuses"))}</h3>${statusBars(s.bookings)}</div>
      </div>
      <div class="two-col" style="margin-top:18px">
        <div class="card card-pad"><h3>${esc(t("admin.by_city"))}</h3>${hbars(s.by_city, { label: (r) => r.city, value: (r) => r.bookings })}</div>
        <div class="card card-pad"><h3>${esc(t("admin.by_body"))}</h3>${hbars(s.by_body, { label: (r) => t("body." + r.body_type), value: (r) => r.bookings })}
          <h3 style="margin-top:18px">${esc(t("admin.growth"))}</h3>${hbars(s.user_growth.slice(-6), { label: (r) => r.month, value: (r) => r.count, color: "var(--success)" })}</div>
      </div>`;
  }

  async function users(p = new URLSearchParams()) {
    const { items } = await api("/api/admin/users?" + p);
    view.innerHTML = searchBox("admin.search_users", `<select class="input" name="kind" style="width:auto" aria-label="${esc(t("admin.kind"))}">
      <option value="">${esc(t("common.all"))}</option><option value="owners">${esc(t("admin.owners"))}</option><option value="admins">${esc(t("admin.admins"))}</option></select>`) +
      `<div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.user"))}</th><th>${esc(t("col.role"))}</th><th>${esc(t("col.activity"))}</th>
        <th>${esc(t("col.registered"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
      ${items.map((u) => `<tr><td data-label="#">${u.id}</td><td data-label="${esc(t("col.user"))}"><b>${esc(u.full_name)}</b><div class="small muted">${esc(u.email)} · ${esc(u.phone || "")}</div></td>
        <td data-label="${esc(t("col.role"))}">${esc(t("role." + u.role))}</td>
        <td data-label="${esc(t("col.activity"))}" class="small">${esc(t("admin.activity", { c: u.cars, b: u.bookings }))}</td>
        <td data-label="${esc(t("col.registered"))}" class="small">${fmtDate(u.created_at)}</td>
        <td data-label="${esc(t("col.status"))}">${u.is_active ? `<span class="tag tag-ok">${esc(t("admin.active"))}</span>` : `<span class="tag tag-bad">${esc(t("admin.blocked_one"))}</span>`}</td>
        <td>${u.role !== "admin" ? `<button class="btn btn-sm ${u.is_active ? "btn-danger" : "btn-outline"}" data-user="${u.id}" data-active="${u.is_active ? 0 : 1}">${esc(t(u.is_active ? "admin.block" : "admin.unblock"))}</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>`;
    for (const [k, v] of p) { const el = $(`#search [name=${k}]`); if (el) el.value = v; }
    onSearch(users);
    view.onclick = async (e) => {
      const b = e.target.closest("[data-user]"); if (!b) return;
      const activate = b.dataset.active === "1";
      if (!activate && !(await confirmBox(t("admin.block_confirm"), t("admin.block"), true))) return;
      try { await api(`/api/admin/users/${b.dataset.user}`, { method: "PATCH", body: { is_active: activate } }); toast(t("common.done"), "ok"); users(p); }
      catch (err) { toast(err.message, "error"); }
    };
  }

  async function cars(p = new URLSearchParams()) {
    const { items } = await api("/api/admin/cars?" + p);
    view.innerHTML = searchBox("admin.search_cars") + `<div class="card table-wrap"><table class="table responsive"><thead><tr>
      <th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("col.owner"))}</th><th>${esc(t("col.price"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>
      ${items.map((c) => `<tr><td data-label="#">${c.id}</td><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${c.id}"><b>${esc(c.brand)} ${esc(c.model)} ${c.year}</b></a><div class="small muted">${esc(c.city)} · ${fmtDate(c.created_at)}</div></td>
        <td data-label="${esc(t("col.owner"))}">${esc(c.owner_name)}</td><td data-label="${esc(t("col.price"))}">${money(c.price_per_day)}</td>
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
        <th>${esc(t("col.dates"))}</th><th>${esc(t("booking.total"))}</th><th>${esc(t("col.commission"))}</th><th>${esc(t("col.status"))}</th></tr></thead><tbody>
      ${items.map((b) => `<tr><td data-label="#">${b.id}</td><td data-label="${esc(t("col.car"))}"><a href="/car.html?id=${b.car_id}">${esc(b.brand)} ${esc(b.model)}</a></td>
        <td data-label="${esc(t("booking.renter"))}">${esc(b.renter_name)}</td><td data-label="${esc(t("col.owner"))}">${esc(b.owner_name)}</td>
        <td data-label="${esc(t("col.dates"))}" class="small">${fmtDate(b.start_date)} → ${fmtDate(b.end_date)}</td>
        <td data-label="${esc(t("booking.total"))}">${money(b.total_price)}</td><td data-label="${esc(t("col.commission"))}">${money(b.commission)} <span class="muted small">(${b.commission_bps / 100}%)</span></td>
        <td data-label="${esc(t("col.status"))}">${statusTag(b.status)}</td></tr>`).join("")}
      </tbody></table>${items.length ? "" : `<div class="empty">${esc(t("dash.no_bookings"))}</div>`}</div>`;
    view.onclick = (e) => { const b = e.target.closest("[data-st]"); if (b) bookings(b.dataset.st); };
  }

  async function reviews() {
    const { items } = await api("/api/admin/reviews");
    view.innerHTML = `<div class="card">${items.length ? items.map((r) => `<div class="list-item" style="grid-template-columns:1fr auto">
        <div><div class="row" style="gap:8px"><span class="stars">${stars(r.rating)}</span><b>${esc(r.author)}</b>
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
          ${rq.items.map((r) => `<tr><td data-label="${esc(t("col.owner"))}"><b>${esc(r.full_name)}</b><div class="small muted">${esc(r.phone || r.email)}</div></td>
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
          <th>${esc(t("earn.paid_out"))}</th><th>${esc(t("earn.balance"))}</th><th></th></tr></thead><tbody>
          ${d.balances.map((b) => `<tr><td data-label="${esc(t("col.owner"))}"><b>${esc(b.full_name)}</b></td><td data-label="${esc(t("earn.online"))}">${money(b.earned_online)}</td>
            <td data-label="${esc(t("earn.paid_out"))}">${money(b.paid_out)}</td><td data-label="${esc(t("earn.balance"))}"><b>${money(b.balance)}</b></td>
            <td>${b.balance > 0 ? `<button class="btn btn-sm" data-payout="${b.id}" data-max="${b.balance}" data-name="${esc(b.full_name)}">${esc(t("admin.payout"))}</button>` : ""}</td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">${esc(t("admin.no_balances"))}</div>`}</div>
      <div class="card table-wrap"><table class="table responsive"><thead><tr><th>#</th><th>${esc(t("col.car"))}</th><th>${esc(t("booking.renter"))}</th>
        <th>${esc(t("pay.method"))}</th><th>${esc(t("pay.amount"))}</th><th>${esc(t("col.status"))}</th><th>${esc(t("col.time"))}</th><th></th></tr></thead><tbody>
        ${d.items.map((p) => `<tr><td data-label="#">${p.id}</td><td data-label="${esc(t("col.car"))}">${esc(p.brand)} ${esc(p.model)}</td>
          <td data-label="${esc(t("booking.renter"))}">${esc(p.renter_name)}</td><td data-label="${esc(t("pay.method"))}">${esc(provName(p.provider))}</td>
          <td data-label="${esc(t("pay.amount"))}">${money(p.amount)}${p.refund_amount ? `<div class="small" style="color:var(--success-ink)">↩ ${money(p.refund_amount)}</div>` : ""}</td>
          <td data-label="${esc(t("col.status"))}">${payStatusTag(p.status)}</td>
          <td data-label="${esc(t("col.time"))}" class="small">${esc(p.paid_at || p.created_at)}</td>
          <td>${p.status === "refund_pending" ? `<button class="btn btn-sm btn-outline" data-refunded="${p.id}">${esc(t("admin.mark_refunded"))}</button>` : `<a class="btn btn-sm btn-outline" href="/receipt.html?payment=${p.id}">${esc(t("pay.receipt"))}</a>`}</td></tr>`).join("")}
      </tbody></table>${d.items.length ? "" : `<div class="empty">${esc(t("admin.no_payments"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const r = e.target.closest("[data-refunded]"), po = e.target.closest("[data-payout]");
      try {
        if (r && await confirmBox(t("admin.refund_confirm"), t("common.yes"))) { await api(`/api/admin/payments/${r.dataset.refunded}/refunded`, { method: "POST" }); toast(t("common.done"), "ok"); payments(); }
        if (po) payoutModal(+po.dataset.payout, +po.dataset.max, po.dataset.name);
      } catch (err) { toast(err.message, "error"); }
    };
  }

  function payoutModal(ownerId, max, name) {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true"><h3>${esc(t("admin.payout"))}: ${esc(name)}</h3>
      <div class="field"><label for="poA">${esc(t("pay.amount"))}</label><input class="input" id="poA" type="number" min="1" max="${max}" value="${max}" required>
        <div class="hint">${esc(t("admin.payout_hint", { max: money(max) }))}</div></div>
      <div class="field"><label for="poN">${esc(t("block.note"))}</label><input class="input" id="poN" maxlength="200" placeholder="${esc(t("admin.payout_note_ph"))}"></div>
      <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button><button class="btn">${esc(t("common.save"))}</button></div></form>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
    $("form", bg).addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("/api/admin/payouts", { method: "POST", body: { owner_id: ownerId, amount: +$("#poA").value, note: $("#poN").value.trim() || null } }); bg.remove(); toast(t("common.done"), "ok"); payments(); }
      catch (err) { toast(err.message, "error"); }
    });
  }

  async function reports(status = "new") {
    const { items } = await api("/api/admin/reports?status=" + status);
    const actionFor = { car: "hide_car", review: "delete_review", user: "block_user" };
    view.innerHTML = `<div class="row" style="gap:6px;margin-bottom:12px">${["new", "resolved", "dismissed"].map((k) =>
        `<button class="btn btn-sm ${k === status ? "" : "btn-outline"}" data-rst="${k}">${esc(t("report.st_" + k))}</button>`).join("")}</div>
      <div class="card">${items.length ? items.map((r) => `<div class="list-item" style="grid-template-columns:1fr auto">
        <div><div class="row" style="gap:8px"><span class="tag tag-bad">${esc(t("report.reason_" + r.reason))}</span><span class="tag tag-info">${esc(t("report.type_" + r.target_type))}</span>
          <span class="small muted">${esc(r.reporter_name)} · ${fmtDate(r.created_at)}</span></div>
          <div style="margin-top:4px">${r.link ? `<a href="${esc(r.link)}">${esc(r.target_label)}</a>` : esc(r.target_label)}</div>
          ${r.comment ? `<div class="small muted">“${esc(r.comment)}”</div>` : ""}</div>
        <div class="actions">${status === "new" ? `${actionFor[r.target_type] ? `<button class="btn btn-sm btn-danger" data-rep="${r.id}" data-ract="${actionFor[r.target_type]}">${esc(t("report.act_" + actionFor[r.target_type]))}</button>` : ""}
          <button class="btn btn-sm btn-ok" data-rep="${r.id}" data-ract="">${esc(t("report.resolve"))}</button>
          <button class="btn btn-sm btn-outline" data-rep="${r.id}" data-rdismiss="1">${esc(t("report.dismiss"))}</button>` : ""}</div></div>`).join("")
        : `<div class="empty">${esc(t("report.none"))}</div>`}</div>`;
    view.onclick = async (e) => {
      const st = e.target.closest("[data-rst]"); if (st) return reports(st.dataset.rst);
      const b = e.target.closest("[data-rep]"); if (!b) return;
      const body = b.dataset.rdismiss ? { status: "dismissed" } : { status: "resolved", action: b.dataset.ract || null };
      if (body.action && !(await confirmBox(t("report.act_confirm"), t("common.yes"), true))) return;
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
