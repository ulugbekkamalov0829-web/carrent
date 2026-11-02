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

// ================= v7: rasmlardagidek dashboard vidjetlari =================
/** Ikonkali katta karta: rangli doira, qiymat, o'sish (▲/▼ %) va kichik grafik. href — bo'lim yoki drill spec */
function kpiCard({ label, value, sub = "", icon: ico = "chart", tone = "blue", trend = null, spark = null, href = "", hint = "" }) {
  const tr = trend === null || trend === undefined || !isFinite(trend) ? "" :
    `<span class="kpi-trend ${trend >= 0 ? "up" : "down"}">${trend >= 0 ? "▲" : "▼"} ${Math.abs(trend).toFixed(1)}%</span>`;
  const inner = `<div class="kpi-top"><span class="kpi-ico t-${tone}">${icon(ico, 22)}</span><div class="kpi-txt"><div class="k">${esc(label)}</div>
      <div class="v">${typeof value === "number" ? numFmt().format(value) : value}</div></div></div>
    <div class="kpi-sub">${tr}${sub ? `<span>${sub}</span>` : ""}</div>${spark || ""}${hint ? `<div class="stat-hint">${esc(hint)}</div>` : ""}`;
  if (href && typeof href === "object") return `<div class="card kpi stat-link" ${drillAttr(href)}>${inner}</div>`;
  return href ? `<a class="card kpi stat-link" href="${esc(href)}">${inner}</a>` : `<div class="card kpi">${inner}</div>`;
}

