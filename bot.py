"""
Vocabulary PDF bot.

Inglizcha lug'at kitobidan (English Vocabulary in Use, Pre-intermediate & Intermediate) tayyorlangan
PDF larni belgilangan kunlarda soat 12:00 da (Toshkent vaqti) barcha ro'yxatdan o'tgan
foydalanuvchilarning shaxsiy chatiga avtomatik yuboradi.
Shuningdek, istalgan foydalanuvchi /unit <raqam> orqali xohlagan unitni darhol yuklab olishi mumkin.
Guruhlarga qo'shilmaydi (avtomatik chiqib ketadi).

Jadval (schedule.json):
  Har hafta yakshanba, seshanba, payshanba kuni soat 12:00 da (Toshkent vaqti)
  3-4, 5-6, 7-8, 9-10, 11-12, ... 99-100 gacha.
"""
import asyncio
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import telegram.error
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    print("XATOLIK: .env faylida BOT_TOKEN ko'rsatilmagan!", file=sys.stderr)
    print("Iltimos, .env faylini oching va tokenni kiriting:", file=sys.stderr)
    print("BOT_TOKEN=9293656050:AAEa0XtGRcshtmkDwiVohvfHZn4k75PswQw", file=sys.stderr)
    sys.exit(1)

ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Asia/Tashkent"))

SCHEDULE_FILE = os.path.join(BASE, "schedule.json")
STATE_FILE = os.path.join(BASE, "state.json")
UNITS_FILE = os.path.join(BASE, "units.json")

# Unit mavzularini yuklab olish
UNITS_INFO = {}
if os.path.exists(UNITS_FILE):
    try:
        with open(UNITS_FILE, encoding="utf-8") as f:
            UNITS_INFO = json.load(f).get("units", {})
    except Exception as e:
        print(f"Ogohlantirish: units.json o'qib bo'lmadi: {e}", file=sys.stderr)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("vocab-bot")
MISSING_WARNED: set[str] = set()


# ---------- Render / Cloud Web healthcheck server ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Vocab Bot is running!")

    def log_message(self, format, *args):
        pass  # ortiqcha log chiqarmaymiz


def self_ping_worker(url: str):
    import time
    import urllib.request
    time.sleep(30)  # Server ishga tushishi uchun dastlabki kutish
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VocabBot-KeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                log.info("Keep-alive self-ping muvaffaqiyatli: status=%s", resp.status)
        except Exception as e:
            log.warning("Keep-alive self-ping ogohlantirish: %s", e)
        time.sleep(240)  # Har 4 daqiqada (Render 15 daqiqalik uyqu chegarasini ushlab qoladi)


def start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Render/Cloud health server %s-portda ishga tushdi", port)

    render_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://pdf-yuklovchi-bot.onrender.com"
    t_ping = threading.Thread(target=self_ping_worker, args=(render_url,), daemon=True)
    t_ping.start()


