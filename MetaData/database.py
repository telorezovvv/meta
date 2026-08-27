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
                    bonus_requests INTEGER DEFAULT 0,
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
                    bonus_given BOOLEAN DEFAULT 0,
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
            
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_limit', '5')")
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
                    cursor.execute('''
                        INSERT INTO referrals (referrer_id, referred_id, is_active, bonus_given)
                        VALUES (?, ?, ?, ?)
                    ''', (referrer_id, user_id, 1, 0))
                    # Даем бонус сразу при создании
                    self._give_referral_bonus(referrer_id, user_id)
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Ошибка создания пользователя: {e}")
            return False
    
    def _give_referral_bonus(self, referrer_id: int, referred_id: int):
        """Выдача бонуса за реферала"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Проверяем, не выдавали ли уже бонус
            cursor.execute('''
                SELECT bonus_given FROM referrals 
                WHERE referrer_id = ? AND referred_id = ?
            ''', (referrer_id, referred_id))
            row = cursor.fetchone()
            
            if row and row[0] == 0:
                # Добавляем бонусный запрос
                cursor.execute('''
                    UPDATE users 
                    SET bonus_requests = bonus_requests + 1
                    WHERE user_id = ?
                ''', (referrer_id,))
                
                # Отмечаем, что бонус выдан
                cursor.execute('''
                    UPDATE referrals 
                    SET bonus_given = 1 
                    WHERE referrer_id = ? AND referred_id = ?
                ''', (referrer_id, referred_id))
                
                conn.commit()
                return True
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
        
        # Сброс ежедневных запросов
        if last_request != str(today):
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET daily_requests = 0, 
                        last_request_date = ? 
                    WHERE user_id = ?
                ''', (str(today), user_id))
                conn.commit()
            daily_requests = 0
        else:
            daily_requests = user.get('daily_requests', 0)
        
        daily_limit = 5  # Изменено с 3 на 5
        bonus_requests = user.get('bonus_requests', 0)
        
        # Общее количество доступных запросов = ежедневные + бонусные
        total_available = daily_limit + bonus_requests
        
        if daily_requests >= total_available:
            return False, f"❌ Вы исчерпали лимит запросов ({total_available}).\n💡 Пригласите друга и получите +1 запрос!\nИспользуйте /referral"
        
        return True, f"✅ Доступно запросов: {total_available - daily_requests}"
    
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
            daily_requests = 0
        else:
            daily_requests = user.get('daily_requests', 0)
        
        daily_limit = 5
        bonus_requests = user.get('bonus_requests', 0)
        total_available = daily_limit + bonus_requests
        
        return max(0, total_available - daily_requests)
    
    def get_referral_code(self, user_id: int) -> Optional[str]:
        user = self.get_user(user_id)
        return user.get('referral_code') if user else None
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        user = self.get_user(user_id)
        if not user:
            return {}
        
        today = datetime.now().date()
        last_request = user.get('last_request_date')
        
        if last_request != str(today):
            daily_used = 0
        else:
            daily_used = user.get('daily_requests', 0)
        
        daily_limit = 5
        bonus_requests = user.get('bonus_requests', 0)
        total_available = daily_limit + bonus_requests
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total, 
                       SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN bonus_given = 1 THEN 1 ELSE 0 END) as bonus_given
                FROM referrals 
                WHERE referrer_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, r.referred_at, r.is_active, r.bonus_given
                FROM referrals r 
                JOIN users u ON r.referred_id = u.user_id 
                WHERE r.referrer_id = ? 
                ORDER BY r.referred_at DESC 
                LIMIT 10
            ''', (user_id,))
            referrals = cursor.fetchall()
        
        return {
            'total_requests': user.get('total_requests', 0),
            'daily_used': daily_used,
            'daily_limit': daily_limit,
            'bonus_requests': bonus_requests,
            'total_available': total_available,
            'remaining': total_available - daily_used,
            'is_subscribed': user.get('is_subscribed', False),
            'referrals': {
                'total': row[0] if row else 0,
                'active': row[1] if row else 0,
                'bonus_given': row[2] if row else 0,
                'referrals': referrals
            }
        }
    
    def process_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Обработка реферала (вызывается когда новый пользователь перешел по ссылке)"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Проверяем, не было ли уже такого реферала
            cursor.execute('SELECT id FROM referrals WHERE referred_id = ?', (referred_id,))
            if cursor.fetchone():
                return False
            
            # Создаем запись о реферале
            cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, is_active, bonus_given)
                VALUES (?, ?, ?, ?)
            ''', (referrer_id, referred_id, 1, 0))
            conn.commit()
        
        # Даем бонус
        return self._give_referral_bonus(referrer_id, referred_id)
    
    def get_user_by_referral_code(self, code: str) -> Optional[int]:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def reset_daily_requests(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET daily_requests = 0, 
                    last_request_date = ? 
                WHERE last_request_date != ?
            ''', (str(datetime.now().date()), str(datetime.now().date())))
            conn.commit()
            print(f"🔄 Дневные лимиты сброшены в {datetime.now()}")


db = Database()
