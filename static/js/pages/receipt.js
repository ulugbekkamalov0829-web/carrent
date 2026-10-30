"use strict";
(async () => {
  await boot("");
  await guard("user", "admin");
  const page = $("#page");
  const q = new URLSearchParams(location.search);
  let p;
  try { p = await api(`/api/payments/${+q.get("payment")}`); } catch (e) { page.innerHTML = `<div class="empty card">${esc(e.message)}</div>`; return; }
  const provName = (k) => (k === "test" ? t("pay.test_name") : k === "click" ? "Click" : "Payme");
  function draw() {
    const paid = p.status === "paid";
    page.innerHTML = `<div class="checkout">
      ${q.get("ok") && paid ? `<div class="success-burst">${icon("check", 34)}</div><h1 class="center" style="font-size:1.5rem">${esc(t("pay.success"))}</h1>` : ""}
      ${p.test_mode ? `<div class="test-banner">${icon("info", 18)}<div><b>${esc(t("pay.test_receipt_t"))}</b><span>${esc(t("pay.test_banner_b"))}</span></div></div>` : ""}
      <article class="card card-pad receipt" id="receipt">
        <div class="row" style="justify-content:space-between;align-items:flex-start"><div><div class="logo"><span class="logo-mark">${LOGO}</span><span>Car<b>Rent</b></span></div>
          <div class="small muted" style="margin-top:6px">${esc(t("pay.receipt"))} № ${p.id}</div></div>
          <span class="tag ${paid ? "tag-ok" : p.status.startsWith("refund") ? "tag-pending" : "tag-hidden"}">${esc(t("pay.st_" + p.status))}</span></div>
        <hr class="dash">
        <div class="sum-row"><span class="muted">${esc(t("col.car"))}</span><b>${esc(p.brand)} ${esc(p.model)} ${p.year}</b></div>
        <div class="sum-row"><span class="muted">${esc(t("col.dates"))}</span><span>${fmtDate(p.start_date)} → ${fmtDate(p.end_date)} (${esc(t("car.days_n", { n: p.days }))})</span></div>
        <div class="sum-row"><span class="muted">${esc(t("booking.renter"))}</span><span>${esc(p.renter_name)}</span></div>
        <div class="sum-row"><span class="muted">${esc(t("booking.owner"))}</span><span>${esc(p.owner_name)}</span></div>
        <div class="sum-row"><span class="muted">${esc(t("pay.method"))}</span><span>${esc(provName(p.provider))}</span></div>
        <div class="sum-row"><span class="muted">${esc(t("col.time"))}</span><span>${esc(p.paid_at || p.created_at)} UTC</span></div>
        ${p.provider_txn_id ? `<div class="sum-row"><span class="muted">${esc(t("pay.txn"))}</span><span class="mono">${esc(p.provider_txn_id)}</span></div>` : ""}
        <hr class="dash">
        <div class="sum-row total"><span>${esc(t("pay.amount"))}</span><span>${money(p.amount)}</span></div>
        ${p.deposit ? `<div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${esc(t("pay.deposit_on_site", { d: money(p.deposit) }))}</span></div>` : ""}
      </article>
      <div class="row no-print" style="justify-content:center;margin-top:14px"><button class="btn btn-outline" id="printBtn">${icon("receipt", 18)} ${esc(t("pay.print"))}</button>
        <a class="btn" href="${Auth.user.role === "admin" ? "/admin.html#payments" : "/dashboard.html#bookings"}">${esc(t("pay.to_bookings"))}</a></div></div>`;
    $("#printBtn").addEventListener("click", () => window.print());
  }
  draw();
  document.addEventListener("langchange", draw);
})();