# ---------- holat (state) ----------
def load_state() -> dict:
    """Holatni (chats, sent) o'qiydi. Eski 'groups' kalitini ham 'chats' bilan sinxronlaydi."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            chats = data.get("chats", data.get("groups", []))
            data["chats"] = chats
            data["groups"] = chats
            if "sent" not in data:
                data["sent"] = {}
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"chats": [], "groups": [], "sent": {}}


def save_state(state: dict) -> None:
    """Holatni atomik tarzda xavfsiz saqlaydi."""
    chats = state.get("chats", state.get("groups", []))
    state["chats"] = chats
    state["groups"] = chats
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def load_schedule(horizon_days: int | None = 0, all_items: bool = False) -> list[dict]:
    """
    schedule.json qoidasi bo'yicha yuboriladigan barcha elementlar ro'yxatini qaytaradi.
    all_items=True bo'lsa barcha 100-unitgacha bo'lgan to'liq jadvalni beradi.
    horizon_days ko'rsatilsa hozirdan o'sha kuncha bo'lganlarini qaytaradi.
    """
    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        cfg = json.load(f)

    day = datetime.strptime(cfg["start"], "%Y-%m-%d").date()
    if all_items or horizon_days is None:
        until = None
    else:
        until = (datetime.now(TZ) + timedelta(days=horizon_days)).date()

    step = cfg["units_per_post"]
    unit = cfg["first_unit"]
    items = []

    while unit <= cfg["last_unit"]:
        if until is not None and day > until:
            break
        if day.weekday() in cfg["weekdays"]:
            a, b = unit, min(unit + step - 1, cfg["last_unit"])
            items.append({
                "id": f"units-{a}-{b}",
                "title": f"{a}-{b} unit",
                "date": day.isoformat(),
                "time": cfg["time"],
                "file": f"Vocabulary_Units_{a}_and_{b}.pdf",
                "caption": cfg["caption"].format(a=a, b=b),
            })
            unit += step
        day += timedelta(days=1)

    return items


def item_time(item: dict) -> datetime:
    return datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


# ---------- shaxsiy chatni ro'yxatga olish ----------
def add_chat(chat_id: int) -> None:
    state = load_state()
    chats = state.get("chats", [])
    if chat_id not in chats:
        chats.append(chat_id)
        state["chats"] = chats
        save_state(state)
        log.info("Yangi qabul qiluvchi chat qo'shildi: %s (Jami: %d)", chat_id, len(chats))


def remove_chat(chat_id: int) -> None:
    state = load_state()
    chats = state.get("chats", [])
    if chat_id in chats:
        chats.remove(chat_id)
        state["chats"] = chats
        save_state(state)
        log.info("Chat o'chirildi: %s (Qoldi: %d)", chat_id, len(chats))


def is_admin(user_id: int | None) -> bool:
    """Admin huquqlarini tekshirish."""
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


def get_unit_caption(a: int, b: int) -> str:
    title_a = UNITS_INFO.get(str(a), {}).get("title", "").replace("*", "").replace("_", "")
    title_b = UNITS_INFO.get(str(b), {}).get("title", "").replace("*", "").replace("_", "")
    lines = [
        f"📚 *English Vocabulary in Use — Unit {a} & {b}*",
        "",
        f"📖 *Unit {a}:* {title_a}" if title_a else f"📖 *Unit {a}*",
        f"📖 *Unit {b}:* {title_b}" if title_b else f"📖 *Unit {b}*",
        "",
        "💡 _Yangi so'zlar va o'zbekcha tarjimalari._",
        "📥 Boshqa unitni olish: `/unit <raqam>` (masalan: `/unit 25`)",
    ]
    return "\n".join(lines)


async def send_unit_pdf(chat_id: int, a: int, b: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Istalgan bitta foydalanuvchiga so'ralgan unit PDF faylini yuborish."""
    filename = f"Vocabulary_Units_{a}_and_{b}.pdf"
    path = os.path.join(BASE, "pdfs", filename)
    if not os.path.exists(path):
        log.warning("PDF fayl topilmadi: %s", path)
        return False

    caption = get_unit_caption(a, b)
    try:
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=filename,
                caption=caption,
                parse_mode="Markdown",
            )
        return True
    except telegram.error.BadRequest:
        # Markdown parsing muammosi bo'lsa oddiy matn bilan yuboramiz
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=filename,
                caption=f"📚 English Vocabulary in Use — Unit {a} & {b}",
            )
        return True
    except Exception as e:
        log.error("PDF yuborishda xatolik: chat=%s xato=%s", chat_id, e)
        return False


# ---------- ommaviy yuborish (schedule) ----------
async def send_item(context: ContextTypes.DEFAULT_TYPE, item: dict) -> int:
    """PDF ni barcha ro'yxatdan o'tgan shaxsiy chatlarga yuboradi."""
    state = load_state()
    path = os.path.join(BASE, "pdfs", item["file"])
    if not os.path.exists(path):
        log.error("PDF fayl mavjud emas: %s", path)
        return 0

    ok = 0
    already = set(state.get("sent", {}).get(item["id"], []))
    chats = list(state.get("chats", []))
    blocked_chats = set()

    for chat_id in chats:
        if chat_id in already:
            continue
        try:
            with open(path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=item["file"],
                    caption=item.get("caption", ""),
                )
            already.add(chat_id)
            ok += 1
            log.info("PDF yuborildi: chat=%s fayl=%s", chat_id, item["file"])
            await asyncio.sleep(0.05)  # Telegram API limitiga tushmaslik uchun
        except telegram.error.Forbidden:
            log.warning("Foydalanuvchi botni bloklagan: chat=%s", chat_id)
            blocked_chats.add(chat_id)
        except Exception:
            log.exception("Yuborib bo'lmadi: chat=%s fayl=%s", chat_id, item["file"])

    state = load_state()
    if blocked_chats:
        current_chats = [c for c in state.get("chats", []) if c not in blocked_chats]
        state["chats"] = current_chats
        state["groups"] = current_chats
    state["sent"][item["id"]] = sorted(already)
    save_state(state)
    return ok


