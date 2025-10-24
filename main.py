# main.py

import os
import logging
import asyncio
import httpx  # httpx را برای پیکربندی وارد می‌کنیم
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from keep_alive import start_keep_alive

# --- تغییرات مربوط به پنل مدیریت ---
# هندلرهای مربوط به مدیریت را از فایل جداگانه وارد می‌کنیم
from admin_panel import setup_admin_handlers

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ایجاد یک کلاینت HTTP بهینه‌سازی‌شده برای پایداری و سرعت بیشتر ---
# این کلاینت به httpx اجازه می‌دهد تا از HTTP/2 استفاده کند و تعداد اتصالات را مدیریت کند
http_client = httpx.AsyncClient(
    http2=True,  # فعال‌سازی HTTP/2 برای افزایش سرعت و کارایی
    limits=httpx.Limits(
        max_keepalive_connections=20,  # تعداد اتصالاتی که برای استفاده‌های بعدی نگه داشته می‌شوند
        max_connections=100,  # حداکثر تعداد کل اتصالات همزمان
        keepalive_expiry=30.0  # مدت زمان نگهداری اتصال بدون استفاده (ثانیه)
    ),
    timeout=httpx.Timeout(
        timeout=60.0,  # تایم‌اوت کلی برای کل درخواست
        connect=10.0,  # تایم‌اوت برای برقراری اولیه اتصال
        read=45.0,     # تایم‌اوت برای دریافت پاسخ از سرور
        write=10.0     # تایم‌اوت برای ارسال درخواست به سرور
    )
)

# کلاینت OpenAI (HuggingFace) - با استفاده از کلاینت HTTP سفارشی
client = AsyncOpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ["HF_TOKEN"],
    http_client=http_client  # معرفی کلاینت سفارشی به OpenAI
)

# --- دیکشنری برای مدیریت وظایف پس‌زمینه هر کاربر ---
# این دیکشنری دیگر در این فایل به صورت مستقیم تعریف نمی‌شود
# و در bot_data اپلیکیشن ذخیره می‌شود تا از فایل مدیریت نیز قابل دسترس باشد.
# user_tasks = {} 

# --- توابع کمکی برای مدیریت وظایف ---

def _cleanup_task(task: asyncio.Task, user_id: int, application):
    """
    این تابع پس از اتمام یک وظیفه (با موفقیت، خطا یا لغو) فراخوانی می‌شود
    تا ورودی مربوط به آن کاربر را از دیکشنری پاک کند.
    """
    # --- تغییرات مربوط به پنل مدیریت ---
    # دسترسی به user_tasks از طریق application
    user_tasks = application.bot_data.get('user_tasks', {})

    if user_id in user_tasks and user_tasks[user_id] == task:
        del user_tasks[user_id]
        logger.info(f"Cleaned up finished task for user {user_id}.")

    # بررسی خطاها، اما با نادیده گرفتن CancelledError که یک رفتار طبیعی است
    try:
        exception = task.exception()
        if exception:
            logger.error(f"Background task for user {user_id} failed with an unexpected error: {exception}")
    except asyncio.CancelledError:
        # این خطا طبیعی است و نیازی به لاگ کردن به عنوان خطا ندارد
        logger.info(f"Task for user {user_id} was successfully cancelled by a newer request.")


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

        # دیگر نیازی به asyncio.wait_for نیست، زیرا تایم‌اوت در کلاینت HTTP تنظیم شده است
        response = await client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated:featherless-ai",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.7,
            top_p=0.95,
            stream=False,
        )

        # ارسال پاسخ به کاربر
        await update.message.reply_text(response.choices[0].message.content)

    except httpx.TimeoutException:
        # این خطا زمانی رخ می‌دهد که یکی از تایم‌اوت‌های httpx منقضی شود
        logger.warning(f"Request timed out for user {user_id}.")
        await update.message.reply_text(
            "⏱️ ارتباط با سرور هوش مصنوعی طولانی شد. لطفاً دوباره تلاش کنید."
        )
    except Exception as e:
        # این بلوک خطاهای مختلف از جمله خطاهای API (مانند 503) را مدیریت می‌کند
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
    """
    user_id = update.effective_user.id

    # --- تغییرات مربوط به پنل مدیریت ---
    # دسترسی به user_tasks از طریق context
    user_tasks = context.application.bot_data.get('user_tasks', {})

    # بررسی اینکه آیا وظیفه‌ای برای این کاربر در حال اجراست یا نه
    if user_id in user_tasks and not user_tasks[user_id].done():
        # یک وظیفه در حال اجراست. آن را لغو کرده و برای درخواست جدید شروع می‌کنیم.
        user_tasks[user_id].cancel()
        logger.info(f"Cancelled previous task for user {user_id} to start a new one.")

    # ایجاد یک وظیفه جدید در پس‌زمینه برای پردازش درخواست
    task = asyncio.create_task(_process_user_request(update, context))

    # ذخیره وظیفه جدید برای کاربر
    user_tasks[user_id] = task

    # اضافه کردن یک تابع callback که پس از اتمام وظیفه اجرا می‌شود
    # --- تغییرات مربوط به پنل مدیریت ---
    # اپلیکیشن را به callback پاس می‌دهیم تا به user_tasks دسترسی داشته باشد
    task.add_done_callback(lambda t: _cleanup_task(t, user_id, context.application))

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

    # --- تغییرات مربوط به پنل مدیریت ---
    # ذخیره دیکشنری user_tasks در bot_data تا از همه جا قابل دسترس باشد
    application.bot_data['user_tasks'] = {}

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # --- تغییرات مربوط به پنل مدیریت ---
    # ثبت تمام هندلرهای مربوط به مدیریت با یک فراخوانی ساده
    setup_admin_handlers(application)

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
