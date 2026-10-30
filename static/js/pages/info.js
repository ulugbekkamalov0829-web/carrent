"use strict";
/* Ma'lumot markazi: Biz haqimizda, Qanday ishlaydi, Tariflar, Xavfsizlik, FAQ, Aloqa, Qoidalar — bitta sahifada */
(async () => {
  await boot("info");
  const meta = await api("/api/meta");
  const page = $("#page");
  const SECTIONS = [["about", "nav.about", "info"], ["how", "nav.how", "list"], ["pricing", "nav.pricing", "wallet"], ["safety", "info.safety", "shield"],
    ["faq", "faq.title", "chat"], ["contact", "nav.contact", "phone"], ["terms", "footer.terms", "log"], ["privacy", "footer.privacy", "lock"]];
  const li = (keys) => keys.map((k) => `<li>${esc(t(k))}</li>`).join("");

  function draw() {
    const pct = meta.commission_bps / 100;
    const rent = 3 * 350000, delivery = 50000, total = rent + delivery, fee = Math.round((total * meta.commission_bps) / 10000);
    const u = Auth.user;
    page.innerHTML = `<div class="info-hero card">
        <div><span class="eyebrow">${esc(t("nav.info"))}</span><h1>${esc(t("info.title"))}</h1><p class="lead">${esc(t("info.lead"))}</p>
          <div class="info-stats"><span><b>${meta.cars_total}</b>${esc(t("home.stat_cars"))}</span><span><b>${meta.owners_total}</b>${esc(t("info.owners"))}</span>
          <span><b>${meta.cities.length}</b>${esc(t("home.stat_cities"))}</span><span><b>${pct}%</b>${esc(t("info.commission"))}</span></div></div>
        <img src="/img/hero-street.jpg" alt="" loading="lazy"></div>
      <nav class="info-tabs" id="infoTabs">${SECTIONS.map(([k, key, ico]) => `<a href="#${k}" data-sec="${k}">${icon(ico, 16)}${esc(t(key))}</a>`).join("")}</nav>
      <div class="info-body">
        <section id="about" class="card card-pad"><h2>${esc(t("about.title"))}</h2><p>${esc(t("about.p1"))}</p><p>${esc(t("about.p2"))}</p>
          <div class="benefits" style="margin-top:16px">
            <div class="soft-box"><span class="eyebrow">${esc(t("ben.renter_eyebrow"))}</span><h3>${esc(t("ben.renter"))}</h3><ul class="benefit-list">${li(["ben.r1", "ben.r2", "ben.r3", "ben.r4"])}</ul></div>
            <div class="soft-box"><span class="eyebrow">${esc(t("ben.owner_eyebrow"))}</span><h3>${esc(t("ben.owner"))}</h3><ul class="benefit-list">${li(["ben.o1", "ben.o2", "ben.o3"])}<li>${esc(t("ben.o4", { pct }))}</li></ul></div></div></section>
        <section id="how" class="card card-pad"><h2>${esc(t("how.title"))}</h2>
          <div class="steps">${[1, 2, 3, 4].map((n) => `<div class="step soft-box"><h3>${esc(t("how.s" + n))}</h3><p>${esc(t(`how.s${n}d`))}</p></div>`).join("")}</div></section>
        <section id="pricing" class="card card-pad"><h2>${esc(t("pricing.title"))}</h2><p>${esc(t("pricing.p1"))}</p>
          <div class="soft-box" style="max-width:520px"><h3>${esc(t("pricing.example"))}</h3>
            <div class="sum-row"><span>350 000 × ${esc(t("car.days_n", { n: 3 }))}</span><span>${money(rent)}</span></div>
            <div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(delivery)}</span></div>
            <div class="sum-row total"><span>${esc(t("pricing.renter_pays"))}</span><span>${money(total)}</span></div>
            <div class="sum-row"><span>${esc(t("booking.fee", { pct }))}</span><span>− ${money(fee)}</span></div>
            <div class="sum-row total"><span>${esc(t("pricing.owner_gets"))}</span><span>${money(total - fee)}</span></div>
            <div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${esc(t("pricing.deposit_note"))}</span></div></div>
          <p class="small muted" style="margin-top:10px">${esc(t("pricing.note"))}</p>
          <h3 style="margin-top:18px">${esc(t("info.pay_methods"))}</h3>
          <div class="row" style="gap:8px">${[["on_site", true], ["click", meta.payments?.click], ["payme", meta.payments?.payme]].map(([k, on]) =>
            `<span class="tag ${on ? "tag-ok" : "tag-hidden"}">${esc(t("info.pm_" + k))}${k !== "on_site" ? ": " + esc(t(on ? "pay.connected" : "pay.not_connected")) : ""}</span>`).join("")}</div></section>
        <section id="safety" class="card card-pad"><h2>${esc(t("trust.title"))}</h2>
          <div class="trust">${[1, 2, 3, 4].map((n) => `<div class="soft-box"><div class="ico">${icon(["lock", "calendar", "star", "shield"][n - 1])}</div><h3>${esc(t("trust.t" + n))}</h3><p>${esc(t(`trust.t${n}d`))}</p></div>`).join("")}</div>
          <h3 style="margin-top:18px">${esc(t("info.tips"))}</h3><ul class="benefit-list">${li(["info.tip1", "info.tip2", "info.tip3", "info.tip4"])}</ul></section>
        <section id="faq" class="card card-pad faq"><h2>${esc(t("faq.title"))}</h2>
          ${[1, 2, 3, 4, 5, 6, 7].map((n) => { const q = n <= 5 ? "faq.q" + n : "info.q" + n, a = n <= 5 ? "faq.a" + n : "info.a" + n;
            return `<details><summary>${esc(t(q))}</summary><p>${esc(t(a))}</p></details>`; }).join("")}</section>
        <section id="contact" class="card card-pad"><h2>${esc(t("contact.title"))}</h2><p>${esc(t("contact.p1"))}</p>
          ${meta.support_user_id ? (u ? `<a class="btn" href="/messages.html?user=${meta.support_user_id}">${icon("chat", 18)} ${esc(t("contact.write_admin"))}</a>`
            : `<a class="btn btn-outline" href="/auth.html?next=${encodeURIComponent("/messages.html?user=" + meta.support_user_id)}#login">${esc(t("contact.login_first"))}</a>`)
            : `<p class="muted">${esc(t("contact.not_set"))}</p>`}
          <p class="small muted" style="margin-top:12px">${esc(t("info.report_hint"))}</p></section>
        <section id="terms" class="card card-pad"><h2>${esc(t("footer.terms"))}</h2><ol>${li(["terms.l1", "terms.l2", "terms.l3", "terms.l4", "terms.l5"])}</ol></section>
        <section id="privacy" class="card card-pad"><h2>${esc(t("footer.privacy"))}</h2><ol>${li(["privacy.l1", "privacy.l2", "privacy.l3", "privacy.l4", "info.privacy5"])}</ol></section>
      </div>`;
    const links = $$("#infoTabs a");
    const io = new IntersectionObserver((ents) => ents.forEach((en) => {
      if (en.isIntersecting) links.forEach((a) => { const on = a.dataset.sec === en.target.id; a.classList.toggle("active", on); if (on) a.scrollIntoView({ block: "nearest", inline: "center" }); });
    }), { rootMargin: "-35% 0px -60% 0px" });
    $$(".info-body > section").forEach((s) => io.observe(s));
    if (location.hash) setTimeout(() => $(location.hash)?.scrollIntoView(), 60);
  }
  draw();
  document.addEventListener("langchange", draw);
})();
