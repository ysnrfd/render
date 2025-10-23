import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient
from keep_alive import start_keep_alive

# شروع سرویس نگه داشتن ربات فعال
start_keep_alive()

# لاگینگ برای دیدن خطاها
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# کلاینت HuggingFace Inference
# توکن از متغیر محیطی خوانده می‌شود
client = InferenceClient(
    provider="featherless-ai",
    api_key=os.environ["HF_TOKEN"],
)

# تابع برای پاسخ به دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال پیام خوشامدگویی when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"سلام {user.mention_html()}! من یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
    )

# تابع اصلی برای پردازش پیام‌های متنی کاربر
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ به پیام کاربر با استفاده از هوش مصنوعی."""
    user_message = update.message.text
    chat_id = update.effective_chat.id

    # به کاربر اطلاع دهید که ربات در حال پردازش است
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        # ساخت درخواست به مدل هوش مصنوعی
        response = client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated",
            messages=[
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
            temperature=0.7,
            top_p=0.9,
            stream=False,  # تغییر از True به False
        )

        # بررسی نوع پاسخ و استخراج متن
        if isinstance(response, str):
            # اگر پاسخ مستقیماً یک رشته است
            response_text = response
        else:
            # اگر پاسخ یک آبجکت است، محتوا را استخراج می‌کنیم
            response_text = ""
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    response_text += chunk.choices[0].delta.content
                elif hasattr(chunk, 'content'):
                    response_text += chunk.content
                elif isinstance(chunk, str):
                    response_text += chunk

        # ارسال پاسخ به کاربر
        await update.message.reply_text(response_text)

    except Exception as e:
        logger.error(f"Error while processing message: {e}")
        await update.message.reply_text("متاسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید.")

def main() -> None:
    """تابع اصلی برای اجرای ربات."""
    # توکن ربات از متغیر محیطی خوانده می‌شود
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set in environment variables!")
        return

    # ساخت اپلیکیشن
    application = Application.builder().token(token).build()

    # اضافه کردن هندلر برای دستور /start
    application.add_handler(CommandHandler("start", start))

    # اضافه کردن هندلر برای تمام پیام‌های متنی
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # اجرای ربات با استفاده از Webhook
    # Render به صورت خودکار یک PORT برای اپلیکیشن شما در نظر می‌گیرد
    port = int(os.environ.get("PORT", 8443))
    # آدرس کامل وب‌هوک شما
    webhook_url = os.environ.get("RENDER_EXTERNAL_URL") + "/webhook"
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url,
        url_path="webhook"
    )

if __name__ == "__main__":
    main()
