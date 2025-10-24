# admin_panel.py

import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# --- تنظیمات ---
# یک متغیر محیطی در Render.com به نام ADMIN_IDS بسازید و آیدی‌های عددی ادمین‌ها را با کاما از هم جدا کنید.
# مثال: 123456789,987654321
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(','))) if os.environ.get("ADMIN_IDS") else []
DATA_FILE = "bot_data.json"

logger = logging.getLogger(__name__)

# --- توابع مدیریت داده‌ها ---

def load_data():
    """داده‌های ربات را از فایل JSON بارگذاری می‌کند."""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # تبدیل لیست آیدی‌های مسدود شده به یک set برای جستجوی سریع‌تر
            data['banned_users'] = set(data.get('banned_users', []))
            return data
    except FileNotFoundError:
        # اگر فایل وجود نداشته باشد، یک ساختار اولیه ایجاد می‌کند
        logger.info("Data file not found. Creating a new one.")
        return {
            "users": {},
            "banned_users": set(),
            "stats": {
                "total_messages": 0,
                "total_users": 0
            }
        }
    except json.JSONDecodeError:
        logger.error("Error decoding JSON data file. Starting with fresh data.")
        return {
            "users": {},
            "banned_users": set(),
            "stats": {
                "total_messages": 0,
                "total_users": 0
            }
        }

def save_data(data):
    """داده‌های ربات را در فایل JSON ذخیره می‌کند."""
    # برای ذخیره، set را دوباره به لیست تبدیل می‌کنیم چون JSON از set پشتیبانی نمی‌کند
    data_to_save = data.copy()
    data_to_save['banned_users'] = list(data['banned_users'])
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

# --- دکوراتور برای دسترسی ادمین ---

def admin_only(func):
    """این دکوراتور تضمین می‌کند که فقط ادمین‌ها بتوانند دستور را اجرا کنند."""
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("⛔️ شما دسترسی لازم برای اجرای این دستور را ندارید.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- هندلرهای دستورات ادمین ---

@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار ربات را نمایش می‌دهد."""
    data = load_data()
    total_users = len(data['users'])
    total_messages = data['stats']['total_messages']
    banned_count = len(data['banned_users'])

    # پیدا کردن 5 کاربر آخر که فعال بوده‌اند
    active_users = sorted(
        data['users'].items(),
        key=lambda item: item[1].get('last_seen', ''),
        reverse=True
    )[:5]

    active_users_text = "\n".join(
        [f"• {user_id}: {info.get('first_name', 'N/A')} (آخرین فعالیت: {info.get('last_seen', 'N/A')})"
         for user_id, info in active_users]
    )

    text = (
        f"📊 **آمار ربات**\n\n"
        f"👥 **تعداد کل کاربران:** `{total_users}`\n"
        f"📝 **تعداد کل پیام‌ها:** `{total_messages}`\n"
        f"🚫 **کاربران مسدود شده:** `{banned_count}`\n\n"
        f"**۵ کاربر اخیر فعال:**\n{active_users_text}"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

@admin_only
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یک پیام را به تمام کاربران ارسال می‌کند."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً پیامی برای ارسال بنویسید.\nمثال: `/broadcast سلام به همه!`")
        return

    message_text = " ".join(context.args)
    data = load_data()
    user_ids = list(data['users'].keys())
    total_sent = 0
    total_failed = 0

    await update.message.reply_text(f"📣 در حال ارسال پیام به `{len(user_ids)}` کاربر...")

    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text)
            total_sent += 1
            await asyncio.sleep(0.05) # کمی صبر برای جلوگیری از محدودیت تلگرام
        except TelegramError as e:
            logger.warning(f"Failed to send broadcast to {user_id}: {e}")
            total_failed += 1

    result_text = (
        f"✅ **ارسال همگانی تمام شد**\n\n"
        f"✅ موفق: `{total_sent}`\n"
        f"❌ ناموفق: `{total_failed}`"
    )
    await update.message.reply_text(result_text, parse_mode='Markdown')

@admin_only
async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یک کاربر را با آیدی عددی مسدود می‌کند."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/ban 123456789`")
        return

    user_id_to_ban = int(context.args[0])
    data = load_data()

    if user_id_to_ban in ADMIN_IDS:
        await update.message.reply_text("🛡️ شما نمی‌توانید یک ادمین را مسدود کنید!")
        return

    if user_id_to_ban in data['banned_users']:
        await update.message.reply_text(f"کاربر `{user_id_to_ban}` از قبل مسدود شده است.")
        return

    data['banned_users'].add(user_id_to_ban)
    save_data(data)
    await update.message.reply_text(f"✅ کاربر `{user_id_to_ban}` با موفقیت مسدود شد.", parse_mode='Markdown')

@admin_only
async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسدودیت یک کاربر را برمی‌دارد."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/unban 123456789`")
        return

    user_id_to_unban = int(context.args[0])
    data = load_data()

    if user_id_to_unban not in data['banned_users']:
        await update.message.reply_text(f"کاربر `{user_id_to_unban}` در لیست مسدود شده‌ها وجود ندارد.")
        return

    data['banned_users'].remove(user_id_to_unban)
    save_data(data)
    await update.message.reply_text(f"✅ مسدودیت کاربر `{user_id_to_unban}` با موفقیت برداشته شد.", parse_mode='Markdown')

@admin_only
async def admin_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اطلاعات یک کاربر خاص را نمایش می‌دهد."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/user_info 123456789`")
        return

    user_id = int(context.args[0])
    data = load_data()
    user_info = data['users'].get(str(user_id))

    if not user_info:
        await update.message.reply_text(f"کاربری با آیدی `{user_id}` در دیتابیس یافت نشد.")
        return

    is_banned = "بله" if user_id in data['banned_users'] else "خیر"
    text = (
        f"ℹ️ **اطلاعات کاربر**\n\n"
        f"🆔 **آیدی:** `{user_id}`\n"
        f"👤 **نام:** {user_info.get('first_name', 'N/A')}\n"
        f"🔷 **نام کاربری:** @{user_info.get('username', 'N/A')}\n"
        f"📊 **تعداد پیام‌ها:** `{user_info.get('message_count', 0)}`\n"
        f"📅 **اولین پیام:** {user_info.get('first_seen', 'N/A')}\n"
        f"🕒 **آخرین فعالیت:** {user_info.get('last_seen', 'N/A')}\n"
        f"🚫 **وضعیت مسدودیت:** {is_banned}"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

@admin_only
async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آخرین خطوط لاگ ربات را ارسال می‌کند."""
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = lines[-30:] # ۳۰ خط آخر را می‌گیرد
            log_text = "".join(last_lines)
            if not log_text:
                await update.message.reply_text("فایل لاگ خالی است.")
                return
            
            # تقسیم پیام اگر طولانی بود
            if len(log_text) > 4096:
                for i in range(0, len(log_text), 4096):
                    await update.message.reply_text(f"```{log_text[i:i+4096]}```", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"```{log_text}```", parse_mode='Markdown')

    except FileNotFoundError:
        await update.message.reply_text("فایل لاگ یافت نشد.")
    except Exception as e:
        await update.message.reply_text(f"خطایی در خواندن لاگ رخ داد: {e}")


# --- تابع راه‌اندازی هندلرها ---
def setup_admin_handlers(application):
    """هندلرهای پنل ادمین را به اپلیکیشن اضافه می‌کند."""
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("unban", admin_unban))
    application.add_handler(CommandHandler("user_info", admin_userinfo))
    application.add_handler(CommandHandler("logs", admin_logs))
    logger.info("Admin panel handlers have been set up.")
