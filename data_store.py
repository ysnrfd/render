# data_store.py
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DATA_FILE = "bot_data.json"

def load_data():
    """داده‌ها را از فایل JSON بارگذاری می‌کند."""
    if not os.path.exists(DATA_FILE):
        return {"banned_users": set(), "user_stats": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["banned_users"] = set(data.get("banned_users", []))
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading data file: {e}. Starting with fresh data.")
        return {"banned_users": set(), "user_stats": {}}

def save_data(data):
    """داده‌ها را در فایل JSON ذخیره می‌کند."""
    try:
        data_to_save = {
            "banned_users": list(data["banned_users"]),
            "user_stats": data["user_stats"]
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
    except IOError as e:
        logger.error(f"Error saving data file: {e}")

def update_user_stats(user_id, username):
    """آمار کاربر را به‌روزرسانی می‌کند."""
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str not in data["user_stats"]:
        data["user_stats"][user_id_str] = {
            "username": username,
            "first_seen": datetime.now().isoformat(),
            "message_count": 0,
            "last_seen": datetime.now().isoformat()
        }
    else:
        data["user_stats"][user_id_str]["last_seen"] = datetime.now().isoformat()
        data["user_stats"][user_id_str]["message_count"] += 1
    save_data(data)

def is_user_banned(user_id):
    """بررسی می‌کند که آیا کاربر بن شده است یا نه."""
    data = load_data()
    return str(user_id) in data["banned_users"]

def ban_user(user_id):
    """یک کاربر را بن می‌کند."""
    data = load_data()
    data["banned_users"].add(str(user_id))
    save_data(data)

def unban_user(user_id):
    """بن یک کاربر را برمی‌دارد."""
    data = load_data()
    data["banned_users"].discard(str(user_id))
    save_data(data)
