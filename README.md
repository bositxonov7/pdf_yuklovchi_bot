# 📚 Vocabulary PDF Telegram Bot

Ushbu bot **English Vocabulary in Use (Pre-intermediate and Intermediate)** kitobidan tayyorlangan 2 ta unitdan iborat so'z-tarjima jadvalli PDF fayllarni belgilangan jadval bo'yicha **faqat sizning shaxsiy Telegram chatingizga** yuborib turadi.

---

## ⏰ Yuborish Jadvali (Toshkent vaqti, `Asia/Tashkent`)
- **Kunlar:** Har hafta **yakshanba**, **seshanba**, **payshanba**
- **Vaqt:** Soat **12:00** da
- **Tartib:**
  - 15-noyabr 2026 (Yakshanba) -> 3-4 unit
  - 17-noyabr 2026 (Seshanba) -> 5-6 unit
  - 19-noyabr 2026 (Payshanba) -> 7-8 unit
  - 22-noyabr 2026 (Yakshanba) -> 9-10 unit
  - ... va 99-100 unitgacha davom etadi.
- **Qoida fayli:** `schedule.json`

---

## 🔒 Xavfsizlik va Shaxsiy Chat
1. **Faqat shaxsiy chat:** Bot guruhlarga qo'shilmaydi (agar tasodifan qo'shilsa ham avtomatik darhol chiqib ketadi).
2. **Qabul qiluvchi:** Botga shaxsiy chatda `/start` yuborsangiz, `chat_id` raqamingiz `state.json` fayliga yoziladi va barcha PDF lar shu yerga keladi.
3. **Admin cheklovi:** `.env` faylida `ADMIN_IDS` ko'rsatilgan bo'lsa, faqat shu foydalanuvchilar `/start` va `/sendnow` qila oladi.

---

## 🛡 Ishonchlilik (Reboot-Safe)
- Barcha yuborilgan PDF lar `state.json` da qayd etiladi.
- Server o'chib yonsa yoki bot ma'lum vaqt to'xtab qolsa:
  - Qayta yonganda **2 kungacha** vaqti o'tib ketgan, lekin hali yuborilmagan PDF larni o'zi topib yuboradi.
  - Hech qanday PDF **ikki marta qayta yuborilmaydi**.
- Agar jadvaldagi PDF fayli `pdfs/` papkasida bo'lmasa, bot to'xtab qolmaydi, logga xato yozib o'tkazib yuboradi.

---

## 🕹 Bot Buyruqlari
- `/start` — Botni shaxsiy chatda faollashtirish va qabul qiluvchi sifatida ro'yxatdan o'tish.
- `/status` — Yaqin kunlardagi yuborishlar holati (yuborilgan, kutilmoqda, PDF yo'q).
- `/sendnow <id>` — Sinov uchun darhol PDF yuborish (masalan: `/sendnow units-3-4` yoki `/sendnow units-11-12`).

---

## 📄 PDF Yaratish (`make_pdfs.py`)
Barcha 3 dan 100 gacha bo'lgan unitlar `units.json` ga birlashtirilgan.
- **Barcha 49 ta PDF ni bir vaqtda yaratish:**
  ```bash
  ./venv/bin/python make_pdfs.py --all
  ```
- **Alohida unitlar uchun yaratish:**
  ```bash
  ./venv/bin/python make_pdfs.py 11 12
  ```

---

## 🚀 Ubuntu VPS Serverga O'rnatish

### 1-usul: `systemd` orqali (Tavsiya etiladi)

1. **Loyiha fayllarini serverga nusxalash:**
   ```bash
   scp -r vocab_bot user@SERVER_IP:/opt/
   ```

2. **Serverga ulanish va sozlash:**
   ```bash
   ssh user@SERVER_IP
   cd /opt/vocab_bot
   ```

3. **Python virtual muhitini ochish va kutubxonalarni o'rnatish:**
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

4. **.env faylini tekshirish:**
   ```bash
   nano .env
   # BOT_TOKEN=9293656050:AAEa0XtGRcshtmkDwiVohvfHZn4k75PswQw
   # ADMIN_IDS=YOUR_TELEGRAM_ID (ixtiyoriy)
   ```

5. **Systemd servisni yoqish:**
   ```bash
   sudo cp vocab-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now vocab-bot
   ```

6. **Holat va loglarni tekshirish:**
   ```bash
   sudo systemctl status vocab-bot
   sudo journalctl -u vocab-bot -f
   ```

---

### 2-usul: `Docker` orqali

```bash
docker compose up -d --build
docker compose logs -f
```
