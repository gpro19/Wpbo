import re
import os
import requests
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from datetime import datetime

logger = logging.getLogger(__name__)

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
        params = {'format': 'epub', 'bot': 'true', 'mode': 'story'}
        
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
