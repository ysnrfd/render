import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from keep_alive import start_keep_alive
import aiohttp

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# کلاینت OpenAI (HuggingFace)
# توکن از متغیر محیطی خوانده می‌شود
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ["HF_TOKEN"],
)

# --- دیکشنری‌های جدید برای مدیریت وضعیت کاربران ---

# دیکشنری برای نگهداری وضعیت پردازش هر کاربر
# {user_id: True/False} -> True یعنی در حال پردازش
user_processing_state = {}

# دیکشنری برای نگهداری قفل هر کاربر برای جلوگیری از ریس‌های مسابقه‌ای (race condition)
# این تضمین می‌کند که دو پردازش همزمان برای یک کاربر شروع نشود
user_locks = {}

# --- توابع ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال پیام خوشامدگویی when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"سلام {user.mention_html()}! من یک ربات هوشمند هستم. هر سوالی دارید بپرسید.\n\n"
        f"توجه: لطفاً تا دریافت پاسخ کامل، سوال جدیدی نپرسید.",
    )

async def get_ai_response(user_message: str) -> str:
    """دریافت پاسخ از مدل هوش مصنوعی به صورت غیرهمزمان"""
    # استفاده از کلاینت OpenAI که می‌تواند غیرهمزمان باشد
    # اما برای اطمینان از عدم مسدود بودن، می‌توان از aiohttp هم استفاده کرد
    # در اینجا ما از کلاینت اصلی استفاده می‌کنیم که ساده‌تر است
    try:
        response = client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated:featherless-ai",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.7,
            top_p=0.95,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling AI API: {e}")
        raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ به پیام کاربر با استفاده از هوش مصنوعی و جلوگیری از درخواست‌های همزمان."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text

    # --- مکانیزم قفل‌گذاری ---
    # اگر قفلی برای این کاربر وجود ندارد، یک قفل جدید بساز
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()

    # قفل این کاربر را بگیر تا فقط یک پردازش برای او همزمان انجام شود
    async with user_locks[user_id]:
        # بررسی کن که آیا این کاربر در حال حاضر درخواست دیگری در حال پردازش دارد یا نه
        if user_processing_state.get(user_id, False):
            # اگر در حال پردازش بود، به او اخطار بده و از تابع خارج شو
            await update.message.reply_text(
                "⏳ لطفاً صبر کنید! درخواست قبلی شما در حال پردازش است. "
                "پاسخ آن را دریافت کنید و سپس سوال جدیدی بپرسید."
            )
            return

        # اگر کاربر مشغول نبود، وضعیت او را به 'در حال پردازش' تغییر بده
        user_processing_state[user_id] = True

    # --- خارج از بلوک قفل ---
    # از اینجا به بعد، درخواست اصلی پردازش می‌شود.
    # قفل آزاد شده و درخواست‌های بعدی همین کاربر در صف انتظار برای گرفتن قفل می‌مانند
    # و با دیدن وضعیت True، رد خواهند شد.

    try:
        # به کاربر اطلاع دهید که ربات در حال پردازش است
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # دریافت پاسخ به صورت غیرهمزمان
        response_text = await get_ai_response(user_message)

        # ارسال پاسخ به کاربر
        await update.message.reply_text(response_text)

    except Exception as e:
        logger.error(f"Error while processing message for user {user_id}: {e}")
        await update.message.reply_text("متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید.")

    finally:
        # **بسیار مهم**: در هر صورت (موفقیت یا خطا)، وضعیت کاربر را به 'آزاد' تغییر بده
        # تا بتواند درخواست بعدی خود را ارسال کند.
        user_processing_state[user_id] = False

def main() -> None:
    """تابع اصلی برای اجرای ربات."""
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set in environment variables!")
        return

    # ساخت اپلیکیشن با فعال‌سازی پردازش همزمان به‌روزرسانی‌ها
    # این کار به ربات اجازه می‌دهد تا کاربران *مختلف* را به صورت همزمان پردازش کند
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
