"""
Vocabulary PDF bot.

Inglizcha lug'at kitobidan (English Vocabulary in Use, Pre-intermediate) tayyorlangan
PDF larni belgilangan kunlarda soat 12:00 da (Toshkent vaqti) faqat shaxsiy chatga yuboradi.
Guruhlarga qo'shilmaydi (avtomatik chiqib ketadi).

Jadval (schedule.json):
  Har hafta yakshanba, seshanba, payshanba kuni soat 12:00 da (Toshkent vaqti)
  3-4, 5-6, 7-8, 9-10, 11-12, ... 99-100 gacha.
"""
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
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

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("vocab-bot")
MISSING_WARNED: set[str] = set()


# ---------- Render / Cloud Web healthcheck server ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - Vocab Bot is running!")

    def log_message(self, format, *args):
        pass  # ortiqcha log chiqarmaymiz


def start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Render/Cloud health server %s-portda ishga tushdi", port)


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
        log.info("Yangi qabul qiluvchi chat qo'shildi: %s", chat_id)


def remove_chat(chat_id: int) -> None:
    state = load_state()
    chats = state.get("chats", [])
    if chat_id in chats:
        chats.remove(chat_id)
        state["chats"] = chats
        save_state(state)
        log.info("Chat o'chirildi: %s", chat_id)


def is_admin(user_id: int | None) -> bool:
    """Agar ADMIN_IDS bo'sh bo'lsa, birinchi foydalanuvchilar kira oladi; to'ldirilgan bo'lsa faqat adminlar."""
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


# ---------- yuborish ----------
async def send_item(context: ContextTypes.DEFAULT_TYPE, item: dict) -> int:
    """PDF ni barcha ro'yxatdan o'tgan shaxsiy chatlarga yuboradi."""
    state = load_state()
    path = os.path.join(BASE, "pdfs", item["file"])
    if not os.path.exists(path):
        log.error("PDF fayl mavjud emas: %s", path)
        return 0

    ok = 0
    already = set(state["sent"].get(item["id"], []))
    chats = list(state.get("chats", []))

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
        except Exception:
            log.exception("Yuborib bo'lmadi: chat=%s fayl=%s", chat_id, item["file"])

    state = load_state()
    state["sent"][item["id"]] = sorted(already)
    save_state(state)
    return ok


async def check_schedule(context: ContextTypes.DEFAULT_TYPE):
    """
    Har daqiqada ishlaydi:
    - Vaqti kelgan va hali yuborilmagan PDF larni yuboradi.
    - Server o'chib yongan bo'lsa ham 2 kungacha o'tib ketganlarini yuboradi.
    - Takroriy yuborilmaydi (state.json tekshiriladi).
    """
    now = datetime.now(TZ)
    state = load_state()
    chats = state.get("chats", [])
    if not chats:
        return

    # Hozirgi kundan 2 kun oldingi va hozirgi kundagi barcha elementlar
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

        sent_to = set(state["sent"].get(item["id"], []))
        if any(c not in sent_to for c in chats):
            log.info("Jadval bo'yicha yuborilmoqda: %s (%s)", item["id"], item["title"])
            await send_item(context, item)


# ---------- guruhlarga qo'shilishni taqiqlash ----------
async def on_group_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guruh yoki superguruhga qo'shilsa yoki xabar kelsa, darhol guruhdan chiqish."""
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        try:
            log.warning("Bot guruhga qo'shildi yoki xabar oldi (ID: %s, Nom: %s). Chiqib ketilmoqda...", chat.id, chat.title)
            await context.bot.leave_chat(chat.id)
        except Exception:
            log.exception("Guruhdan chiqishda xatolik: chat_id=%s", chat.id)


