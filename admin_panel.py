# admin_panel.py

import logging
import os
import sys
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

# دریافت لاگر از فایل اصلی
logger = logging.getLogger(__name__)

# --- تغییرات مربوط به امنیت ---
# خواندن اطلاعات مدیر از متغیرهای محیطی Render
# این روش مشابه HF_TOKEN است و امنیت را تضمین می‌کند
try:
    ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
    ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
except KeyError:
    logger.critical(
        "FATAL: ADMIN_USERNAME or ADMIN_PASSWORD environment variables are not set. "
        "Please set them in your Render Environment tab and restart the service."
    )
    sys.exit(1) # متوقف کردن برنامه در صورت عدم وجود متغیرهای محیطی

# دیکشنری برای نگهداری جلسات مدیران (احراز هویت شده یا نه)
# {user_id: {"authenticated": bool, "step": "username"|"password"}}
admin_sessions = {}

# لیست برای ذخیره لاگ‌های مدیریتی
admin_logs = []

# --- توابع کمکی ---

def log_admin_action(user_id: int, action: str):
    """یک عملیات مدیریتی را لاگ می‌کند."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Admin {user_id}: {action}"
    admin_logs.append(log_entry)
    logger.info(f"ADMIN LOG: {log_entry}")

def is_admin(user_id: int) -> bool:
    """بررسی می‌کند که آیا کاربر مدیر احراز هویت شده است یا نه."""
    return user_id in admin_sessions and admin_sessions[user_id].get("authenticated", False)

# --- توابع اصلی پنل مدیریت ---

async def authenticate_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فرآیند احراز هویت دو مرحله‌ای مدیر را مدیریت می‌کند."""
    user_id = update.effective_user.id
    message_text = update.message.text

    # اگر کاربر قبلاً احراز هویت شده، منوی مدیریت را نمایش بده
    if is_admin(user_id):
        await show_admin_menu(update, context)
        return

    # اگر کاربر در فرآیند احراز هویت است
    if user_id in admin_sessions:
        step = admin_sessions[user_id].get("step")

        if step == "username":
            if message_text == ADMIN_USERNAME:
                admin_sessions[user_id]["step"] = "password"
                await update.message.reply_text("✅ نام کاربری صحیح است.\n\nلطفاً رمز عبور را وارد کنید:")
            else:
                await update.message.reply_text("❌ نام کاربری اشتباه است. لطفاً دوباره تلاش کنید:")
            return

        if step == "password":
            if message_text == ADMIN_PASSWORD:
                admin_sessions[user_id]["authenticated"] = True
                log_admin_action(user_id, "Successfully authenticated")
                await update.message.reply_text("✅ احراز هویت با موفقیت انجام شد! به پنل مدیریت خوش آمدید.")
                await show_admin_menu(update, context)
            else:
                await update.message.reply_text("❌ رمز عبور اشتباه است. فرآیند از ابتدا شروع می‌شود.")
                del admin_sessions[user_id] # جلسه را برای شروع مجدد حذف کن
            return

    # شروع فرآیند احراز هویت
    admin_sessions[user_id] = {"step": "username", "authenticated": False}
    await update.message.reply_text("🔐 برای ورود به پنل مدیریت، لطفاً نام کاربری را وارد کنید:")


