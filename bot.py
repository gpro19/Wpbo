import logging
import os
import re
import requests
from datetime import datetime, time
from flask import Flask
import threading
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, CallbackQueryHandler
)

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi Flask
app = Flask(__name__)

# Konfigurasi Database
client = MongoClient("mongodb+srv://galeh:galeh@cluster0.jvzcxuk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["wattpad_bot"]
users_collection = db["users"]
admins_collection = db["admins"]

# Token Bot Telegram
TOKEN = "7619753860:AAHDPdB12JDzsTyj2Q1CWOJV6y4ol0XXCfw"  # Ganti dengan token Anda
ADMIN_CHAT_ID = 1910497806  # Ganti dengan chat ID admin
ADMIN_USERNAME = "@MzCoder"  # Ganti dengan username admin
LOG_CHANNEL_ID = "-1002594638851"  # Ganti dengan channel log Anda

def get_user(user_id):
    now = datetime.now()
    today = datetime.combine(now.date(), time.min)
    
    user = users_collection.find_one({"user_id": user_id})
    
    # Jika user belum ada atau belum direset hari ini
    if not user or user.get("last_reset", today) < today:
        if not user:
            user_data = {
                "user_id": user_id,
                "daily_quota": 1,
                "extra_quota": 0,
                "last_reset": today,
                "created_at": now
            }
            users_collection.insert_one(user_data)
        else:
            # Reset daily_quota ke 1 dan simpan extra_quota yang ada
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"daily_quota": 1, "last_reset": today}}
            )
        
        user = users_collection.find_one({"user_id": user_id})
    
    return user

def update_user_quota(user_id, amount):
    now = datetime.now()
    today = datetime.combine(now.date(), time.min)
    
    user = users_collection.find_one({"user_id": user_id})
    
    # Jika belum reset hari ini, reset dulu
    if not user or user.get("last_reset", today) < today:
        get_user(user_id)
    
    # Update extra_quota (bisa negatif jika pengurangan quota)
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"extra_quota": amount}}
    )

def reset_daily_quotas(context: CallbackContext):
    today = datetime.combine(datetime.now().date(), time.min)
    users_collection.update_many(
        {"last_reset": {"$lt": today}},
        {"$set": {"daily_quota": 1, "last_reset": today}}
    )
    logger.info("✅ Reset harian quota selesai")

def start(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    total_quota = user["daily_quota"] + user["extra_quota"]    
    
    update.message.reply_text(
        f"📚 *Wattpad to EPUB Bot*\n\n"
        f"🔄 Quota Anda hari ini: *{total_quota}* (1 quota harian gratis)\n"
        "Kirim link cerita Wattpad untuk mendapatkan EPUB.\n"
        "Quota harian direset tiap hari pukul 00:00 WIB.\n"
        "Gunakan /beli untuk quota tambahan.",
        parse_mode="Markdown"
    )
    
def help(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Bantuan Penggunaan Bot\n\n"
        "Berikut adalah daftar perintah yang tersedia:\n"
        "/start - Memulai bot dan menampilkan informasi dasar\n"
        "/help - Menampilkan pesan bantuan ini\n"
        "/quota - Mengecek quota Anda\n"
        "/beli - Membeli quota tambahan\n\n"
        "Cara menggunakan bot:\n"
        "1. Pastikan Anda sudah subscribe channel kami dan join grup kami.\n"
        "2. Kirim link cerita Wattpad yang ingin Anda unduh.\n"
        "3. Ikuti petunjuk yang diberikan oleh bot.\n\n"
        "Jika Anda mengalami masalah, hubungi admin: {}".format(ADMIN_USERNAME),
        parse_mode="Markdown"
    )


def beli_quota(update: Update, context: CallbackContext):
    user = update.effective_user
    harga = (
        "💰 *Daftar Harga Quota*\n\n"
        "• 100 Quota - Rp5.000\n"
        "• 300 Quota - Rp15.000\n"
        "• 700 Quota - Rp20.000\n"
        "• 1500 Quota - Rp30.000\n\n"
        "💳 *Cara Pembelian*:\n"
        f"1. Hubungi admin {ADMIN_USERNAME}\n"
        f"2. Kirimkan User ID Anda: `{user.id}`\n"
        "3. Pilih paket quota yang diinginkan\n"
        "4. Admin akan memberikan instruksi pembayaran\n"
        "5. Setelah pembayaran, quota akan ditambahkan ke akun Anda"
    )
    update.message.reply_text(harga, parse_mode="Markdown")


def admin_tambah_quota(update: Update, context: CallbackContext):
    """Perintah admin untuk menambah quota"""
    # Debug: Print admin info
    logger.info(f"User ID: {update.effective_user.id}, Chat ID: {update.effective_chat.id}")
    
    # More flexible admin check
    if update.effective_user.id != ADMIN_CHAT_ID and update.effective_chat.id != ADMIN_CHAT_ID:
        update.message.reply_text("❌ Hanya untuk admin!")
        return
    
    try:
        user_id = int(context.args[0])
        jumlah = int(context.args[1])
    except (IndexError, ValueError):
        update.message.reply_text("Format: /addquota [user_id] [jumlah_quota]")
        return
    
    # Update quota
    update_user_quota(user_id, jumlah)
    
    # Get updated user data
    user = get_user(user_id)
    total_quota = user["daily_quota"] + user["extra_quota"]
    
    # Send notification to user
    context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Admin telah menambahkan *+{jumlah} Quota*!\n"
             f"🔄 Total quota Anda sekarang: {total_quota}",            
        parse_mode="Markdown"
    )
    
    update.message.reply_text(f"✅ Berhasil menambahkan {jumlah} quota untuk user {user_id}")

