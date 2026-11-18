# 📚 Vocabulary PDF Telegram Bot (@pdf_yukla_bot)

Ushbu bot **English Vocabulary in Use (Pre-intermediate & Intermediate)** kitobidan tayyorlangan 2 ta unitdan iborat so'z-tarjima jadvalli PDF fayllarni barcha o'rganuvchilarga taqdim etadi.

---

## 🌟 Imkoniyatlar
1. **Ochiq va Bepul:** Barcha xohlovchilar botdan to'liq va teng foydalanishi mumkin (`/start` orqali obuna bo'lishadi).
2. **Istalgan unitni yuklab olish:** Jadvalni kutmasdan, istalgan unitni darhol olish mumkin:
   - Masalan: `/unit 5`, `/unit 24`, `/unit 50`
   - Shunchaki chatga `25` deb raqam yuborilsa ham bot tushunadi va PDF ni jo'natadi!
3. **Avtomatik Dars Jadvali:**
   - **Kunlar:** Har hafta **yakshanba**, **seshanba**, **payshanba**
   - **Vaqt:** Soat **12:00** da (Toshkent vaqti)
   - **Navbat:** 3-4, 5-6, 7-8, ... 99-100 gacha.
4. **Faqat Shaxsiy Chat:** Bot guruh va kanallardan avtomatik chiqib ketadi va o'rganuvchilarga shaxsiy chatda xizmat ko'rsatadi.
5. **Reboot-Safe:** Server qayta yonganda hech qanday dars takrorlanmaydi, o'tkazib yuborilgan darslar esa avtomatik yetkaziladi.

---

## 🕹 Bot Buyruqlari

### O'rganuvchilar uchun:
- `/start` — Botga obuna bo'lish va salomlashish.
- `/unit <raqam>` — Istalgan unit PDF faylini darhol yuklab olish (masalan: `/unit 15`).
- `/list` yoki `/units` — Mavzular va unitlar mundarijasi.
- `/status` — Darslar jadvali va navbatdagi unitlar holati.
- `/help` — Foydalanish bo'yicha yordam.

### Admin uchun (`ADMIN_IDS` ga tegishli):
- `/stats` — Obunachilar soni va tizim statistikasi.
- `/sendnow <id>` — Istalgan PDF ni barcha obunachilarga darhol tarqatish (masalan: `/sendnow units-3-4`).
- `/broadcast <xabar>` — Barcha obunachilarga e'lon yoki xabar yuborish.

---

## ⏰ Jadval Sozlamalari (`schedule.json`)
```json
{
  "start": "2026-11-15",
  "weekdays": [6, 1, 3],
  "time": "12:00",
  "first_unit": 3,
  "units_per_post": 2,
  "last_unit": 100,
  "caption": "📚 Unit {a}-{b}: so'zlar va tarjimalari"
}
```

---

## ☁️ Render.com da 24/7 Uptime (Uyg'oq saqlash)
Render bepul xizmatlari 15 daqiqadan so'ng uxlab qolmasligi uchun botda ichki HTTP server (`PORT`) va keep-alive worker mavjud. 

100% kafolatli uzluksiz ishlashi uchun:
1. [cron-job.org](https://cron-job.org) dan bepul ro'yxatdan o'ting.
2. Cronjob yarating: URL manzilga `https://pdf-yuklovchi-bot.onrender.com` kiriting va har 5 daqiqaga qo'ying.

---

## 📄 PDF Fayllarni Yaratish (`make_pdfs.py`)
Barcha 49 ta PDF fayl `pdfs/` papkasida tayyor holda mavjud.
Qayta yaratish uchun:
```bash
python3 make_pdfs.py --all
```
