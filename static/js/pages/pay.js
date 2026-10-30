"use strict";
/* Sinov to'lov sahifasi: faqat demo/dev rejimda ishlaydi. Karta ma'lumoti so'ralmaydi va hech qanday pul yechilmaydi. */
(async () => {
  await boot("");
  await guard("user");
  const page = $("#page");
  const id = +new URLSearchParams(location.search).get("payment");
  let p;
  try { p = await api(`/api/payments/${id}`); } catch (e) { page.innerHTML = `<div class="empty card">${esc(e.message)}</div>`; return; }
  function draw() {
    const done = p.status === "paid";
    page.innerHTML = `<div class="checkout">
      <div class="test-banner">${icon("info", 18)}<div><b>${esc(t("pay.test_banner_t"))}</b><span>${esc(t("pay.test_banner_b"))}</span></div></div>
      <div class="card card-pad">
        <div class="row" style="justify-content:space-between"><h1 style="font-size:1.4rem;margin:0">${esc(t("pay.checkout"))}</h1><span class="pay-logo pay-test">TEST</span></div>
        <p class="muted">${esc(p.brand)} ${esc(p.model)} ${p.year} · ${esc(p.city)}</p>
        <div class="sum-row"><span>${esc(t("col.dates"))}</span><b>${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</b></div>
        <div class="sum-row"><span>${money(p.price_per_day)} × ${esc(t("car.days_n", { n: p.days }))}</span><span>${money(p.price_per_day * p.days)}</span></div>
        ${p.delivery ? `<div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(p.amount - p.price_per_day * p.days)}</span></div>` : ""}
        <div class="sum-row total"><span>${esc(t("pay.amount"))}</span><span>${money(p.amount)}</span></div>
        ${p.deposit ? `<div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${esc(t("pay.deposit_on_site", { d: money(p.deposit) }))}</span></div>` : ""}
        ${done ? `<div class="notice info" style="margin:16px 0 0">${esc(t("pay.already_paid"))}</div><a class="btn btn-block btn-lg" style="margin-top:14px" href="/receipt.html?payment=${p.id}">${esc(t("pay.receipt"))}</a>`
          : `<div class="row" style="margin-top:18px"><button class="btn btn-outline" id="payCancel">${esc(t("common.cancel"))}</button>
            <button class="btn btn-lg spacer" id="payOk">${icon("lock", 18)} ${esc(t("pay.test_confirm", { sum: money(p.amount) }))}</button></div>`}
      </div>
      <p class="small muted center">${esc(t("pay.test_footer"))}</p></div>`;
    $("#payOk")?.addEventListener("click", (e) => withLoading(e.currentTarget, async () => {
      try { await api(`/api/payments/${p.id}/test/confirm`, { method: "POST" }); location.href = `/receipt.html?payment=${p.id}&ok=1`; }
      catch (err) { toast(err.message, "error"); }
    }));
    $("#payCancel")?.addEventListener("click", async () => {
      await api(`/api/payments/${p.id}/test/cancel`, { method: "POST" }).catch(() => {});
      location.href = "/dashboard.html#bookings";
    });
  }
  draw();
  document.addEventListener("langchange", draw);
})();
