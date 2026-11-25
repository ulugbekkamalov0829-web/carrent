/* Shartnoma sahifasi: o'qish, email kodi bilan imzolash, (admin) tasdiqlash, chop etish / PDF */
"use strict";
(async () => {
  await boot("");
  const me = await guard();
  const root = $("#root");
  const bookingId = Number(new URLSearchParams(location.search).get("booking"));
  let c;

  async function load() {
    try { c = await api(`/api/bookings/${bookingId}/contract`); draw(); }
    catch (e) { root.innerHTML = `<div class="empty card"><h2>${esc(t("ctr.title"))}</h2><p>${esc(e.message)}</p><a class="btn" href="/dashboard.html#bookings">${esc(t("dash.my_bookings"))}</a></div>`; }
  }

  const stTag = (st) => `<span class="tag ${st === "approved" ? "tag-ok" : st === "signed" ? "tag-info" : st === "cancelled" ? "tag-bad" : "tag-pending"}">${esc(t("ctr.st_" + st))}</span>`;
  const step = (done, label, sub) => `<li class="${done ? "done" : ""}"><span>${icon(done ? "check" : "pen", 14)}</span><div><b>${esc(label)}</b><div class="small muted">${esc(sub || "")}</div></div></li>`;

  function draw() {
    document.title = `${t("ctr.title")} ${c.number} — CarRent`;
    const back = me.role === "admin" ? "/admin.html#contracts" : `/dashboard.html?mode=${c.my_role === "owner" ? "owner" : "renter"}#bookings`;
    root.innerHTML = `<div class="ctr-top no-print">
        <a href="${back}" class="small">← ${esc(t("common.back"))}</a>
        <div class="row" style="gap:8px">${stTag(c.status)}
          <button class="btn btn-sm btn-outline" id="printBtn">${icon("download", 16)} ${esc(t("ctr.pdf"))}</button></div></div>
      <div class="ctr-layout">
        <div>${ContractDoc.html(c)}</div>
        <aside class="ctr-side no-print">
          <div class="card card-pad"><h3>${icon("doc", 18)} ${esc(t("ctr.progress"))}</h3>
            <ol class="ctr-steps">
              ${step(true, t("ctr.s_created"), fmtDate(c.created_at))}
              ${step(!!c.owner_signed_at, t("ctr.s_owner"), c.owner_signed_at || c.booking.owner_name)}
              ${step(!!c.renter_signed_at, t("ctr.s_renter"), c.renter_signed_at || c.booking.renter_name)}
              ${step(c.status === "approved", t("ctr.s_admin"), c.approved_at || t("ctr.s_admin_sub"))}
            </ol></div>
          ${c.can_sign ? `<div class="card card-pad sign-card" id="signCard"><h3>${icon("pen", 18)} ${esc(t("ctr.sign_title"))}</h3>
              <p class="small">${esc(t("ctr.sign_how"))}</p>
              <label class="check"><input type="checkbox" id="agree"><span>${esc(t("ctr.agree"))}</span></label>
              <button class="btn btn-block" id="sendCode" style="margin-top:12px">${icon("mail", 16)} ${esc(t("ctr.send_code"))}</button>
              <div id="codeArea"></div></div>` : ""}
          ${me.role === "admin" && c.status === "signed" ? `<div class="card card-pad"><h3>${icon("shield", 18)} ${esc(t("ctr.admin_check"))}</h3>
              <ul class="small check-list">${["ac1", "ac2", "ac3", "ac4"].map((k) => `<li>${esc(t("ctr." + k))}</li>`).join("")}</ul>
              <p class="small ${c.intact ? "ok-ink" : "bad-ink"}">${icon(c.intact ? "check" : "flag", 14)} ${esc(t(c.intact ? "ctr.intact" : "ctr.tampered"))}</p>
              <button class="btn btn-block btn-ok" id="approveBtn" ${c.intact ? "" : "disabled"}>${icon("check", 16)} ${esc(t("ctr.approve"))}</button></div>` : ""}
          <div class="card card-pad small muted">${icon("info", 14)} ${esc(t("ctr.legal_side"))}</div>
        </aside></div>`;
    $("#printBtn").addEventListener("click", () => window.print());
    $("#approveBtn")?.addEventListener("click", async () => {
      if (!(await confirmBox(t("ctr.approve_confirm"), t("ctr.approve")))) return;
      try { await api(`/api/admin/contracts/${c.id}/approve`, { method: "POST" }); toast(t("ctr.approved"), "ok"); load(); } catch (e) { toast(e.message, "error"); }
    });
    $("#sendCode")?.addEventListener("click", sendCode);
  }

  async function sendCode() {
    if (!$("#agree").checked) { toast(t("ctr.need_agree"), "error"); return; }
    await withLoading($("#sendCode"), async () => {
      try {
        const r = await api(`/api/contracts/${c.id}/sign/start`, { method: "POST" });
        const area = $("#codeArea");
        area.innerHTML = `<p class="small" style="margin:12px 0 6px">${esc(t("verify.sent_to", { to: r.to }))}</p>
          ${r.dev_inbox ? `<p class="small"><a href="/dev-inbox.html" target="_blank" rel="noopener">${esc(t("dev.open_inbox"))}</a></p>` : ""}
          <div id="signOtp"></div><div class="code-timer" id="signTimer"></div>
          <button class="btn btn-block btn-ok" id="signBtn" style="margin-top:10px">${icon("pen", 16)} ${esc(t("ctr.sign_btn"))}</button>`;
        const otp = otpField($("#signOtp"), () => $("#signBtn").click());
        otp.focus();
        codeTimer($("#signTimer"), r.ttl_sec);
        cooldown($("#sendCode"), r.resend_sec || 60, "otp.resend");
        $("#signBtn").addEventListener("click", async () => {
          if (otp.value.length !== 6) { otp.error(); return; }
          await withLoading($("#signBtn"), async () => {
            try {
              c = await api(`/api/contracts/${c.id}/sign`, { method: "POST", body: { code: otp.value, agree: true } });
              toast(t("ctr.signed_ok"), "ok"); draw();
            } catch (e) { otp.error(); toast(e.message, "error"); }
          });
        });
      } catch (e) { toast(e.message, "error"); }
    });
  }

  await load();
  document.addEventListener("langchange", () => c && draw());
})();
