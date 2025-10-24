# admin_panel.py

import os
import json
import logging
import csv
import io
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError, BadRequest

# --- تنظیمات ---
# یک متغیر محیطی در Render.com به نام ADMIN_IDS بسازید و آیدی‌های عددی ادمین‌ها را با کاما از هم جدا کنید.
# مثال: 123456789,987654321
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(','))) if os.environ.get("ADMIN_IDS") else []
DATA_FILE = "bot_data.json"
MAINTENANCE_FILE = "maintenance_status.json"
WELCOME_FILE = "welcome_messages.json"

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
            },
            "welcome_message": "سلام {user_mention}! 🤖\n\nمن یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
            "goodbye_message": "کاربر {user_mention} گروه را ترک کرد. خداحافظ!",
            "maintenance_mode": False
        }
    except json.JSONDecodeError:
        logger.error("Error decoding JSON data file. Starting with fresh data.")
        return {
            "users": {},
            "banned_users": set(),
            "stats": {
                "total_messages": 0,
                "total_users": 0
            },
            "welcome_message": "سلام {user_mention}! 🤖\n\nمن یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
            "goodbye_message": "کاربر {user_mention} گروه را ترک کرد. خداحافظ!",
            "maintenance_mode": False
        }

def save_data(data):
    """داده‌های ربات را در فایل JSON ذخیره می‌کند."""
    # برای ذخیره، set را دوباره به لیست تبدیل می‌کنیم چون JSON از set پشتیبانی نمی‌کند
    data_to_save = data.copy()
    data_to_save['banned_users'] = list(data['banned_users'])
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

def load_maintenance_status():
    """وضعیت تعمیرات را بارگذاری می‌کند."""
    try:
        with open(MAINTENANCE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"enabled": False, "message": "ربات در حال تعمیر است. لطفاً بعداً تلاش کنید."}

def save_maintenance_status(status):
    """وضعیت تعمیرات را ذخیره می‌کند."""
    with open(MAINTENANCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=4, ensure_ascii=False)

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
        "🗑️ `/clear_data [تایید]` - پاک کردن داده‌های کاربران\n"
        "📢 `/announce [پیام]` - ارسال اطلاعیه با فرمت خاص\n"
        "👋 `/set_welcome [پیام]` - تنظیم پیام خوشامدگویی\n"
        "👋 `/set_goodbye [پیام]` - تنظیم پیام خداحافظی\n"
        "🔧 `/maintenance [on/off]` - فعال/غیرفعال کردن حالت تعمیرات\n"
        "📤 `/export_data` - خروجی گرفتن داده‌ها به صورت CSV\n"
        "⏱️ `/rate_limit [تعداد] [بازه زمانی]` - تنظیم محدودیت نرخ ارسال پیام\n"
        "📋 `/commands` - نمایش این لیست دستورات"
    )
    await update.message.reply_text(commands_text, parse_mode='Markdown')

