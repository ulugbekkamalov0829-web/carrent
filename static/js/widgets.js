/* Kabinet va admin panel uchun umumiy vizual elementlar (real ma'lumotdan chiziladi) */
"use strict";

/** Raqamli karta. href — havola (bo'lim) yoki drill spec (obyekt): bosilganda shu raqam tarkibi batafsil ochiladi.
    hint — "bu raqam nimani anglatadi" izohi (kartaning pastida kichik matn). */
function stat(k, v, s = "", href = "", hint = "") {
  const inner = `<div class="k">${esc(k)}</div><div class="v">${typeof v === "number" ? numFmt().format(v) : esc(v)}</div><div class="s">${s}</div>${hint ? `<div class="stat-hint">${esc(hint)}</div>` : ""}`;
  const go = `<span class="stat-go" aria-hidden="true">${icon("arrowr", 16)}</span>`;
  if (href && typeof href === "object") return `<div class="card stat stat-link" ${drillAttr(href)}>${inner}${go}</div>`;
  return href ? `<a class="card stat stat-link" href="${esc(href)}">${inner}${go}</a>` : `<div class="card stat">${inner}</div>`;
}

/** Oylik ustunli grafik: ustun = umumiy tushum, ichida owner ulushi va platforma komissiyasi alohida rangda */
function revenueChart(monthly, { split = true, drill = null } = {}) {
  const max = Math.max(1, ...monthly.map((m) => m.revenue));
  const months = t("cal.months_short").split(",");
  return `<div class="chart" role="img" aria-label="${esc(t("chart.revenue"))}">${monthly.map((m) => {
    const [, mm] = m.month.split("-");
    const h = Math.max(2, (m.revenue / max) * 100);
    const fee = m.revenue ? (m.commission / m.revenue) * 100 : 0;
    return `<div class="bar-wrap" ${drill && m.count ? drillAttr(drill(m)) : ""} title="${esc(m.month)}: ${money(m.revenue)} · ${esc(t("chart.bookings_n", { n: m.count }))}">
      <span class="val">${m.revenue ? shortMoney(m.revenue) : ""}</span>
      <div class="bar" style="height:${h}%">${split ? `<div class="fee" style="height:${fee}%"></div><div class="net" style="flex:1"></div>` : `<div class="net" style="flex:1"></div>`}</div>
      <span class="lbl">${esc(months[+mm - 1])}</span></div>`;
  }).join("")}</div>
  ${split ? `<div class="legend"><span><i style="background:var(--primary)"></i>${esc(t("chart.net"))}</span><span><i style="background:#93a9ec"></i>${esc(t("chart.fee"))}</span></div>` : ""}`;
}

function hbars(items, { label, value, fmt = (v) => numFmt().format(v), color = "var(--primary)", drill = null }) {
  const max = Math.max(1, ...items.map(value));
  return `<div class="hbars">${items.map((it) => `<div class="hb" ${drill && value(it) ? drillAttr(drill(it)) : ""}><span>${esc(label(it))}</span>
    <div class="track"><div class="fill" style="width:${(value(it) / max) * 100}%;background:${color}"></div></div><b>${esc(fmt(value(it)))}</b></div>`).join("")}</div>`;
}

function statusBars(b, drill = null) {
  const colors = { pending: "var(--warning)", approved: "var(--success)", completed: "var(--primary)", rejected: "var(--danger)", cancelled: "#9ca3af" };
  const total = Object.values(b).reduce((a, x) => a + x, 0) || 1;
  return `<div class="hbars">${Object.keys(colors).map((k) => `<div class="hb" ${drill && b[k] ? drillAttr(drill(k)) : ""}><span>${esc(t("status." + k))}</span>
    <div class="track"><div class="fill" style="width:${(b[k] / total) * 100}%;background:${colors[k]}"></div></div><b>${b[k]}</b></div>`).join("")}</div>`;
}

/** To'lov holati yorlig'i — kabinet, admin va kvitansiyada bir xil rang */
function payStatusTag(st) {
  const cls = st === "paid" || st === "refunded" ? "tag-ok" : ["refund_pending", "pending", "created"].includes(st) ? "tag-pending" : st === "failed" ? "tag-bad" : "tag-hidden";
  return `<span class="tag ${cls}">${esc(t("pay.st_" + st))}</span>`;
}

