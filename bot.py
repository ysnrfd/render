import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient

# تنظیم لاگینگ برای عیب‌یابی
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔒 بررسی وجود توکن‌ها قبل از اجرای کد
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("❌ خطای فاتال: TELEGRAM_TOKEN تنظیم نشده است!")
    exit(1)
if not HF_API_KEY:
    logger.error("❌ خطای فاتال: HF_API_KEY تنظیم نشده است!")
    exit(1)

# 🤖 تنظیمات مدل هوش مصنوعی
client = InferenceClient(
    "huihui-ai/gemma-3-27b-it-abliterated",
    token=HF_API_KEY,
    timeout=120
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    
    logger.info(f"📩 دریافت پیام از {chat_id}: {user_message}")
    
    try:
        # 🧠 فراخوانی مدل هوش مصنوعی
        response = client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.5,
            top_p=0.7,
        )
        
        # 💬 ارسال پاسخ
        bot_response = response.choices[0].message.content
        
        # ✂️ تقسیم پیام‌های طولانی
        if len(bot_response) > 4000:
            bot_response = bot_response[:4000] + "...\n\n(پاسخ کوتاه‌شده)"
        
        await update.message.reply_text(bot_response)
        logger.info(f"📤 پاسخ به {chat_id}: {bot_response[:100]}...")
        
    except Exception as e:
        error_msg = f"❌ خطایی رخ داد: {str(e)}"
        await update.message.reply_text(error_msg)
        logger.error(f"🚨 خطا در پردازش پیام از {chat_id}: {str(e)}")

if __name__ == "__main__":
    # 🚀 راه‌اندازی ربات
    logger.info("🔄 در حال راه‌اندازی ربات...")
    
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        logger.info("✅ ربات با موفقیت ساخته شد")
    except Exception as e:
        logger.error(f"❌ خطا در ساخت ربات: {str(e)}")
        exit(1)
    
    # اضافه کردن هندلر پیام‌ها
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 🌐 استفاده از Webhook
    port = int(os.getenv("PORT", 5000))
    logger.info(f"/WebAPI در حال اجرای وبهوک روی پورت {port}")
    
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook",
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
