import os
import re
import sqlite3
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")  # @ProGarageUz
DB_PATH = "codes.db"

def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def db_get_file_id(code: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id FROM movies WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def db_set_movie(code: str, file_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO movies(code, file_id) VALUES(?, ?)", (code, file_id))
    conn.commit()
    conn.close()

def normalize_code(text: str) -> str:
    digits = re.findall(r"\d+", text)
    return "".join(digits)

def subscribe_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Kanalga obuna bo‘lish", url=f"https://t.me/{FORCE_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("🔁 Tekshirish", callback_data="check_sub")]
    ])

async def is_subscribed(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await ctx.bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! 🎬\n"
        "Instagramdagi reelsda berilgan KODni shu yerga yozib yuboring.\n\n"
        "Misol: 34 56 23"
    )

async def handle_code_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    code = normalize_code(raw)

    if not code:
        await update.message.reply_text("❗ Kodni raqamlar bilan yuboring. Misol: 34 56 23")
        return

    # obuna tekshir
    if not await is_subscribed(update.effective_user.id, ctx):
        ctx.user_data["pending_code"] = code
        await update.message.reply_text(
            "🎬 Kinoni olish uchun avval kanalga obuna bo‘ling.\n"
            "Obuna bo‘lgach, 🔁 Tekshirish tugmasini bosing.",
            reply_markup=subscribe_keyboard()
        )
        return

    file_id = db_get_file_id(code)
    if not file_id:
        await update.message.reply_text(
            "❌ Bu kod bo‘yicha kino topilmadi.\n"
            "Kod noto‘g‘ri bo‘lishi mumkin. Yana tekshirib yuboring."
        )
        return

    await ctx.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption="✅ Mana kino!")

async def on_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    pending_code = ctx.user_data.get("pending_code")
    if not pending_code:
        await q.edit_message_text("Kod topilmadi. Iltimos, kodni qayta yuboring.")
        return

    if not await is_subscribed(q.from_user.id, ctx):
        await q.edit_message_text(
            "❌ Hali obuna ko‘rinmadi.\n"
            "Kanalga obuna bo‘lib, yana Tekshirishni bosing.",
            reply_markup=subscribe_keyboard()
        )
        return

    file_id = db_get_file_id(pending_code)
    if not file_id:
        await q.edit_message_text("❌ Bu kod bo‘yicha kino topilmadi. Kodni qayta yuboring.")
        return

    await q.edit_message_text("✅ Obuna tasdiqlandi! Kinoni yuboryapman…")
    await ctx.bot.send_video(chat_id=q.message.chat_id, video=file_id, caption="✅ Mana kino!")

# Admin: video file_id ni olish va kodga biriktirish
async def save_last_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    file_id = None
    if update.message.video:
        file_id = update.message.video.file_id
    elif update.message.document and (update.message.document.mime_type or "").startswith("video/"):
        file_id = update.message.document.file_id

    if not file_id:
        return

    ctx.user_data["last_video_file_id"] = file_id
    await update.message.reply_text(
        "✅ Video qabul qilindi.\n"
        f"file_id:\n{file_id}\n\n"
        "Endi biriktirish uchun:\n"
        "/bind KOD\n"
        "Misol: /bind 345623"
    )

async def bind_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # faqat admin
    if user_id not in ADMIN_IDS:
        return  # hech narsa javob bermaydi

    if not context.args:
        await update.message.reply_text("❗ Misol: /bind 3")
        return

    code = context.args[0].strip()

    if not code.isdigit():
        await update.message.reply_text("❗ Kod faqat son bo‘lishi kerak. Misol: /bind 78")
        return

    if "last_video_file_id" not in context.user_data:
        await update.message.reply_text("❗ Avval video yuboring, keyin /bind qiling.")
        return

    video_map[code] = context.user_data["last_video_file_id"]
    save_data()

    await update.message.reply_text(f"✅ Kino {code} raqamiga biriktirildi.")

def main():

    db_init()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bind", bind_handler))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, save_last_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code_text))
    app.add_handler(CallbackQueryHandler(on_check, pattern="^check_sub$"))

    print("✅ Bot ishga tushdi (Ctrl+C to‘xtatadi)")
    app.run_polling()

if __name__ == "__main__":
    main()
