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
from telegram.error import TelegramError

# --- کتابخانه‌های جدید برای ویژگی‌های اضافه شده ---
import matplotlib
matplotlib.use('Agg') # تنظیم برای استفاده در محیط بدون رابط کاربری گرافیکی
import matplotlib.pyplot as plt
import pandas as pd
import tempfile
import psutil
import platform

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
        "🎯 `/targeted_broadcast [معیار] [مقدار] [پیام]` - ارسال پیام هدفمند\n"
        "📅 `/schedule_broadcast [YYYY-MM-DD] [HH:MM] [پیام]` - ارسال برنامه‌ریزی شده\n"
        "📋 `/list_scheduled` - نمایش لیست ارسال‌های برنامه‌ریزی شده\n"
        "🗑️ `/remove_scheduled [شماره]` - حذف ارسال برنامه‌ریزی شده\n"
        "🚫 `/ban [آیدی]` - مسدود کردن کاربر\n"
        "✅ `/unban [آیدی]` - رفع مسدودیت کاربر\n"
        "💌 `/direct_message [آیدی] [پیام]` - ارسال پیام مستقیم به کاربر\n"
        "ℹ️ `/user_info [آیدی]` - نمایش اطلاعات کاربر\n"
        "📝 `/logs` - نمایش آخرین لاگ‌ها\n"
        "📂 `/logs_file` - دانلود فایل کامل لاگ‌ها\n"
        "👥 `/users_list [صفحه]` - نمایش لیست کاربران\n"
        "🔍 `/user_search [نام]` - جستجوی کاربر بر اساس نام\n"
        "💾 `/backup` - ایجاد نسخه پشتیبان از داده‌ها\n"
        "📊 `/export_csv` - دانلود اطلاعات کاربران در فایل CSV\n"
        "🔧 `/maintenance [on/off]` - فعال/غیرفعال کردن حالت نگهداری\n"
        "👋 `/set_welcome [پیام]` - تنظیم پیام خوشامدگویی\n"
        "👋 `/set_goodbye [پیام]` - تنظیم پیام خداحافظی\n"
        "📈 `/activity_heatmap` - دریافت نمودار فعالیت کاربران\n"
        "⏱️ `/response_stats` - نمایش آمار زمان پاسخگویی\n"
        "🚫 `/add_blocked_word [کلمه]` - افزودن کلمه مسدود\n"
        "✅ `/remove_blocked_word [کلمه]` - حذف کلمه مسدود\n"
        "📜 `/list_blocked_words` - نمایش لیست کلمات مسدود\n"
        "💻 `/system_info` - نمایش اطلاعات سیستم\n"
        "🔄 `/reset_stats [messages/all]` - ریست کردن آمار\n"
        "📋 `/commands` - نمایش این لیست دستورات"
    )
    await update.message.reply_text(commands_text, parse_mode='Markdown')

@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار ربات را نمایش می‌دهد."""
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
async def admin_targeted_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام به گروه خاصی از کاربران بر اساس معیارهای مشخص."""
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ فرمت صحیح: `/targeted_broadcast [معیار] [مقدار] [پیام]`\n"
                                       "معیارهای موجود: `active_days`, `message_count`, `banned`")
        return
    
    criteria = context.args[0].lower()
    value = context.args[1]
    message_text = " ".join(context.args[2:])
    
    target_users = []
    
    if criteria == "active_days":
        try:
            days = int(value)
            target_users = data_manager.get_active_users(days)
        except ValueError:
            await update.message.reply_text("⚠️ مقدار روز باید یک عدد صحیح باشد.")
            return
    
    elif criteria == "message_count":
        try:
            min_count = int(value)
            target_users = data_manager.get_users_by_message_count(min_count)
        except ValueError:
            await update.message.reply_text("⚠️ تعداد پیام باید یک عدد صحیح باشد.")
            return
    
    elif criteria == "banned":
        if value.lower() == "true":
            target_users = list(data_manager.DATA['banned_users'])
        elif value.lower() == "false":
            for user_id in data_manager.DATA['users']:
                if int(user_id) not in data_manager.DATA['banned_users']:
                    target_users.append(int(user_id))
        else:
            await update.message.reply_text("⚠️ مقدار برای معیار banned باید true یا false باشد.")
            return
    
    else:
        await update.message.reply_text("⚠️ معیار نامعتبر است. معیارهای موجود: active_days, message_count, banned")
        return
    
    if not target_users:
        await update.message.reply_text("هیچ کاربری با معیارهای مشخص شده یافت نشد.")
        return
    
    await update.message.reply_text(f"📣 در حال ارسال پیام به `{len(target_users)}` کاربر...")
    
    total_sent, total_failed = 0, 0
    for user_id in target_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text)
            total_sent += 1
            await asyncio.sleep(0.05)
        except TelegramError as e:
            logger.warning(f"Failed to send targeted broadcast to {user_id}: {e}")
            total_failed += 1
    
    result_text = f"✅ **ارسال هدفمند تمام شد**\n\n✅ موفق: `{total_sent}`\n❌ ناموفق: `{total_failed}`"
    await update.message.reply_text(result_text, parse_mode='Markdown')

