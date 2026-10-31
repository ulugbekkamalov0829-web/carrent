/* Batafsil ko'rish (drill-down): dashboard yoki hisobotdagi istalgan raqam, ustun yoki qator bosilganda
   o'ng tomonda oyna ochiladi va aynan shu raqam qaysi yozuvlardan tashkil topgani ko'rinadi:
   qaysi mashina (rasmi bilan), kimniki, kim ijaraga olgan, qachon, qancha, holati.
   Element: <... data-drill='{"scope":"admin","entity":"bookings","city":"Toshkent shahri","title":"..."}'>.
   Admin uchun odam ismlari uning boshqaruv sahifasiga (/admin.html#user/ID) olib boradi. */
"use strict";

/** Elementga qo'yiladigan atribut: bosilganda batafsil oyna ochiladi */
const drillAttr = (spec) => `data-drill="${esc(JSON.stringify(spec))}" role="button" tabindex="0" title="${esc(t("drill.tap"))}"`;

const Drill = {
  last: null,

  person(id, name, avatar, scope) {
    const inner = `${avatarHtml({ full_name: name, avatar }, "xs")}<span>${esc(name)}</span>`;
    return scope === "admin" ? `<a class="dr-person" href="/admin.html#user/${id}" title="${esc(t("drill.open_user"))}">${inner}</a>` : `<span class="dr-person">${inner}</span>`;
  },

  thumb(it) {
    return `<a class="dr-thumb" href="/car.html?id=${it.car_id ?? it.id}" target="_blank" rel="noopener">${carImage(it)}</a>`;
  },

  payTag(st) { return st && st !== "on_site" ? payStatusTag(st) : `<span class="tag tag-hidden">${esc(t("pay.st_on_site"))}</span>`; },

  rows: {
    bookings(it, s) {
      return `<div class="dr-row">${Drill.thumb(it)}
        <div class="dr-main"><div class="dr-title"><a href="/car.html?id=${it.car_id}" target="_blank" rel="noopener">${esc(it.brand)} ${esc(it.model)} ${it.year}</a>
          <span class="muted small">#${it.id} · ${esc(Places.label(it.city, it.district))}</span></div>
          <div class="small">${icon("calendar", 14)} ${fmtDate(it.start_date)} → ${fmtDate(it.end_date)} · ${esc(t("rep.days_n", { n: it.days }))}</div>
          <div class="dr-people"><span class="muted small">${esc(t("booking.renter"))}:</span> ${Drill.person(it.renter_id, it.renter_name, it.renter_avatar, s)}
            ${s !== "owner" ? `<span class="muted small">${esc(t("col.owner"))}:</span> ${Drill.person(it.owner_id, it.owner_name, it.owner_avatar, s)}` : ""}</div>
          ${s === "admin" && (it.renter_phone || it.owner_phone) ? `<div class="small muted">${it.renter_phone ? `☎ ${esc(fmtPhone(it.renter_phone))}` : ""} ${it.owner_phone ? `· ☎ ${esc(fmtPhone(it.owner_phone))}` : ""}</div>` : ""}
          ${it.note ? `<div class="small muted">“${esc(it.note)}”</div>` : ""}</div>
        <div class="dr-side"><b>${money(it.total_price)}</b>
          ${it.commission !== undefined ? `<div class="small muted">${esc(t("col.commission"))}: ${money(it.commission)}</div><div class="small muted">${esc(t(s === "owner" ? "col.payout" : "admin.owner_share"))}: ${money(it.owner_payout)}</div>` : ""}
          ${it.refunded ? `<div class="small" style="color:var(--success-ink)">↩ ${money(it.refunded)}</div>` : ""}
          <div class="dr-tags">${statusTag(it.status)} ${Drill.payTag(it.payment_status)}</div></div></div>`;
    },
    cars(it, s) {
      const state = !it.is_approved ? `<span class="tag tag-bad">${esc(t("car.state_moderated"))}</span>` : it.is_active ? `<span class="tag tag-ok">${esc(t("car.state_active"))}</span>` : `<span class="tag tag-hidden">${esc(t("car.state_hidden"))}</span>`;
      return `<div class="dr-row">${Drill.thumb(it)}
        <div class="dr-main"><div class="dr-title"><a href="/car.html?id=${it.id}" target="_blank" rel="noopener">${esc(it.brand)} ${esc(it.model)} ${it.year}</a>
          <span class="muted small">${esc(Places.label(it.city, it.district))}</span></div>
          ${s === "admin" ? `<div class="dr-people"><span class="muted small">${esc(t("col.owner"))}:</span> ${Drill.person(it.owner_id, it.owner_name, it.owner_avatar, s)}</div>` : ""}
          <div class="small muted">${money(it.price_per_day)} ${esc(t("car.per_day"))} · ${esc(t("drill.views_n", { n: it.views }))}${it.rating ? ` · ★ ${it.rating} (${it.reviews})` : ""}</div>
          <div class="dr-occ"><div class="track"><i style="width:${Math.min(100, it.occupancy)}%"></i></div>
            <span class="small">${esc(t("drill.occ_line", { pct: it.occupancy, busy: it.busy_days, idle: it.idle_days }))}</span></div></div>
        <div class="dr-side"><b>${money(s === "owner" ? it.payout : it.gross)}</b><div class="small muted">${esc(t("drill.trips_n", { n: it.trips }))}</div>
          <div class="dr-tags">${state}</div></div></div>`;
    },
    users(it) {
      return `<div class="dr-row"><a class="dr-thumb user" href="/admin.html#user/${it.id}">${avatarHtml(it, "lg")}</a>
        <div class="dr-main"><div class="dr-title"><a href="/admin.html#user/${it.id}">${esc(it.full_name)}</a>
          <span class="muted small">#${it.id} · ${esc(t("role." + it.role))}</span></div>
          <div class="small muted">${esc(it.email)}${it.phone ? ` · ${esc(fmtPhone(it.phone))}` : ""}</div>
          <div class="small">${esc(t("admin.activity", { c: it.cars, b: it.bookings }))}${it.region ? ` · ${esc(Places.label(it.region, it.district))}` : ""}</div></div>
        <div class="dr-side"><div class="small muted">${fmtDate(it.created_at)}</div>
          <div class="dr-tags">${it.is_active ? `<span class="tag tag-ok">${esc(t("admin.active"))}</span>` : `<span class="tag tag-bad">${esc(t("admin.blocked_one"))}</span>`}
          ${it.complaints ? `<span class="tag tag-bad">${icon("flag", 12)} ${it.complaints}</span>` : ""}</div></div></div>`;
    },
    payments(it, s) {
      const prov = it.provider === "test" ? t("pay.test_name") : it.provider === "click" ? "Click" : "Payme";
      return `<div class="dr-row">${Drill.thumb(it)}
        <div class="dr-main"><div class="dr-title"><a href="/car.html?id=${it.car_id}" target="_blank" rel="noopener">${esc(it.brand)} ${esc(it.model)} ${it.year}</a>
          <span class="muted small">${esc(t("drill.booking_n", { n: it.booking_id }))} · ${fmtDate(it.start_date)} → ${fmtDate(it.end_date)}</span></div>
          <div class="dr-people"><span class="muted small">${esc(t("drill.payer"))}:</span> ${Drill.person(it.renter_id, it.renter_name, it.renter_avatar, s)}
            ${s !== "owner" ? `<span class="muted small">${esc(t("col.owner"))}:</span> ${Drill.person(it.owner_id, it.owner_name, it.owner_avatar, s)}` : ""}</div>
          <div class="small muted">${esc(prov)} · ${esc(it.paid_at || it.created_at)}</div></div>
        <div class="dr-side"><b>${money(it.amount)}</b>${it.refund_amount ? `<div class="small" style="color:var(--success-ink)">↩ ${money(it.refund_amount)}</div>` : ""}
          <div class="dr-tags">${payStatusTag(it.status)} <a class="small" href="/receipt.html?payment=${it.id}" target="_blank" rel="noopener">${esc(t("pay.receipt"))}</a></div></div></div>`;
    },
    reviews(it, s) {
      return `<div class="dr-row">${Drill.thumb(it)}
        <div class="dr-main"><div class="dr-title"><span class="stars">${stars(it.rating)}</span>
          <span class="tag ${it.kind === "car" ? "tag-info" : "tag-pending"}">${esc(t("review.kind_" + it.kind))}</span></div>
          ${it.comment ? `<div>“${esc(it.comment)}”</div>` : ""}${it.reply ? `<div class="small muted">↳ ${esc(it.reply)}</div>` : ""}
          <div class="dr-people">${Drill.person(it.author_id, it.author_name, it.author_avatar, s)} <span class="muted">→</span>
            ${it.kind === "car" ? `<a href="/car.html?id=${it.car_id}" target="_blank" rel="noopener">${esc(it.brand)} ${esc(it.model)}</a>` : Drill.person(it.target_user_id, it.target_name, null, s)}</div></div>
        <div class="dr-side"><div class="small muted">${fmtDate(it.created_at)}</div></div></div>`;
    },
    payouts(it, s) {
      return `<div class="dr-row"><span class="dr-thumb user">${avatarHtml({ full_name: it.owner_name, avatar: it.owner_avatar }, "lg")}</span>
        <div class="dr-main"><div class="dr-title">${Drill.person(it.owner_id, it.owner_name, it.owner_avatar, s)}</div>
          ${it.note ? `<div class="small muted">${esc(it.note)}</div>` : ""}<div class="small muted">${esc(it.created_by_name || "")}</div></div>
        <div class="dr-side"><b>${money(it.amount)}</b><div class="small muted">${fmtDate(it.created_at)}</div></div></div>`;
    },
  },

  summary(e, s, d) {
    const chip = (k, v) => `<div class="dr-chip"><span>${esc(t(k))}</span><b>${v}</b></div>`;
    const S = d.summary;
    const parts = [chip("drill.count", numFmt().format(S.count))];
    if (e === "bookings") {
      parts.push(chip("drill.sum_total", money(S.total)));
      if (S.commission !== undefined) parts.push(chip("col.commission", money(S.commission)), chip(s === "owner" ? "col.payout" : "admin.owner_share", money(S.payout)));
      parts.push(chip("rep.c_days", numFmt().format(S.days)), chip("drill.cars", S.cars));
      if (s === "admin") parts.push(chip("drill.renters", S.renters), chip("drill.owners", S.owners));
    } else if (e === "cars") {
      parts.push(chip("car.state_active", S.active), chip("col.occupancy", `${S.occupancy}%`), chip(s === "owner" ? "col.payout" : "rep.c_gmv", money(s === "owner" ? S.payout : S.gross)));
    } else if (e === "payments") {
      parts.push(chip("drill.sum_total", money(S.total)));
      if (S.refunded) parts.push(chip("mypay.refunded", money(S.refunded)));
    } else if (e === "reviews" && S.avg) parts.push(chip("owner.rating", `★ ${S.avg}`));
    else if (e === "payouts") parts.push(chip("drill.sum_total", money(S.total)));
    else if (e === "users" && S.blocked) parts.push(chip("admin.blocked", S.blocked));
    return `<div class="dr-chips">${parts.join("")}</div>`;
  },

  csv(e, items) {
    const cols = { bookings: ["id", "start_date", "end_date", "days", "brand", "model", "year", "city", "renter_name", "owner_name", "total_price", "commission", "owner_payout", "status", "payment_status"],
      cars: ["id", "brand", "model", "year", "city", "owner_name", "price_per_day", "trips", "busy_days", "occupancy", "gross", "payout", "views"],
      users: ["id", "full_name", "email", "phone", "role", "cars", "bookings", "created_at", "is_active"],
      payments: ["id", "booking_id", "brand", "model", "renter_name", "owner_name", "provider", "amount", "refund_amount", "status", "paid_at"],
      reviews: ["id", "kind", "rating", "comment", "author_name", "target_name", "brand", "model", "created_at"],
      payouts: ["id", "owner_name", "amount", "note", "created_at"] }[e];
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const body = [cols.join(";"), ...items.map((it) => cols.map((c) => q(it[c])).join(";"))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" }));
    a.download = `carrent-${e}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },

  async open(spec) {
    this.close();
    this.last = spec;
    const { title = "", sub = "", ...filters } = spec;
    const bg = document.createElement("div");
    bg.className = "drawer-bg"; bg.id = "drillBg";
    bg.innerHTML = `<aside class="drawer card" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <header class="dr-head"><div><div class="small muted">${icon("search", 14)} ${esc(t("drill.kicker"))}</div><h3>${esc(title)}</h3>${sub ? `<div class="small muted">${esc(sub)}</div>` : ""}</div>
        <button class="icon-btn" data-dr-close aria-label="${esc(t("common.close"))}">${icon("close", 20)}</button></header>
      <div class="dr-body"><div class="skeleton" style="height:70px;margin-bottom:10px"></div><div class="skeleton" style="height:70px;margin-bottom:10px"></div><div class="skeleton" style="height:70px"></div></div></aside>`;
    document.body.append(bg);
    document.body.classList.add("no-scroll");
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.closest("[data-dr-close]")) this.close(); });
    $("[data-dr-close]", bg).focus();
    try {
      const d = await api("/api/drill?" + new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v !== null && v !== undefined)));
      if (!document.body.contains(bg)) return;
      const e = d.entity, s = d.scope, render = this.rows[e];
      $(".dr-body", bg).innerHTML = `${this.summary(e, s, d)}
        <div class="dr-tools">${d.items.length > 4 ? `<input class="input" id="drQ" placeholder="${esc(t("drill.filter_ph"))}" aria-label="${esc(t("drill.filter_ph"))}">` : `<span></span>`}
          ${d.items.length ? `<button class="btn btn-sm btn-outline" id="drCsv">${icon("download", 16)} ${esc(t("rep.csv"))}</button>` : ""}</div>
        <div class="dr-list">${d.items.length ? d.items.map((it) => `<div class="dr-item" data-text="${esc(JSON.stringify(Object.values(it)).toLowerCase())}">${render(it, s)}</div>`).join("")
          : `<div class="empty">${esc(t("drill.empty"))}</div>`}</div>
        ${d.more ? `<p class="small muted">${esc(t("drill.more"))}</p>` : ""}
        <p class="small muted dr-foot">${icon("info", 14)} ${esc(t("drill.foot"))}</p>`;
      $("#drQ", bg)?.addEventListener("input", (ev) => {
        const q = ev.target.value.trim().toLowerCase();
        $$(".dr-item", bg).forEach((x) => x.classList.toggle("hidden", q && !x.dataset.text.includes(q)));
      });
      $("#drCsv", bg)?.addEventListener("click", () => this.csv(e, d.items));
    } catch (err) {
      $(".dr-body", bg).innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    }
  },

  close() {
    $("#drillBg")?.remove();
    document.body.classList.remove("no-scroll");
  },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-drill]");
  if (!el) return;
  const inner = e.target.closest("a, button");
  if (inner && inner !== el && el.contains(inner)) return;   // ichidagi alohida havola o'z ishini qiladi
  e.preventDefault();
  try { Drill.open(JSON.parse(el.dataset.drill)); } catch (err) { console.error(err); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("#drillBg")) { Drill.close(); return; }
  if ((e.key === "Enter" || e.key === " ") && e.target.matches?.("[data-drill]")) { e.preventDefault(); e.target.click(); }
});
window.addEventListener("hashchange", () => Drill.close());
