"use strict";
/* Kirish sahifasi: neon halqa ichida 3D aylanuvchi karta.
   Old tomon — kirish / parolni tiklash / emailni tasdiqlash, orqa tomon — ro'yxatdan o'tish. */
(async () => {
  const me = await boot("", { bare: true });
  const next = new URLSearchParams(location.search).get("next");
  // Faqat sayt ichidagi manzilga qaytaramiz (open redirect hujumidan himoya)
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
  const home = (u) => safeNext || (u.role === "admin" ? "/admin.html" : "/dashboard.html");
  if (me && location.hash !== "#verify") { location.replace(home(me)); return; }
  // Meta fonda yuklanadi — tugmalar darhol ishlashi uchun kutilmaydi
  let meta = {};
  const metaP = api("/api/meta").then((m) => (meta = m)).catch(() => meta);

  // ---- Ikonkalar ----
  [["backIco", "arrowl", 16], ["chMail", "mail", 18], ["chPhone", "phone", 18]].forEach(([id, name, s]) => { $("#" + id).innerHTML = icon(name, s); });

  // ---- Chap tomon: suratlar almashinuvi ----
  const slides = $$(".slide"), dots = $$("#slideDots button");
  let cur = 0, slideTimer;
  const showSlide = (i) => {
    cur = (i + slides.length) % slides.length;
    slides.forEach((s, k) => s.classList.toggle("on", k === cur));
    dots.forEach((d, k) => { d.classList.toggle("on", k === cur); d.setAttribute("aria-label", String(k + 1)); });
    $("#slideTitle").textContent = t(`auth.slide${cur + 1}_t`);
    $("#slideText").textContent = t(`auth.slide${cur + 1}_b`);
    $(".auth-visual-inner").classList.remove("swap"); void $(".auth-visual-inner").offsetWidth; $(".auth-visual-inner").classList.add("swap");
  };
  const autoplay = () => { clearInterval(slideTimer); slideTimer = setInterval(() => showSlide(cur + 1), 6500); };
  dots.forEach((d, k) => d.addEventListener("click", () => { showSlide(k); autoplay(); }));
  autoplay();
  document.addEventListener("langchange", () => showSlide(cur));
  api("/api/reviews/latest").then(({ items }) => {
    const list = items.filter((r) => r.comment).slice(0, 5);
    if (!list.length) return;
    let i = 0;
    const draw = () => {
      const r = list[i++ % list.length];
      $("#authQuote").innerHTML = `<div class="stars">${stars(r.rating)}</div><p>“${esc(r.comment)}”</p><b>${esc(r.author)}</b> · <span>${esc(r.brand)} ${esc(r.model)}</span>`;
      $("#authQuote").classList.remove("in"); void $("#authQuote").offsetWidth; $("#authQuote").classList.add("in");
    };
    draw(); setInterval(draw, 7000);
  }).catch(() => {});

  // ---- Panellar va 3D aylanish ----
  const card = $("#card3d");
  const FRONT = { login: "#paneLogin", forgot: "#paneForgot", verify: "#paneVerify" };
  function show(name) {
    const back = name === "register";
    card.classList.toggle("signup-mode", back);
    // Ko'rinmayotgan tomon CSS'da visibility:hidden — bosilmaydi va Tab bilan fokus olmaydi
    if (!back) Object.entries(FRONT).forEach(([k, sel]) => $(sel).classList.toggle("hidden", k !== name));
    if (name === "register" && !$("#rEmail").value && $("#lLogin").value.includes("@")) $("#rEmail").value = $("#lLogin").value;
    if (name !== "forgot") resetForgot();
    if (name === "forgot" && !$("#fLogin").value && $("#lLogin").value) { setChannel($("#lLogin").value.includes("@") ? "email" : "sms"); $("#fLogin").value = $("#lLogin").value; }
    history.replaceState(null, "", location.pathname + location.search + "#" + name);
    const target = back ? "#rName" : name === "login" ? "#lLogin" : name === "forgot" ? "#fLogin" : null;
    if (target) setTimeout(() => $(target)?.focus({ preventScroll: true }), back ? 650 : 50);
  }
  $$("[data-goto]").forEach((b) => b.addEventListener("click", () => show(b.dataset.goto)));
  window.addEventListener("hashchange", () => { const h = location.hash.slice(1); if (h === "register" || (FRONT[h] && h !== "verify")) show(h); });
  bindPasswordToggles();
  // Fokusdagi maydon izohi sarlavha ostida ko'rinadi (maydonlar joyidan siljimaydi)
  const subOf = (el) => el.closest(".pane, #fStep1, #fStep2")?.querySelector(".neon-sub");
  document.addEventListener("focusin", (e) => {
    const sub = subOf(e.target), key = e.target.dataset?.hint;
    if (!sub || !key || e.target.closest("#registerForm") && key === "auth.pw_hint") return;
    if (sub.dataset.orig === undefined) sub.dataset.orig = sub.textContent;
    sub.textContent = t(key); sub.classList.add("is-hint");
  });
  document.addEventListener("focusout", (e) => {
    const sub = subOf(e.target);
    if (sub && sub.dataset.orig !== undefined) { sub.textContent = sub.dataset.orig; delete sub.dataset.orig; sub.classList.remove("is-hint"); }
  });
  metaP.then(() => {
    if (meta.dev_inbox) $$("#fInbox, #vInbox").forEach((a) => a.classList.remove("hidden"));
    // Haqiqiy rejimda ulanmagan kanal tanlanmaydi (kod hech qayerga bormaydi)
    for (const [ch, okv] of [["email", meta.email_real || meta.dev_inbox], ["sms", meta.sms_real || meta.dev_inbox]]) {
      const b = $(`#fChannel [data-ch="${ch}"]`); b.disabled = !okv; b.title = okv ? "" : t("chan.unavailable");
    }
    if (!(meta.sms_real || meta.dev_inbox) && channel === "sms") setChannel("email");
  });

  // ---- Parol qoidalari: har bir bajarilgan shart yashil bo'ladi ----
  const regPw = pwChecklist($("#rPassword"), { compact: true });
  const resetPw = pwChecklist($("#fPass"), { compact: true });
  pwGenerator($("#rPassword")); pwGenerator($("#fPass"));
  document.addEventListener("langchange", () => paintChannel());

  // ---- Xato ko'rsatish ----
  function fieldError(id, msg) {
    const input = $("#" + id), field = input.closest(".field");
    $$(".err", field).forEach((x) => x.remove());
    input.removeAttribute("aria-invalid");
    if (msg) { input.setAttribute("aria-invalid", "true"); const d = document.createElement("div"); d.className = "err"; d.textContent = msg; field.append(d); }
    return !msg;
  }

  // ---- Kirish (email yoki telefon) ----
  async function login(loginId, password, btn) {
    await withLoading(btn, async () => {
      try {
        const { user } = await api("/api/auth/login", { method: "POST", body: { login: loginId, password } });
        toast(t("auth.welcome", { name: user.full_name }), "ok");
        await Creds.save(loginId, password, user.full_name);
        location.href = Passkey.offerAfterLogin(home(user));
      } catch (e) { showFieldErrors($("#loginForm"), e); toast(e.message, "error"); $(".ring-wrap").classList.add("shake"); setTimeout(() => $(".ring-wrap").classList.remove("shake"), 450); }
    });
  }
  $("#loginForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const id = $("#lLogin").value.trim(), pw = $("#lPassword").value;
    if (!id || !pw) { toast(t("val.fill_login"), "error"); return; }
    login(id, pw, $("#loginForm button[type=submit]"));
  });

  // ---- Ro'yxatdan o'tish ----
  const reg = $("#registerForm");
  Places.bind($("#rRegion"), $("#rDistrict"), { short: true });
  document.addEventListener("langchange", () => Places.bind($("#rRegion"), $("#rDistrict"), { region: $("#rRegion").value, district: $("#rDistrict").value, short: true }));
  reg.addEventListener("submit", async (e) => {
    e.preventDefault();
    const okName = fieldError("rName", $("#rName").value.trim().length >= 3 ? "" : t("val.name"));
    const okEmail = fieldError("rEmail", /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test($("#rEmail").value.trim()) ? "" : t("val.email"));
    const okPhone = fieldError("rPhone", /^998\d{9}$/.test($("#rPhone").value.replace(/\D/g, "")) ? "" : t("val.phone"));
    const okPlace = fieldError("rRegion", $("#rRegion").value ? "" : t("place.need_region")) && fieldError("rDistrict", $("#rDistrict").value ? "" : t("place.need_district"));
    const okPw = fieldError("rPassword", regPw.valid() ? "" : regPw.firstError());
    if (!$("#rTerms").checked) { toast(t("val.terms"), "error"); return; }
    if (!(okName && okEmail && okPhone && okPlace && okPw)) return;
    await withLoading($("#registerForm button[type=submit]"), async () => {
      try {
        const { user } = await api("/api/auth/register", { method: "POST", body: {
          full_name: $("#rName").value.trim(), email: $("#rEmail").value.trim(), phone: $("#rPhone").value.trim(),
          region: $("#rRegion").value, district: $("#rDistrict").value,
          password: $("#rPassword").value, accept_terms: true, marketing_ok: false, lang: I18N.lang } });
        toast(t("auth.welcome", { name: user.full_name }), "ok");
        // Telefon/brauzer "parolni saqlaysizmi?" deb so'raydi — keyingi safar o'zi to'ldiradi
        await Creds.save($("#rEmail").value.trim(), $("#rPassword").value, user.full_name);
        await metaP;
        // Kod faqat email kanali haqiqatan ishlasa (yoki demo test qutisi bo'lsa) so'raladi
        Passkey.offerAfterLogin("");
        if (meta.email_real || meta.dev_inbox) { startVerify(user, false); return; }
        location.href = safeNext || "/dashboard.html";
      } catch (err) { showFieldErrors(reg, err); toast(err.message, "error"); }
    });
  });

  // ---- Emailni tasdiqlash ----
  const vOtp = otpField($("#vOtp"), () => $("#vConfirm").click());
  function startVerify(user, send) {
    $("#vSentTo").textContent = t("verify.sent_to", { to: user.email });
    show("verify");
    cooldown($("#vResend"), 60, "otp.resend");
    codeTimer($("#vTimer"), (meta.code_ttl_min || 3) * 60);
    $("#vChanNote").textContent = t("chan.not_real_email"); $("#vChanNote").classList.toggle("hidden", !!meta.email_real);
    if (send) api("/api/me/verify/start", { method: "POST", body: { channel: "email" } }).catch((e) => toast(e.message, "error"));
    setTimeout(() => vOtp.focus(), 650);
  }
  $("#vConfirm").addEventListener("click", async () => {
    if (vOtp.value.length !== 6) { vOtp.error(); return; }
    await withLoading($("#vConfirm"), async () => {
      try { await api("/api/me/verify/confirm", { method: "POST", body: { channel: "email", code: vOtp.value } }); toast(t("verify.done"), "ok"); location.href = safeNext || "/dashboard.html"; }
      catch (e) { vOtp.error(); toast(e.message, "error"); }
    });
  });
  $("#vResend").addEventListener("click", async () => {
    try { const r = await api("/api/me/verify/start", { method: "POST", body: { channel: "email" } }); toast(t("otp.sent"), "ok"); cooldown($("#vResend"), 60, "otp.resend"); codeTimer($("#vTimer"), r.ttl_sec || 180); }
    catch (e) { toast(e.message, "error"); }
  });
  $("#vSkip").addEventListener("click", () => (location.href = safeNext || "/dashboard.html"));

  // ---- Parolni tiklash: email yoki telefon ----
  let channel = "email", resetLogin = "";
  function paintChannel() {
    $$("#fChannel button").forEach((b) => { b.classList.toggle("on", b.dataset.ch === channel); b.setAttribute("aria-checked", b.dataset.ch === channel); });
    $("#fLoginLabel").textContent = t(channel === "email" ? "field.email" : "field.phone");
    $("#fLogin").type = channel === "email" ? "email" : "tel";
    $("#fLogin").dataset.hint = channel === "email" ? "hint.forgot_email" : "hint.forgot_phone";
    applyHints($("#paneForgot"));
  }
  function setChannel(ch) { channel = ch; paintChannel(); }
  /** Parolni tiklash oynasini boshlang'ich holatga qaytaradi: usul tanlash va manzil kiritish bosqichi */
  function resetForgot() {
    $("#fStep2").classList.add("hidden"); $("#fStep1").classList.remove("hidden");
    $("#fChanNote").classList.add("hidden"); clearInterval($("#fTimer")._timer);
    fOtp?.clear(); $("#fPass").value = ""; $("#fPass").dispatchEvent(new Event("input"));
    showCodePart();
  }
  /** Tiklash ikki qadamda: avval kod tekshiriladi, to'g'ri bo'lsa — yangi parol oynasi */
  function showCodePart() { $("#fCodePart").classList.remove("hidden"); $("#fPwPart").classList.add("hidden"); $("#fResend").classList.remove("hidden"); }
  $("#fOkIco").innerHTML = icon("check", 16);
  async function checkCode() {
    if (fOtp.value.length !== 6) { fOtp.error(); toast(t("val.code"), "error"); return; }
    await withLoading($("#fCheck"), async () => {
      try {
        await api("/api/auth/reset/check", { method: "POST", body: { login: resetLogin, code: fOtp.value } });
        $("#fCodePart").classList.add("hidden"); $("#fPwPart").classList.remove("hidden"); $("#fResend").classList.add("hidden");
        $("#fSentTo").textContent = t("forgot.new_pw_sub");
        setTimeout(() => $("#fPass").focus(), 60);
      } catch (err) { fOtp.error(); toast(err.message, "error"); }
    });
  }
  $("#fCheck").addEventListener("click", checkCode);
  $("#fOther").addEventListener("click", () => { resetForgot(); $("#fLogin").focus(); });
  $$("#fChannel button").forEach((b) => b.addEventListener("click", () => { setChannel(b.dataset.ch); $("#fLogin").value = ""; $("#fLogin").focus(); }));
  paintChannel();
  var fOtp = otpField($("#fOtp"), () => checkCode());

  async function requestCode(btn) {
    const v = $("#fLogin").value.trim();
    if (channel === "email" ? !/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v) : !/^998\d{9}$/.test(v.replace(/\D/g, ""))) {
      fieldError("fLogin", t(channel === "email" ? "val.email" : "val.phone")); return false;
    }
    fieldError("fLogin", "");
    return withLoading(btn, async () => {
      try {
        const r = await api("/api/auth/forgot", { method: "POST", body: { login: v } });
        resetLogin = v;
        $("#fSentTo").textContent = t(channel === "email" ? "forgot.sent_email" : "forgot.sent_sms", { to: v, min: r.ttl_min });
        $("#fChanNote").textContent = t(channel === "email" ? "chan.not_real_email" : "chan.not_real_sms");
        $("#fChanNote").classList.toggle("hidden", !!r.real);
        $("#fStep1").classList.add("hidden"); $("#fStep2").classList.remove("hidden"); showCodePart();
        codeTimer($("#fTimer"), r.ttl_sec || r.ttl_min * 60);
        cooldown($("#fResend"), r.resend_sec || 60, "otp.resend"); fOtp.clear(); setTimeout(() => fOtp.focus(), 60);
        return true;
      } catch (e) { toast(e.message, "error"); return false; }
    });
  }
  $("#forgotForm").addEventListener("submit", (e) => { e.preventDefault(); requestCode($("#forgotForm .btn")); });
  $("#fResend").addEventListener("click", () => { $("#fLogin").value = resetLogin; requestCode($("#fResend")).then((sent) => sent && toast(t("otp.sent"), "ok")); });
  $("#resetForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (fOtp.value.length !== 6) { fOtp.error(); toast(t("val.code"), "error"); return; }
    if (!resetPw.valid()) { fieldError("fPass", resetPw.firstError()); return; }
    await withLoading($("#resetForm .btn"), async () => {
      try {
        const { user } = await api("/api/auth/reset", { method: "POST", body: { login: resetLogin, code: fOtp.value, new_password: $("#fPass").value } });
        toast(t("forgot.done"), "ok");
        await Creds.save(user.email, $("#fPass").value, user.full_name);
        location.href = home(user);
      } catch (err) {
        showFieldErrors($("#resetForm"), err); toast(err.message, "error");
        if (err.status === 400 && !err.errors?.length) { showCodePart(); fOtp.clear(); fOtp.error(); }   // kod eskirgan bo'lsa — qaytadan
      }
    });
  });

  // ---- Saqlangan parol bilan avtomatik to'ldirish va barmoq izi bilan kirish ----
  Creds.fill($("#lLogin"), $("#lPassword"));
  // Barmoq izi bilan kirish — faqat o'rnatilgan ilovada; saytda har safar email va parol
  if (new URLSearchParams(location.search).get("again")) toast(t("visit.again"), "");
  if (IS_APP && Passkey.supported()) {
    $("#passkeyBtn").classList.remove("hidden");
    $("#passkeyBtn").addEventListener("click", async (e) => {
      await withLoading(e.currentTarget, async () => {
        try { const { user } = await Passkey.login(); toast(t("auth.welcome", { name: user.full_name }), "ok"); location.href = home(user); }
        catch (err) { if (err.name !== "NotAllowedError" && err.name !== "AbortError") toast(err.message, "error"); }
      });
    });
    // O'rnatilgan ilova (PWA) va oldin barmoq izi yoqilgan qurilma — darhol so'raymiz (bank ilovalari kabi)
    // Shu telefonda barmoq izi yoqilgan bo'lsa — kirish oynasi ochilishi bilan telefonning barmoq izi oynasi chiqadi (bank ilovalari kabi)
    if (Passkey.enabledHere() && ["", "login"].includes(location.hash.slice(1))) setTimeout(() => $("#passkeyBtn").click(), 450);
  }

  // ---- Boshlang'ich panel ----
  const start = location.hash.slice(1);
  if (start === "verify" && me) startVerify(me, true);
  else show(start === "register" || (FRONT[start] && start !== "verify") ? start : "login");
})();
