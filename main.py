# main.py

import os
import logging
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from keep_alive import start_keep_alive

# --- تغییرات جدید ---
# وارد کردن پنل ادمین
import admin_panel

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO,
    filename='bot.log', filemode='a' # لاگ‌ها را در فایل bot.log ذخیره می‌کند
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

# --- دیکشنری برای مدیریت وظایف پس‌زمینه هر کاربر ---
user_tasks = {}

# --- تغییرات جدید ---
# بارگذاری داده‌های ربات (کاربران، آمار و ...)
bot_data = admin_panel.load_data()

# --- توابع کمکی برای مدیریت وظایف ---
def _cleanup_task(task: asyncio.Task, user_id: int):
    if user_id in user_tasks and user_tasks[user_id] == task:
        del user_tasks[user_id]
        logger.info(f"Cleaned up finished task for user {user_id}.")
    try:
        exception = task.exception()
        if exception:
            logger.error(f"Background task for user {user_id} failed with an unexpected error: {exception}")
    except asyncio.CancelledError:
        logger.info(f"Task for user {user_id} was successfully cancelled by a newer request.")

# --- تغییرات جدید ---
def update_user_stats(user_id: int, user_data: dict):
    """آمار کاربر را پس از هر پیام به‌روز می‌کند."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_id_str = str(user_id)
    
    if user_id_str not in bot_data['users']:
        bot_data['users'][user_id_str] = {
            'first_seen': now_str,
            'message_count': 0
        }
        bot_data['stats']['total_users'] += 1

    bot_data['users'][user_id_str]['last_seen'] = now_str
    bot_data['users'][user_id_str]['message_count'] += 1
    bot_data['stats']['total_messages'] += 1
    
    admin_panel.save_data(bot_data)


async def _process_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    user_id = update.effective_user.id

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        response = await client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated:featherless-ai",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.7,
            top_p=0.95,
            stream=False,
        )
        await update.message.reply_text(response.choices[0].message.content)
        
        # --- تغییرات جدید ---
        # پس از ارسال موفقیت‌آمیز پاسخ، آمار را به‌روز کن
        update_user_stats(user_id, bot_data)

    except httpx.TimeoutException:
        logger.warning(f"Request timed out for user {user_id}.")
        await update.message.reply_text("⏱️ ارتباط با سرور هوش مصنوعی طولانی شد. لطفاً دوباره تلاش کنید.")
    except Exception as e:
        logger.error(f"Error while processing message for user {user_id}: {e}")
        await update.message.reply_text("❌ متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید.")

# --- هندلرهای اصلی ربات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    
    # --- تغییرات جدید ---
    # ثبت کاربر جدید در صورت اولین تماس
    update_user_stats(user_id, bot_data)
    
    await update.message.reply_html(
        f"سلام {user.mention_html()}! 🤖\n\n"
        f"من یک ربات هوشمند هستم. هر سوالی دارید بپرسید.\n"
        f"توجه: درخواست‌های شما به صورت همزمان پردازش می‌شوند. "
        f"اگر درخواست جدیدی بفرستید، پردازش قبلی لغو خواهد شد.",
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    # --- تغییرات جدید ---
    # بررسی اینکه آیا کاربر مسدود شده است یا خیر
    if user_id in bot_data['banned_users']:
        logger.info(f"Banned user {user_id} tried to send a message.")
        return # اگر مسدود بود، کاری نکن و پیام را پردازش نکن

    if user_id in user_tasks and not user_tasks[user_id].done():
        user_tasks[user_id].cancel()
        logger.info(f"Cancelled previous task for user {user_id} to start a new one.")

    task = asyncio.create_task(_process_user_request(update, context))
    user_tasks[user_id] = task
    task.add_done_callback(lambda t: _cleanup_task(t, user_id))

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set in environment variables!")
        return

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # --- تغییرات جدید ---
    # راه‌اندازی و ثبت هندلرهای پنل ادمین
    admin_panel.setup_admin_handlers(application)

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
