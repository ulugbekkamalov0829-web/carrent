/* Hisobotlar: owner, ijarachi va admin uchun bitta modul.
   Davr tanlanadi -> server raqamlarni va oddiy tildagi xulosalarni qaytaradi -> bu yerda chiroyli ko'rinishda chiziladi.
   Har bir ko'rsatkich yonida "bu nima degani" izohi bor; CSV (Excel) va chop etish (PDF) tugmalari. */
"use strict";

const Reports = {
  state: { preset: "month", from: "", to: "" },

  presets() {
    const d = new Date(), y = d.getFullYear(), m = d.getMonth();
    const iso = isoDate, ago = (n) => iso(new Date(y, m, d.getDate() - n));
    return {
      week: [ago(6), iso(d)], month: [iso(new Date(y, m, 1)), iso(d)], last_month: [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))],
      d30: [ago(29), iso(d)], q: [ago(89), iso(d)], year: [iso(new Date(y, 0, 1)), iso(d)],
    };
  },

  range() {
    if (this.state.preset !== "custom") [this.state.from, this.state.to] = this.presets()[this.state.preset];
    return [this.state.from, this.state.to];
  },

  /** Hisobot ichidagi raqam bosilganda ochiladigan batafsil ro'yxat (drill.js) */
  spec(kind, entity, title, extra = {}) {
    const [from, to] = [this.cur.period.from, this.cur.period.to];
    const period = entity === "cars" ? { p_from: from, p_to: to } : { from, to };
    return { scope: kind, entity, title, sub: `${fmtDate(from)} — ${fmtDate(to)}`, ...period, ...extra };
  },

  kpiDrill(kind, code) {
    const title = t("rep.k_" + code);
    const done = { status: "done" }, lost = { status: "cancelled,rejected" };
    const m = {
      owner: { income: done, gross: done, commission: done, trips: done, rental_days: done, avg_check: done, lost, occupancy: ["cars", {}] },
      renter: { spent: done, trips: done, rental_days: done, avg_day: done, cancelled: { status: "cancelled" },
        refunds: ["payments", { status: "refunded,refund_pending", date_field: "cancelled" }] },
      admin: { gmv: done, platform_income: done, trips: done, avg_check: done, lost_rate: { ...lost, date_field: "created" },
        online_paid: ["payments", {}], refunds: ["payments", { status: "refunded,refund_pending", date_field: "cancelled" }],
        payouts: ["payouts", {}], new_users: ["users", {}], new_cars: ["cars", { date_field: "created", from: this.cur.period.from, to: this.cur.period.to }] },
    }[kind][code];
    if (!m) return null;
    const [entity, extra] = Array.isArray(m) ? m : ["bookings", m];
    return this.spec(kind, entity, title, extra);
  },

  async render(view, kind) {
    try { const saved = JSON.parse(localStorage.getItem("rep.state") || "null"); if (saved?.preset) this.state = saved; } catch {}
    const [from, to] = this.range();
    const qs = `from=${from}&to=${to}`;
    const r = await api(`/api/analytics/${kind}?${qs}`);
    this.cur = r; this.kind = kind;
    view.innerHTML = `<div class="rep">
      ${this.toolbar(kind, qs)}
      <div class="rep-period">${icon("calendar", 16)} <b>${fmtDate(r.period.from)} — ${fmtDate(r.period.to)}</b>
        <span class="muted">· ${esc(t("rep.days_n", { n: r.period.days }))} · ${esc(t("rep.compared", { a: fmtDate(r.prev.from), b: fmtDate(r.prev.to) }))}</span></div>
      <div class="print-only rep-print-head"><b>CarRent — ${esc(t("rep.title"))}: ${esc(t("rep.kind_" + kind))}</b><span>${esc(Auth.user.full_name)} · ${fmtDate(r.generated)}</span></div>
      ${this.insights(r.insights)}
      <p class="drill-note no-print">${icon("info", 14)} ${esc(t("rep.click_any"))}</p>
      <div class="stats rep-kpis">${r.kpis.map((k) => this.kpi(k)).join("")}</div>
      <div class="card card-pad rep-chart-card"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t("rep.chart_" + r.series_label))}</h3>
        <span class="small muted">${esc(t(r.series.unit === "day" ? "rep.by_day" : "rep.by_month"))}</span></div>
        ${this.chart(r.series, r.series2)}</div>
      ${this.tables(kind, r)}
      <p class="small muted rep-foot">${icon("info", 14)} ${esc(t("rep.rule"))}</p>
    </div>`;
    this.bind(view, kind);
  },

  toolbar(kind, qs) {
    const p = this.state.preset;
    return `<div class="rep-toolbar no-print">
      <div class="chips" role="group" aria-label="${esc(t("rep.period"))}">${["week", "month", "last_month", "d30", "q", "year", "custom"].map((k) =>
        `<button type="button" class="chip-btn ${p === k ? "on" : ""}" data-preset="${k}">${esc(t("rep.p_" + k))}</button>`).join("")}</div>
      <form class="rep-custom ${p === "custom" ? "" : "hidden"}" id="repCustom">
        <input class="input" type="date" id="repFrom" value="${esc(this.state.from)}" aria-label="${esc(t("rep.from"))}" required>
        <span class="muted">—</span>
        <input class="input" type="date" id="repTo" value="${esc(this.state.to)}" aria-label="${esc(t("rep.to"))}" required>
        <button class="btn btn-sm">${esc(t("rep.show"))}</button></form>
      <span class="spacer"></span>
      <a class="btn btn-sm btn-outline" href="/api/analytics/${kind}.csv?${qs}" download>${icon("download", 16)} ${esc(t("rep.csv"))}</a>
      <button type="button" class="btn btn-sm btn-outline" id="repPrint">${icon("print", 16)} ${esc(t("rep.print"))}</button>
    </div>`;
  },

  fmt(v, f) {
    if (v === null || v === undefined) return "—";
    if (f === "money") return money(v);
    if (f === "pct") return `${v}%`;
    return numFmt().format(v);
  },

  kpi(k) {
    let delta = "";
    if (k.change !== null && k.change !== undefined) {
      const up = k.change > 0, good = k.change === 0 ? null : up === k.up_good;
      delta = `<span class="delta ${good === null ? "" : good ? "good" : "bad"}">${up ? "▲" : k.change < 0 ? "▼" : "•"} ${Math.abs(k.change)}%</span>`;
    } else if (!k.prev && k.value) delta = `<span class="delta new">${esc(t("rep.new"))}</span>`;
    const d = this.kpiDrill(this.kind, k.code);
    const ICO = { income: ["wallet", "green"], gross: ["dollar", "purple"], commission: ["chart", "blue"], trips: ["car", "blue"], rental_days: ["calendar", "orange"],
      occupancy: ["gauge", "green"], avg_check: ["receipt", "purple"], lost: ["flag", "red"], spent: ["wallet", "purple"], avg_day: ["dollar", "blue"],
      refunds: ["swap", "green"], cancelled: ["close", "red"], gmv: ["dollar", "purple"], platform_income: ["trend", "green"], online_paid: ["card", "blue"],
      payouts: ["wallet", "orange"], new_users: ["users", "blue"], new_cars: ["car", "green"], lost_rate: ["flag", "red"] }[k.code] || ["chart", "blue"];
    return `<div class="card stat rep-kpi ${d ? "stat-link" : ""}" ${d ? drillAttr(d) : ""}>${d ? `<span class="stat-go" aria-hidden="true">${icon("arrowr", 16)}</span>` : ""}<div class="k"><span class="kpi-ico sm t-${ICO[1]}">${icon(ICO[0], 16)}</span>${esc(t("rep.k_" + k.code))}</div>
      <div class="v">${k.fmt === "money" ? `${esc(numFmt().format(Math.round(k.value || 0)))}<small class="unit">${esc(t("currency"))}</small>` : esc(this.fmt(k.value, k.fmt))}</div>
      <div class="s">${delta} <span class="muted">${esc(t("rep.was", { v: this.fmt(k.prev, k.fmt) }))}</span></div>
      <div class="rep-hint">${esc(t("rep.h_" + k.code))}</div></div>`;
  },

  insightText(i) {
    const p = { ...(i.params || {}) };
    const moneyKeys = i.code === "rating" ? ["sum", "prev", "fee", "market"] : ["sum", "prev", "fee", "market", "avg"];
    for (const key of moneyKeys) if (typeof p[key] === "number") p[key] = money(p[key]);
    if (p.wd !== undefined) p.wd = t("rep.wd").split(",")[p.wd];
    if (p.body) p.body = t("body." + p.body);
    return t("rep.i_" + i.code, p);
  },

  /** Xulosa qatori bosilganda — u qaysi yozuvlarga asoslanganini ochadi */
  insightDrill(i) {
    const k = this.kind, p = i.params || {}, title = this.insightText(i);
    const done = { status: "done" }, lost = { status: "cancelled,rejected", date_field: "created" };
    const m = {
      income_up: done, income_down: done, income_first: done, best_car: { car_id: p.car_id, status: "done" }, idle_car: { car_id: p.car_id },
      many_lost: lost, pending_now: { status: "pending", from: null, to: null }, rating: ["reviews", {}], compensation: done,
      renter_total: done, spent_up: done, spent_down: done, fav_body: { body: p.body, status: "done" }, cheaper_than_market: done, pricier_than_market: done,
      renter_refunds: ["payments", { status: "refunded,refund_pending", date_field: "cancelled" }], renter_review: { status: "completed", from: null, to: null },
      gmv_up: done, gmv_down: done, gmv_first: done, top_city: { city: p.city, status: "done" }, online_share: ["payments", {}], admin_lost: lost, users_growth: ["users", {}],
    }[i.code];
    if (!m) return null;
    const [entity, extra] = Array.isArray(m) ? m : ["bookings", m];
    return this.spec(k, entity, title, extra);
  },

  insights(list) {
    if (!list.length) return "";
    const ico = { good: "check", warn: "flag", info: "bulb", action: "bell" };
    return `<div class="card card-pad rep-insights"><h3>${icon("bulb", 18)} ${esc(t("rep.insights"))}</h3><ul>
      ${list.map((i) => { const dr = i.link ? null : this.insightDrill(i); return `<li class="ins ins-${i.kind} ${dr ? "ins-link" : ""}" ${dr ? drillAttr(dr) : ""}><span class="ins-ico">${icon(ico[i.kind] || "info", 16)}</span>
        <span>${esc(this.insightText(i))}${i.link ? ` <a href="${esc(i.link)}" class="no-print">${esc(t("rep.open"))} →</a>` : ""}</span>${dr ? `<span class="ins-go no-print">${icon("arrowr", 15)}</span>` : ""}</li>`; }).join("")}</ul></div>`;
  },

  chart(series, series2) {
    const months = t("cal.months_short").split(",");
    const pts = series.points.map((p) => ({ k: p.k, v: p.v, n: p.n, label: series.unit === "day" ? fmtDate(p.k).slice(0, 5) : `${months[+p.k.slice(5, 7) - 1]} ${p.k.slice(2, 4)}` }));
    const total = pts.reduce((a, p) => a + p.v, 0);
    const drill = (p) => this.spec(this.kind, "bookings", `${t("rep.chart_" + this.cur.series_label)}: ${p.label}`,
      { status: "done", from: null, to: null, ...(series.unit === "day" ? { day: p.k } : { month: p.k }) });
    const fees = series2 ? series2.points.reduce((a, p) => a + p.v, 0) : 0;
    return `${areaChart(pts, { drill, height: 240 })}
      <div class="small muted" style="margin-top:6px"><button type="button" class="link-btn" ${drillAttr(this.spec(this.kind, "bookings", t("rep.chart_all"), { status: "done" }))}>${esc(t("rep.chart_total", { sum: money(total) }))} →</button>${series2 ? ` · ${esc(t("rep.legend_fee"))}: ${money(fees)}` : ""}</div>`;
  },

  table(title, head, body, empty = "rep.no_rows") {
    return `<div class="card rep-table"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t(title))}</h3></div>
      ${body.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr>${head.map((h) => `<th>${esc(t(h))}</th>`).join("")}</tr></thead>
      <tbody>${body.map((row) => { const cells = Array.isArray(row) ? row : row.cells;
        return `<tr ${row.drill ? drillAttr(row.drill) : ""}>${cells.map((c, i) => `<td data-label="${esc(t(head[i]))}">${c}</td>`).join("")}</tr>`; }).join("")}</tbody></table></div>`
      : `<div class="empty">${esc(t(empty))}</div>`}</div>`;
  },

  statusDonut(kind, f) {
    const ks = ["completed", "approved", "pending", "cancelled", "rejected"], col = { completed: "#10b981", approved: "#3b82f6", pending: "#f59e0b", cancelled: "#9ca3af", rejected: "#ef4444" };
    const total = ks.reduce((a, k) => a + (f?.[k] || 0), 0);
    if (!total) return `<div class="card card-pad"><h3>${esc(t("rep.t_status_share"))}</h3><div class="empty">${esc(t("rep.no_rows"))}</div></div>`;
    let acc = 0;
    const arcs = ks.filter((k) => f[k]).map((k) => { const a0 = (acc / total) * 2 * Math.PI, a1 = ((acc += f[k]) / total) * 2 * Math.PI;
      const big = a1 - a0 > Math.PI ? 1 : 0, r = 42, c = 50, p = (a) => `${c + r * Math.sin(a)} ${c - r * Math.cos(a)}`;
      const d = f[k] === total ? `M ${c} ${c - r} A ${r} ${r} 0 1 1 ${c - 0.01} ${c - r}` : `M ${p(a0)} A ${r} ${r} 0 ${big} 1 ${p(a1)}`;
      return `<path d="${d}" stroke="${col[k]}" stroke-width="14" fill="none" class="arc" ${drillAttr(this.spec(kind, "bookings", `${t("rep.t_status_share")}: ${t("status." + k)}`, { status: k, date_field: "created" }))}><title>${esc(t("status." + k))}: ${f[k]}</title></path>`; }).join("");
    return `<div class="card card-pad"><h3>${esc(t("rep.t_status_share"))}</h3><div class="rep-donut"><svg viewBox="0 0 100 100" role="img" aria-label="${esc(t("rep.t_status_share"))}">${arcs}
        <text x="50" y="48" text-anchor="middle" font-size="16" font-weight="800">${total}</text><text x="50" y="62" text-anchor="middle" font-size="7" fill="#6b7280">${esc(t("rep.requests"))}</text></svg>
      <ul>${ks.filter((k) => f[k]).map((k) => `<li ${drillAttr(this.spec(kind, "bookings", `${t("rep.t_status_share")}: ${t("status." + k)}`, { status: k, date_field: "created" }))}><i style="background:${col[k]}"></i>${esc(t("status." + k))}<b>${f[k]} · ${Math.round((100 * f[k]) / total)}%</b></li>`).join("")}</ul></div></div>`;
  },

  funnel(kind, f) {
    const created = Object.values(f || {}).reduce((a, x) => a + x, 0);
    return `<div class="card card-pad"><h3>${esc(t("rep.t_funnel"))}</h3>
      ${created ? `<div class="funnel">${["pending", "approved", "completed", "rejected", "cancelled"].map((s) =>
        `<div class="fn" ${drillAttr(this.spec(kind, "bookings", `${t("rep.t_funnel")}: ${t("status." + s)}`, { status: s, date_field: "created" }))}><span>${esc(t("status." + s))}</span><div class="track"><i class="st-${s}" style="width:${(f[s] / created) * 100}%"></i></div><b>${f[s]}</b></div>`).join("")}</div>
        <p class="small muted" style="margin:10px 0 0">${esc(t("rep.funnel_note", { n: created }))}</p>` : `<div class="empty">${esc(t("rep.no_rows"))}</div>`}</div>`;
  },

  share(v, total) { return total ? `<div class="share"><i style="width:${Math.round((v / total) * 100)}%"></i></div>` : ""; },

  tables(kind, r) {
    const T = r.tables;
    if (kind === "owner") {
      const tot = T.per_car.reduce((a, c) => a + c.payout, 0);
      return this.table("rep.t_per_car", ["col.car", "rep.c_trips", "rep.c_busy", "col.occupancy", "col.revenue", "rep.c_income"],
        T.per_car.map((c) => ({ drill: this.spec(kind, "bookings", c.title, c.trips ? { car_id: c.id, status: "done" } : { car_id: c.id, date_field: "created" }), cells: [
          `<a href="/car.html?id=${c.id}">${esc(c.title)}</a><div class="small muted">${esc(c.city)}${c.rating ? ` · ★ ${c.rating}` : ""}</div>`,
          c.trips, `${c.busy_days} / ${c.busy_days + c.idle_days}`,
          `<span class="occ ${c.occupancy < 25 ? "low" : c.occupancy >= 60 ? "high" : ""}">${c.occupancy}%</span>`, money(c.gross),
          `<b>${money(c.payout)}</b>${this.share(c.payout, tot)}`] })), "rep.no_cars") + `<div class="two-col">${this.funnel(kind, T.funnel)}${this.statusDonut(kind, T.funnel)}</div>`;
    }
    if (kind === "renter") {
      const tot = T.by_body.reduce((a, x) => a + x.spent, 0);
      return `<div class="two-col">${this.table("rep.t_by_body", ["rep.c_body", "rep.c_trips", "rep.c_spent"],
          T.by_body.map((x) => ({ drill: this.spec(kind, "bookings", `${t("rep.t_by_body")}: ${t("body." + x.key)}`, { body: x.key, status: "done" }),
            cells: [esc(t("body." + x.key)), x.trips, `${money(x.spent)}${this.share(x.spent, tot)}`] })))}
        ${this.table("rep.t_by_city", ["col.city", "rep.c_trips", "rep.c_spent"], T.by_city.map((x) => ({ drill: this.spec(kind, "bookings", `${t("rep.t_by_city")}: ${x.key}`, { city: x.key, status: "done" }),
          cells: [esc(x.key), x.trips, money(x.spent)] })))}</div>
        ${this.table("rep.t_trips", ["col.car", "col.dates", "rep.c_days", "booking.total", "col.status"],
          T.trips.map((x) => ({ drill: this.spec(kind, "bookings", x.title, { car_id: x.car_id }), cells: [`<a href="/car.html?id=${x.car_id}">${esc(x.title)}</a>`, `<span class="small">${fmtDate(x.start_date)} → ${fmtDate(x.end_date)}</span>`,
            x.days, money(x.total_price), statusTag(x.status)] })))}
        <div class="two-col">${this.funnel(kind, T.funnel)}${this.statusDonut(kind, T.funnel)}</div>`;
    }
    const gmv = T.by_city.reduce((a, x) => a + x.gmv, 0);
    const f = T.funnel;
    const provName = (k) => (k === "test" ? t("pay.test_name") : k === "click" ? "Click" : "Payme");
    return `<div class="two-col">
        ${this.table("rep.t_by_city", ["col.city", "rep.c_trips", "rep.c_gmv", "rep.c_fee"],
          T.by_city.map((x) => ({ drill: this.spec(kind, "bookings", `${t("rep.t_by_city")}: ${x.key}`, { city: x.key, status: "done" }),
            cells: [esc(x.key), x.trips, `${money(x.gmv)}${this.share(x.gmv, gmv)}`, money(x.commission)] })))}
        ${this.funnel(kind, f)}
      </div>
      <div class="two-col">
        ${this.table("rep.t_top_owners", ["col.owner", "rep.c_trips", "rep.c_income", "rep.c_fee"],
          T.top_owners.map((o) => ({ drill: this.spec(kind, "bookings", o.name, { owner_id: o.id, status: "done" }),
            cells: [`<a href="/admin.html#user/${o.id}"><b>${esc(o.name)}</b></a>`, o.trips, money(o.payout), money(o.commission)] })))}
        ${this.table("rep.t_top_cars", ["col.car", "rep.c_trips", "rep.c_gmv"],
          T.top_cars.map((c) => ({ drill: this.spec(kind, "bookings", c.title, { car_id: c.id, status: "done" }),
            cells: [`<a href="/car.html?id=${c.id}">${esc(c.title)}</a><div class="small muted">${esc(c.city)}</div>`, c.trips, money(c.gmv)] })))}
      </div>
      ${this.table("rep.t_providers", ["pay.method", "rep.c_count", "pay.amount"], T.providers.map((p) => ({ drill: this.spec(kind, "payments", `${t("rep.t_providers")}: ${provName(p.key)}`, { provider: p.key }),
        cells: [esc(provName(p.key)), p.n, money(p.amount)] })), "rep.no_online")}`;
  },

  bind(view, kind) {
    const save = () => { try { localStorage.setItem("rep.state", JSON.stringify(this.state)); } catch {} };
    $$("[data-preset]", view).forEach((b) => b.addEventListener("click", () => {
      this.state.preset = b.dataset.preset;
      if (b.dataset.preset === "custom") {
        if (!this.state.from) [this.state.from, this.state.to] = this.presets().month;
        save(); $$("[data-preset]", view).forEach((x) => x.classList.toggle("on", x === b)); $("#repCustom").classList.remove("hidden"); return;
      }
      save(); this.render(view, kind).catch((e) => toast(e.message, "error"));
    }));
    $("#repCustom")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const a = $("#repFrom").value, b = $("#repTo").value;
      if (!a || !b) { toast(t("date.invalid"), "error"); return; }
      this.state = { preset: "custom", from: a <= b ? a : b, to: a <= b ? b : a };
      save(); this.render(view, kind).catch((err) => toast(err.message, "error"));
    });
    $("#repPrint")?.addEventListener("click", () => window.print());
  },
};
