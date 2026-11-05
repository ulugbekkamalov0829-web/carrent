/* Qabul-topshirish dalolatnomasi: mashina berilganda va qaytarilganda holati (probeg, yoqilg'i, tozalik, shikast, rasmlar).
   Bir tomon to'ldiradi, ikkinchisi tasdiqlaydi. Qaytarishda yoqilg'i/probeg bo'yicha qo'shimcha summa avtomatik hisoblanadi. */
"use strict";
(async () => {
  await boot("");
  const me = await guard("user", "admin");
  const root = $("#root");
  const bid = Number(new URLSearchParams(location.search).get("booking"));
  let d, files = { pickup: [], return: [] };

  async function load() {
    try { d = await api(`/api/bookings/${bid}/handovers`); draw(); }
    catch (e) { root.innerHTML = `<div class="empty card"><h2>${esc(t("ho.title"))}</h2><p>${esc(e.message)}</p></div>`; }
  }
  const isParty = () => me.id === d.booking.renter_id || me.id === d.booking.owner_id;
  const fuelBar = (pct) => `<div class="fuel-bar" aria-label="${pct}%"><i style="width:${pct}%"></i><span>${pct}%</span></div>`;

  /** Ijarachi mashinani olishda hujjatlarni e'lon bilan solishtiradi (soxta ma'lumotdan himoya) */
  const docsCheck = (kind) => `<div class="docs-check"><b>${icon("idcard", 16)} ${esc(t("ho.docs_t"))}</b>
    <ul><li>${esc(t("ho.docs_1"))}</li><li>${esc(t("ho.docs_2"))}</li><li>${esc(t("ho.docs_3"))}</li></ul>
    <label class="check"><input type="checkbox" data-docs="${kind}"><span><b>${esc(t("ho.docs_ok"))}</b></span></label>
    <p class="small muted" style="margin:6px 0 0">${esc(t("ho.docs_bad"))}</p></div>`;

  function actCard(kind) {
    const h = d[kind], b = d.booking, today = isoDate(new Date());
    const title = `<h3>${icon(kind === "pickup" ? "key" : "car", 18)} ${esc(t("ho.k_" + kind))}</h3>`;
    if (h) {
      const canConfirm = isParty() && h.created_by !== me.id && !h.confirmed_at;
      return `<div class="card card-pad ho-card">${title}
        <div class="ho-facts">
          <div><span class="muted small">${esc(t("ho.odometer"))}</span><b>${numFmt().format(h.odometer_km)} ${esc(t("unit.km"))}</b></div>
          <div><span class="muted small">${esc(t("ho.fuel"))}</span>${fuelBar(h.fuel_pct)}</div>
          <div><span class="muted small">${esc(t("ho.clean"))}</span><b>${esc(t(h.clean ? "common.yes" : "common.no"))}</b></div>
          <div><span class="muted small">${esc(t("ho.damage"))}</span><b class="${h.damage ? "bad-ink" : ""}">${esc(t(h.damage ? "ho.has_damage" : "ho.no_damage"))}</b></div></div>
        ${h.notes ? `<p class="small" style="margin:8px 0">“${esc(h.notes)}”</p>` : ""}
        <div class="ho-photos">${h.photos.map((p, i) => `<button type="button" data-ph="${kind}" data-i="${i}"><img src="${esc(p)}" alt="" loading="lazy"></button>`).join("")}</div>
        <div class="small muted">${esc(t("ho.filled_by", { name: h.created_by_name, d: h.created_at }))}</div>
        ${h.confirmed_at ? `<div class="small ${h.objection ? "bad-ink" : "ok-ink"}">${icon(h.objection ? "flag" : "check", 14)} ${esc(h.objection ? t("ho.objected", { name: h.confirmed_by_name, text: h.objection }) : t("ho.confirmed_by", { name: h.confirmed_by_name, d: h.confirmed_at }))}</div>`
          : `<div class="small muted">${esc(t("ho.wait_confirm"))}</div>`}
        ${h.docs_checked ? `<div class="small ok-ink">${icon("idcard", 14)} ${esc(t("ho.docs_done"))}</div>` : ""}
        ${canConfirm && kind === "pickup" && me.id === d.booking.renter_id ? docsCheck(kind) : ""}
        ${canConfirm ? `<div class="row" style="gap:8px;margin-top:10px"><button class="btn btn-sm btn-ok" data-confirm="${kind}">${icon("check", 15)} ${esc(t("ho.confirm"))}</button>
          <button class="btn btn-sm btn-outline" data-object="${kind}">${esc(t("ho.object"))}</button></div>` : ""}</div>`;
    }
    const can = isParty() && ["approved", "completed"].includes(b.status) && (kind === "return" ? !!d.pickup : today >= d.can_pickup_from);
    if (!can) return `<div class="card card-pad ho-card empty-ho">${title}<p class="muted small">${esc(t(kind === "return" && !d.pickup ? "ho.return_after" : !isParty() ? "ho.not_party" : "ho.pickup_from", { d: fmtDate(d.can_pickup_from) }))}</p></div>`;
    const prev = kind === "return" ? d.pickup : null;
    return `<form class="card card-pad ho-card ho-form" data-kind="${kind}" novalidate>${title}
      <p class="small muted">${esc(t("ho.form_hint"))}</p>
      <div class="grid-2"><div class="field"><label>${esc(t("ho.odometer"))}</label><input class="input" name="odometer_km" type="number" min="${prev ? prev.odometer_km : 0}" inputmode="numeric" required placeholder="${prev ? prev.odometer_km : 45000}"></div>
        <div class="field"><label>${esc(t("ho.fuel"))}: <b data-fuelv>${prev ? prev.fuel_pct : 100}%</b></label><input type="range" name="fuel_pct" min="0" max="100" step="5" value="${prev ? (d.car.fuel_policy === "full" ? 100 : prev.fuel_pct) : 100}" class="fuel-range"></div></div>
      <label class="check"><input type="checkbox" name="clean" checked><span>${esc(t("ho.clean_q"))}</span></label>
      <label class="check"><input type="checkbox" name="damage"><span>${esc(t("ho.damage_q"))}</span></label>
      <div class="field" style="margin-top:8px"><label>${esc(t("ho.notes"))}</label><textarea class="input" name="notes" maxlength="1000" placeholder="${esc(t("ho.notes_ph"))}"></textarea></div>
      <div class="field"><label>${esc(t("ho.photos"))}</label>
        <div class="ho-angles small muted">${esc(t("ho.angles"))}</div>
        <div class="row" style="gap:8px"><label class="btn btn-sm btn-outline" style="margin:0">${icon("camera", 15)} ${esc(t("form.camera"))}<input type="file" accept="image/*" capture="environment" class="sr-only" data-add="${kind}"></label>
          <label class="btn btn-sm btn-outline" style="margin:0">${icon("plus", 15)} ${esc(t("ho.pick"))}<input type="file" accept="image/*" multiple class="sr-only" data-add="${kind}"></label>
          <span class="small" data-count>${files[kind].length} / 8</span></div>
        <div class="ho-photos preview" data-prev="${kind}">${files[kind].map((f, i) => `<button type="button" data-rm="${kind}" data-i="${i}" title="${esc(t("common.delete"))}"><img src="${esc(f.url)}" alt=""></button>`).join("")}</div></div>
      ${kind === "pickup" && me.id === d.booking.renter_id ? docsCheck(kind) : ""}
      <button class="btn btn-block">${icon("check", 16)} ${esc(t("ho.save"))}</button></form>`;
  }

  function calcCard() {
    const c = d.calc; if (!c) return "";
    const isOwner = me.id === d.booking.owner_id;
    const row = (k, v, cls = "") => `<div class="sum-row ${cls}"><span>${k}</span><span>${v}</span></div>`;
    return `<div class="card card-pad ho-calc"><h3>${icon("gauge", 18)} ${esc(t("ho.calc"))}</h3>
      ${row(esc(t("ho.km_used")), `${numFmt().format(c.km_used)} ${esc(t("unit.km"))}${c.km_allowed !== null ? ` / ${numFmt().format(c.km_allowed)}` : ""}`)}
      ${c.km_over ? row(esc(t("ho.km_over", { n: c.km_over })), money(c.km_charge)) : ""}
      ${row(esc(t("ho.fuel_short")), c.fuel_short_pct ? `${c.fuel_short_pct}%${c.fuel_liters ? ` ≈ ${c.fuel_liters} ${esc(t("unit.l"))}` : ""}` : esc(t("ho.none")))}
      ${c.fuel_charge ? row(esc(t("ho.fuel_charge")), money(c.fuel_charge)) : ""}
      ${row(`<b>${esc(t("ho.extra_total"))}</b>`, `<b>${money(c.total)}</b>`, "total")}
      ${c.deposit ? row(esc(t("ho.from_deposit")), money(c.from_deposit), "sub") : ""}
      ${c.rates_missing ? `<p class="small muted">${esc(t("ho.rates_missing"))}</p>` : ""}
      ${c.new_damage ? `<div class="notice" style="margin-top:10px">${icon("flag", 15)} ${esc(t("ho.new_damage"))}</div>` : ""}
      ${c.dirty ? `<p class="small muted">${esc(t("ho.dirty"))}</p>` : ""}
      ${isOwner && (c.total > 0 || c.new_damage) ? `<button class="btn btn-sm" id="claimBtn" style="margin-top:10px">${icon("shield", 15)} ${esc(t("ho.claim"))}</button>
        <p class="small muted">${esc(t("ho.claim_hint"))}</p>` : ""}
      ${!c.total && !c.new_damage ? `<p class="small ok-ink">${icon("check", 14)} ${esc(t("ho.all_good"))}</p>` : ""}</div>`;
  }

  function draw() {
    const b = d.booking;
    document.title = `${t("ho.title")} — CarRent`;
    root.innerHTML = `<div class="ctr-top"><a class="small" href="/dashboard.html?mode=${me.id === b.owner_id ? "owner" : "renter"}#bookings">← ${esc(t("common.back"))}</a></div>
      <div class="page-head"><div><h1>${esc(t("ho.title"))}</h1><div class="muted">${esc(`${b.brand} ${b.model} ${b.year}`)} · ${fmtDate(b.start_date)} → ${fmtDate(b.end_date)} · ${esc(t("ctr.owner"))}: ${esc(b.owner_name)} · ${esc(t("ctr.renter"))}: ${esc(b.renter_name)}</div></div></div>
      <div class="notice info" style="margin-bottom:16px">${esc(t("ho.why"))}</div>
      <div class="two-col">${actCard("pickup")}${actCard("return")}</div>
      ${calcCard()}`;
    bind();
  }

  function bind() {
    $$("input[type=range].fuel-range").forEach((r) => r.addEventListener("input", () => { r.closest(".field").querySelector("[data-fuelv]").textContent = r.value + "%"; }));
    $$("[data-add]").forEach((inp) => inp.addEventListener("change", async () => {
      const k = inp.dataset.add;
      for (const f of [...inp.files]) {
        if (files[k].length >= 8) { toast(t("form.max_images", { n: 8 }), "error"); break; }
        const c = await compressImage(f, 1600); files[k].push({ file: c, url: URL.createObjectURL(c) });
      }
      inp.value = ""; keepFormAndRedraw(k);
    }));
    root.onclick = async (e) => {
      const rm = e.target.closest("[data-rm]"), ph = e.target.closest("[data-ph]"), cf = e.target.closest("[data-confirm]"), ob = e.target.closest("[data-object]");
      if (rm) { const k = rm.dataset.rm; URL.revokeObjectURL(files[k][+rm.dataset.i].url); files[k].splice(+rm.dataset.i, 1); keepFormAndRedraw(k); }
      if (ph) lightbox(d[ph.dataset.ph].photos.map((p) => ({ path: p })), +ph.dataset.i);
      try {
        const dc = $(`[data-docs="${cf?.dataset.confirm}"]`);
        if (cf && dc && !dc.checked) { toast(t("ho.docs_need"), "error"); dc.closest(".docs-check").classList.add("shake"); setTimeout(() => dc.closest(".docs-check")?.classList.remove("shake"), 450); return; }
        if (cf && await confirmBox(t("ho.confirm_q"), t("ho.confirm"))) { d = await api(`/api/bookings/${bid}/handover/${cf.dataset.confirm}/confirm`, { method: "POST", body: { agree: true, docs_checked: !!dc?.checked } }); toast(t("common.done"), "ok"); draw(); }
        if (ob) {
          const text = prompt(t("ho.object_q")); if (!text) return;
          d = await api(`/api/bookings/${bid}/handover/${ob.dataset.object}/confirm`, { method: "POST", body: { agree: false, objection: text } }); toast(t("common.done"), "ok"); draw();
        }
        if (e.target.closest("#claimBtn")) await claim();
      } catch (err) { toast(err.message, "error"); }
    };
    $$(".ho-form").forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const k = f.dataset.kind;
      if (!f.odometer_km.value) { toast(t("ho.need_odo"), "error"); return; }
      if (files[k].length < 4) { toast(t("ho.need_photos"), "error"); return; }
      if (f.damage.checked && !f.notes.value.trim()) { toast(t("ho.need_notes"), "error"); return; }
      const fd = new FormData();
      fd.append("kind", k); fd.append("odometer_km", f.odometer_km.value); fd.append("fuel_pct", f.fuel_pct.value);
      const dcf = $("[data-docs]", f);
      if (dcf && !dcf.checked) { toast(t("ho.docs_need"), "error"); return; }
      fd.append("docs_checked", dcf?.checked ? "1" : "0");
      fd.append("clean", f.clean.checked ? "1" : "0"); fd.append("damage", f.damage.checked ? "1" : "0"); fd.append("notes", f.notes.value.trim());
      files[k].forEach((x) => fd.append("photos", x.file));
      await withLoading($("button.btn-block", f), async () => {
        try { d = await api(`/api/bookings/${bid}/handover`, { method: "POST", form: fd }); files[k] = []; toast(t("ho.saved"), "ok"); draw(); }
        catch (err) { toast(err.message, "error"); }
      });
    }));
  }

  /** Forma qiymatlarini saqlagan holda rasm ro'yxatini yangilaydi */
  function keepFormAndRedraw(k) {
    const f = $(`.ho-form[data-kind="${k}"]`); if (!f) return;
    const v = { odo: f.odometer_km.value, fuel: f.fuel_pct.value, clean: f.clean.checked, dmg: f.damage.checked, notes: f.notes.value };
    draw();
    const g = $(`.ho-form[data-kind="${k}"]`);
    g.odometer_km.value = v.odo; g.fuel_pct.value = v.fuel; g.clean.checked = v.clean; g.damage.checked = v.dmg; g.notes.value = v.notes;
    g.querySelector("[data-fuelv]").textContent = v.fuel + "%";
  }

  async function claim() {
    const c = d.calc, ret = d.return;
    const parts = [];
    if (c.km_over) parts.push(t("ho.claim_km", { n: c.km_over, sum: money(c.km_charge) }));
    if (c.fuel_charge) parts.push(t("ho.claim_fuel", { pct: c.fuel_short_pct, sum: money(c.fuel_charge) }));
    if (c.new_damage) parts.push(t("ho.claim_damage", { text: ret.notes || "" }));
    const desc = `${t("ho.claim_intro")} ${parts.join("; ")}.`;
    if (!(await confirmBox(`${desc}\n\n${t("ho.claim_confirm")}`, t("ho.claim")))) return;
    await api("/api/disputes", { method: "POST", body: { booking_id: bid, type: c.new_damage ? "damage" : "fuel_mileage", description: desc.slice(0, 2000), amount: c.total || null } });
    toast(t("ho.claim_sent"), "ok");
    setTimeout(() => (location.href = "/dashboard.html?mode=owner#disputes"), 900);
  }

  await load();
  document.addEventListener("langchange", () => d && draw());
})();
