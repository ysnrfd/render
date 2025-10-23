import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from huggingface_hub import InferenceClient

# 🔒 توکن‌ها را از متغیرهای محیطی بخوانید
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")

# 🤖 تنظیمات مدل هوش مصنوعی (بدون پارامتر provider)
client = InferenceClient(
    "huihui-ai/gemma-3-27b-it-abliterated",  # نام مدل را مستقیماً وارد کنید
    token=HF_API_KEY,  # نام صحیح پارامتر: token (نه api_key)
    timeout=60
)

async def handle_message(update: Update, context):
    user_message = update.message.text
    
    # 🔄 نمایش "در حال پردازش..." 
    await update.message.reply_text("⏳ در حال پردازش درخواست شما...")
    
    try:
        # 🧠 فراخوانی مدل هوش مصنوعی
        stream = client.chat.completions.create(
            model="huihui-ai/gemma-3-27b-it-abliterated",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.5,
            top_p=0.7,
            stream=True,
        )
        
        # 📝 جمع‌آوری پاسخ
        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        
        # ✂️ تقسیم پیام‌های طولانی
        if len(full_response) > 4000:
            full_response = full_response[:4000] + "...\n\n(پاسخ کوتاه‌شده)"
        
        # 💬 ارسال پاسخ
        await update.message.reply_text(full_response)
    
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی رخ داد: {str(e)}")

if __name__ == "__main__":
    # 🚀 راه‌اندازی ربات
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # 🌐 استفاده از Webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook",
        drop_pending_updates=True
    )
