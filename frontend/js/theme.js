// Sahifa chizilishidan oldin: tungi rejim va (o'rnatilgan ilovada) ekran qulfi — kontent PIN kiritilmaguncha ko'rinmaydi
try {
  if (localStorage.getItem("cr.theme") === "dark") document.documentElement.dataset.theme = "dark";
  var app = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  var pinUser = localStorage.getItem("cr.pinUser");
  var hiddenAt = +(sessionStorage.getItem("cr.hiddenAt") || 0);
  if (app && pinUser && !location.pathname.startsWith("/auth") && (sessionStorage.getItem("cr.unlocked") !== pinUser || (hiddenAt && Date.now() - hiddenAt > 60000))) {
    document.documentElement.classList.add("app-locked");
    // Himoya: biror sabab bilan (tarmoq xatosi, server uyg'onmagan) qulf oynasi chiqmasa — 8 soniyadan keyin ekranni yashirmaymiz
    setTimeout(function () {
      if (!document.querySelector(".lock-screen")) document.documentElement.classList.remove("app-locked");
    }, 8000);
  }
} catch (e) { /* maxfiy rejim */ }