@admin_only
async def admin_schedule_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم ارسال برنامه‌ریزی شده پیام به همه کاربران."""
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ فرمت صحیح: `/schedule_broadcast [YYYY-MM-DD] [HH:MM] [پیام]`")
        return
    
    try:
        date_str, time_str = context.args[0], context.args[1]
        message_text = " ".join(context.args[2:])
        
        scheduled_time = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
        
        if scheduled_time <= datetime.now():
            await update.message.reply_text("⚠️ زمان برنامه‌ریزی شده باید در آینده باشد.")
            return
        
        data_manager.DATA['scheduled_broadcasts'].append({
            'time': scheduled_time.strftime('%Y-%m-%d %H:%M:%S'),
            'message': message_text,
            'status': 'pending'
        })
        data_manager.save_data()
        
        await update.message.reply_text(f"✅ پیام برای زمان `{scheduled_time.strftime('%Y-%m-%d %H:%M')}` برنامه‌ریزی شد.")
        
    except ValueError:
        await update.message.reply_text("⚠️ فرمت زمان نامعتبر است. لطفاً از فرمت YYYY-MM-DD HH:MM استفاده کنید.")

@admin_only
async def admin_list_scheduled_broadcasts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست ارسال‌های برنامه‌ریزی شده."""
    if not data_manager.DATA['scheduled_broadcasts']:
        await update.message.reply_text("هیچ ارسال برنامه‌ریزی شده‌ای وجود ندارد.")
        return
    
    broadcasts_text = "📅 **لیست ارسال‌های برنامه‌ریزی شده:**\n\n"
    for i, broadcast in enumerate(data_manager.DATA['scheduled_broadcasts'], 1):
        status_emoji = "✅" if broadcast['status'] == 'sent' else "⏳"
        broadcasts_text += f"{i}. {status_emoji} `{broadcast['time']}` - {broadcast['message'][:50]}...\n"
    
    await update.message.reply_text(broadcasts_text, parse_mode='Markdown')

@admin_only
async def admin_remove_scheduled_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف یک ارسال برنامه‌ریزی شده."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً شماره ارسال برنامه‌ریزی شده را وارد کنید.\nمثال: `/remove_scheduled 1`")
        return
    
    index = int(context.args[0]) - 1
    
    if not data_manager.DATA['scheduled_broadcasts'] or not (0 <= index < len(data_manager.DATA['scheduled_broadcasts'])):
        await update.message.reply_text("⚠️ شماره ارسال برنامه‌ریزی شده نامعتبر است.")
        return
    
    removed_broadcast = data_manager.DATA['scheduled_broadcasts'].pop(index)
    data_manager.save_data()
    
    await update.message.reply_text(f"✅ ارسال برنامه‌ریزی شده برای زمان `{removed_broadcast['time']}` حذف شد.")

