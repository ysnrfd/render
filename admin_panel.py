# admin_panel.py

import logging
import os
import sys
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters
from data_store import load_data, save_data, ban_user, unban_user

logger = logging.getLogger(__name__)

# --- احراز هویت مدیر از متغیرهای محیطی ---
try:
    ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]
    ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
except KeyError:
    logger.critical("FATAL: ADMIN_USERNAME or ADMIN_PASSWORD not set.")
    sys.exit(1)

# --- حالت‌های مکالمه برای ویژگی‌های تعاملی ---
(CHANGE_TEMP, CHANGE_MODEL, BROADCAST_MSG, DM_USER_MSG) = range(5)

# --- داده‌های محلی پنل مدیریت ---
admin_sessions = {}
admin_logs = []

def log_admin_action(user_id: int, action: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Admin {user_id}: {action}"
    admin_logs.append(log_entry)
    logger.info(f"ADMIN LOG: {log_entry}")

def is_admin(user_id: int) -> bool:
    return user_id in admin_sessions and admin_sessions[user_id].get("authenticated", False)

# --- توابع اصلی احراز هویت و منو ---
async def authenticate_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    if is_admin(user_id):
        await show_admin_menu(update, context)
        return
    if user_id in admin_sessions:
        step = admin_sessions[user_id].get("step")
        if step == "username":
            if message_text == ADMIN_USERNAME:
                admin_sessions[user_id]["step"] = "password"
                await update.message.reply_text("✅ نام کاربری صحیح است.\n\nلطفاً رمز عبور را وارد کنید:")
            else:
                await update.message.reply_text("❌ نام کاربری اشتباه است.")
            return
        if step == "password":
            if message_text == ADMIN_PASSWORD:
                admin_sessions[user_id]["authenticated"] = True
                log_admin_action(user_id, "Authenticated")
                await update.message.reply_text("✅ احراز هویت با موفقیت انجام شد!")
                await show_admin_menu(update, context)
            else:
                await update.message.reply_text("❌ رمز عبور اشتباه است.")
                del admin_sessions[user_id]
            return
    admin_sessions[user_id] = {"step": "username", "authenticated": False}
    await update.message.reply_text("🔐 برای ورود به پنل مدیریت، لطفاً نام کاربری را وارد کنید:")

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    maintenance_status = "🔴 روشن" if context.application.bot_data.get('maintenance_mode') else "🟢 خاموش"
    
    keyboard = [
        [InlineKeyboardButton("📊 داشبورد آمار", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users_menu")],
        [InlineKeyboardButton("📢 ارسال پیام", callback_data="admin_message_menu")],
        [InlineKeyboardButton("⚙️ تنظیمات پیشرفته", callback_data="admin_settings_menu")],
        [InlineKeyboardButton("📋 لاگ‌ها و دانلود", callback_data="admin_logs_menu")],
        [InlineKeyboardButton(f"🛠️ حالت تعمیرات: {maintenance_status}", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton("🔄 راه‌اندازی مجدد", callback_data="admin_restart")],
        [InlineKeyboardButton("🚪 خروج", callback_data="admin_logout")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠️ منوی مدیریت پیشرفته:", reply_markup=reply_markup)

# --- پردازشگر اصلی کال‌بک‌ها ---
async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ دسترسی غیرمجاز.")
        return

    action = query.data
    log_admin_action(user_id, f"Clicked on {action}")

    if action == "admin_stats":
        await show_admin_stats(query, context)
    elif action == "admin_users_menu":
        await show_users_menu(query)
    elif action == "admin_message_menu":
        await show_message_menu(query)
    elif action == "admin_settings_menu":
        await show_settings_menu(query, context)
    elif action == "admin_logs_menu":
        await show_logs_menu(query)
    elif action == "admin_toggle_maintenance":
        await toggle_maintenance_mode(query, context)
    elif action == "admin_restart":
        await restart_bot(query)
    elif action == "admin_logout":
        await logout_admin(query)
    elif action.startswith("admin_back_"):
        target_menu = action.replace("admin_back_", "")
        if target_menu == "main":
            await show_admin_menu(update, context)
        elif target_menu == "users":
            await show_users_menu(query)
        elif target_menu == "settings":
            await show_settings_menu(query, context)
    elif action.startswith("user_"):
        await handle_user_action(query, context, action)
    elif action == "settings_change_temp":
        await query.edit_message_text("🌡️ لطفاً دمای جدید (بین 0.0 تا 2.0) را وارد کنید:")
        return CHANGE_TEMP
    elif action == "settings_change_model":
        await query.edit_message_text("🧠 لطفاً نام مدل جدید را وارد کنید:")
        return CHANGE_MODEL
    elif action == "broadcast_prompt":
        await query.edit_message_text("📢 پیام همگانی خود را بنویسید:")
        return BROADCAST_MSG
    elif action == "admin_download_logs":
        await download_logs(query)
    elif action == "admin_view_logs":
        await show_admin_logs(query)
    elif action == "user_list":
        data = load_data()
        await show_user_list(query, data)

# --- ویژگی: داشبورد آمار ---
async def show_admin_stats(query, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    total_users = len(data['user_stats'])
    total_messages = sum(u['message_count'] for u in data['user_stats'].values())
    banned_users = len(data['banned_users'])
    
    stats_text = (
        f"📊 **داشبورد آمار ربات**\n\n"
        f"👥 کل کاربران: `{total_users}`\n"
        f"📨 کل پیام‌ها: `{total_messages}`\n"
        f"🚫 کاربران بن شده: `{banned_users}`\n"
        f"⏰ زمان فعلی: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ویژگی: مدیریت کاربران ---
async def show_users_menu(query):
    keyboard = [
        [InlineKeyboardButton("📋 مشاهده لیست کاربران", callback_data="user_list")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👥 مدیریت کاربران:", reply_markup=reply_markup)

async def handle_user_action(query, context: ContextTypes.DEFAULT_TYPE, action: str):
    data = load_data()
    parts = action.split('_')
    action_type = parts[1]
    user_id_str = parts[2]

    if user_id_str not in data['user_stats']:
        await query.answer("کاربر پیدا نشد.", show_alert=True)
        return

    user_info = data['user_stats'][user_id_str]
    user_id = int(user_id_str)
    
    if action_type == "details":
        is_banned = str(user_id) in data['banned_users']
        details_text = (
            f"👤 **جزئیات کاربر**\n\n"
            f"🆔 آیدی: `{user_id}`\n"
            f"👤 نام کاربری: @{user_info.get('username', 'N/A')}\n"
            f"📅 اولین بازدید: {user_info['first_seen'][:10]}\n"
            f"📅 آخرین بازدید: {user_info['last_seen'][:10]}\n"
            f"📨 تعداد پیام‌ها: `{user_info['message_count']}`\n"
            f"🚫 وضعیت: {'بن شده' if is_banned else 'عادی'}"
        )
        keyboard = [
            [InlineKeyboardButton("📩 ارسال پیام", callback_data=f"dm_user_{user_id}")],
            [InlineKeyboardButton("📜 مشاهده تاریخچه", callback_data=f"history_user_{user_id}")],
            [InlineKeyboardButton("✅ آنبن کردن" if is_banned else "🚫 بن کردن", callback_data=f"ban_user_{user_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(details_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif action_type == "ban":
        if str(user_id) in data['banned_users']:
            unban_user(user_id)
            log_admin_action(query.from_user.id, f"Unbanned user {user_id}")
            await query.answer("کاربر آنبن شد.", show_alert=True)
        else:
            ban_user(user_id)
            log_admin_action(query.from_user.id, f"Banned user {user_id}")
            await query.answer("کاربر با موفقیت بن شد.", show_alert=True)
        await handle_user_action(query, context, f"user_details_{user_id}")

    elif action_type == "dm":
        context.user_data['dm_target_id'] = user_id
        await query.edit_message_text(f"📩 پیام خود را برای ارسال به کاربر `{user_id}` وارد کنید:", parse_mode='Markdown')
        return DM_USER_MSG

    elif action_type == "history":
        history = context.application.bot_data.get('chat_history', {}).get(str(user_id), [])
        if not history:
            history_text = "هیچ تاریخچه‌ای برای این کاربر یافت نشد."
        else:
            history_text = "📜 **آخرین پیام‌های ذخیره شده:**\n\n"
            for i, msg in enumerate(history):
                role = "👤 User" if msg['role'] == 'user' else "🤖 Bot"
                history_text += f"{i+1}. {role}: {msg['content']}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"user_details_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(history_text, reply_markup=reply_markup, parse_mode='Markdown')
        
async def show_user_list(query, data):
    users = list(data['user_stats'].items())[-15:]
    text = "📋 **آخرین کاربران:**\n\n"
    keyboard = []
    for user_id_str, info in users:
        username = info.get('username', 'N/A')
        text += f"• `{user_id_str}` - @{username}\n"
        keyboard.append([InlineKeyboardButton(f"👤 @{username} ({user_id_str})", callback_data=f"user_details_{user_id_str}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_users")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ویژگی: ارسال پیام ---
async def show_message_menu(query):
    keyboard = [
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="broadcast_prompt")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📢 ارسال پیام:", reply_markup=reply_markup)

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    
    message_text = update.message.text
    data = load_data()
    sent_count, failed_count = 0, 0
    
    await update.message.reply_text("📡 در حال ارسال پیام همگانی...")
    
    for user_id_str in data['user_stats']:
        if str(user_id_str) in data['banned_users']: continue
        try:
            await context.bot.send_message(chat_id=int(user_id_str), text=message_text)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1
            
    log_admin_action(update.effective_user.id, f"Broadcasted message to {sent_count} users. {failed_count} failed.")
    await update.message.reply_text(f"✅ ارسال تمام شد.\n✅ موفق: {sent_count}\n❌ ناموفق: {failed_count}")
    return ConversationHandler.END

async def handle_dm_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    
    target_id = context.user_data.get('dm_target_id')
    if not target_id:
        await update.message.reply_text("خطا: کاربر هدف مشخص نشده است.")
        return ConversationHandler.END
        
    message_text = update.message.text
    try:
        await context.bot.send_message(chat_id=target_id, text=message_text)
        await update.message.reply_text(f"✅ پیام به کاربر `{target_id}` ارسال شد.", parse_mode='Markdown')
        log_admin_action(update.effective_user.id, f"Sent DM to {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ ارسال پیام ناموفق بود: {e}")
        
    del context.user_data['dm_target_id']
    return ConversationHandler.END

# --- ویژگی: تنظیمات پیشرفته ---
async def show_settings_menu(query, context: ContextTypes.DEFAULT_TYPE):
    settings = context.application.bot_data.get('settings', {})
    text = f"⚙️ **تنظیمات پیشرفته**\n\n🧠 مدل: `{settings.get('model')}`\n🌡️ دما: `{settings.get('temperature')}`"
    keyboard = [
        [InlineKeyboardButton("🌡️ تغییر دما", callback_data="settings_change_temp")],
        [InlineKeyboardButton("🧠 تغییر مدل", callback_data="settings_change_model")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_setting_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    
    new_value = update.message.text
    current_state = context.user_data.get('admin_setting_state')
    
    if current_state == CHANGE_TEMP:
        try:
            temp = float(new_value)
            if 0.0 <= temp <= 2.0:
                context.application.bot_data['settings']['temperature'] = temp
                await update.message.reply_text(f"✅ دما با موفقیت به `{temp}` تغییر یافت.", parse_mode='Markdown')
                log_admin_action(update.effective_user.id, f"Changed temperature to {temp}")
            else:
                await update.message.reply_text("❌ مقدار نامعتبر است. لطفاً عددی بین 0.0 و 2.0 وارد کنید.")
                return
        except ValueError:
            await update.message.reply_text("❌ فرمت نامعتبر است. لطفاً یک عدد وارد کنید.")
            return

    elif current_state == CHANGE_MODEL:
        context.application.bot_data['settings']['model'] = new_value
        await update.message.reply_text(f"✅ مدل با موفقیت به `{new_value}` تغییر یافت.", parse_mode='Markdown')
        log_admin_action(update.effective_user.id, f"Changed model to {new_value}")

    del context.user_data['admin_setting_state']
    return ConversationHandler.END

# --- ویژگی: لاگ‌ها و دانلود ---
async def show_logs_menu(query):
    keyboard = [
        [InlineKeyboardButton("👀 مشاهده لاگ‌ها", callback_data="admin_view_logs")],
        [InlineKeyboardButton("💾 دانلود لاگ‌ها", callback_data="admin_download_logs")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📋 مدیریت لاگ‌ها:", reply_markup=reply_markup)

async def show_admin_logs(query):
    if not admin_logs:
        await query.edit_message_text("هیچ لاگ مدیریتی ثبت نشده است.")
        return
    recent_logs = admin_logs[-20:]
    logs_text = "📋 **آخرین لاگ‌های مدیریتی:**\n\n" + "\n".join(recent_logs)
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(logs_text, reply_markup=reply_markup, parse_mode='Markdown')

async def download_logs(query):
    log_content = "\n".join(admin_logs)
    if not log_content: log_content = "No admin logs available."
    log_file = io.BytesIO(log_content.encode('utf-8'))
    log_file.name = f"admin_logs_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    await query.message.reply_document(document=log_file, caption="📋 فایل لاگ‌های مدیریتی شما")
    await query.edit_message_text("✅ فایل لاگ آماده شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]))

# --- ویژگی: حالت تعمیرات ---
async def toggle_maintenance_mode(query, context: ContextTypes.DEFAULT_TYPE):
    current_mode = context.application.bot_data.get('maintenance_mode', False)
    new_mode = not current_mode
    context.application.bot_data['maintenance_mode'] = new_mode
    status_text = "روشن" if new_mode else "خاموش"
    log_admin_action(query.from_user.id, f"Toggled maintenance mode to {status_text}")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"✅ حالت تعمیرات **{status_text}** شد.", reply_markup=reply_markup, parse_mode='Markdown')

# --- ویژگی‌های پایه ---
async def restart_bot(query):
    log_admin_action(query.from_user.id, "Requested bot restart")
    await query.edit_message_text("🔄 در حال راه‌اندازی مجدد ربات...")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def logout_admin(query):
    user_id = query.from_user.id
    if user_id in admin_sessions:
        del admin_sessions[user_id]
        log_admin_action(user_id, "Logged out")
    await query.edit_message_text("✅ شما با موفقیت از پنل مدیریت خارج شدید.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await authenticate_admin(update, context)

# --- ثبت هندلرها ---
def setup_admin_handlers(application):
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_callback_handler, pattern="^(settings_change_temp|settings_change_model|dm_user_|broadcast_prompt)$")
        ],
        states={
            CHANGE_TEMP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_setting_change)],
            CHANGE_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_setting_change)],
            DM_USER_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dm_to_user)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)],
        },
        fallbacks=[CommandHandler("admin", admin_command)],
        per_message=False
    )
    
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^user_"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^settings_"))
    application.add_handler(conv_handler)

    # ذخیره state برای کنترل بهتر
    application.add_handler(CallbackQueryHandler(lambda u, c: c.user_data.__setitem__('admin_setting_state', CHANGE_TEMP), pattern="^settings_change_temp$"))
    application.add_handler(CallbackQueryHandler(lambda u, c: c.user_data.__setitem__('admin_setting_state', CHANGE_MODEL), pattern="^settings_change_model$"))
    application.add_handler(CallbackQueryHandler(lambda u, c: c.user_data.__setitem__('admin_setting_state', BROADCAST_MSG), pattern="^broadcast_prompt$"))
