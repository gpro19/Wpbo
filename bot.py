import re
import os
import requests
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from flask import Flask
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi Flask
flask_app = Flask(__name__)

# Konfigurasi Bot
TELEGRAM_TOKEN = "7619753860:AAHDPdB12JDzsTyj2Q1CWOJV6y4ol0XXCfw"
LOG_CHANNEL_ID = "-1002594638851"
ADMIN_USERNAME = "@MzCoder"  # Ganti dengan username admin Anda
ADMIN_IDS = [1910497806]  # Ganti dengan ID admin Anda

# Harga Quota
QUOTA_PRICES = {
    100: 5000,
    300: 15000,
    700: 20000,
    1000: 25000
}

class DatabaseManager:
    def __init__(self, db_name="wattpad_bot.db"):
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
        logger.info("Daily quotas have been reset")

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
            self.add_quota(transaction[1], transaction[3])  # user_id, quota_amount
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

class WattpadBot:
    def __init__(self, db_manager):
        self.headers = {"User-Agent": "WattpadToEPUBBot/1.0"}
        self.base_url = "https://wpd.rambhat.la"
        self.story_pattern = r'wattpad\.com/story/(\d+)'
        self.part_pattern = r'wattpad\.com/(\d+)'
        self.temp_dir = "temp_downloads"
        self.db = db_manager
        
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def get_story_info(self, story_id):
        try:
            url = f"https://www.wattpad.com/api/v3/stories/{story_id}"
            params = {
                'fields': 'id,title,user(name),cover,readCount,voteCount,commentCount,'
                         'modifyDate,numParts,language(name),completed,mature'
            }
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting story info: {e}")
            return None

    def create_download_keyboard(self, story_id):
        safe_id = str(story_id).replace('_', '-')
        keyboard = [
            [InlineKeyboardButton("📥 Download EPUB", callback_data=f"dl_{safe_id}_epub")],
            [InlineKeyboardButton("🌐 View on Wattpad", url=f"https://www.wattpad.com/story/{story_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def format_story_details(self, story_data):
        details = f"📖 <b>{story_data['title']}</b>\n"
        details += f"👤 Author: {story_data['user']['name']}\n"
        details += f"⭐ Votes: {story_data['voteCount']:,}\n"
        details += f"👀 Reads: {story_data['readCount']:,}\n"
        details += f"🗨️ Comments: {story_data['commentCount']:,}\n\n"
        
        last_updated = datetime.strptime(story_data["modifyDate"], "%Y-%m-%dT%H:%M:%SZ")
        status = "✅ Completed" if story_data["completed"] else "⏳ Ongoing"
        details += f"{status} | Updated: {last_updated.strftime('%Y-%m-%d')}\n"
        
        if story_data["mature"]:
            details += "🔞 Mature Content\n"
            
        return details

    def download_epub(self, story_id):
        params = {
            'format': 'epub',
            'bot': 'true',
            'mode': 'story'
        }
        
        try:
            url = f"{self.base_url}/download/{story_id}"
            response = requests.get(url, params=params, stream=True, timeout=60)
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    def log_to_channel(self, context: CallbackContext, user_id: int, username: str, story_id: str, title: str):
        try:
            log_message = (
                f"📥 Download Log\n\n"
                f"👤 User: [{username}](tg://user?id={user_id})\n"
                f"🆔 ID: {user_id}\n"
                f"📖 Story: [{title}](https://www.wattpad.com/story/{story_id})\n"
                f"🆔 Story ID: {story_id}\n"
                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=log_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send log to channel: {e}")

    def handle_callback_query(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        
        user = query.from_user
        self.db.create_user(user)
        self.db.reset_daily_quota()
        
        try:
            action = query.data.split('_')[0]
            
            if action == 'dl':
                self.handle_download_callback(query, context)
            elif action == 'buy':
                self.handle_buy_quota(query, context)
            elif action == 'check':
                self.handle_check_quota(query, context)
            elif action == 'back':
                self.handle_back_callback(query, context)
                
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            query.edit_message_text("⚠️ An error occurred. Please try again.")

    def handle_download_callback(self, query, context):
        _, story_id, file_type = query.data.split('_', 2)
        story_id = story_id.replace('-', '_')
        
        message = query.message
        processing_msg = message.reply_text("⏳ Processing your download request...")
        
        user = query.from_user
        if not self.db.use_quota(user.id):
            self.handle_no_quota(message, user)
            processing_msg.delete()
            return
        
        try:
            story_info = self.get_story_info(story_id)
            if not story_info:
                processing_msg.edit_text("❌ Failed to get story information.")
                return
            
            title = re.sub(r'[\\/*?:"<>|]', '_', story_info['title'])
            filename = f"{title}(@WattpadToEPUBbot).epub"
            filepath = os.path.join(self.temp_dir, filename)
            
            response = self.download_epub(story_id)
            if not response:
                processing_msg.edit_text("❌ Download failed. Please try again later.")
                return
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            with open(filepath, 'rb') as f:
                message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=f"📚 {story_info['title']}\n⚡ Downloaded via @WattpadToEPUBbot"
                )
            
            self.log_to_channel(
                context=context,
                user_id=user.id,
                username=user.username or user.first_name,
                story_id=story_id,
                title=story_info['title']
            )
            
            processing_msg.delete()
            query.edit_message_reply_markup(reply_markup=None)
            
        except Exception as e:
            logger.error(f"Error in download handler: {e})
            processing_msg.edit_text("⚠️ An error occurred. Please try again.")
        finally:
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)

    def handle_no_quota(self, message, user):
        keyboard = [
            [InlineKeyboardButton("💳 Beli Quota Tambahan", callback_data="buy_quota")],
            [InlineKeyboardButton("🔄 Cek Quota Saya", callback_data="check_quota")]
        ]
        
        message.reply_text(
            "⚠️ Quota harian Anda telah habis.\n\n"
            f"💰 Harga: Rp {QUOTA_PRICES[100]:,} (100 Quota)\n"
            f"💰 Harga: Rp {QUOTA_PRICES[300]:,} (300 Quota)\n"
            f"💰 Harga: Rp {QUOTA_PRICES[700]:,} (700 Quota)\n"
            f"💰 Harga: Rp {QUOTA_PRICES[1000]:,} (1000 Quota)\n\n"
            "Silakan beli quota tambahan atau tunggu hingga quota harian di-reset besok.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def handle_buy_quota(self, query, context):
        keyboard = [
            [InlineKeyboardButton("100 Quota - Rp 5.000", callback_data="buy_100")],
            [InlineKeyboardButton("300 Quota - Rp 15.000", callback_data="buy_300")],
            [InlineKeyboardButton("700 Quota - Rp 20.000", callback_data="buy_700")],
            [InlineKeyboardButton("1000 Quota - Rp 25.000", callback_data="buy_1000")],
            [InlineKeyboardButton(f"Hubungi {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")]
        ]
        
        price_list = (
            "💰 *Price List Quota*\n\n"
            "📌 Paket Hemat:\n"
            "├ 100 Quota = Rp 5.000\n"
            "├ 300 Quota = Rp 15.000\n"
            "├ 700 Quota = Rp 20.000\n"
            "└ 1000 Quota = Rp 25.000\n\n"
            "⚡ Bonus semakin banyak quota yang dibeli!\n\n"
            "Pilih paket quota atau hubungi admin langsung untuk pembelian custom."
        )
        
        query.edit_message_text(
            price_list,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def handle_quota_selection(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        
        try:
            quota_amount = int(query.data.split('_')[1])
            price = self.db.get_price_for_quota(quota_amount)
            
            payment_info = (
                f"💰 *Pembelian {quota_amount} Quota*\n\n"
                f"Total Harga: Rp {price:,}\n\n"
                "Silakan transfer ke rekening berikut:\n"
                "✳️ Bank ABC: 1234567890 a/n YourName\n"
                "✳️ Bank XYZ: 0987654321 a/n YourName\n\n"
                "Setelah transfer, kirim bukti pembayaran dengan command:\n"
                f"/payment {quota_amount} [BANK_TUJUAN]\n"
                f"Contoh: `/payment {quota_amount} Bank ABC`\n\n"
                f"Atau hubungi {ADMIN_USERNAME} untuk bantuan."
            )
            
            keyboard = [
                [InlineKeyboardButton("👈 Kembali", callback_data="buy_quota")],
                [InlineKeyboardButton(f"Chat {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")]
            ]
            
            query.edit_message_text(
                payment_info,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error in quota selection: {e}")
            query.edit_message_text("⚠️ Terjadi kesalahan. Silakan coba lagi.")

    def handle_check_quota(self, query, context):
        user = query.from_user
        user_data = self.db.get_user(user.id)
        
        remaining_quota = user_data[4]
        last_reset_date = datetime.strptime(user_data[5], '%Y-%m-%d')
        next_reset = (last_reset_date + timedelta(days=1)).strftime('%d %B %Y')
        
        message = (
            f"📊 *Info Quota Anda*\n\n"
            f"✅ **Quota Tersedia:** {remaining_quota}\n"
            f"🔄 **Reset Quota:** {next_reset}\n\n"
            f"ℹ️ Quota harian akan direset setiap hari pukul 00:00 WIB"
        )
        
        query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Beli Quota Tambahan", callback_data="buy_quota")],
                [InlineKeyboardButton("👈 Kembali", callback_data="back_to_quota")]
            ])
        )

    def handle_back_callback(self, query, context):
        user = query.from_user
        story_ids = re.findall(self.story_pattern, query.message.text)
        
        if story_ids:
            story_id = story_ids[0]
            story_info = self.get_story_info(story_id)
            
            if story_info:
                query.edit_message_text(
                    self.format_story_details(story_info),
                    reply_markup=self.create_download_keyboard(story_id),
                    parse_mode='HTML'
                )
                return
        
        query.edit_message_text("Pilih opsi lain atau coba lagi.")

        def handle_message(self, update: Update, context: CallbackContext):
        """Menangani pesan masuk dari pengguna"""
        message = update.message
        if not message or message.from_user.is_bot:
            return
        
        user = message.from_user
        self.db.create_user(user)  # Pastikan user terdaftar
        
        text = message.text or message.caption
        if not text:
            return
        
        # Cek jika pesan mengandung link Wattpad
        story_ids = set(re.findall(self.story_pattern, text))
        part_ids = set(re.findall(self.part_pattern, text))
        
        for story_id in story_ids:
            try:
                story_info = self.get_story_info(story_id)
                if not story_info:
                    continue
                
                # Kirim info story dengan tombol download
                message.reply_photo(
                    photo=story_info['cover'],
                    caption=self.format_story_details(story_info),
                    reply_markup=self.create_download_keyboard(story_id),
                    parse_mode='HTML'
                )
                
            except Exception as e:
                logger.error(f"Error processing story {story_id}: {e}")

def start_command(update: Update, context: CallbackContext):
    """Handler untuk command /start"""
    help_text = (
        "📚 *Wattpad to EPUB Bot*\n\n"
        "Kirimkan link cerita Wattpad dan saya akan mengkonversinya ke format EPUB.\n\n"
        "🔄 1 Download gratis per hari\n"
        "💰 Beli quota tambahan dengan harga spesial:\n"
        "├ 100 Quota: Rp 5.000\n"
        "├ 300 Quota: Rp 15.000\n"
        "├ 700 Quota: Rp 20.000\n"
        "└ 1000 Quota: Rp 25.000\n\n"
        "🔧 Fitur:\n"
        "- Download cepat format EPUB\n"
        "- Format cerita tetap terjaga\n"
        "- Notifikasi ketika quota direset\n\n"
        "Gunakan /help untuk melihat semua command"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Beli Quota", callback_data="buy_quota")],
        [InlineKeyboardButton(f"💬 Hubungi {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")]
    ]
    
    update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def scheduled_reset():
    """Task terjadwal untuk reset quota harian"""
    db = DatabaseManager()
    while True:
        now = datetime.now()
        # Reset setiap hari jam 00:00 WIB (GMT+7) atau jam 17:00 UTC
        next_reset = (now + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_reset - now).total_seconds()
        
        logger.info(f"Sleeping for {sleep_seconds} seconds until next reset...")
        time.sleep(sleep_seconds)
        
        db.reset_daily_quota()
        logger.info("Daily quota reset completed")

@flask_app.route('/')
def home():
    return "Wattpad to EPUB Bot is running!"

def main():
    """Fungsi utama untuk menjalankan bot"""
    db_manager = DatabaseManager()
    
    # Jalankan task reset harian di background
    reset_thread = threading.Thread(target=scheduled_reset, daemon=True)
    reset_thread.start()

    # Inisialisasi Telegram Updater
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Inisialisasi Wattpad Bot
    wattpad_bot = WattpadBot(db_manager)

    # Daftarkan handler
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('help', start_command))
    dispatcher.add_handler(CommandHandler('quota', show_quota))
    dispatcher.add_handler(CommandHandler('buyquota', buy_quota))
    dispatcher.add_handler(CommandHandler('paymentinfo', payment_info))
    dispatcher.add_handler(CommandHandler('payment', handle_payment))
    
    # Admin commands
    dispatcher.add_handler(CommandHandler('addquota', admin_add_quota))
    dispatcher.add_handler(CommandHandler('verify', verify_payment))

    # Callback queries
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_buy_quota, pattern='^buy_quota$'))
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_quota_selection, pattern='^buy_'))
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_check_quota, pattern='^check_quota$'))
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_callback_query))
    
    # Message handler
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, wattpad_bot.handle_message))

    # Jalankan Flask di thread terpisah
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(
            host='0.0.0.0',
            port=8000,
            debug=False,
            use_reloader=False
        ),
        daemon=True
    )
    flask_thread.start()

    logger.info("Bot starting...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # Pastikan folder download ada
    if not os.path.exists("temp_downloads"):
        os.makedirs("temp_downloads")
        
    main()
