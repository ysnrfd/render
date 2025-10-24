# data_manager.py

import os
import json
import logging
from datetime import datetime

# --- تنظیمات مسیر فایل‌ها ---
# مسیر پوشه‌ای که اسکریپت در آن قرار دارد
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "bot_data.json")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

# --- کش داده‌های گلوبال ---
# این دیکشنری، حافظه اصلی ربات برای نگهداری اطلاعات کاربران است.
DATA = {
    "users": {},
    "banned_users": set(),
    "stats": {
        "total_messages": 0,
        "total_users": 0
    },
    "welcome_message": "سلام {user_mention}! 🤖\n\nمن یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
    "goodbye_message": "کاربر {user_mention} گروه را ترک کرد. خداحافظ!",
    "maintenance_mode": False
}

logger = logging.getLogger(__name__)

def load_data():
    """داده‌ها را از فایل JSON بارگذاری کرده و در کش گلوبال ذخیره می‌کند."""
    global DATA
    try:
        if not os.path.exists(DATA_FILE):
            logger.info(f"فایل داده در {DATA_FILE} یافت نشد. یک فایل جدید ایجاد می‌شود.")
            save_data() # فایل را با داده‌های پیش‌فرض ایجاد می‌کند
            return

        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
            # تبدیل لیست آیدی‌های مسدود شده به set برای جستجوی سریع‌تر
            loaded_data['banned_users'] = set(loaded_data.get('banned_users', []))
            DATA.update(loaded_data)
            logger.info(f"داده‌ها با موفقیت از {DATA_FILE} بارگذاری شدند.")

    except json.JSONDecodeError as e:
        logger.error(f"خطا در خواندن JSON از {DATA_FILE}: {e}. ربات با داده‌های اولیه شروع به کار می‌کند.")
    except Exception as e:
        logger.error(f"خطای غیرمنتظره هنگام بارگذاری داده‌ها: {e}. ربات با داده‌های اولیه شروع به کار می‌کند.")

def save_data():
    """کش گلوبال داده‌ها را در فایل JSON ذخیره می‌کند."""
    global DATA
    try:
        # برای ذخیره، set را دوباره به لیست تبدیل می‌کنیم چون JSON از set پشتیبانی نمی‌کند
        data_to_save = DATA.copy()
        data_to_save['banned_users'] = list(DATA['banned_users'])
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        logger.debug(f"داده‌ها با موفقیت در {DATA_FILE} ذخیره شدند.")
    except Exception as e:
        logger.error(f"خطای مهلک: امکان ذخیره داده‌ها در {DATA_FILE} وجود ندارد. خطا: {e}")

def update_user_stats(user_id: int, user):
    """آمار کاربر را پس از هر پیام به‌روز کرده و داده‌ها را ذخیره می‌کند."""
    global DATA
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_id_str = str(user_id)
    
    if user_id_str not in DATA['users']:
        DATA['users'][user_id_str] = {
            'first_name': user.first_name,
            'username': user.username,
            'first_seen': now_str,
            'message_count': 0
        }
        DATA['stats']['total_users'] += 1
        logger.info(f"کاربر جدید ثبت شد: {user_id} ({user.first_name})")

    DATA['users'][user_id_str]['last_seen'] = now_str
    DATA['users'][user_id_str]['message_count'] += 1
    DATA['stats']['total_messages'] += 1
    
    # برای جلوگیری از از دست رفتن داده، بلافاصله ذخیره می‌کنیم
    save_data()

def is_user_banned(user_id: int) -> bool:
    """بررسی می‌کند آیا کاربر مسدود شده است یا خیر."""
    return user_id in DATA['banned_users']

def ban_user(user_id: int):
    """کاربر را مسدود کرده و ذخیره می‌کند."""
    DATA['banned_users'].add(user_id)
    save_data()

def unban_user(user_id: int):
    """مسدودیت کاربر را برداشته و ذخیره می‌کند."""
    DATA['banned_users'].discard(user_id)
    save_data()

# بارگذاری اولیه داده‌ها در زمان ایمپورت شدن ماژول
load_data()