async def check_schedule(context: ContextTypes.DEFAULT_TYPE):
    """
    Har daqiqada ishlaydi:
    - Vaqti kelgan va hali yuborilmagan PDF larni barcha obunachilarga yuboradi.
    - Takroriy yuborilmaydi (state.json tekshiriladi).
    """
    now = datetime.now(TZ)
    state = load_state()
    chats = state.get("chats", [])
    if not chats:
        return

    items = load_schedule(horizon_days=0)
    for item in items:
        itime = item_time(item)
        if now < itime:
            continue
        # 2 kundan ortiq o'tib ketgan bo'lsa yubormaymiz
        if (now - itime).total_seconds() > 2 * 86400:
            continue

        path = os.path.join(BASE, "pdfs", item["file"])
        if not os.path.exists(path):
            if item["id"] not in MISSING_WARNED:
                MISSING_WARNED.add(item["id"])
                log.error("PDF fayl yo'q, yuborilmadi: %s", item["file"])
            continue

        sent_to = set(state.get("sent", {}).get(item["id"], []))
        if any(c not in sent_to for c in chats):
            log.info("Jadval bo'yicha yuborilmoqda: %s (%s)", item["id"], item["title"])
            await send_item(context, item)


# ---------- guruhlarga qo'shilishni taqiqlash ----------
async def on_group_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruh yoki superguruhga qo'shilsa yoki xabar kelsa, darhol guruhdan chiqish."""
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        try:
            log.warning("Bot guruhga qo'shildi (ID: %s, Nom: %s). Chiqib ketilmoqda...", chat.id, chat.title)
            await context.bot.leave_chat(chat.id)
        except Exception:
            log.exception("Guruhdan chiqishda xatolik: chat_id=%s", chat.id)