@admin_only
async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یک کاربر را با آیدی عددی مسدود کرده و به او اطلاع می‌دهد."""
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
    
    # ارسال پیام به کاربر مسدود شده
    try:
        await context.bot.send_message(
            chat_id=user_id_to_ban, 
            text="⛔️ شما توسط ادمین ربات مسدود شدید و دیگر نمی‌توانید از خدمات ربات استفاده کنید."
        )
    except TelegramError as e:
        logger.warning(f"Could not send ban notification to user {user_id_to_ban}: {e}")

    await update.message.reply_text(f"✅ کاربر `{user_id_to_ban}` با موفقیت مسدود شد.", parse_mode='Markdown')

@admin_only
async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسدودیت یک کاربر را برمی‌دارد و به او اطلاع می‌دهد."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ لطفاً آیدی عددی کاربر را وارد کنید.\nمثال: `/unban 123456789`")
        return

    user_id_to_unban = int(context.args[0])

    if not data_manager.is_user_banned(user_id_to_unban):
        await update.message.reply_text(f"کاربر `{user_id_to_unban}` در لیست مسدود شده‌ها وجود ندارد.")
        return

    data_manager.unban_user(user_id_to_unban)

    # ارسال پیام به کاربر برای رفع مسدودیت
    try:
        await context.bot.send_message(
            chat_id=user_id_to_unban, 
            text="✅ مسدودیت شما توسط ادمین ربات برداشته شد. می‌توانید دوباره از ربات استفاده کنید."
        )
    except TelegramError as e:
        logger.warning(f"Could not send unban notification to user {user_id_to_unban}: {e}")

    await update.message.reply_text(f"✅ مسدودیت کاربر `{user_id_to_unban}` با موفقیت برداشته شد.", parse_mode='Markdown')

@admin_only
async def admin_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال پیام مستقیم به یک کاربر خاص."""
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ فرمت صحیح: `/direct_message [آیدی] [پیام]`")
        return
    
    user_id_str = context.args[0]
    if not user_id_str.isdigit():
        await update.message.reply_text("⚠️ لطفاً یک آیدی عددی معتبر وارد کنید.")
        return
    
    message_text = " ".join(context.args[1:])
    user_id = int(user_id_str)
    
    try:
        await context.bot.send_message(chat_id=user_id, text=message_text)
        await update.message.reply_text(f"✅ پیام با موفقیت به کاربر `{user_id}` ارسال شد.", parse_mode='Markdown')
    except TelegramError as e:
        await update.message.reply_text(f"❌ خطا در ارسال پیام: {e}")

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
async def admin_logs_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فایل کامل لاگ ربات را ارسال می‌کند."""
    try:
        await update.message.reply_document(
            document=open(data_manager.LOG_FILE, 'rb'),
            caption="📂 فایل کامل لاگ‌های ربات"
        )
    except FileNotFoundError:
        await update.message.reply_text("فایل لاگ یافت نشد.")
    except Exception as e:
        await update.message.reply_text(f"خطایی در ارسال فایل لاگ رخ داد: {e}")

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
        os.remove(backup_file) # حذف فایل پس از ارسال
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ایجاد نسخه پشتیبان: {e}")
        logger.error(f"Error creating backup: {e}")

@admin_only
async def admin_export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد و ارسال فایل CSV از اطلاعات کاربران."""
    users = data_manager.DATA['users']
    
    df_data = []
    for user_id, user_info in users.items():
        is_banned = "بله" if int(user_id) in data_manager.DATA['banned_users'] else "خیر"
        df_data.append({
            'User ID': user_id,
            'First Name': user_info.get('first_name', 'N/A'),
            'Username': user_info.get('username', 'N/A'),
            'Message Count': user_info.get('message_count', 0),
            'First Seen': user_info.get('first_seen', 'N/A'),
            'Last Seen': user_info.get('last_seen', 'N/A'),
            'Banned': is_banned
        })
    
    df = pd.DataFrame(df_data)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        df.to_csv(f.name, index=False)
        temp_file_path = f.name
    
    await update.message.reply_document(
        document=open(temp_file_path, 'rb'),
        caption="📊 فایل CSV اطلاعات کاربران"
    )
    
    os.unlink(temp_file_path)

