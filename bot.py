import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from huggingface_hub import InferenceClient

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# بررسی توکن‌ها
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN تنظیم نشده است!")
    exit(1)
if not HF_API_KEY:
    logger.error("❌ HF_API_KEY تنظیم نشده است!")
    exit(1)

# تنظیمات مدل هوش مصنوعی
client = InferenceClient(
    "huihui-ai/gemma-3-27b-it-abliterated",
    token=HF_API_KEY,
    timeout=120
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    try:
        # فراخوانی مدل هوش مصنوعی
        response = client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.5,
            top_p=0.7,
        )
        
        # ارسال پاسخ
        bot_response = response.choices[0].message.content
        if len(bot_response) > 4000:
            bot_response = bot_response[:4000] + "...\n\n(پاسخ کوتاه‌شده)"
        
        await update.message.reply_text(bot_response)
    
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی رخ داد: {str(e)}")

if __name__ == "__main__":
    # راه‌اندازی ربات
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # استفاده از Webhook
    port = int(os.getenv("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook",
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
