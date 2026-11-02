/* Ochiq tekshirish: QR kod shu sahifaga olib keladi. Shartnoma haqiqiymi, imzolanganmi, matni o'zgarmaganmi */
"use strict";
(async () => {
  await boot("");
  const root = $("#root");
  const p = new URLSearchParams(location.search);
  let r = null, err = null;
  try { r = await api(`/api/contracts/verify?n=${encodeURIComponent(p.get("n") || "")}&t=${encodeURIComponent(p.get("t") || "")}`); }
  catch (e) { err = e; }
  function draw() {
    if (!r) {
      root.innerHTML = `<div class="verify-card card card-pad bad"><div class="v-ico">${icon("close", 34)}</div><h1>${esc(t("vfy.not_found"))}</h1><p>${esc(t("vfy.not_found_sub"))}</p></div>`;
      return;
    }
    const good = r.status === "approved" && r.intact;
    root.innerHTML = `<div class="verify-card card card-pad ${good ? "good" : r.status === "cancelled" || !r.intact ? "bad" : "wait"}">
      <div class="v-ico">${icon(good ? "check" : r.status === "cancelled" || !r.intact ? "close" : "shield", 34)}</div>
      <h1>${esc(t(good ? "vfy.valid" : !r.intact ? "vfy.tampered" : "vfy.st_" + r.status))}</h1>
      <p class="muted">${esc(t("vfy.number"))}: <b>${esc(r.number)}</b></p>
      <div class="terms-list" style="text-align:left;margin-top:16px">
        <div><span class="muted">${esc(t("vfy.car"))}</span><b>${esc(r.car)}</b></div>
        <div><span class="muted">${esc(t("col.dates"))}</span><b>${fmtDate(r.start_date)} → ${fmtDate(r.end_date)}</b></div>
        <div><span class="muted">${esc(t("ctr.owner"))}</span><b>${esc(r.owner)} ${r.owner_signed_at ? "✓" : ""}</b></div>
        <div><span class="muted">${esc(t("ctr.renter"))}</span><b>${esc(r.renter)} ${r.renter_signed_at ? "✓" : ""}</b></div>
        <div><span class="muted">${esc(t("vfy.approved"))}</span><b>${esc(r.approved_at || "—")}</b></div>
        <div><span class="muted">${esc(t("ctr.hash"))}</span><b><code>${esc(r.body_hash.slice(0, 24))}…</code></b></div>
        <div><span class="muted">${esc(t("vfy.integrity"))}</span><b>${esc(t(r.intact ? "ctr.intact" : "ctr.tampered"))}</b></div>
      </div>
      <p class="small muted" style="margin-top:14px">${esc(t("vfy.note"))}</p></div>`;
  }
  draw();
  document.addEventListener("langchange", draw);
})();