@admin_only
async def admin_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حالت نگهداری ربات را فعال یا غیرفعال کرده و به کاربران اطلاع می‌دهد."""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("⚠️ فرمت صحیح: `/maintenance on` یا `/maintenance off`")
        return

    status = context.args[0].lower()
    
    if status == 'on':
        if data_manager.DATA.get('maintenance_mode', False):
            await update.message.reply_text("🔧 ربات از قبل در حالت نگهداری قرار دارد.")
            return
            
        data_manager.DATA['maintenance_mode'] = True
        data_manager.save_data()
        
        await update.message.reply_text("✅ حالت نگهداری ربات فعال شد. در حال اطلاع‌رسانی به کاربران...")
        
        user_ids = list(data_manager.DATA['users'].keys())
        for user_id_str in user_ids:
            try:
                # به ادمین‌ها پیام ارسال نشود
                if int(user_id_str) not in ADMIN_IDS:
                    await context.bot.send_message(
                        chat_id=int(user_id_str), 
                        text="🔧 ربات در حال حاضر در حالت به‌روزرسانی و نگهداری قرار دارد. لطفاً چند لحظه دیگر صبر کنید. از صبر شما سپاسگزاریم!"
                    )
                    await asyncio.sleep(0.05) # جلوگیری از محدودیت تلگرام
            except TelegramError:
                continue # نادیده گرفتن کاربرانی که ربات را مسدود کرده‌اند

    elif status == 'off':
        if not data_manager.DATA.get('maintenance_mode', False):
            await update.message.reply_text("✅ ربات از قبل در حالت عادی قرار دارد.")
            return

        data_manager.DATA['maintenance_mode'] = False
        data_manager.save_data()

        await update.message.reply_text("✅ حالت نگهداری ربات غیرفعال شد. در حال اطلاع‌رسانی به کاربران...")

        user_ids = list(data_manager.DATA['users'].keys())
        for user_id_str in user_ids:
            try:
                if int(user_id_str) not in ADMIN_IDS:
                    await context.bot.send_message(
                        chat_id=int(user_id_str), 
                        text="✅ به‌روزرسانی ربات به پایان رسید. از صبر شما سپاسگزاریم! می‌توانید دوباره از ربات استفاده کنید."
                    )
                    await asyncio.sleep(0.05)
            except TelegramError:
                continue

@admin_only
async def admin_set_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم پیام خوشامدگویی جدید."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً پیام خوشامدگویی جدید را وارد کنید.\n"
                                       "مثال: `/set_welcome سلام {user_mention}! به ربات خوش آمدید.`")
        return
    
    new_message = " ".join(context.args)
    data_manager.DATA['welcome_message'] = new_message
    data_manager.save_data()
    
    await update.message.reply_text("✅ پیام خوشامدگویی با موفقیت به‌روزرسانی شد.")

@admin_only
async def admin_set_goodbye_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم پیام خداحافظی جدید."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً پیام خداحافظی جدید را وارد کنید.\n"
                                       "مثال: `/set_goodbye {user_mention}، خداحافظ!`")
        return
    
    new_message = " ".join(context.args)
    data_manager.DATA['goodbye_message'] = new_message
    data_manager.save_data()
    
    await update.message.reply_text("✅ پیام خداحافظی با موفقیت به‌روزرسانی شد.")

@admin_only
async def admin_activity_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد و ارسال نمودار فعالیت کاربران."""
    users = data_manager.DATA['users']
    activity_hours = [0] * 24
    
    for user_info in users.values():
        if 'last_seen' in user_info:
            try:
                last_seen = datetime.strptime(user_info['last_seen'], '%Y-%m-%d %H:%M:%S')
                activity_hours[last_seen.hour] += 1
            except ValueError:
                continue
    
    plt.figure(figsize=(12, 6))
    plt.bar(range(24), activity_hours, color='skyblue')
    plt.title('نمودار فعالیت کاربران بر اساس ساعت')
    plt.xlabel('ساعت')
    plt.ylabel('تعداد کاربران فعال')
    plt.xticks(range(24))
    plt.grid(axis='y', alpha=0.3)
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        plt.savefig(f.name, bbox_inches='tight')
        temp_file_path = f.name
    
    plt.close()
    
    await update.message.reply_photo(
        photo=open(temp_file_path, 'rb'),
        caption="📊 نمودار فعالیت کاربران بر اساس ساعت"
    )
    
    os.unlink(temp_file_path)

