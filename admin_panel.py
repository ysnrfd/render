# admin_panel.py

import os
import logging
import csv
import io
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError

# --- تنظیمات ---
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(','))) if os.environ.get("ADMIN_IDS") else []

# وارد کردن مدیر داده‌ها
import data_manager

logger = logging.getLogger(__name__)

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
async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش تمام دستورات موجود ادمین."""
    commands_text = (
        "📋 **دستورات ادمین ربات:**\n\n"
        "📊 `/stats` - نمایش آمار ربات\n"
        "📢 `/broadcast [پیام]` - ارسال پیام به تمام کاربران\n"
        "🚫 `/ban [آیدی]` - مسدود کردن کاربر\n"
        "✅ `/unban [آیدی]` - رفع مسدودیت کاربر\n"
        "ℹ️ `/user_info [آیدی]` - نمایش اطلاعات کاربر\n"
        "📝 `/logs` - نمایش لاگ‌های ربات\n"
        "👥 `/users_list [صفحه]` - نمایش لیست کاربران\n"
        "🔍 `/user_search [نام]` - جستجوی کاربر بر اساس نام\n"
        "💾 `/backup` - ایجاد نسخه پشتیبان از داده‌ها\n"
        "📋 `/commands` - نمایش این لیست دستورات"
    )
    await update.message.reply_text(commands_text, parse_mode='Markdown')

@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار ربات را نمایش می‌دهد."""
    # استفاده از داده‌های متمرکز
    total_users = len(data_manager.DATA['users'])
    total_messages = data_manager.DATA['stats']['total_messages']
    banned_count = len(data_manager.DATA['banned_users'])
    
    now = datetime.now()
    active_24h = sum(1 for user in data_manager.DATA['users'].values() 
                    if 'last_seen' in user and 
                    datetime.strptime(user['last_seen'], '%Y-%m-%d %H:%M:%S') > now - timedelta(hours=24))
    
    active_7d = sum(1 for user in data_manager.DATA['users'].values() 
                   if 'last_seen' in user and 
                   datetime.strptime(user['last_seen'], '%Y-%m-%d %H:%M:%S') > now - timedelta(days=7))

    active_users = sorted(
        data_manager.DATA['users'].items(),
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
        f"🚫 **کاربران مسدود شده:** `{banned_count}`\n"
        f"🟢 **کاربران فعال 24 ساعت گذشته:** `{active_24h}`\n"
        f"🟢 **کاربران فعال 7 روز گذشته:** `{active_7d}`\n\n"
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
    user_ids = list(data_manager.DATA['users'].keys())
    total_sent = 0
    total_failed = 0

    await update.message.reply_text(f"📣 در حال ارسال پیام به `{len(user_ids)}` کاربر...")

    for user_id_str in user_ids:
        try:
            await context.bot.send_message(chat_id=int(user_id_str), text=message_text)
            total_sent += 1
            await asyncio.sleep(0.05)
        except TelegramError as e:
            logger.warning(f"Failed to send broadcast to {user_id_str}: {e}")
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

    if user_id_to_ban in ADMIN_IDS:
        await update.message.reply_text("🛡️ شما نمی‌توانید یک ادمین را مسدود کنید!")
        return

    if data_manager.is_user_banned(user_id_to_ban):
        await update.message.reply_text(f"کاربر `{user_id_to_ban}` از قبل مسدود شده است.")
        return

    data_manager.ban_user(user_id_to_ban)
    await update.message.reply_text(f"✅ کاربر `{user_id_to_ban}` با موفقیت مسدود شد.", parse_mode='Markdown')

@admin_only
async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسدودیت یک کاربر را برمی‌دارد."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/unban 123456789`")
        return

    user_id_to_unban = int(context.args[0])

    if not data_manager.is_user_banned(user_id_to_unban):
        await update.message.reply_text(f"کاربر `{user_id_to_unban}` در لیست مسدود شده‌ها وجود ندارد.")
        return

    data_manager.unban_user(user_id_to_unban)
    await update.message.reply_text(f"✅ مسدودیت کاربر `{user_id_to_unban}` با موفقیت برداشته شد.", parse_mode='Markdown')