# ---------- buyruqlar ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha foydalanuvchilar uchun ochiq /start buyrug'i."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id if user else None
    first_name = user.first_name if user else "O'rganuvchi"

    # Har qanday foydalanuvchini obunachi sifatida ro'yxatga olamiz
    add_chat(chat_id)

    id_hint = f"\n\n🆔 Sizning Telegram ID: `{user_id}`" if is_admin(user_id) else ""
    welcome_text = (
        f"👋 Assalomu alaykum, *{first_name}*!\n\n"
        "📚 *English Vocabulary in Use* (Pre-intermediate & Intermediate) botiga xush kelibsiz!\n\n"
        "Bu bot orqali siz ingliz tili lug'atlarini Unit 3 dan 100 gacha bo'lgan "
        "barcha mavzular bo'yicha qulay PDF formatda yuklab olishingiz mumkin.\n\n"
        "🗓 *Avtomatik dars jadvali:*\n"
        "Har hafta **yakshanba, seshanba va payshanba** kunlari soat **12:00** da (Toshkent vaqti) "
        "navbatdagi 2 ta unit PDF-fayli shu chatingizga avtomatik yuborib turiladi.\n\n"
        "📥 *Istalgan unitni hoziroq olish:*\n"
        "Jadvalni kutmasdan, istalgan unitni hoziroq olishingiz mumkin:\n"
        "• `/unit 5` — 5 va 6-unitlar lug'ati\n"
        "• `/unit 24` — 23 va 24-unitlar lug'ati\n\n"
        "📌 *Mavjud buyruqlar:*\n"
        "• `/unit <raqam>` — istalgan unitni PDF shaklida yuklab olish\n"
        "• `/list` yoki `/units` — barcha mavzular va unitlar ro'yxati\n"
        "• `/status` — darslar jadvali va navbatdagi unitlar\n"
        "• `/help` — qo'llanma" + id_hint
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def cmd_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi istalgan unitni darhol so'rab olishi uchun buyruq."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    chat_id = update.effective_chat.id
    add_chat(chat_id)

    raw_arg = " ".join(context.args).strip() if context.args else ""
    if not raw_arg:
        await update.message.reply_text(
            "📌 *Unit raqamini ko'rsating!*\n\n"
            "Masalan:\n"
            "• `/unit 5` — 5 va 6-unitlar lug'ati\n"
            "• `/unit 24` — 23 va 24-unitlar lug'ati\n\n"
            "Kitobda jami 3 dan 100 gacha unitlar mavjud.\n"
            "Barcha ro'yxatni ko'rish uchun: `/list`",
            parse_mode="Markdown",
        )
        return

    digits = "".join(ch if ch.isdigit() else " " for ch in raw_arg).split()
    if not digits:
        await update.message.reply_text(
            "⚠️ Noto'g'ri format. Iltimos, raqam kiriting. Masalan: `/unit 15`",
            parse_mode="Markdown",
        )
        return

    u = int(digits[0])
    if u < 3:
        await update.message.reply_text(
            "ℹ️ 1 va 2-unitlar kitobning kirish qismi bo'lib, lug'at darslari **Unit 3** dan boshlanadi.\n\n"
            "Birinchi darsni olish uchun: `/unit 3`",
            parse_mode="Markdown",
        )
        return
    if u > 100:
        await update.message.reply_text(
            "⚠️ Bu kitobda unitlar **3 dan 100 gacha** mavjud.\n"
            "Iltimos, 3 dan 100 gacha raqam tanlang. Masalan: `/unit 50`",
            parse_mode="Markdown",
        )
        return

    if u % 2 == 1:
        a, b = u, min(u + 1, 100)
    else:
        a, b = u - 1, u

    msg = await update.message.reply_text(f"⏳ Unit {a} & {b} tayyorlanmoqda, kuting...")
    success = await send_unit_pdf(chat_id, a, b, context)
    try:
        await msg.delete()
    except Exception:
        pass

    if not success:
        await update.message.reply_text(f"❌ Kechirasiz, Unit {a}-{b} fayli topilmadi.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha unitlar bo'limlari va mavzulari ro'yxati."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    add_chat(update.effective_chat.id)

    text = (
        "📚 *English Vocabulary in Use (Pre-intermediate & Intermediate)*\n"
        "Barcha mavjud unitlar (Unit 3 dan 100 gacha):\n\n"
        "🔤 *Learning & Words (3–10)*\n"
        "• Unit 3–4: Using a dictionary / English language words\n"
        "• Unit 5–6: Classroom language / Prefixes\n"
        "• Unit 7–8: Suffixes / Word combinations\n"
        "• Unit 9–10: Reading & Speaking / Nouns & Verbs\n\n"
        "👥 *People & Daily Life (11–30)*\n"
        "• Unit 11–12: Physical appearance / Character & Personality\n"
        "• Unit 13–14: Feelings & Emotions / Relationships & Family\n"
        "• Unit 15–16: Daily routine / Houses & Homes\n"
        "• Unit 17–18: Food & Cooking / Clothes & Fashion\n"
        "• Unit 19–20: Health & Illness / Shopping & Money\n\n"
        "🌍 *World, Travel & Leisure (31–60)*\n"
        "• Unit 31–40: Towns, Transport, Holidays, Weather, Nature\n"
        "• Unit 41–50: Work, Jobs, Education, Technology, Media\n"
        "• Unit 51–60: Free time, Sports, Cinema, Music, Travel\n\n"
        "💡 *Advanced Themes & Idioms (61–100)*\n"
        "• Unit 61–70: Feelings, Abstract concepts, Crime, Politics\n"
        "• Unit 71–80: Modifiers, Style, Connecting ideas\n"
        "• Unit 81–90: Phrasal verbs & Common idioms\n"
        "• Unit 91–100: Word building & Common mistakes\n\n"
        "📥 *Istalgan unitni olish uchun:*\n"
        "Shunchaki raqamini yozing yoki buyruq yuboring:\n"
        "Masalan: `/unit 15` yoki `/unit 45`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jadval va yuborilgan PDF lar holati."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None
    state = load_state()
    now = datetime.now(TZ)
    chats = state.get("chats", [])
    sent_count = len(state.get("sent", {}))

    lines = [
        "📊 *English Vocabulary Bot Holati*",
        f"👥 Faol o'rganuvchilar: {len(chats)} kishi",
        f"🕒 Toshkent vaqti: {now:%d.%m.%Y %H:%M}",
        f"📦 Yuborilgan darslar: {sent_count} / 49 ta",
        "",
        "🗓 *Yaqin kunlardagi darslar (soat 12:00 da):*",
    ]

    upcoming = [i for i in load_schedule(horizon_days=14) if item_time(i) >= now - timedelta(days=2)][:6]
    if not upcoming:
        lines.append("Yaqin kunlar uchun rejalashtirilgan yuborishlar mavjud emas.")
    else:
        for item in upcoming:
            t = item_time(item)
            done = len(state.get("sent", {}).get(item["id"], []))
            if done > 0:
                mark = "✅ yuborilgan"
            elif now >= t:
                mark = "⏳ navbatda"
            else:
                mark = "📅 kutilmoqda"
            lines.append(f"• `{t:%d.%m %a %H:%M}` — *{item['title']}*: {mark}")

    lines.append("\n📥 *Istalgan unitni olish:* `/unit <raqam>` (masalan: `/unit 7`)")
    if is_admin(user_id):
        lines.append("\n👑 _Admin buyruqlari:_ `/stats`, `/sendnow <id>`, `/broadcast <xabar>`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botdan foydalanish yo'riqnomasi."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    text = (
        "ℹ️ *Vocabulary Bot qo'llanmasi:*\n\n"
        "Bu bot **English Vocabulary in Use (Pre-intermediate & Intermediate)** "
        "kitobining 3-unitidan 100-unitigacha bo'lgan barcha yangi so'zlari, talaffuzi va "
        "o'zbekcha tarjimalari jamlangan PDF fayllarini taqdim etadi.\n\n"
        "📌 *Asosiy buyruqlar:*\n"
        "• `/start` — Botni qayta ishga tushirish va obunani yangilash\n"
        "• `/unit <raqam>` — Istalgan unitni PDF shaklida olish (masalan: `/unit 25`)\n"
        "• `/list` yoki `/units` — Barcha mavjud unitlar ro'yxati\n"
        "• `/status` — Darslar jadvali va navbatdagi unitlar\n"
        "• `/help` — Ushbu yordam xabari\n\n"
        "💡 *Qulaylik:* Siz hatto `/unit` deb yozmasdan ham, shunchaki raqam yuborsangiz (masalan `15`), "
        "bot avtomatik ravishda shu unit PDF ini yuboradi!\n\n"
        "🗓 *Jadval:* Har hafta **yakshanba, seshanba va payshanba** kunlari soat **12:00** da (Toshkent vaqti) "
        "yangi dars avtomatik yuboriladi."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminlar uchun bot statistikasi."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if not is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return

    state = load_state()
    chats = state.get("chats", [])
    sent_dict = state.get("sent", {})
    all_items = load_schedule(all_items=True)

    text = (
        "📈 *Admin Statistikasi:*\n\n"
        f"👥 *Jami obunachilar:* {len(chats)} ta shaxsiy chat\n"
        f"📄 *Jami tayyor PDF lar:* {len(all_items)} ta (Unit 3–100)\n"
        f"✅ *Yuborilgan juftliklar:* {len(sent_dict)} ta\n"
        f"🕒 *Server vaqti:* {datetime.now(TZ):%Y-%m-%d %H:%M:%S (%Z)}\n\n"
        "Admin boshqaruv buyruqlari:\n"
        "• `/sendnow <id>` — PDF ni barcha obunachilarga hozir yuborish\n"
        "• `/broadcast <xabar>` — barcha obunachilarga e'lon yuborish"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_sendnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sendnow <id> - sinov uchun shu zahoti barchaga yuborish (faqat admin)."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if not is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return

    all_items = {i["id"]: i for i in load_schedule(all_items=True)}

    if not context.args:
        recent_ids = [i["id"] for i in load_schedule(horizon_days=14)][:6]
        msg = (
            "Foydalanish: `/sendnow <id>`\n\n"
            "Mavjud ID lardan misollar:\n" +
            "\n".join(f"• `/sendnow {i}`" for i in recent_ids)
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    arg = context.args[0].strip()
    if not arg.startswith("units-") and "-" in arg:
        arg = f"units-{arg}"
    elif arg.isdigit():
        u = int(arg)
        if u % 2 == 1:
            a, b = u, min(u + 1, 100)
        else:
            a, b = u - 1, u
        arg = f"units-{a}-{b}"

    if arg not in all_items:
        await update.message.reply_text(f"❌ Noto'g'ri ID: `{arg}`. Masalan: `/sendnow units-3-4`", parse_mode="Markdown")
        return

    item = all_items[arg]
    path = os.path.join(BASE, "pdfs", item["file"])
    if not os.path.exists(path):
        await update.message.reply_text(f"❌ Xatolik: `{item['file']}` fayli `pdfs/` papkasida topilmadi!", parse_mode="Markdown")
        return

    state = load_state()
    state["sent"].pop(item["id"], None)
    save_state(state)

    n = await send_item(context, item)
    if n > 0:
        await update.message.reply_text(f"✅ *{item['title']}* muvaffaqiyatli {n} ta foydalanuvchiga yuborildi!", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Yuborilmadi. Obunachilar mavjud emas yoki loglarni tekshiring.")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin barcha obunachilarga e'lon yuborishi uchun."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if not is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return

    if not context.args:
        await update.message.reply_text("Foydalanish: `/broadcast <xabar matni>`", parse_mode="Markdown")
        return

    msg_text = "📢 *E'lon:*\n\n" + " ".join(context.args)
    state = load_state()
    chats = list(state.get("chats", []))

    sent = 0
    blocked = []
    for cid in chats:
        try:
            await context.bot.send_message(chat_id=cid, text=msg_text, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except telegram.error.Forbidden:
            blocked.append(cid)
        except Exception as e:
            log.warning("Broadcast xatolik chat=%s: %s", cid, e)

    if blocked:
        state["chats"] = [c for c in chats if c not in blocked]
        save_state(state)

    await update.message.reply_text(f"✅ Xabar {sent} ta foydalanuvchiga muvaffaqiyatli yetkazildi!")


async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy chatda foydalanuvchi shunchaki raqam yoki matn yuborsa qulay javob berish."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    text = (update.message.text or "").strip().lower()
    chat_id = update.effective_chat.id
    add_chat(chat_id)

    # Agar raqam kiritilgan bo'lsa (masalan "25", "unit 25", "u25")
    digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
    if digits:
        u = int(digits[0])
        if 3 <= u <= 100:
            if u % 2 == 1:
                a, b = u, min(u + 1, 100)
            else:
                a, b = u - 1, u
            msg = await update.message.reply_text(f"⏳ Unit {a} & {b} tayyorlanmoqda, kuting...")
            success = await send_unit_pdf(chat_id, a, b, context)
            try:
                await msg.delete()
            except Exception:
                pass
            if not success:
                await update.message.reply_text(f"❌ Fayl topilmadi: `Vocabulary_Units_{a}_and_{b}.pdf`")
            return
        elif u < 3:
            await update.message.reply_text("ℹ️ Lug'at darslari **Unit 3** dan boshlanadi. `/unit 3` buyrug'ini yuboring.")
            return
        elif u > 100:
            await update.message.reply_text("⚠️ Kitobda unitlar 3 dan 100 gacha mavjud. Masalan: `/unit 25`")
            return

    # Boshqa matnlar uchun yo'naltirish
    await update.message.reply_text(
        "👋 Lug'at PDF faylini yuklab olish uchun unit raqamini yozing.\n\n"
        "Masalan: `15` yoki `/unit 15`\n"
        "Barcha unitlar ro'yxati: `/list`\n"
        "Darslar jadvali: `/status`\n"
        "Yordam: `/help`",
        parse_mode="Markdown",
    )


def main():
    log.info("Bot tayyorlanmoqda...")
    port_env = os.environ.get("PORT")
    if port_env:
        try:
            start_health_server(int(port_env))
        except Exception:
            log.exception("Health serverni ishga tushirishda xatolik")

    app = Application.builder().token(BOT_TOKEN).build()

    # Buyruqlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("unit", cmd_unit))
    app.add_handler(CommandHandler("get", cmd_unit))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("units", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("sendnow", cmd_sendnow))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Guruhga qo'shilsa darhol chiqib ketish
    app.add_handler(ChatMemberHandler(on_group_activity, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, on_group_activity))

    # Shaxsiy chatda kiritilgan har qanday matn yoki raqamni tutib olish
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (~filters.COMMAND), on_private_message))

    # Har 60 soniyada jadvalni tekshirish
    app.job_queue.run_repeating(check_schedule, interval=60, first=5)

    log.info("Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
