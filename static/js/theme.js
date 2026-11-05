// Tungi rejim sahifa chizilishidan oldin qo'llanadi (oq "miltillash" bo'lmasligi uchun)
try { if (localStorage.getItem("cr.theme") === "dark") document.documentElement.dataset.theme = "dark"; } catch (e) { /* maxfiy rejim */ }