/** Silliq chiziqli grafik (maydoni bo'yalgan) — SVG. points: [{k, v, label}] */
function areaChart(points, { height = 220, fmt = shortMoney, color = "var(--primary)", drill = null, empty = "rep.no_chart" } = {}) {
  if (!points.length || !points.some((p) => p.v)) return `<div class="empty" style="padding:30px 10px">${esc(t(empty))}</div>`;
  const W = 640, H = height, pad = { l: 46, r: 12, t: 16, b: 28 };
  const max = Math.max(...points.map((p) => p.v)) * 1.15 || 1;
  const x = (i) => pad.l + (points.length === 1 ? (W - pad.l - pad.r) / 2 : (i * (W - pad.l - pad.r)) / (points.length - 1));
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const pts = points.map((p, i) => [x(i), y(p.v)]);
  // Catmull-Rom -> Bezier: chiziq silliq bo'ladi
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    d += ` C${p1[0] + (p2[0] - p0[0]) / 6},${p1[1] + (p2[1] - p0[1]) / 6} ${p2[0] - (p3[0] - p1[0]) / 6},${p2[1] - (p3[1] - p1[1]) / 6} ${p2[0]},${p2[1]}`;
  }
  const area = `${d} L${pts[pts.length - 1][0]},${H - pad.b} L${pts[0][0]},${H - pad.b} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max * f);
  const every = Math.ceil(points.length / 8);
  const gid = "ag" + Math.random().toString(36).slice(2, 7);
  return `<div class="area-chart"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(t("chart.revenue"))}">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".28"/><stop offset="1" stop-color="${color}" stop-opacity=".02"/></linearGradient></defs>
    ${ticks.map((v) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${pad.l - 6}" y="${y(v) + 4}" class="ytick">${esc(v ? fmt(v) : "0")}</text>`).join("")}
    <path d="${area}" fill="url(#${gid})"/><path d="${d}" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round"/>
    ${points.map((p, i) => `${i % every === 0 || i === points.length - 1 ? `<text x="${x(i)}" y="${H - 8}" class="xtick">${esc(p.label)}</text>` : ""}`).join("")}
  </svg><div class="ac-dots">${points.map((p, i) => `<button type="button" class="ac-dot" style="left:${(x(i) / W) * 100}%;top:${(y(p.v) / H) * 100}%"
      ${drill && p.n ? drillAttr(drill(p)) : ""} data-tip="${esc(`${p.label}: ${money(p.v)}${p.n !== undefined ? ` · ${t("chart.bookings_n", { n: p.n })}` : ""}`)}"></button>`).join("")}</div></div>`;
}

/** Kichik chiziq (kartadagi trend) */
function sparkline(values, color = "var(--success)") {
  if (!values.length || !values.some(Boolean)) return "";
  const W = 160, H = 40, max = Math.max(...values) || 1;
  const pts = values.map((v, i) => `${(i * W) / Math.max(1, values.length - 1)},${H - 4 - (v / max) * (H - 8)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

/** Kichik ustunlar (buyurtmalar soni) */
function miniBars(values, color = "#f59e0b") {
  if (!values.length) return "";
  const max = Math.max(1, ...values);
  return `<div class="mini-bars" aria-hidden="true">${values.map((v) => `<i style="height:${Math.max(8, (v / max) * 100)}%;background:${color}"></i>`).join("")}</div>`;
}

/** Halqa (faol/jami) */
function donut(part, total, color = "var(--primary)") {
  const r = 18, c = 2 * Math.PI * r, f = total ? part / total : 0;
  return `<svg class="donut" viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="${r}" fill="none" stroke="var(--line)" stroke-width="5"/>
    <circle cx="22" cy="22" r="${r}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c * f} ${c}" transform="rotate(-90 22 22)"/></svg>`;
}

/** O'sish foizi: oxirgi ikki qiymat bo'yicha */
const trendPct = (arr) => { const n = arr.length; if (n < 2 || !arr[n - 2]) return null; return (100 * (arr[n - 1] - arr[n - 2])) / arr[n - 2]; };

/** Bandlik taqvimi: qaysi kunlar band (qizil) va bo'sh (yashil). bookings: [{start_date, end_date, status, car_id}] */
function occCalendar(el, bookings, { cars = [], month = null } = {}) {
  let m = month || new Date(new Date().getFullYear(), new Date().getMonth(), 1), carId = "";
  const draw = () => {
    const y = m.getFullYear(), mo = m.getMonth(), days = new Date(y, mo + 1, 0).getDate(), first = (new Date(y, mo, 1).getDay() + 6) % 7;
    const act = bookings.filter((b) => ["approved", "completed"].includes(b.status) && (!carId || b.car_id === +carId));
    const pend = bookings.filter((b) => b.status === "pending" && (!carId || b.car_id === +carId));
    const total = carId ? 1 : Math.max(1, cars.length);
    const today = isoDate(new Date());
    let cells = "";
    for (let i = 0; i < first; i++) cells += `<span></span>`;
    for (let dd = 1; dd <= days; dd++) {
      const iso = isoDate(new Date(y, mo, dd));
      const n = act.filter((b) => b.start_date <= iso && b.end_date >= iso).length, p = pend.some((b) => b.start_date <= iso && b.end_date >= iso);
      const cls = n >= total ? "full" : n ? "part" : p ? "pend" : iso < today ? "past" : "free";
      cells += `<span class="oc ${cls} ${iso === today ? "today" : ""}" title="${esc(`${fmtDate(iso)} — ${t("occ.busy_n", { n, total })}`)}">${dd}</span>`;
    }
    el.innerHTML = `<div class="oc-head"><button type="button" class="icon-btn ghost" data-m="-1" aria-label="${esc(t("cal.prev"))}">${icon("arrowl", 16)}</button>
        <b>${esc(cap(t("cal.months").split(",")[mo]))} ${y}</b><button type="button" class="icon-btn ghost" data-m="1" aria-label="${esc(t("cal.next"))}">${icon("arrowr", 16)}</button>
        ${cars.length > 1 ? `<select class="input oc-car">${[`<option value="">${esc(t("occ.all_cars"))}</option>`, ...cars.map((c) => `<option value="${c.id}" ${String(c.id) === carId ? "selected" : ""}>${esc(c.brand)} ${esc(c.model)}</option>`)].join("")}</select>` : ""}</div>
      <div class="oc-grid">${t("cal.dow").split(",").map((w) => `<span class="oc-w">${esc(w)}</span>`).join("")}${cells}</div>
      <div class="oc-legend"><span><i class="full"></i>${esc(t("occ.busy"))}</span>${cars.length > 1 && !carId ? `<span><i class="part"></i>${esc(t("occ.part"))}</span>` : ""}<span><i class="pend"></i>${esc(t("occ.pending"))}</span><span><i class="free"></i>${esc(t("occ.free"))}</span></div>`;
    $$("[data-m]", el).forEach((b) => b.addEventListener("click", () => { m = new Date(m.getFullYear(), m.getMonth() + +b.dataset.m, 1); draw(); }));
    $(".oc-car", el)?.addEventListener("change", (e) => { carId = e.target.value; draw(); });
  };
  draw();
}
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