/** Bekor qilish siyosati: "3+ kun oldin — 100%" ko'rinishidagi ro'yxat (qoidalar serverdan keladi) */
function policyList(policy = [{ min_days: 3, pct: 100 }, { min_days: 1, pct: 50 }]) {
  const rows = policy.map((r, i) => {
    const next = policy[i - 1];
    const when = next ? t("policy.range", { a: r.min_days, b: next.min_days - 1 }) : t("policy.from", { n: r.min_days });
    return `<div class="policy-row"><span>${esc(when)}</span><b class="${r.pct === 100 ? "ok" : "mid"}">${r.pct}%</b></div>`;
  });
  rows.push(`<div class="policy-row"><span>${esc(t("policy.started"))}</span><b class="no">${esc(t("policy.contact_owner"))}</b></div>`);
  return `<div class="policy">${rows.join("")}</div>`;
}


/** Nizo kartochkasi: kabinetda (me = foydalanuvchi id) va admin panelda (me = null) bir xil ko'rinish */
function disputeCard(d, me, admin = false) {
  const active = ["open", "in_review"].includes(d.status);
  const stCls = { open: "tag-pending", in_review: "tag-pending", resolved: "tag-ok", rejected: "tag-bad", cancelled: "tag-hidden" }[d.status];
  const iAmOther = me && d.against_id === me, iOpened = me && d.opened_by === me;
  return `<article class="card card-pad disp ${active ? "active" : ""}">
    <div class="row" style="justify-content:space-between;align-items:flex-start">
      <div><b>${esc(t("disp.t_" + d.type))}</b> <span class="tag ${stCls}">${esc(t("disp.st_" + d.status))}</span>
        <div class="small muted">${esc(t("disp.booking"))} №${d.booking_id} · <a href="/car.html?id=${d.car_id}">${esc(d.brand)} ${esc(d.model)} ${d.year}</a>
          · ${fmtDate(d.start_date)} → ${fmtDate(d.end_date)} · ${timeAgo(d.created_at)}</div></div>
      ${d.amount ? `<div class="disp-amt"><span class="small muted">${esc(t("disp.amount"))}</span><b>${money(d.amount)}</b></div>` : ""}
    </div>
    <div class="disp-grid">
      <div class="disp-side"><span class="small muted">${esc(t("disp.opened_by"))}: <b>${admin ? `<a href="/admin.html#user/${d.opened_by}">${esc(d.opener_name)}</a>` : esc(d.opener_name)}</b></span><p>${esc(d.description)}</p></div>
      <div class="disp-side other"><span class="small muted">${esc(t("disp.answer"))} (${admin ? `<a href="/admin.html#user/${d.against_id}">${esc(d.against_name)}</a>` : esc(d.against_name)})</span>
        ${d.response ? `<p>${esc(d.response)}</p>` : iAmOther && active ? `<form class="disp-reply" data-id="${d.id}"><textarea class="input" name="text" minlength="5" maxlength="2000" required placeholder="${esc(t("disp.answer_ph"))}"></textarea>
          <button class="btn btn-sm" style="margin-top:6px">${esc(t("disp.answer_send"))}</button></form>` : `<p class="muted small">—</p>`}</div>
    </div>
    ${d.decision_note ? `<div class="disp-decision"><b>${icon("shield", 16)} ${esc(t("disp.decision"))}: ${esc(t("disp.o_" + d.outcome))}</b>
      <p>${esc(d.decision_note)}</p>${d.compensation ? `<div class="small">${esc(t("disp.comp"))}: <b>${money(d.compensation)}</b></div>` : ""}</div>` : ""}
    <div class="row" style="gap:6px;margin-top:10px">
      ${admin ? `<a class="btn btn-sm btn-outline" href="/messages.html?user=${d.opened_by}">${icon("chat", 16)} ${esc(d.opener_name)}</a>
        <a class="btn btn-sm btn-outline" href="/messages.html?user=${d.against_id}">${icon("chat", 16)} ${esc(d.against_name)}</a>
        ${d.status === "open" ? `<button class="btn btn-sm btn-outline" data-take="${d.id}">${esc(t("disp.take"))}</button>` : ""}
        ${active ? `<button class="btn btn-sm" data-resolve="${d.id}" data-a="${d.opened_by}" data-an="${esc(d.opener_name)}" data-b="${d.against_id}" data-bn="${esc(d.against_name)}">${esc(t("disp.resolve"))}</button>` : ""}`
      : `<a class="btn btn-sm btn-outline" href="/messages.html?user=${iOpened ? d.against_id : d.opened_by}&car=${d.car_id}">${icon("chat", 16)} ${esc(t("disp.chat_with"))}</a>
        ${iOpened && active ? `<button class="btn btn-sm btn-outline" data-withdraw="${d.id}">${esc(t("disp.withdraw"))}</button>` : ""}`}
    </div></article>`;
}