@admin_only
async def admin_response_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار زمان پاسخگویی ربات."""
    stats = data_manager.DATA['stats']
    await update.message.reply_text(
        "📈 **آمار زمان پاسخگویی ربات**\n\n"
        f"🟢 میانگین زمان پاسخگویی: `{stats.get('avg_response_time', 'N/A'):.2f}` ثانیه\n"
        f"🔴 بیشترین زمان پاسخگویی: `{stats.get('max_response_time', 'N/A'):.2f}` ثانیه\n"
        f"🟢 کمترین زمان پاسخگویی: `{stats.get('min_response_time', 'N/A'):.2f}` ثانیه\n"
        f"📊 کل پاسخ‌های ثبت شده: `{stats.get('total_responses', 'N/A')}`"
    )

@admin_only
async def admin_add_blocked_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن کلمه یا عبارت به لیست کلمات مسدود شده."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً کلمه یا عبارت مورد نظر را وارد کنید.\n"
                                       "مثال: `/add_blocked_word کلمه_نامناسب`")
        return
    
    word = " ".join(context.args).lower()
    
    if word in data_manager.DATA['blocked_words']:
        await update.message.reply_text(f"⚠️ کلمه «{word}» از قبل در لیست کلمات مسدود شده وجود دارد.")
        return
    
    data_manager.DATA['blocked_words'].append(word)
    data_manager.save_data()
    
    await update.message.reply_text(f"✅ کلمه «{word}» به لیست کلمات مسدود شده اضافه شد.")

@admin_only
async def admin_remove_blocked_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف کلمه یا عبارت از لیست کلمات مسدود شده."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً کلمه یا عبارت مورد نظر را وارد کنید.\n"
                                       "مثال: `/remove_blocked_word کلمه_نامناسب`")
        return
    
    word = " ".join(context.args).lower()
    
    if word not in data_manager.DATA['blocked_words']:
        await update.message.reply_text(f"⚠️ کلمه «{word}» در لیست کلمات مسدود شده وجود ندارد.")
        return
    
    data_manager.DATA['blocked_words'].remove(word)
    data_manager.save_data()
    
    await update.message.reply_text(f"✅ کلمه «{word}» از لیست کلمات مسدود شده حذف شد.")

@admin_only
async def admin_list_blocked_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست کلمات مسدود شده."""
    if not data_manager.DATA['blocked_words']:
        await update.message.reply_text("هیچ کلمه مسدود شده‌ای در لیست وجود ندارد.")
        return
    
    words_list = "\n".join([f"• {word}" for word in data_manager.DATA['blocked_words']])
    await update.message.reply_text(f"🚫 **لیست کلمات مسدود شده:**\n\n{words_list}")

@admin_only
async def admin_system_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش اطلاعات سیستم و منابع."""
    bot_start_time_str = data_manager.DATA.get('bot_start_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    bot_start_time = datetime.strptime(bot_start_time_str, '%Y-%m-%d %H:%M:%S')
    uptime = datetime.now() - bot_start_time
    
    system_info = (
        f"💻 **اطلاعات سیستم:**\n\n"
        f"🖥️ سیستم‌عامل: {platform.system()} {platform.release()}\n"
        f"🐍 نسخه پایتون: {platform.python_version()}\n"
        f"💾 حافظه RAM استفاده شده: {psutil.virtual_memory().percent}%\n"
        f"💾 حافظه RAM آزاد: {psutil.virtual_memory().available / (1024**3):.2f} GB\n"
        f"💾 فضای دیسک استفاده شده: {psutil.disk_usage('/').percent}%\n"
        f"💾 فضای دیسک آزاد: {psutil.disk_usage('/').free / (1024**3):.2f} GB\n"
        f"⏱️ زمان اجرای ربات: {uptime}"
    )
    
    await update.message.reply_text(system_info, parse_mode='Markdown')

@admin_only
async def admin_reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ریست کردن آمار ربات."""
    if not context.args:
        await update.message.reply_text("⚠️ لطفاً نوع آماری که می‌خواهید ریست کنید را مشخص کنید.\n"
                                       "مثال: `/reset_stats messages` یا `/reset_stats all`")
        return
    
    stat_type = context.args[0].lower()
    
    if stat_type == "messages":
        data_manager.DATA['stats']['total_messages'] = 0
        for user_id in data_manager.DATA['users']:
            data_manager.DATA['users'][user_id]['message_count'] = 0
        await update.message.reply_text("✅ آمار پیام‌ها با موفقیت ریست شد.")
    
    elif stat_type == "all":
        data_manager.DATA['stats'] = {
            'total_messages': 0,
            'total_users': len(data_manager.DATA['users']),
            'avg_response_time': 0,
            'max_response_time': 0,
            'min_response_time': 0,
            'total_responses': 0
        }
        for user_id in data_manager.DATA['users']:
            data_manager.DATA['users'][user_id]['message_count'] = 0
        await update.message.reply_text("✅ تمام آمارها با موفقیت ریست شد.")
    
    else:
        await update.message.reply_text("⚠️ نوع آمار نامعتبر است. گزینه‌های موجود: messages, all")
        return
    
    data_manager.save_data()

# --- هندلر برای دکمه‌های صفحه‌بندی ---
async def users_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش دکمه‌های صفحه‌بندی لیست کاربران."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("users_list:"):
        page = int(query.data.split(":")[1])
        context.args = [str(page)]
        await admin_users_list(update, context)