def cek_quota(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    total_quota = user["daily_quota"] + user["extra_quota"]
    
    update.message.reply_text(
        f"🔄 Quota Anda saat ini: *{total_quota}*\n",
        parse_mode="Markdown"
    )


class WattpadBot:
    def __init__(self):
        self.headers = {"User-Agent": "WattpadToEPUBBot/1.0"}
        self.base_url = "https://wpd.rambhat.la"
        self.story_pattern = r'wattpad\.com/story/(\d+)'
        self.part_pattern = r'wattpad\.com/(\d+)'
        self.temp_dir = "temp_downloads"
        
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def get_story_info(self, story_id):
        """Mendapatkan informasi story dari Wattpad API"""
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
        """Membuat keyboard inline untuk download options"""
        safe_id = str(story_id).replace('_', '-')
        
        keyboard = [
            [
                InlineKeyboardButton("📥 Download EPUB", 
                                   callback_data=f"dl_{safe_id}_epub"),
            ],
            [
                InlineKeyboardButton("🌐 View on Wattpad", 
                                   url=f"https://www.wattpad.com/story/{story_id}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def format_story_details(self, story_data):
        """Format informasi story untuk ditampilkan"""
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
        """Download EPUB file dari Wattpad"""
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
        """Mengirim log ke channel"""
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
        """Menangani callback dari inline keyboard"""
        query = update.callback_query
        query.answer()
        
        user = get_user(query.from_user.id)
        total_quota = user["daily_quota"] + user["extra_quota"]
        
        if total_quota <= 0:            
            query.message.reply_text(
                "❌ Quota Anda habis!\n"
                "Quota harian akan direset besok pukul 00:00 WIB.\n"
                "Gunakan /beli untuk quota tambahan."
            )
            return
        
        try:
            _, story_id, file_type = query.data.split('_', 2)
            story_id = story_id.replace('-', '_')
        except Exception as e:
            logger.error(f"Invalid callback data: {query.data} - {e}")
            query.edit_message_text("⚠️ Invalid request. Please try again.")
            return
        
        message = query.message
        processing_msg = message.reply_text("⏳ Processing your download request...")
        
        try:
            story_info = self.get_story_info(story_id)
            if not story_info:
                processing_msg.edit_text("❌ Failed to get story information.")
                return
            
            title = re.sub(r'[\\/*?:"<>|]', '_', story_info['title'])
            watermark = "@WattpadToEPUBbot"
            filename = f"{title} ({watermark}).epub"
            
            response = self.download_epub(story_id)
            if not response:
                processing_msg.edit_text("❌ Download failed. Please try again later.")
                return
            
            filepath = os.path.join(self.temp_dir, filename)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): 
                    if chunk:
                        f.write(chunk)
            
            # Kurangi quota (prioritaskan daily_quota)
            if user["daily_quota"] > 0:
                users_collection.update_one(
                    {"user_id": user["user_id"]},
                    {"$inc": {"daily_quota": -1}}
                )
            else:
                users_collection.update_one(
                    {"user_id": user["user_id"]},
                    {"$inc": {"extra_quota": -1}}
                )
            
            with open(filepath, 'rb') as f:
                message.reply_document(
                    document=InputFile(f, filename=filename),
                    caption=f"📚 {story_info['title']}\n⚡ Downloaded via @WattpadToEPUBbot"
                )
            
            user = query.from_user
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
            logger.error(f"Error in callback handler: {e}")
            processing_msg.edit_text("⚠️ An error occurred. Please try again.")
            
        finally:
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)

    def handle_message(self, update: Update, context: CallbackContext):
        """Menangani pesan masuk"""
        message = update.message
        if not message or message.from_user.is_bot:
            return
        
        text = message.text or message.caption
        if not text:
            return
        
        story_ids = set(re.findall(self.story_pattern, text))
        part_ids = set(re.findall(self.part_pattern, text))
        
        if not story_ids and not part_ids:
            return
        
        for story_id in story_ids:
            try:
                story_info = self.get_story_info(story_id)
                if not story_info:
                    continue
                
                message.reply_photo(
                    photo=story_info['cover'],
                    caption=self.format_story_details(story_info),
                    reply_markup=self.create_download_keyboard(story_id),
                    parse_mode='HTML'
                )
                
            except Exception as e:
                logger.error(f"Error processing story {story_id}: {e}")

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        update.effective_message.reply_text("⚠️ Terjadi kesalahan. Silakan coba lagi.")

def main():
    """Entry point untuk aplikasi"""
    # Inisialisasi bot
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    wattpad_bot = WattpadBot()
    
    # Tambahkan handler
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help))
    dispatcher.add_handler(CommandHandler("beli", beli_quota))
    dispatcher.add_handler(CommandHandler("quota", cek_quota))
    dispatcher.add_handler(CommandHandler("addquota", admin_tambah_quota, filters=Filters.chat(ADMIN_CHAT_ID)))
    dispatcher.add_handler(MessageHandler(Filters.regex(r'wattpad\.com/story/\d+'), wattpad_bot.handle_message))
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_callback_query))
    dispatcher.add_error_handler(error_handler)
    
    # Jadwalkan reset harian pukul 00:00
    job_queue = updater.job_queue
    job_queue.run_daily(reset_daily_quotas, time=time(hour=0, minute=0, second=0))
    
    # Jalankan Flask di thread terpisah
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    # Jalankan bot
    updater.start_polling()
    logger.info("Bot sudah berjalan...")
    updater.idle()

if __name__ == '__main__':
    # Buat admin default jika belum ada
    if admins_collection.count_documents({}) == 0:
        admins_collection.insert_one({
            "user_id": ADMIN_CHAT_ID,
            "username": ADMIN_USERNAME,
            "created_at": datetime.now()
        })
    
    main()
