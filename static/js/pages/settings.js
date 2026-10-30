"use strict";
(async () => {
  await boot("settings");
  await guard("user", "admin");
  const meta = await api("/api/meta").catch(() => ({}));
  const body = $("#setBody");
  const SECTIONS = [["profile", "set.profile", "user"], ["verify", "set.verify", "shield"], ["security", "set.security", "lock"],
    ["notifications", "set.notifications", "bell"], ["privacy", "set.privacy", "eye"], ["language", "set.language", "globe"], ["danger", "set.danger", "trash"]];
  const u = () => Auth.user;
  const can = { email: meta.email_real || meta.dev_inbox, sms: meta.sms_real || meta.dev_inbox };

  function nav() {
    $("#setNav").setAttribute("aria-label", t("nav.settings"));
    $("#setNav").innerHTML = SECTIONS.filter(([k]) => k !== "danger" || u().role !== "admin")
      .map(([k, key, ico]) => `<a href="#${k}" class="${k === "danger" ? "danger" : ""}" data-sec="${k}">${icon(ico, 18)}${esc(t(key))}</a>`).join("");
  }
  const card = (id, title, sub, inner, cls = "") => `<section class="card card-pad ${cls}" id="${id}"><div class="set-head"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div></div>${inner}</section>`;
  const vTag = (ok) => ok ? `<span class="verified">${icon("check", 13)} ${esc(t("verify.ok"))}</span>` : `<span class="tag tag-pending">${esc(t("verify.no"))}</span>`;

  function draw() {
    nav();
    const me = u(), p = me.notify_prefs || {};
    body.innerHTML =
      card("profile", t("set.profile"), t("set.profile_sub"), `
        <div class="avatar-edit">${avatarHtml(me)}<div><label class="btn btn-outline btn-sm" for="avFile" style="margin:0">${icon("camera", 16)} ${esc(t("set.avatar_pick"))}</label>
          <input type="file" id="avFile" accept="image/jpeg,image/png,image/webp" class="sr-only"><div class="hint">${esc(t("hint.avatar"))}</div></div></div>
        <form id="pForm" novalidate style="max-width:620px">
          <div class="field"><label for="pn">${esc(t("field.full_name"))}</label><input class="input" id="pn" name="full_name" value="${esc(me.full_name)}" required data-hint="hint.full_name"></div>
          <div class="grid-2"><div class="field"><label for="pp">${esc(t("field.phone"))}</label><input class="input" type="tel" id="pp" name="phone" value="${esc(me.phone || "")}" required placeholder="+998 90 123 45 67" data-hint="hint.phone_change"></div>
          <div class="field"><label for="pr">${esc(t("field.region"))}</label><input class="input" id="pr" name="region" value="${esc(me.region || "")}" placeholder="Toshkent" data-hint="hint.region"></div></div>
          <button class="btn">${esc(t("common.save"))}</button></form>`) +
      card("verify", t("set.verify"), t("set.verify_sub"), `
        <div class="status-row"><span class="ico-box">${icon("mail")}</span><div class="grow"><b>${esc(me.email)}</b><span class="small muted">${esc(t("field.email"))}</span></div>
          ${vTag(me.email_verified)}${me.email_verified ? "" : `<button class="btn btn-sm" data-vstart="email" ${can.email ? "" : "disabled"}>${esc(t("verify.send"))}</button>`}
          <button class="btn btn-sm btn-outline" id="emailChangeBtn" ${can.email ? "" : "disabled"}>${esc(t("set.change_email"))}</button>
          <div class="verify-box hidden" id="vbox-email"></div></div>
        <div class="status-row"><span class="ico-box">${icon("phone")}</span><div class="grow"><b>${esc(me.phone || "—")}</b><span class="small muted">${esc(t("field.phone"))}</span></div>
          ${vTag(me.phone_verified)}${me.phone_verified || !me.phone ? "" : `<button class="btn btn-sm" data-vstart="sms" ${can.sms ? "" : "disabled"}>${esc(t("verify.send_sms"))}</button>`}
          <div class="verify-box hidden" id="vbox-sms"></div></div>
        ${!can.email || !can.sms ? `<p class="small muted" style="margin:10px 0 0">${esc(t(!can.email ? "set.channels_off" : "set.sms_off"))}</p>` : ""}
        <div class="verify-box hidden" id="emailChangeBox" style="margin-top:12px"></div>`) +
      card("security", t("set.security"), t("set.security_sub"), `
        <form id="pwForm" novalidate style="max-width:520px">
          <div class="field"><label for="op">${esc(t("sec.current"))}</label><div class="pw-wrap"><input class="input" type="password" id="op" name="old_password" autocomplete="current-password" required><button type="button" class="pw-eye" data-pw="op"></button></div></div>
          <div class="field"><label for="np">${esc(t("sec.new"))}</label><div class="pw-wrap"><input class="input" type="password" id="np" name="new_password" autocomplete="new-password" required minlength="12" data-hint="auth.pw_hint"><button type="button" class="pw-eye" data-pw="np"></button></div></div>
          <button class="btn">${esc(t("sec.update"))}</button><p class="small muted" style="margin-top:8px">${esc(t("set.pw_note"))}</p></form>
        <h3 style="margin-top:22px">${esc(t("set.sessions"))}</h3><p class="small muted">${esc(t("set.sessions_sub"))}</p>
        <div id="sessions"><div class="skeleton" style="height:80px"></div></div>
        <button class="btn btn-outline btn-sm" id="logoutAll" style="margin-top:10px">${esc(t("set.logout_all"))}</button>`) +
      card("notifications", t("set.notifications"), t("set.notifications_sub"), `
        <form id="nForm">
          ${sw("email_booking", p.email_booking, "set.n_email_booking", "set.n_email_booking_d", !can.email)}
          ${sw("email_messages", p.email_messages, "set.n_email_messages", "set.n_email_messages_d", !can.email)}
          ${sw("sms_booking", p.sms_booking, "set.n_sms_booking", "set.n_sms_booking_d", !can.sms)}
          ${!meta.email_real || !meta.sms_real ? `<p class="small muted" style="margin:8px 0 0">${esc(t(meta.dev_inbox ? "set.n_dev" : "set.n_off"))}</p>` : ""}
        </form>`) +
      card("privacy", t("set.privacy"), t("set.privacy_sub"), `
        <form id="prForm">${sw("show_phone", me.show_phone, "set.show_phone", "set.show_phone_d")}${sw("marketing_ok", me.marketing_ok, "set.marketing", "set.marketing_d")}</form>`) +
      card("language", t("set.language"), t("set.language_sub"), `<div class="lang-cards">${I18N.langs.map((l) =>
        `<button type="button" data-setlang="${l}" class="${l === I18N.lang ? "on" : ""}"><b>${l.toUpperCase()}</b>${esc(I18N.names[l])}</button>`).join("")}</div>`) +
      (me.role === "admin" ? "" : card("danger", t("set.danger"), t("set.danger_sub"), `
        <form id="delForm" novalidate style="max-width:520px"><div class="field"><label for="dp">${esc(t("field.password"))}</label>
          <input class="input" type="password" id="dp" autocomplete="current-password" required data-hint="hint.delete"></div>
          <button class="btn btn-danger">${icon("trash", 16)} ${esc(t("set.delete"))}</button></form>`, "danger-zone"));
    applyHints(body); bindPasswordToggles(body);
    bind(); loadSessions(); spy();
    if (location.hash) $(location.hash)?.scrollIntoView();
  }
  function sw(name, on, tKey, dKey, disabled = false) {
    return `<label class="switch"><span class="txt"><b>${esc(t(tKey))}</b><span>${esc(t(dKey))}</span></span>
      <input type="checkbox" name="${name}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}></label>`;
  }

  async function savePrefs() {
    const me = u(), n = $("#nForm"), pr = $("#prForm");
    const bodyData = { show_phone: pr.show_phone.checked, marketing_ok: pr.marketing_ok.checked,
      email_booking: n.email_booking.checked, email_messages: n.email_messages.checked, sms_booking: n.sms_booking.checked };
    try { const r = await api("/api/me/prefs", { method: "PUT", body: bodyData }); Object.assign(me, r.user); toast(t("common.saved"), "ok"); }
    catch (err) { toast(err.message, "error"); }
  }

  // Kod kiritish bloki (tasdiqlash yoki email almashtirish uchun)
  function codeBox(box, sentTo, onSubmit, onResend) {
    box.classList.remove("hidden");
    box.innerHTML = `<p class="small" style="margin-top:0">${esc(t("verify.sent_to", { to: sentTo }))}</p><div class="otp-host"></div>
      <div class="row" style="margin-top:12px"><button class="btn btn-sm" data-ok>${esc(t("verify.confirm"))}</button>
      <button type="button" class="linkbtn" data-resend>${esc(t("otp.resend"))}</button>
      ${meta.dev_inbox ? `<a class="linkbtn" href="/dev-inbox.html" target="_blank" rel="noopener">${esc(t("dev.open_inbox"))}</a>` : ""}</div>`;
    const otp = otpField($(".otp-host", box), () => $("[data-ok]", box).click());
    otp.focus();
    cooldown($("[data-resend]", box), 60, "otp.resend");
    $("[data-ok]", box).addEventListener("click", async () => {
      if (otp.value.length !== 6) { otp.error(); return; }
      try { await onSubmit(otp.value); } catch (err) { otp.error(); toast(err.message, "error"); }
    });
    $("[data-resend]", box).addEventListener("click", async () => {
      try { await onResend(); toast(t("otp.sent"), "ok"); cooldown($("[data-resend]", box), 60, "otp.resend"); } catch (err) { toast(err.message, "error"); }
    });
  }

  function bind() {
    $("#pForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = formData(e.target);
      try { const r = await api("/api/auth/me", { method: "PUT", body: { full_name: d.full_name, phone: d.phone, region: d.region || null } });
        const phoneChanged = r.user.phone !== u().phone; Object.assign(Auth.user, r.user); toast(t(phoneChanged ? "set.phone_reverify" : "common.saved"), "ok"); renderNavInner(); draw(); }
      catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
    });
    $("#avFile").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      if (f.size > 10 * 1024 * 1024) { toast(t("img.too_big", { n: 10 }), "error"); return; }
      const fd = new FormData(); fd.append("avatar", await compressImage(f, 800));
      try { const r = await api("/api/me/avatar", { method: "POST", form: fd }); Object.assign(Auth.user, r.user); toast(t("common.saved"), "ok"); renderNavInner(); draw(); }
      catch (err) { toast(err.message, "error"); }
    });
    $$("[data-vstart]").forEach((b) => b.addEventListener("click", async () => {
      const ch = b.dataset.vstart;
      const start = () => api("/api/me/verify/start", { method: "POST", body: { channel: ch } });
      try {
        const r = await withLoading(b, start);
        codeBox($("#vbox-" + ch), r.sent_to, async (code) => {
          const res = await api("/api/me/verify/confirm", { method: "POST", body: { channel: ch, code } });
          Object.assign(Auth.user, res.user); toast(t("verify.done"), "ok"); draw();
        }, start);
      } catch (err) { toast(err.message, "error"); }
    }));
    $("#emailChangeBtn").addEventListener("click", () => {
      const box = $("#emailChangeBox"); box.classList.remove("hidden");
      box.innerHTML = `<form id="ecForm" novalidate><div class="grid-2"><div class="field"><label for="ecE">${esc(t("set.new_email"))}</label><input class="input" type="email" id="ecE" required placeholder="new@example.com" data-hint="hint.new_email"></div>
        <div class="field"><label for="ecP">${esc(t("field.password"))}</label><input class="input" type="password" id="ecP" required autocomplete="current-password" data-hint="hint.confirm_pw"></div></div>
        <button class="btn btn-sm">${esc(t("verify.send"))}</button></form>`;
      applyHints(box); $("#ecE").focus();
      $("#ecForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const start = () => api("/api/me/email/start", { method: "POST", body: { new_email: $("#ecE").value.trim(), password: $("#ecP").value } });
        try {
          const r = await withLoading($("#ecForm .btn"), start);
          codeBox(box, r.sent_to, async (code) => {
            const res = await api("/api/me/email/confirm", { method: "POST", body: { code } });
            Object.assign(Auth.user, res.user); toast(t("set.email_changed"), "ok"); renderNavInner(); draw();
          }, start);
        } catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
      });
    });
    $("#pwForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("/api/auth/change-password", { method: "POST", body: formData(e.target) }); e.target.reset(); toast(t("sec.updated"), "ok"); loadSessions(); }
      catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
    });
    $("#logoutAll").addEventListener("click", async () => {
      if (!(await confirmBox(t("set.logout_all_confirm"), t("common.yes")))) return;
      try { await api("/api/me/logout-all", { method: "POST" }); toast(t("set.logged_out_all"), "ok"); loadSessions(); } catch (err) { toast(err.message, "error"); }
    });
    $$("#nForm input, #prForm input").forEach((i) => i.addEventListener("change", savePrefs));
    $$("[data-setlang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.setlang)));
    $("#delForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!$("#dp").value) { toast(t("val.password"), "error"); return; }
      if (!(await confirmBox(t("set.delete_confirm"), t("set.delete"), true))) return;
      try { await api("/api/me/delete", { method: "POST", body: { password: $("#dp").value } }); toast(t("set.deleted"), "ok"); setTimeout(() => (location.href = "/"), 900); }
      catch (err) { toast(err.message, "error"); }
    });
  }

  function device(ua) {
    ua = ua || "";
    const os = /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iOS" : /Windows/i.test(ua) ? "Windows" : /Mac OS/i.test(ua) ? "macOS" : /Linux/i.test(ua) ? "Linux" : "";
    const br = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "";
    return [br, os].filter(Boolean).join(" · ") || t("set.unknown_device");
  }
  async function loadSessions() {
    const { items } = await api("/api/me/sessions");
    $("#sessions").innerHTML = items.map((s) => `<div class="session"><span class="ico-box">${icon(/Android|iPhone/i.test(s.user_agent || "") ? "phone" : "grid")}</span>
      <div class="grow"><b>${esc(device(s.user_agent))}</b><span class="small muted">${esc(s.ip || "")} · ${esc(t("set.last_seen"))}: ${timeAgo(s.last_seen)}</span></div>
      ${s.current ? `<span class="tag tag-ok">${esc(t("set.this_device"))}</span>` : `<button class="btn btn-sm btn-outline" data-revoke="${esc(s.id)}">${esc(t("set.revoke"))}</button>`}</div>`).join("");
    $$("[data-revoke]").forEach((b) => b.addEventListener("click", async () => {
      try { await api(`/api/me/sessions/${encodeURIComponent(b.dataset.revoke)}`, { method: "DELETE" }); toast(t("common.done"), "ok"); loadSessions(); } catch (err) { toast(err.message, "error"); }
    }));
  }
  // Chap menyu: ko'rinib turgan bo'limni belgilash
  function spy() {
    const links = $$("#setNav a");
    const io = new IntersectionObserver((ents) => ents.forEach((en) => {
      if (en.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.dataset.sec === en.target.id));
    }), { rootMargin: "-30% 0px -60% 0px" });
    $$(".settings-body > section").forEach((s) => io.observe(s));
  }
  draw();
  document.addEventListener("langchange", draw);
})();
