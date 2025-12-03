import sqlite3
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager

class Database:
    def __init__(self, db_name='keys.db'):
        self.db_name = db_name
        self._local = threading.local()
        self.create_tables()
        self.upgrade_tables()  # Добавляем обновление таблиц
    
    @property
    def conn(self):
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    @contextmanager
    def get_cursor(self):
        cursor = self.conn.cursor()
        try:
            yield cursor
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def create_tables(self):
        with self.get_cursor() as cursor:
            # Пользователи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Ключи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    key TEXT,
                    duration INTEGER,
                    config_url TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Платежи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    duration INTEGER,
                    proof_photo_id TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_key TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
    
    def upgrade_tables(self):
        """Обновление структуры таблиц если они устарели"""
        with self.get_cursor() as cursor:
            # Проверяем есть ли колонка admin_key в таблице payments
            try:
                cursor.execute("SELECT admin_key FROM payments LIMIT 1")
            except sqlite3.OperationalError:
                # Колонки нет, нужно добавить
                print("⚠️ Обновляю структуру базы данных...")
                try:
                    cursor.execute("ALTER TABLE payments ADD COLUMN admin_key TEXT")
                    print("✅ Колонка admin_key добавлена")
                except Exception as e:
                    print(f"❌ Ошибка при обновлении базы: {e}")
    
    def add_user(self, user_id, username):
        with self.get_cursor() as cursor:
            cursor.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
    
    def add_key(self, user_id, key, duration, config_url=""):
        expires_at = datetime.now() + timedelta(days=duration)
        with self.get_cursor() as cursor:
            cursor.execute(
                '''INSERT INTO keys (user_id, key, duration, config_url, expires_at) 
                   VALUES (?, ?, ?, ?, ?)''',
                (user_id, key, duration, config_url, expires_at.strftime('%Y-%m-%d %H:%M:%S'))
            )
    
    def add_payment(self, user_id, amount, duration, proof_photo_id):
        with self.get_cursor() as cursor:
            cursor.execute(
                '''INSERT INTO payments (user_id, amount, duration, proof_photo_id) 
                   VALUES (?, ?, ?, ?)''',
                (user_id, amount, duration, proof_photo_id)
            )
            return cursor.lastrowid
    
    def update_payment_with_key(self, payment_id, key):
        with self.get_cursor() as cursor:
            cursor.execute(
                "UPDATE payments SET status = 'approved', admin_key = ? WHERE id = ?",
                (key, payment_id)
            )
    
    def get_user_keys(self, user_id):
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT key, duration, config_url, is_active, expires_at FROM keys WHERE user_id = ?",
                (user_id,)
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    'key': row['key'],
                    'duration': row['duration'],
                    'config_url': row['config_url'],
                    'is_active': bool(row['is_active']),
                    'expires_at': row['expires_at']
                })
            return result
    
    def get_pending_payments(self):
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, amount, duration FROM payments WHERE status = 'pending'"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_payment_by_id(self, payment_id):
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT p.*, u.username FROM payments p LEFT JOIN users u ON p.user_id = u.user_id WHERE p.id = ?",
                (payment_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def delete_payment(self, payment_id):
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
            return cursor.rowcount > 0
    
    def get_all_payments(self):
        with self.get_cursor() as cursor:
            cursor.execute('''
                SELECT p.*, u.username 
                FROM payments p 
                LEFT JOIN users u ON p.user_id = u.user_id 
                ORDER BY p.created_at DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_user_count(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def close(self):
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            del self._local.conn