import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI  # استفاده از کلاینت غیرهمزمان
from keep_alive import start_keep_alive

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# کلاینت OpenAI (HuggingFace) - نسخه غیرهمزمان
client = AsyncOpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ["HF_TOKEN"],
)

# --- دیکشنری برای مدیریت وظایف پس‌زمینه هر کاربر ---
# این دیکشنری شناسه کاربر را به وظیفه (Task) در حال اجرا متصل می‌کند
# {user_id: asyncio.Task}
user_tasks = {}

# --- توابع کمکی برای مدیریت وظایف ---

def _cleanup_task(task: asyncio.Task, user_id: int):
    """
    این تابع پس از اتمام یک وظیفه (با موفقیت، خطا یا لغو) فراخوانی می‌شود
    تا ورودی مربوط به آن کاربر را از دیکشنری پاک کند.
    """
    if user_id in user_tasks and user_tasks[user_id] == task:
        del user_tasks[user_id]
        logger.info(f"Cleaned up finished task for user {user_id}.")

    # اگر وظیفه به دلیل خطایی که مدیریت نشده متوقف شده، آن را لاگ کن
    if task.exception():
        logger.error(f"Background task for user {user_id} failed: {task.exception()}")


async def _process_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    این تابع اصلی پردازش درخواست است که در پس‌زمینه اجرا می‌شود.
    """
    chat_id = update.effective_chat.id
    user_message = update.message.text
    user_id = update.effective_user.id

    try:
        # به کاربر اطلاع دهید که ربات در حال پردازش است
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # استفاده از asyncio.wait_for برای ایجاد تایم‌اوت (مثلا ۶۰ ثانیه)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="huihui-ai/gemma-3-27b-it-abliterated:featherless-ai",
                messages=[{"role": "user", "content": user_message}],
                temperature=0.7,
                top_p=0.95,
                stream=False,
            ),
            timeout=60.0
        )

        # ارسال پاسخ به کاربر
        await update.message.reply_text(response.choices[0].message.content)

    except asyncio.TimeoutError:
        # اگر درخواست بیش از حد طول کشید
        logger.warning(f"Request timed out for user {user_id}.")
        await update.message.reply_text(
            "⏱️ پردازش درخواست شما بیش از حد طولانی شد و لغو گردید. لطفاً دوباره تلاش کنید."
        )
    except Exception as e:
        # برای سایر خطاها
        logger.error(f"Error while processing message for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید."
        )

# --- هندلرهای اصلی ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال پیام خوشامدگویی."""
    user = update.effective_user
    await update.message.reply_html(
        f"سلام {user.mention_html()}! 🤖\n\n"
        f"من یک ربات هوشمند هستم. هر سوالی دارید بپرسید.\n"
        f"توجه: درخواست‌های شما به صورت همزمان پردازش می‌شوند. "
        f"اگر درخواست جدیدی بفرستید، پردازش قبلی لغو خواهد شد.",
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    این هندلر پیام‌ها را دریافت کرده و وظیفه پردازش را به پس‌زمینه محول می‌کند.
    این تابع بسیار سریع اجرا می‌شود و ربات را گیر نمی‌اندازد.
    """
    user_id = update.effective_user.id

    # بررسی اینکه آیا وظیفه‌ای برای این کاربر در حال اجراست یا نه
    if user_id in user_tasks and not user_tasks[user_id].done():
        # یک وظیفه در حال اجراست. آن را لغو کرده و برای درخواست جدید شروع می‌کنیم.
        # این کار باعث می‌شود ربات همیشه به آخرین پیام کاربر پاسخ دهد.
        user_tasks[user_id].cancel()
        logger.info(f"Cancelled previous task for user {user_id} to start a new one.")

    # ایجاد یک وظیفه جدید در پس‌زمینه برای پردازش درخواست
    # asyncio.create_task تابع را بدون منتظر ماندن برای اتمام آن اجرا می‌کند
    task = asyncio.create_task(_process_user_request(update, context))

    # ذخیره وظیفه جدید برای کاربر
    user_tasks[user_id] = task

    # اضافه کردن یک تابع callback که پس از اتمام وظیفه اجرا می‌شود
    # این تابع مسئول پاکسازی دیکشنری است
    task.add_done_callback(lambda t: _cleanup_task(t, user_id))

def main() -> None:
    """تابع اصلی برای اجرای ربات."""
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set in environment variables!")
        return

    # ساخت اپلیکیشن با فعال‌سازی پردازش همزمان به‌روزرسانی‌ها برای کاربران مختلف
    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

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
