"use strict";
(async () => {
  await boot(location.hash === "#pricing" ? "pricing" : location.hash === "#contact" ? "contact" : "about");
  const meta = await api("/api/meta");
  function draw() {
    const pct = meta.commission_bps / 100;
    const rent = 3 * 350000, delivery = 50000, total = rent + delivery;
    const fee = Math.round((total * meta.commission_bps) / 10000);
    $("#pricingExample").innerHTML = `<h3>${esc(t("pricing.example"))}</h3>
      <div class="sum-row"><span>350 000 × ${esc(t("car.days_n", { n: 3 }))}</span><span>${money(rent)}</span></div>
      <div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(delivery)}</span></div>
      <div class="sum-row total"><span>${esc(t("pricing.renter_pays"))}</span><span>${money(total)}</span></div>
      <div class="sum-row"><span>${esc(t("booking.fee", { pct }))}</span><span>− ${money(fee)}</span></div>
      <div class="sum-row total"><span>${esc(t("pricing.owner_gets"))}</span><span>${money(total - fee)}</span></div>
      <div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${esc(t("pricing.deposit_note"))}</span></div>`;
    const u = Auth.user;
    $("#contactBox").innerHTML = meta.support_user_id
      ? (u ? `<a class="btn" href="/messages.html?user=${meta.support_user_id}">${esc(t("contact.write_admin"))}</a>`
           : `<a class="btn btn-outline" href="/auth.html?next=${encodeURIComponent("/messages.html?user=" + meta.support_user_id)}#login">${esc(t("contact.login_first"))}</a>`)
      : `<p class="muted">${esc(t("contact.not_set"))}</p>`;
  }
  draw();
  document.addEventListener("langchange", draw);
  if (location.hash) setTimeout(() => $(location.hash)?.scrollIntoView(), 100);
})();
