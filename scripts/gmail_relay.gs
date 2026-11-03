/**
 * CarRent — Gmail ko'prigi (Google Apps Script).
 *
 * Nima uchun: Render'ning bepul tarifi SMTP portlarini (25, 465, 587) yopib qo'ygan, shuning uchun
 * server Gmail'ga to'g'ridan-to'g'ri ulana olmaydi. Bu skript sizning Gmail akkauntingizda ishlaydi
 * va server unga oddiy HTTPS so'rovi yuboradi — xat sizning Gmail'ingizdan jo'natiladi.
 * Bepul: oddiy Gmail akkaunti uchun kuniga 100 tagacha xat.
 *
 * O'rnatish:
 *  1) https://script.google.com -> "New project" (Yangi loyiha)
 *  2) Code.gs ichidagi hamma narsani o'chirib, shu faylni qo'ying
 *  3) Pastdagi TOKEN ni o'zingiz o'ylab topgan uzun maxfiy so'zga almashtiring
 *  4) Deploy -> New deployment -> turi: "Web app"
 *       Execute as: Me (o'zim)       Who has access: Anyone (hamma)
 *  5) Ruxsat so'rasa — "Allow" (Advanced -> Go to ... (unsafe) — bu o'zingizning skriptingiz)
 *  6) Berilgan "Web app URL" (https://script.google.com/macros/s/.../exec) ni Render'da
 *     EMAIL_RELAY_URL ga, TOKEN ni EMAIL_RELAY_TOKEN ga yozing.
 */
const TOKEN = "BU-YERGA-UZUN-MAXFIY-SOZ-YOZING";

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.token !== TOKEN) return out({ ok: false, error: "token" });
    if (!d.to || !d.subject) return out({ ok: false, error: "to/subject" });
    MailApp.sendEmail({ to: d.to, subject: d.subject, body: d.body || "", name: d.name || "CarRent" });
    return out({ ok: true, left: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

function doGet() {
  return out({ ok: true, service: "CarRent Gmail relay" });
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
