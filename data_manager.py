# data_manager.py

import os
import json
import logging
from datetime import datetime, timedelta

# --- تنظیمات مسیر فایل‌ها ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "bot_data.json")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

# --- کش داده‌های گلوبال ---
DATA = {
    "users": {},
    "banned_users": set(),
    "stats": {
        "total_messages": 0,
        "total_users": 0,
        "avg_response_time": 0.0,
        "max_response_time": 0.0,
        "min_response_time": float('inf'),
        "total_responses": 0
    },
    "welcome_message": "سلام {user_mention}! 🤖\n\nمن یک ربات هوشمند هستم. هر سوالی دارید بپرسید.",
    "goodbye_message": "کاربر {user_mention} گروه را ترک کرد. خداحافظ!",
    "maintenance_mode": False,
    "blocked_words": [],
    "scheduled_broadcasts": [],
    "bot_start_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}

logger = logging.getLogger(__name__)

def load_data():
    """داده‌ها را از فایل JSON بارگذاری کرده و در کش گلوبال ذخیره می‌کند."""
    global DATA
    try:
        if not os.path.exists(DATA_FILE):
            logger.info(f"فایل داده در {DATA_FILE} یافت نشد. یک فایل جدید ایجاد می‌شود.")
            save_data()
            return

        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
            loaded_data['banned_users'] = set(loaded_data.get('banned_users', []))
            
            # اطمینان از وجود کلیدهای جدید در فایل‌های قدیمی
            if 'blocked_words' not in loaded_data: loaded_data['blocked_words'] = []
            if 'scheduled_broadcasts' not in loaded_data: loaded_data['scheduled_broadcasts'] = []
            if 'maintenance_mode' not in loaded_data: loaded_data['maintenance_mode'] = False
            if 'bot_start_time' not in loaded_data: loaded_data['bot_start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if 'avg_response_time' not in loaded_data['stats']:
                loaded_data['stats']['avg_response_time'] = 0.0
                loaded_data['stats']['max_response_time'] = 0.0
                loaded_data['stats']['min_response_time'] = float('inf')
                loaded_data['stats']['total_responses'] = 0

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
    
    save_data()

def update_response_stats(response_time: float):
    """آمار زمان پاسخگویی را به‌روز می‌کند."""
    global DATA
    
    if DATA['stats']['total_responses'] == 0:
        DATA['stats']['min_response_time'] = response_time

    DATA['stats']['total_responses'] += 1
    
    # محاسبه میانگین جدید
    current_avg = DATA['stats']['avg_response_time']
    total_responses = DATA['stats']['total_responses']
    new_avg = ((current_avg * (total_responses - 1)) + response_time) / total_responses
    DATA['stats']['avg_response_time'] = new_avg
    
    # به‌روزرسانی حداکثر و حداقل زمان پاسخگویی
    if response_time > DATA['stats']['max_response_time']:
        DATA['stats']['max_response_time'] = response_time
    
    if response_time < DATA['stats']['min_response_time']:
        DATA['stats']['min_response_time'] = response_time
    
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

def contains_blocked_words(text: str) -> bool:
    """بررسی می‌کند آیا متن حاوی کلمات مسدود شده است یا خیر."""
    if not DATA['blocked_words']:
        return False
    
    text_lower = text.lower()
    for word in DATA['blocked_words']:
        if word in text_lower:
            return True
    
    return False

def get_active_users(days: int) -> list:
    """لیست کاربران فعال در بازه زمانی مشخص را برمی‌گرداند."""
    now = datetime.now()
    cutoff_date = now - timedelta(days=days)
    
    active_users = []
    for user_id, user_info in DATA['users'].items():
        if 'last_seen' in user_info:
            try:
                last_seen = datetime.strptime(user_info['last_seen'], '%Y-%m-%d %H:%M:%S')
                if last_seen >= cutoff_date:
                    active_users.append(int(user_id))
            except ValueError:
                continue
    
    return active_users

def get_users_by_message_count(min_count: int) -> list:
    """لیست کاربران با تعداد پیام بیشتر یا مساوی مقدار مشخص را برمی‌گرداند."""
    users = []
    for user_id, user_info in DATA['users'].items():
        if user_info.get('message_count', 0) >= min_count:
            users.append(int(user_id))
    
    return users

# بارگذاری اولیه داده‌ها در زمان ایمپورت شدن ماژول
load_data()