@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار ربات را نمایش می‌دهد."""
    data = load_data()
    total_users = len(data['users'])
    total_messages = data['stats']['total_messages']
    banned_count = len(data['banned_users'])
    
    # محاسبه کاربران فعال در 24 ساعت گذشته
    now = datetime.now()
    active_24h = sum(1 for user in data['users'].values() 
                    if 'last_seen' in user and 
                    datetime.strptime(user['last_seen'], '%Y-%m-%d %H:%M:%S') > now - timedelta(hours=24))
    
    # محاسبه کاربران فعال در 7 روز گذشته
    active_7d = sum(1 for user in data['users'].values() 
                   if 'last_seen' in user and 
                   datetime.strptime(user['last_seen'], '%Y-%m-%d %H:%M:%S') > now - timedelta(days=7))

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
    
    # محاسبه میانگین پیام در روز
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

@admin_only
async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست کامل کاربران با صفحه‌بندی."""
    data = load_data()
    users = data['users']
    
    # تعیین صفحه مورد نظر
    page = 1
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
        if page < 1:
            page = 1
    
    # تعداد کاربران در هر صفحه
    users_per_page = 20
    total_users = len(users)
    total_pages = (total_users + users_per_page - 1) // users_per_page
    
    if page > total_pages:
        page = total_pages
    
    # محاسبه شروع و پایان لیست برای صفحه فعلی
    start_idx = (page - 1) * users_per_page
    end_idx = min(start_idx + users_per_page, total_users)
    
    # مرتب‌سازی کاربران بر اساس آخرین فعالیت
    sorted_users = sorted(
        users.items(),
        key=lambda item: item[1].get('last_seen', ''),
        reverse=True
    )
    
    # ساخت متن لیست کاربران
    users_text = f"👥 **لیست کاربران (صفحه {page}/{total_pages})**\n\n"
    
    for i, (user_id, user_info) in enumerate(sorted_users[start_idx:end_idx], start=start_idx + 1):
        is_banned = "🚫" if int(user_id) in data['banned_users'] else "✅"
        username = user_info.get('username', 'N/A')
        first_name = user_info.get('first_name', 'N/A')
        last_seen = user_info.get('last_seen', 'N/A')
        message_count = user_info.get('message_count', 0)
        
        users_text += f"{i}. {is_banned} `{user_id}` - {first_name} (@{username})\n"
        users_text += f"   پیام‌ها: `{message_count}` | آخرین فعالیت: `{last_seen}`\n\n"
    
    # ساخت دکمه‌های صفحه‌بندی
    keyboard = []
    
    if page > 1:
        keyboard.append([InlineKeyboardButton("⬅️ صفحه قبل", callback_data=f"users_list:{page-1}")])
    
    if page < total_pages:
        keyboard.append([InlineKeyboardButton("➡️ صفحه بعد", callback_data=f"users_list:{page+1}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(users_text, parse_mode='Markdown', reply_markup=reply_markup)

@admin_only
async def admin_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جستجوی کاربر بر اساس نام یا نام کاربری."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً نام یا نام کاربری برای جستجو وارد کنید.\nمثال: `/user_search علی`")
        return
    
    search_term = " ".join(context.args).lower()
    data = load_data()
    users = data['users']
    
    # جستجوی کاربران
    matching_users = []
    for user_id, user_info in users.items():
        first_name = user_info.get('first_name', '').lower()
        username = user_info.get('username', '').lower()
        
        if search_term in first_name or search_term in username:
            is_banned = "🚫" if int(user_id) in data['banned_users'] else "✅"
            matching_users.append((user_id, user_info, is_banned))
    
    if not matching_users:
        await update.message.reply_text(f"هیچ کاربری با نام «{search_term}» یافت نشد.")
        return
    
    # ساخت متن نتایج جستجو
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
        data = load_data()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"bot_backup_{timestamp}.json"
        
        # برای ذخیره، set را دوباره به لیست تبدیل می‌کنیم چون JSON از set پشتیبانی نمی‌کند
        data_to_backup = data.copy()
        data_to_backup['banned_users'] = list(data['banned_users'])
        
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

@admin_only
async def admin_clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاک کردن داده‌های کاربران با تایید."""
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text(
            "⚠️ **هشدار: این عملیات تمام داده‌های کاربران را پاک می‌کند!**\n\n"
            "برای تایید و ادامه، دستور زیر را ارسال کنید:\n"
            "`/clear_data confirm`"
        )
        return
    
    try:
        # ساخت داده‌های جدید
        new_data = {
            "users": {},
            "banned_users": [],
            "stats": {
                "total_messages": 0,
                "total_users": 0
            },
            "welcome_message": "سلام {user_mention}! 🤖\n\nمن یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
            "goodbye_message": "کاربر {user_mention} گروه را ترک کرد. خداحافظ!",
            "maintenance_mode": False
        }
        
        save_data(new_data)
        await update.message.reply_text("✅ تمام داده‌های کاربران با موفقیت پاک شد.")
        logger.warning("All user data cleared by admin.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در پاک کردن داده‌ها: {e}")
        logger.error(f"Error clearing data: {e}")

@admin_only
async def admin_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال اطلاعیه با فرمت خاص."""
    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً پیامی برای ارسال بنویسید.\n"
            "مثال: `/announce *مهم*: به همه کاربران اطلاع دهید!`"
        )
        return
    
    message_text = " ".join(context.args)
    data = load_data()
    user_ids = list(data['users'].keys())
    total_sent = 0
    total_failed = 0

    await update.message.reply_text(f"📣 در حال ارسال اطلاعیه به `{len(user_ids)}` کاربر...")

    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=message_text,
                parse_mode='Markdown'
            )
            total_sent += 1
            await asyncio.sleep(0.05) # کمی صبر برای جلوگیری از محدودیت تلگرام
        except TelegramError as e:
            logger.warning(f"Failed to send announcement to {user_id}: {e}")
            total_failed += 1

    result_text = (
        f"✅ **ارسال اطلاعیه تمام شد**\n\n"
        f"✅ موفق: `{total_sent}`\n"
        f"❌ ناموفق: `{total_failed}`"
    )
    await update.message.reply_text(result_text, parse_mode='Markdown')

@admin_only
async def admin_set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم پیام خوشامدگویی برای کاربران جدید."""
    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً پیام خوشامدگویی را وارد کنید.\n"
            "می‌توانید از متغیرهای زیر استفاده کنید:\n"
            "`{user_mention}` - نام کاربر با لینک\n"
            "`{user_name}` - نام کاربر\n"
            "`{user_id}` - آیدی کاربر\n\n"
            "مثال: `/set_welcome خوش آمدی {user_mention}!`"
        )
        return
    
    welcome_message = " ".join(context.args)
    data = load_data()
    data['welcome_message'] = welcome_message
    save_data(data)
    
    await update.message.reply_text(
        f"✅ پیام خوشامدگویی با موفقیت تنظیم شد:\n\n"
        f"{welcome_message}"
    )

@admin_only
async def admin_set_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم پیام خداحافظی برای کاربرانی که گروه را ترک می‌کنند."""
    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً پیام خداحافظی را وارد کنید.\n"
            "می‌توانید از متغیرهای زیر استفاده کنید:\n"
            "`{user_mention}` - نام کاربر با لینک\n"
            "`{user_name}` - نام کاربر\n"
            "`{user_id}` - آیدی کاربر\n\n"
            "مثال: `/set_goodbye {user_mention} گروه را ترک کرد. خداحافظ!`"
        )
        return
    
    goodbye_message = " ".join(context.args)
    data = load_data()
    data['goodbye_message'] = goodbye_message
    save_data(data)
    
    await update.message.reply_text(
        f"✅ پیام خداحافظی با موفقیت تنظیم شد:\n\n"
        f"{goodbye_message}"
    )