async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی اصلی مدیریت را با دکمه‌های شیشه‌ای نمایش می‌دهد."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 مشاهده آمار", callback_data="admin_stats")],
        [InlineKeyboardButton("📋 مشاهده لاگ‌ها", callback_data="admin_logs")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("⚙️ تنظیمات ربات", callback_data="admin_settings")],
        [InlineKeyboardButton("🔄 راه‌اندازی مجدد ربات", callback_data="admin_restart")],
        [InlineKeyboardButton("🚪 خروج از مدیریت", callback_data="admin_logout")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠️ منوی مدیریت ربات:", reply_markup=reply_markup)


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کال‌بک‌های دکمه‌های منوی مدیریت را پردازش می‌کند."""
    query = update.callback_query
    await query.answer() # برای نشان دادن لودینگ و جلوگیری از تایم‌اوت

    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ دسترسی غیرمجاز.")
        return

    action = query.data

    if action == "admin_stats":
        await show_admin_stats(query, context)
    elif action == "admin_logs":
        await show_admin_logs(query)
    elif action == "admin_users":
        await show_admin_users(query, context)
    elif action == "admin_settings":
        await show_admin_settings(query)
    elif action == "admin_restart":
        await restart_bot(query)
    elif action == "admin_logout":
        await logout_admin(query)
    elif action == "admin_back_main":
        await show_admin_menu(update, context)


async def show_admin_stats(query, context: ContextTypes.DEFAULT_TYPE):
    """آمار ربات را نمایش می‌دهد."""
    # دسترسی به دیکشنری user_tasks از طریق context
    user_tasks = context.application.bot_data.get('user_tasks', {})
    
    active_tasks = sum(1 for task in user_tasks.values() if not task.done())
    
    stats_text = (
        f"📊 **آمار ربات**\n\n"
        f"👥 کل کاربران فعال (درخواست ارسال کرده): `{len(user_tasks)}`\n"
        f"🔄 درخواست‌های در حال پردازش: `{active_tasks}`\n"
        f"📝 تعداد لاگ‌های مدیریتی: `{len(admin_logs)}`\n"
        f"⏰ زمان فعلی: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_admin_logs(query):
    """آخرین لاگ‌های مدیریتی را نمایش می‌دهد."""
    if not admin_logs:
        await query.edit_message_text("هیچ لاگ مدیریتی ثبت نشده است.")
        return

    recent_logs = admin_logs[-15:] # نمایش آخرین ۱۵ لاگ
    logs_text = "📋 **آخرین لاگ‌های مدیریتی:**\n\n" + "\n".join(recent_logs)
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(logs_text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_admin_users(query, context: ContextTypes.DEFAULT_TYPE):
    """لیستی از کاربران فعال را نمایش می‌دهد."""
    user_tasks = context.application.bot_data.get('user_tasks', {})
    
    if not user_tasks:
        await query.edit_message_text("هیچ کاربر فعالی وجود ندارد.")
        return

    users_text = f"👥 **مدیریت کاربران**\n\nتعداد کل کاربران: `{len(user_tasks)}`\n\n"
    users_text += "۱۰ کاربر آخر:\n"
    for i, user_id in enumerate(list(user_tasks.keys())[-10:], 1):
        task = user_tasks[user_id]
        status = "🟢 در حال پردازش" if not task.done() else "🔴 اتمام یافته"
        users_text += f"{i}. کاربر `{user_id}`: {status}\n"

    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_admin_settings(query):
    """تنظیمات فعلی ربات را نمایش می‌دهد."""
    settings_text = (
        "⚙️ **تنظیمات فعلی ربات**\n\n"
        f"🧠 مدل هوش: `huihui-ai/gemma-3-27b-it-abliterated`\n"
        f"🌡️ دما (Temperature): `0.7`\n"
        f"🔢 Top-p: `0.95`\n"
        f"📡 حالت استریم (Stream): `خاموش`\n"
        f"⏱️ تایم‌اوت کلی: `60 ثانیه`\n"
        f"🔗 حداکثر اتصالات: `100`\n"
        f"🔐 نام کاربری مدیر: `{ADMIN_USERNAME}`"
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(settings_text, reply_markup=reply_markup, parse_mode='Markdown')


async def restart_bot(query):
    """بات را راه‌اندازی مجدد می‌کند."""
    log_admin_action(query.from_user.id, "Requested bot restart")
    await query.edit_message_text("🔄 در حال راه‌اندازی مجدد ربات...")
    
    # این دستور اسکریپت پایتون را با همان آرگومان‌های اولیه دوباره اجرا می‌کند
    # این روش در بسیاری از محیط‌ها (مانند Render) کار می‌کند.
    os.execl(sys.executable, sys.executable, *sys.argv)


async def logout_admin(query):
    """مدیر را از پنل خارج می‌کند."""
    user_id = query.from_user.id
    if user_id in admin_sessions:
        del admin_sessions[user_id]
        log_admin_action(user_id, "Logged out")
    
    await query.edit_message_text("✅ شما با موفقیت از پنل مدیریت خارج شدید.")


# --- هندلر دستور /admin ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /admin را برای ورود به پنل مدیریت پردازش می‌کند."""
    await authenticate_admin(update, context)

# تابعی برای ثبت تمام هندلرهای مربوط به مدیریت
def setup_admin_handlers(application):
    """هندلرهای مربوط به پنل مدیریت را در اپلیکیشن ثبت می‌کند."""
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
