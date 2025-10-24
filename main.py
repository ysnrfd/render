# main.py

import os
import logging
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from keep_alive import start_keep_alive

# --- وارد کردن ماژول‌های سفارشی ---
from admin_panel import setup_admin_handlers
from data_store import update_user_stats, is_user_banned

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ایجاد یک کلاینت HTTP بهینه‌سازی‌شده ---
http_client = httpx.AsyncClient(
    http2=True,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0),
    timeout=httpx.Timeout(timeout=60.0, connect=10.0, read=45.0, write=10.0)
)

# کلاینت OpenAI (HuggingFace)
client = AsyncOpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ["HF_TOKEN"],
    http_client=http_client
)

# --- توابع کمکی برای مدیریت وظایف ---
def _cleanup_task(task: asyncio.Task, user_id: int, application):
    """پس از اتمام یک وظیفه، آن را از لیست وظایف حذف می‌کند."""
    user_tasks = application.bot_data.get('user_tasks', {})
    if user_id in user_tasks and user_tasks[user_id] == task:
        del user_tasks[user_id]
        logger.info(f"Cleaned up finished task for user {user_id}.")
    try:
        exception = task.exception()
        if exception:
            logger.error(f"Background task for user {user_id} failed: {exception}")
    except asyncio.CancelledError:
        logger.info(f"Task for user {user_id} was cancelled.")

async def _process_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست کاربر را پردازش کرده و پاسخ را برمی‌گرداند."""
    chat_id = update.effective_chat.id
    user_message = update.message.text
    user_id = update.effective_user.id
    user_id_str = str(user_id)

    # --- مدیریت تاریخچه چت (با محدودیت ۳ پیام) ---
    chat_history = context.application.bot_data.get('chat_history', {})
    if user_id_str not in chat_history:
        chat_history[user_id_str] = []

    # پیام کاربر را به تاریخچه اضافه کن
    chat_history[user_id_str].append({"role": "user", "content": user_message})

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # خواندن تنظیمات از bot_data
        bot_settings = context.application.bot_data.get('settings', {})
        model = bot_settings.get('model', "huihui-ai/gemma-3-27b-it-abliterated:featherless-ai")
        temperature = bot_settings.get('temperature', 0.7)

        # ارسال کل تاریخچه به مدل
        response = await client.chat.completions.create(
            model=model,
            messages=chat_history[user_id_str],
            temperature=temperature,
            top_p=0.95,
            stream=False,
        )
        
        bot_response = response.choices[0].message.content

        # پاسخ ربات را به تاریخچه اضافه کن
        chat_history[user_id_str].append({"role": "assistant", "content": bot_response})

        # نکته کلیدی: فقط ۳ پیام آخر را نگه دار
        if len(chat_history[user_id_str]) > 3:
            chat_history[user_id_str] = chat_history[user_id_str][-3:]

        # ارسال پاسخ به کاربر
        await update.message.reply_text(bot_response)

    except httpx.TimeoutException:
        logger.warning(f"Request timed out for user {user_id}.")
        await update.message.reply_text("⏱️ ارتباط با سرور هوش مصنوعی طولانی شد. لطفاً دوباره تلاش کنید.")
    except Exception as e:
        logger.error(f"Error while processing message for user {user_id}: {e}")
        await update.message.reply_text("❌ متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید.")

# --- هندلرهای اصلی ربات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال پیام خوشامدگویی."""
    user = update.effective_user
    await update.message.reply_html(
        f"سلام {user.mention_html()}! 🤖\n\n"
        f"من یک ربات هوشمند هستم. هر سوالی دارید بپرسید."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پیام‌های کاربران را مدیریت می‌کند."""
    user_id = update.effective_user.id
    
    # 1. بررسی بن بودن کاربر
    if is_user_banned(user_id):
        logger.info(f"Banned user {user_id} tried to use the bot.")
        return

    # 2. بررسی حالت تعمیرات
    if context.application.bot_data.get('maintenance_mode', False):
        from admin_panel import is_admin 
        if not is_admin(user_id):
            await update.message.reply_text("🛠️ ربات در حال حاضر در حالت تعمیرات است. لطفاً بعداً تلاش کنید.")
            return

    # به‌روزرسانی آمار کاربر
    update_user_stats(user_id, update.effective_user.username)
    
    # پردازش پیام
    user_tasks = context.application.bot_data.get('user_tasks', {})
    if user_id in user_tasks and not user_tasks[user_id].done():
        user_tasks[user_id].cancel()
        logger.info(f"Cancelled previous task for user {user_id}.")

    task = asyncio.create_task(_process_user_request(update, context))
    user_tasks[user_id] = task
    task.add_done_callback(lambda t: _cleanup_task(t, user_id, context.application))

def main() -> None:
    """تابع اصلی برای اجرای ربات."""
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set in environment variables!")
        return

    application = Application.builder().token(token).concurrent_updates(True).build()
    
    # مقداردهی اولیه داده‌های ربات در bot_data
    application.bot_data['user_tasks'] = {}
    application.bot_data['maintenance_mode'] = False
    application.bot_data['settings'] = {
        'model': "huihui-ai/gemma-3-27b-it-abliterated:featherless-ai",
        'temperature': 0.7
    }
    application.bot_data['chat_history'] = {}

    # ثبت هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    setup_admin_handlers(application) # ثبت هندلرهای مدیریت

    port = int(os.environ.get("PORT", 8443))
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL") + "/webhook"
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url,
        url_path="webhook"
    )

if __name__ == "__main__":
    main()
