import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

DB_PATH = Path("data.db")


class Database:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_subscribed BOOLEAN DEFAULT 0,
                    total_requests INTEGER DEFAULT 0,
                    daily_requests INTEGER DEFAULT 0,
                    last_request_date DATE,
                    referrer_id INTEGER,
                    referral_code TEXT UNIQUE,
                    FOREIGN KEY (referrer_id) REFERENCES users (user_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referred_id INTEGER UNIQUE,
                    referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                    FOREIGN KEY (referred_id) REFERENCES users (user_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_limit', '3')")
            conn.commit()

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: int, username: str = None, first_name: str = None,
                    last_name: str = None, referrer_id: int = None) -> bool:
        try:
            import hashlib
            referral_code = hashlib.sha256(f"{user_id}metadata2024".encode()).hexdigest()[:8].upper()

            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, referral_code, referrer_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, referral_code, referrer_id))

                if referrer_id:
                    cursor.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, user_id))

                conn.commit()
                return True
        except:
            return False

    def update_subscription(self, user_id: int, is_subscribed: bool):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_subscribed = ? WHERE user_id = ?', (is_subscribed, user_id))
            conn.commit()

    def can_make_request(self, user_id: int) -> Tuple[bool, str]:
        user = self.get_user(user_id)
        if not user:
            return False, "Пользователь не найден"

        if not user.get('is_subscribed'):
            return False, "❌ Вы не подписаны на канал!"

        today = datetime.now().date()
        last_request = user.get('last_request_date')

        if last_request != str(today):
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET daily_requests = 0, last_request_date = ? WHERE user_id = ?', (str(today), user_id))
                conn.commit()
            daily_requests = 0
        else:
            daily_requests = user.get('daily_requests', 0)

        daily_limit = 3

        if daily_requests >= daily_limit:
            return False, f"❌ Вы исчерпали дневной лимит ({daily_limit}).\n💡 Пригласите друга и получите +1 запрос!\nИспользуйте /referral"

        return True, f"✅ Доступно запросов: {daily_limit - daily_requests}"

    def add_request(self, user_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET daily_requests = daily_requests + 1,
                    total_requests = total_requests + 1,
                    last_request_date = ?
                WHERE user_id = ?
            ''', (str(datetime.now().date()), user_id))
            conn.commit()

    def get_remaining_requests(self, user_id: int) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0

        today = datetime.now().date()
        last_request = user.get('last_request_date')

        if last_request != str(today):
            return 3

        return max(0, 3 - user.get('daily_requests', 0))

    def add_bonus_request(self, user_id: int, amount: int = 1):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET daily_requests = daily_requests - ? WHERE user_id = ? AND daily_requests > 0', (amount, user_id))
            conn.commit()

    def get_referral_code(self, user_id: int) -> Optional[str]:
        user = self.get_user(user_id)
        return user.get('referral_code') if user else None

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        user = self.get_user(user_id)
        if not user:
            return {}

        today = datetime.now().date()
        last_request = user.get('last_request_date')
        daily_used = 0 if last_request != str(today) else user.get('daily_requests', 0)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as total, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active FROM referrals WHERE referrer_id = ?', (user_id,))
            row = cursor.fetchone()

            cursor.execute('SELECT u.user_id, u.username, u.first_name, r.referred_at, r.is_active FROM referrals r JOIN users u ON r.referred_id = u.user_id WHERE r.referrer_id = ? ORDER BY r.referred_at DESC LIMIT 10', (user_id,))
            referrals = cursor.fetchall()

        return {
            'total_requests': user.get('total_requests', 0),
            'daily_used': daily_used,
            'daily_limit': 3,
            'remaining': 3 - daily_used,
            'is_subscribed': user.get('is_subscribed', False),
            'referrals': {
                'total': row[0] if row else 0,
                'active': row[1] if row else 0,
                'referrals': referrals
            }
        }

    def process_referral(self, referrer_id: int, referred_id: int) -> bool:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM referrals WHERE referred_id = ?', (referred_id,))
            if cursor.fetchone():
                return False

            cursor.execute('INSERT INTO referrals (referrer_id, referred_id, is_active) VALUES (?, ?, ?)', (referrer_id, referred_id, 1))
            conn.commit()

        self.add_bonus_request(referrer_id, 1)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET referrer_id = ? WHERE user_id = ?', (referrer_id, referred_id))
            conn.commit()

        return True

    def get_user_by_referral_code(self, code: str) -> Optional[int]:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
            row = cursor.fetchone()
            return row[0] if row else None

    def reset_daily_requests(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET daily_requests = 0, last_request_date = ?', (str(datetime.now().date()),))
            conn.commit()


db = Database()