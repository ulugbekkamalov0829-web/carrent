/* Kabinet va admin panel uchun umumiy vizual elementlar (real ma'lumotdan chiziladi) */
"use strict";

function stat(k, v, s = "") {
  return `<div class="card stat"><div class="k">${esc(k)}</div><div class="v">${typeof v === "number" ? numFmt().format(v) : esc(v)}</div><div class="s">${s}</div></div>`;
}

/** Oylik ustunli grafik: ustun = umumiy tushum, ichida owner ulushi va platforma komissiyasi alohida rangda */
function revenueChart(monthly, { split = true } = {}) {
  const max = Math.max(1, ...monthly.map((m) => m.revenue));
  const months = t("cal.months_short").split(",");
  return `<div class="chart" role="img" aria-label="${esc(t("chart.revenue"))}">${monthly.map((m) => {
    const [, mm] = m.month.split("-");
    const h = Math.max(2, (m.revenue / max) * 100);
    const fee = m.revenue ? (m.commission / m.revenue) * 100 : 0;
    return `<div class="bar-wrap" title="${esc(m.month)}: ${money(m.revenue)} · ${esc(t("chart.bookings_n", { n: m.count }))}">
      <span class="val">${m.revenue ? shortMoney(m.revenue) : ""}</span>
      <div class="bar" style="height:${h}%">${split ? `<div class="fee" style="height:${fee}%"></div><div class="net" style="flex:1"></div>` : `<div class="net" style="flex:1"></div>`}</div>
      <span class="lbl">${esc(months[+mm - 1])}</span></div>`;
  }).join("")}</div>
  ${split ? `<div class="legend"><span><i style="background:var(--primary)"></i>${esc(t("chart.net"))}</span><span><i style="background:#93a9ec"></i>${esc(t("chart.fee"))}</span></div>` : ""}`;
}

function hbars(items, { label, value, fmt = (v) => numFmt().format(v), color = "var(--primary)" }) {
  const max = Math.max(1, ...items.map(value));
  return `<div class="hbars">${items.map((it) => `<div class="hb"><span>${esc(label(it))}</span>
    <div class="track"><div class="fill" style="width:${(value(it) / max) * 100}%;background:${color}"></div></div><b>${esc(fmt(value(it)))}</b></div>`).join("")}</div>`;
}

function statusBars(b) {
  const colors = { pending: "var(--warning)", approved: "var(--success)", completed: "var(--primary)", rejected: "var(--danger)", cancelled: "#9ca3af" };
  const total = Object.values(b).reduce((a, x) => a + x, 0) || 1;
  return `<div class="hbars">${Object.keys(colors).map((k) => `<div class="hb"><span>${esc(t("status." + k))}</span>
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
