import re
import os
import requests
import logging
from datetime import datetime
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

# Token Bot Telegram
TELEGRAM_TOKEN = "7619753860:AAHDPdB12JDzsTyj2Q1CWOJV6y4ol0XXCfw"  # Ganti dengan token Anda

# Channel ID untuk log
LOG_CHANNEL_ID = "-1002594638851"  # Ganti dengan channel log Anda


def start_command(update: Update, context: CallbackContext):
    """Handler untuk command /start"""
    help_text = (
        "📚 *Wattpad to EPUB Bot*\n\n"
        "Send me a Wattpad story URL and I'll convert it to EPUB format.\n\n"
        "Features:\n"
        "- Fast EPUB download\n"
        "- Preserves story formatting\n\n"
        "Just send me a Wattpad link to get started!"
    )
    update.message.reply_text(help_text, parse_mode='Markdown')

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
            filename = f"{title}({watermark}).epub"
            
            response = self.download_epub(story_id)
            if not response:
                processing_msg.edit_text("❌ Download failed. Please try again later.")
                return
            
            filepath = os.path.join(self.temp_dir, filename)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): 
                    if chunk:
                        f.write(chunk)
            
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

@flask_app.route('/')
def home():
    return "Wattpad to EPUB Bot is running!"

def main():
    """Entry point untuk aplikasi"""
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    wattpad_bot = WattpadBot()
    
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, wattpad_bot.handle_message))
    dispatcher.add_handler(CallbackQueryHandler(wattpad_bot.handle_callback_query))
    
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
