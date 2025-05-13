import sqlite3
from datetime import datetime
from config import DATABASE_NAME

class DatabaseManager:
    def __init__(self, db_name=DATABASE_NAME):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                quota INTEGER DEFAULT 1,
                last_reset_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                quota_amount INTEGER,
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

    def create_user(self, user):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, quota, last_reset_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user.id, user.username, user.first_name, user.last_name, 1, today))
        self.conn.commit()

    def reset_daily_quota(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE users 
            SET quota = 1, 
                last_reset_date = ?
            WHERE last_reset_date < ?
        ''', (today, today))
        self.conn.commit()

    def use_quota(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET quota = quota - 1 
            WHERE user_id = ? AND quota > 0
        ''', (user_id,))
        affected_rows = cursor.rowcount
        self.conn.commit()
        return affected_rows > 0

    def add_quota(self, user_id, amount):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET quota = quota + ? 
            WHERE user_id = ?
        ''', (amount, user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def create_transaction(self, user_id, quota_amount, payment_method):
        cursor = self.conn.cursor()
        amount = self.get_price_for_quota(quota_amount)
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, quota_amount, payment_method)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, quota_amount, payment_method))
        self.conn.commit()
        return cursor.lastrowid

    def verify_transaction(self, transaction_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.*, u.username 
            FROM transactions t
            LEFT JOIN users u ON t.user_id = u.user_id
            WHERE t.id = ? AND t.status = 'pending'
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        
        if transaction:
            cursor.execute('''
                UPDATE transactions
                SET status = 'completed'
                WHERE id = ?
            ''', (transaction_id,))
            self.add_quota(transaction[1], transaction[3])
            self.conn.commit()
            return transaction
        return None

    def get_price_for_quota(self, quota_amount):
        if quota_amount == 100:
            return 5000
        elif quota_amount == 300:
            return 15000
        elif quota_amount == 700:
            return 20000
        elif quota_amount == 1000:
            return 25000
        return quota_amount * 50  # Default price if not in special offers