@admin_only
async def admin_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اطلاعات یک کاربر خاص را نمایش می‌دهد."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/user_info 123456789`")
        return

    user_id = int(context.args[0])
    user_info = data_manager.DATA['users'].get(str(user_id))

    if not user_info:
        await update.message.reply_text(f"کاربری با آیدی `{user_id}` در دیتابیس یافت نشد.")
        return

    is_banned = "بله" if data_manager.is_user_banned(user_id) else "خیر"
    
    if 'first_seen' in user_info and 'last_seen' in user_info:
        first_date = datetime.strptime(user_info['first_seen'], '%Y-%m-%d %H:%M:%S')
        last_date = datetime.strptime(user_info['last_seen'], '%Y-%m-%d %H:%M:%S')
        days_active = max(1, (last_date - first_date).days)
        avg_messages = user_info.get('message_count', 0) / days_active
    else:
        avg_messages = user_info.get('message_count', 0)
    
    text = (
        f"ℹ️ **اطلاعات کاربر**\n\n"
        f"🆔 **آیدی:** `{user_id}`\n"
        f"👤 **نام:** {user_info.get('first_name', 'N/A')}\n"
        f"🔷 **نام کاربری:** @{user_info.get('username', 'N/A')}\n"
        f"📊 **تعداد پیام‌ها:** `{user_info.get('message_count', 0)}`\n"
        f"📈 **میانگین پیام در روز:** `{avg_messages:.2f}`\n"
        f"📅 **اولین پیام:** {user_info.get('first_seen', 'N/A')}\n"
        f"🕒 **آخرین فعالیت:** {user_info.get('last_seen', 'N/A')}\n"
        f"🚫 **وضعیت مسدودیت:** {is_banned}"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

@admin_only
async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آخرین خطوط لاگ ربات را ارسال می‌کند."""
    try:
        with open(data_manager.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = lines[-30:]
            log_text = "".join(last_lines)
            if not log_text:
                await update.message.reply_text("فایل لاگ خالی است.")
                return
            
            if len(log_text) > 4096:
                for i in range(0, len(log_text), 4096):
                    await update.message.reply_text(f"```{log_text[i:i+4096]}```", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"```{log_text}```", parse_mode='Markdown')

    except FileNotFoundError:
        await update.message.reply_text("فایل لاگ یافت نشد.")
    except Exception as e:
        await update.message.reply_text(f"خطایی در خواندن لاگ رخ داد: {e}")

@admin_only
async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست کامل کاربران با صفحه‌بندی."""
    users = data_manager.DATA['users']
    
    page = 1
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
        if page < 1: page = 1
    
    users_per_page = 20
    total_users = len(users)
    total_pages = (total_users + users_per_page - 1) // users_per_page
    
    if page > total_pages: page = total_pages
    
    start_idx = (page - 1) * users_per_page
    end_idx = min(start_idx + users_per_page, total_users)
    
    sorted_users = sorted(users.items(), key=lambda item: item[1].get('last_seen', ''), reverse=True)
    
    users_text = f"👥 **لیست کاربران (صفحه {page}/{total_pages})**\n\n"
    
    for i, (user_id, user_info) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
        is_banned = "🚫" if int(user_id) in data_manager.DATA['banned_users'] else "✅"
        username = user_info.get('username', 'N/A')
        first_name = user_info.get('first_name', 'N/A')
        last_seen = user_info.get('last_seen', 'N/A')
        message_count = user_info.get('message_count', 0)
        
        users_text += f"{i}. {is_banned} `{user_id}` - {first_name} (@{username})\n"
        users_text += f"   پیام‌ها: `{message_count}` | آخرین فعالیت: `{last_seen}`\n\n"
    
    keyboard = []
    if page > 1: keyboard.append([InlineKeyboardButton("⬅️ صفحه قبل", callback_data=f"users_list:{page-1}")])
    if page < total_pages: keyboard.append([InlineKeyboardButton("➡️ صفحه بعد", callback_data=f"users_list:{page+1}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(users_text, parse_mode='Markdown', reply_markup=reply_markup)

@admin_only
async def admin_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جستجوی کاربر بر اساس نام یا نام کاربری."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً نام یا نام کاربری برای جستجو وارد کنید.\nمثال: `/user_search علی`")
        return
    
    search_term = " ".join(context.args).lower()
    users = data_manager.DATA['users']
    
    matching_users = []
    for user_id, user_info in users.items():
        first_name = user_info.get('first_name', '').lower()
        username = user_info.get('username', '').lower()
        
        if search_term in first_name or search_term in username:
            is_banned = "🚫" if int(user_id) in data_manager.DATA['banned_users'] else "✅"
            matching_users.append((user_id, user_info, is_banned))
    
    if not matching_users:
        await update.message.reply_text(f"هیچ کاربری با نام «{search_term}» یافت نشد.")
        return
    
    results_text = f"🔍 **نتایج جستجو برای «{search_term}»**\n\n"
    
    for user_id, user_info, is_banned in matching_users:
        username = user_info.get('username', 'N/A')
        first_name = user_info.get('first_name', 'N/A')
        last_seen = user_info.get('last_seen', 'N/A')
        message_count = user_info.get('message_count', 0)
        
        results_text += f"{is_banned} `{user_id}` - {first_name} (@{username})\n"
        results_text += f"   پیام‌ها: `{message_count}` | آخرین فعالیت: `{last_seen}`\n\n"
    
    await update.message.reply_text(results_text, parse_mode='Markdown')

@admin_only
async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد نسخه پشتیبان از داده‌های ربات."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"bot_backup_{timestamp}.json"
        
        data_to_backup = data_manager.DATA.copy()
        data_to_backup['banned_users'] = list(data_manager.DATA['banned_users'])
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_backup, f, indent=4, ensure_ascii=False)
        
        await update.message.reply_document(
            document=open(backup_file, 'rb'),
            caption=f"✅ نسخه پشتیبان با موفقیت ایجاد شد: {backup_file}"
        )
        
        logger.info(f"Backup created: {backup_file}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ایجاد نسخه پشتیبان: {e}")
        logger.error(f"Error creating backup: {e}")

# --- هندلر برای دکمه‌های صفحه‌بندی ---
async def users_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دکمه‌های صفحه‌بندی لیست کاربران."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("users_list:"):
        page = int(query.data.split(":")[1])
        context.args = [str(page)]
        await admin_users_list(update, context)

# --- تابع راه‌اندازی هندلرها ---
def setup_admin_handlers(application):
    """هندلرهای پنل ادمین را به اپلیکیشن اضافه می‌کند."""
    application.add_handler(CommandHandler("commands", admin_commands))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("unban", admin_unban))
    application.add_handler(CommandHandler("user_info", admin_userinfo))
    application.add_handler(CommandHandler("logs", admin_logs))
    application.add_handler(CommandHandler("users_list", admin_users_list))
    application.add_handler(CommandHandler("user_search", admin_user_search))
    application.add_handler(CommandHandler("backup", admin_backup))
    
    # اضافه کردن هندلر برای دکمه‌های صفحه‌بندی
    application.add_handler(CallbackQueryHandler(users_list_callback, pattern="^users_list:"))
    
    logger.info("Admin panel handlers have been set up.")