@admin_only
async def admin_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فعال یا غیرفعال کردن حالت تعمیرات."""
    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await update.message.reply_text(
            "⚠️ لطفاً وضعیت حالت تعمیرات را مشخص کنید.\n"
            "مثال: `/maintenance on` یا `/maintenance off`"
        )
        return
    
    status = context.args[0].lower() == "on"
    maintenance_status = load_maintenance_status()
    maintenance_status["enabled"] = status
    
    if status:
        if len(context.args) > 1:
            maintenance_status["message"] = " ".join(context.args[1:])
        else:
            maintenance_status["message"] = "ربات در حال تعمیر است. لطفاً بعداً تلاش کنید."
        
        await update.message.reply_text(
            f"✅ حالت تعمیرات فعال شد.\n\n"
            f"پیام به کاربران:\n{maintenance_status['message']}"
        )
    else:
        await update.message.reply_text("✅ حالت تعمیرات غیرفعال شد.")
    
    save_maintenance_status(maintenance_status)

@admin_only
async def admin_export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خروجی گرفتن داده‌های کاربران به صورت CSV."""
    try:
        data = load_data()
        users = data['users']
        
        # ایجاد فایل CSV در حافظه
        output = io.StringIO()
        writer = csv.writer(output)
        
        # نوشتن هدر
        writer.writerow(['User ID', 'First Name', 'Username', 'Message Count', 'First Seen', 'Last Seen', 'Banned'])
        
        # نوشتن داده‌های کاربران
        for user_id, user_info in users.items():
            is_banned = "Yes" if int(user_id) in data['banned_users'] else "No"
            writer.writerow([
                user_id,
                user_info.get('first_name', 'N/A'),
                user_info.get('username', 'N/A'),
                user_info.get('message_count', 0),
                user_info.get('first_seen', 'N/A'),
                user_info.get('last_seen', 'N/A'),
                is_banned
            ])
        
        # ارسال فایل
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"users_data_{timestamp}.csv"
        
        await update.message.reply_document(
            document=output.getvalue(),
            filename=filename,
            caption=f"✅ داده‌های کاربران با موفقیت خروجی گرفته شد: {filename}"
        )
        
        logger.info(f"Data exported to CSV: {filename}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در خروجی گرفتن داده‌ها: {e}")
        logger.error(f"Error exporting data: {e}")

@admin_only
async def admin_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم محدودیت نرخ ارسال پیام برای کاربران."""
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text(
            "⚠️ لطفاً تعداد پیام و بازه زمانی (به ثانیه) را وارد کنید.\n"
            "مثال: `/rate_limit 5 60` (حداکثر 5 پیام در 60 ثانیه)"
        )
        return
    
    max_messages = int(context.args[0])
    time_window = int(context.args[1])
    
    data = load_data()
    if 'rate_limit' not in data:
        data['rate_limit'] = {}
    
    data['rate_limit']['max_messages'] = max_messages
    data['rate_limit']['time_window'] = time_window
    save_data(data)
    
    await update.message.reply_text(
        f"✅ محدودیت نرخ ارسال پیام تنظیم شد:\n\n"
        f"حداکثر `{max_messages}` پیام در `{time_window}` ثانیه"
    )

# --- هندلر برای دکمه‌های صفحه‌بندی ---
async def users_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دکمه‌های صفحه‌بندی لیست کاربران."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("users_list:"):
        page = int(query.data.split(":")[1])
        
        # شبیه‌سازی دستور users_list با صفحه مشخص
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
    application.add_handler(CommandHandler("clear_data", admin_clear_data))
    application.add_handler(CommandHandler("announce", admin_announce))
    application.add_handler(CommandHandler("set_welcome", admin_set_welcome))
    application.add_handler(CommandHandler("set_goodbye", admin_set_goodbye))
    application.add_handler(CommandHandler("maintenance", admin_maintenance))
    application.add_handler(CommandHandler("export_data", admin_export_data))
    application.add_handler(CommandHandler("rate_limit", admin_rate_limit))
    
    # اضافه کردن هندلر برای دکمه‌های صفحه‌بندی
    application.add_handler(CallbackQueryHandler(users_list_callback, pattern="^users_list:"))
    
    logger.info("Admin panel handlers have been set up.")