# --- تابع برای پردازش ارسال‌های برنامه‌ریزی شده ---
async def process_scheduled_broadcasts(context: ContextTypes.DEFAULT_TYPE):
    """پردازش ارسال‌های برنامه‌ریزی شده و ارسال پیام‌ها در زمان مقرر."""
    now = datetime.now()
    broadcasts_to_send_indices = []
    
    for i, broadcast in enumerate(data_manager.DATA['scheduled_broadcasts']):
        if broadcast['status'] == 'pending':
            broadcast_time = datetime.strptime(broadcast['time'], '%Y-%m-%d %H:%M:%S')
            if broadcast_time <= now:
                broadcasts_to_send_indices.append(i)

    if not broadcasts_to_send_indices:
        return
    
    user_ids = list(data_manager.DATA['users'].keys())
    
    for index in broadcasts_to_send_indices:
        broadcast = data_manager.DATA['scheduled_broadcasts'][index]
        message_text = broadcast['message']
        total_sent, total_failed = 0, 0
        
        for user_id_str in user_ids:
            try:
                await context.bot.send_message(chat_id=int(user_id_str), text=message_text)
                total_sent += 1
                await asyncio.sleep(0.05)
            except TelegramError as e:
                logger.warning(f"Failed to send scheduled broadcast to {user_id_str}: {e}")
                total_failed += 1
        
        # به‌روزرسانی وضعیت ارسال
        data_manager.DATA['scheduled_broadcasts'][index]['status'] = 'sent'
        data_manager.DATA['scheduled_broadcasts'][index]['sent_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
        data_manager.DATA['scheduled_broadcasts'][index]['sent_count'] = total_sent
        data_manager.DATA['scheduled_broadcasts'][index]['failed_count'] = total_failed
        
        logger.info(f"Scheduled broadcast sent: {total_sent} successful, {total_failed} failed")
    
    data_manager.save_data()

# --- تابع راه‌اندازی هندلرها ---
def setup_admin_handlers(application):
    """هندلرهای پنل ادمین را به اپلیکیشن اضافه می‌کند."""
    # هندلرهای اصلی
    application.add_handler(CommandHandler("commands", admin_commands))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("unban", admin_unban))
    application.add_handler(CommandHandler("user_info", admin_userinfo))
    application.add_handler(CommandHandler("logs", admin_logs))
    application.add_handler(CommandHandler("logs_file", admin_logs_file)) # <--- هندلر جدید
    application.add_handler(CommandHandler("users_list", admin_users_list))
    application.add_handler(CommandHandler("user_search", admin_user_search))
    application.add_handler(CommandHandler("backup", admin_backup))
    
    # هندلرهای جدید
    application.add_handler(CommandHandler("targeted_broadcast", admin_targeted_broadcast))
    application.add_handler(CommandHandler("schedule_broadcast", admin_schedule_broadcast))
    application.add_handler(CommandHandler("list_scheduled", admin_list_scheduled_broadcasts))
    application.add_handler(CommandHandler("remove_scheduled", admin_remove_scheduled_broadcast))
    application.add_handler(CommandHandler("direct_message", admin_direct_message))
    application.add_handler(CommandHandler("export_csv", admin_export_csv))
    application.add_handler(CommandHandler("maintenance", admin_maintenance)) # <--- هندلر جایگزین شده
    application.add_handler(CommandHandler("set_welcome", admin_set_welcome_message))
    application.add_handler(CommandHandler("set_goodbye", admin_set_goodbye_message))
    application.add_handler(CommandHandler("activity_heatmap", admin_activity_heatmap))
    application.add_handler(CommandHandler("response_stats", admin_response_stats))
    application.add_handler(CommandHandler("add_blocked_word", admin_add_blocked_word))
    application.add_handler(CommandHandler("remove_blocked_word", admin_remove_blocked_word))
    application.add_handler(CommandHandler("list_blocked_words", admin_list_blocked_words))
    application.add_handler(CommandHandler("system_info", admin_system_info))
    application.add_handler(CommandHandler("reset_stats", admin_reset_stats))
    
    # هندلر برای دکمه‌های صفحه‌بندی
    application.add_handler(CallbackQueryHandler(users_list_callback, pattern="^users_list:"))
    
    # شروع وظیفه دوره‌ای برای بررسی ارسال‌های برنامه‌ریزی شده
    application.job_queue.run_repeating(process_scheduled_broadcasts, interval=60, first=0)
    
    logger.info("Admin panel handlers have been set up.")
