"use strict";
(async () => {
  const user = await boot("home");
  const today = isoDate(new Date());
  $("#start").min = today; $("#end").min = today;
  $("#start").addEventListener("change", () => { $("#end").min = $("#start").value; if ($("#end").value && $("#end").value < $("#start").value) $("#end").value = $("#start").value; });

  // Qidiruv: bo'sh maydonlar URL'ga tushmaydi
  $("#searchForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
    location.href = "/cars.html" + (p.toString() ? "?" + p : "");
  });

  const [meta, reco, reviews] = await Promise.all([api("/api/meta"), api("/api/recommendations?limit=8"), api("/api/reviews/latest")]);
  $("#city").insertAdjacentHTML("beforeend", meta.cities.map((c) => `<option value="${esc(c.city)}">${esc(c.city)}</option>`).join(""));

  function draw() {
    $("#heroStats").innerHTML = `<span><b>${meta.cars_total}</b>${esc(t("home.stat_cars"))}</span><span><b>${meta.cities.length}</b>${esc(t("home.stat_cities"))}</span>
      <span><b>${meta.completed_total}</b>${esc(t("home.stat_trips"))}</span><span><b>${shortMoney(meta.price_min)}</b>${esc(t("home.stat_from"))}</span>`;
    $("#commissionLine").textContent = t("ben.o4", { pct: meta.commission_bps / 100 });
    if (user && reco.personal && user.role !== "admin") { $("#recoTitle").textContent = t("home.for_you"); $("#recoSub").textContent = t("home.for_you_sub"); }
    $("#reco").innerHTML = reco.items.length ? reco.items.map((c) => carCard(c, { reason: !!user })).join("")
      : `<div class="empty card" style="grid-column:1/-1">${esc(t("cars.empty"))}</div>`;
    $("#regions").innerHTML = meta.cities.map((c) => `<a class="card region" href="/cars.html?city=${encodeURIComponent(c.city)}">
      <b>${esc(c.city)}</b><span class="muted small">${esc(t("regions.count", { n: c.count }))}</span></a>`).join("");
    $("#testimonials").innerHTML = reviews.items.length ? reviews.items.slice(0, 3).map((r) => `<figure class="card quote" style="margin:0">
      <div class="stars">${stars(r.rating)}</div><p>“${esc(r.comment)}”</p>
      <figcaption class="row"><span class="avatar">${esc(initials(r.author))}</span><div><b>${esc(r.author)}</b>
      <div class="small muted"><a href="/car.html?id=${r.car_id}">${esc(r.brand)} ${esc(r.model)}</a> · ${fmtDate(r.created_at)}</div></div></figcaption></figure>`).join("")
      : `<p class="muted">${esc(t("reviews.none"))}</p>`;
  }
  draw();
  document.addEventListener("langchange", draw);
})();
