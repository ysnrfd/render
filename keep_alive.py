import requests
import threading
import time

def ping_service():
    """ارسال درخواست پینگ به سرویس برای نگه داشتن آن فعال."""
    url = "https://render-telegram-bot-2-bmin.onrender.com"
    while True:
        try:
            requests.get(url)
            print(f"Pinged {url} to keep service alive")
        except Exception as e:
            print(f"Error pinging service: {e}")
        
        # هر 14 دقیقه یک بار پینگ بزن (زیر 15 دقیقه برای جلوگیری از خاموشی)
        time.sleep(14 * 60)

# شروع ترد پینگ در پس‌زمینه
def start_keep_alive():
    """شروع سرویس نگه داشتن ربات فعال."""
    thread = threading.Thread(target=ping_service)
    thread.daemon = True
    thread.start()