# ---------- buyruqlar ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shaxsiy chatda /start yozgan odam PDF qabul qiluvchi bo'ladi."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None

    if not is_admin(user_id):
        await update.message.reply_text("Kechirasiz, bu bot faqat admin shaxsiy foydalanishi uchun.")
        log.warning("Ruxsatsiz /start: user_id=%s", user_id)
        return

    add_chat(update.effective_chat.id)
    id_hint = f"\n\n🆔 Sizning Telegram ID: `{user_id}`" if not ADMIN_IDS else ""
    await update.message.reply_text(
        "👋 Salom! Ro'yxatga olindingiz ✅\n\n"
        "📚 *English Vocabulary in Use* lug'at PDF lari har hafta "
        "*yakshanba, seshanba va payshanba* kuni soat *12:00* da (Toshkent vaqti) "
        "avtomatik tarzda shu shaxsiy chatingizga yuborib turiladi.\n\n"
        "Buyruqlar:\n"
        "• /status — jadval va yuborilgan PDF lar holati\n"
        "• /sendnow <id> — sinov uchun PDF ni shu zahoti yuborish" + id_hint,
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jadval va yuborilgan PDF lar holati."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    state = load_state()
    now = datetime.now(TZ)
    chats = state.get("chats", [])
    lines = [
        "📊 *Vocabulary Bot Holati*",
        f"👤 Qabul qiluvchi: {len(chats)} ta shaxsiy chat",
        f"🕒 Toshkent vaqti: {now:%d.%m.%Y %H:%M}",
        "",
        "📅 *Yaqin kunlardagi yuborishlar:*",
    ]

    # Yaqin kunlardagi elementlar (oxirgi 3 kundan keyingi 14 kungacha)
    upcoming = [i for i in load_schedule(horizon_days=14) if item_time(i) >= now - timedelta(days=3)][:8]
    if not upcoming:
        lines.append("Jadvalda yaqin kunlar uchun yuborishlar mavjud emas.")

    for item in upcoming:
        t = item_time(item)
        done = len(state.get("sent", {}).get(item["id"], []))
        exists = os.path.exists(os.path.join(BASE, "pdfs", item["file"]))

        if not exists:
            mark = "⚠️ PDF yo'q"
        elif done and done >= len(chats) and len(chats) > 0:
            mark = "✅ yuborilgan"
        elif now >= t:
            mark = "⏳ navbatda"
        else:
            mark = "📅 kutilmoqda"
        lines.append(f"• `{t:%d.%m %a %H:%M}` — *{item['title']}*: {mark} (`{item['id']}`)")

    lines.append("\n💡 _Sinov uchun yuborish:_ `/sendnow units-3-4`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_sendnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sendnow <id> - sinov uchun shu zahoti yuborish (faqat admin)."""
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if not is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return

    all_items = {i["id"]: i for i in load_schedule(all_items=True)}

    if not context.args or context.args[0] not in all_items:
        recent_ids = [i["id"] for i in load_schedule(horizon_days=14)][:6]
        msg = (
            "Foydalanish: `/sendnow <id>`\n\n"
            "Mavjud ID lardan misollar:\n" +
            "\n".join(f"• `/sendnow {i}`" for i in recent_ids)
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    item = all_items[context.args[0]]
    path = os.path.join(BASE, "pdfs", item["file"])
    if not os.path.exists(path):
        await update.message.reply_text(f"❌ Xatolik: `{item['file']}` fayli `pdfs/` papkasida topilmadi!", parse_mode="Markdown")
        return

    # Sinov uchun sent holatidan chiqarib darhol yuboramiz
    state = load_state()
    state["sent"].pop(item["id"], None)
    save_state(state)

    n = await send_item(context, item)
    if n > 0:
        await update.message.reply_text(f"✅ *{item['title']}* muvaffaqiyatli {n} ta shaxsiy chatga yuborildi!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Yuborilmadi. Avval /start bosing yoki loglarni tekshiring.")


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
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sendnow", cmd_sendnow))

    # Guruhga qo'shilsa darhol chiqib ketish
    app.add_handler(ChatMemberHandler(on_group_activity, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, on_group_activity))

    # Har 60 soniyada jadvalni tekshirish
    app.job_queue.run_repeating(check_schedule, interval=60, first=5)

    log.info("Bot muvaffaqiyatli ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
