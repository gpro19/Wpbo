import re
import tempfile
import os
from datetime import datetime
from typing import Dict, Set
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
)
import requests
import logging
from flask import Flask
import threading

# Set up logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
flask_app = Flask(__name__)

# Bot token
TELEGRAM_TOKEN = "8079725112:AAF6lX0qvwz-dTkAkXmpHV1ZDdzcrxDBJWk"  # Ganti dengan token bot Anda

class WattpadBot:
    def __init__(self):
        self.headers = {"user-agent": "WPDTelegramBot"}
        self.host = "https://wpd.rambhat.la"
        self.temp_dir = tempfile.gettempdir()

        # URL patterns
        self.story_pattern = r"wattpad\.com/story/(\d+)"
        self.part_pattern = r"wattpad\.com/(\d+)"

    def get_story(self, story_id: int) -> Dict:
        url = f"https://www.wattpad.com/api/v3/stories/{story_id}?fields=id,cover,readCount,voteCount,commentCount,modifyDate,numParts,language(name),user(name),completed,mature,title,parts(id)"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_story_from_part(self, part_id: int) -> Dict:
        url = f"https://www.wattpad.com/api/v3/story_parts/{part_id}?fields=groupId,group(cover,readCount,voteCount,commentCount,modifyDate,numParts,language(name),user(name),completed,mature,title,parts(id))"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def download_file(self, url: str, filename: str) -> str:
        filepath = os.path.join(self.temp_dir, filename)
        response = requests.get(url, headers=self.headers, stream=True)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return filepath
        return None

    def format_story_info(self, story: Dict) -> str:
        info = f"📖 <b>{story['title']}</b>\n"
        info += f"👤 Author: {story['user']['name']}\n\n"
        info += f"👀 Reads: {story['readCount']:,}\n"
        info += f"⭐ Votes: {story['voteCount']:,}\n"
        info += f"🗨️ Comments: {story['commentCount']:,}\n\n"
        info += f"🔖 Parts: {story['numParts']}\n"
        info += f"🌏 Language: {story['language']['name']}\n\n"

        last_updated = datetime.strptime(story["modifyDate"], "%Y-%m-%dT%H:%M:%SZ")
        info += f"✅ Completed on {last_updated.strftime('%Y-%m-%d')}" if story["completed"] else f"🚧 Last updated on {last_updated.strftime('%Y-%m-%d')}"
        
        if story["mature"]:
            info += " 🚸 Mature Content\n"
        return info

    def create_keyboard(self, story_id: int) -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("📥 Download EPUB", callback_data=f"download_{story_id}_epub"),
                InlineKeyboardButton("🖼️ EPUB with Images", callback_data=f"download_{story_id}_epub_images"),
            ],
            [
                InlineKeyboardButton("🌐 View on Wattpad", url=f"https://wattpad.com/story/{story_id}")
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def handle_button_click(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        query.answer()
        
        data = query.data
        if not data.startswith('download_'):
            return
            
        _, story_id, file_type = data.split('_')
        query.edit_message_reply_markup(reply_markup=None)
        
        message = query.message.reply_text("⏳ Downloading story, please wait...")
        
        try:
            story_data = self.get_story(story_id)
            title = story_data["title"]
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)

            if file_type == "epub":
                url = f"{self.host}/download/{story_id}?bot=true&format=epub"
                filename = f"{safe_title}.epub"
            else:  # epub_images
                url = f"{self.host}/download/{story_id}?bot=true&format=epub&download_images=true"
                filename = f"{safe_title}_with_images.epub"
            
            filepath = self.download_file(url, filename)
            
            if filepath:
                with open(filepath, 'rb') as file:
                    context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=InputFile(file, filename=filename),
                        caption=f"Here's your downloaded story: {title}"
                    )
                
                os.remove(filepath)
                message.delete()
            else:
                message.edit_text("❌ Failed to download the story. Please try again later.")
                
        except Exception as e:
            logger.error(f"Error handling download: {e}")
            message.edit_text("❌ An error occurred while downloading the story.")
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
            
    def handle_message(self, update: Update, context: CallbackContext) -> None:
        message = update.message
        if message.from_user.is_bot:
            return

        text = message.text or message.caption
        if not text:
            return

        story_ids = set(re.findall(self.story_pattern, text))
        part_ids = set(re.findall(self.part_pattern, text))

        if not story_ids and not part_ids:
            return

        processed_parts = set()
        processed_stories = set()
        responses = []

        for story_id in story_ids:
            try:
                data = self.get_story(story_id)
                story_id_str = str(data["id"])
                
                if story_id_str in processed_stories:
                    continue
                
                formatted_info = self.format_story_info(data)
                keyboard = self.create_keyboard(story_id_str)
                cover_url = data["cover"]
                
                responses.append((formatted_info, cover_url, keyboard))
                processed_stories.add(story_id_str)
                processed_parts.update(str(part["id"]) for part in data["parts"])
                
            except Exception as e:
                logger.error(f"Error processing story {story_id}: {e}")

        for part_id in part_ids:
            if part_id in processed_parts:
                continue
                
            try:
                data = self.get_story_from_part(part_id)
                story = data["group"]
                story_id_str = str(story["id"])
                
                formatted_info = self.format_story_info(story)
                keyboard = self.create_keyboard(story_id_str)
                cover_url = story["cover"]

                responses.append((formatted_info, cover_url, keyboard))
                processed_stories.add(story_id_str)
                processed_parts.update(str(part["id"]) for part in story["parts"])
                
            except Exception as e:
                logger.error(f"Error processing part {part_id}: {e}")

        for info, cover_url, keyboard in responses:
            try:
                message.reply_photo(
                    photo=cover_url,
                    caption=info,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Error sending response: {e}")
                message.reply_text(
                    info, reply_markup=keyboard, parse_mode="HTML"
                )


@flask_app.route('/')
def home():
    return "Wattpad Bot is running!"


def start(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Welcome to Wattpad Story Downloader Bot!\n\n"
        "Just send me a Wattpad story URL and I'll provide EPUB download options.\n\n"
        "Example URLs I recognize:\n"
        "- https://www.wattpad.com/story/12345678\n"
        "- https://www.wattpad.com/98765432\n"
    )
    context.bot.send_message(chat_id=update.message.chat_id, text=help_text)


def info(update: Update, context: CallbackContext) -> None:
    info_text = (
        "📚 <b>Wattpad Story Downloader Bot</b>\n\n"
        "This bot downloads Wattpad stories in EPUB format.\n"
        "Source: github.com/TheOnlyWayUp/WPDBot"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Source Code", url="https://github.com/TheOnlyWayUp/WPDBot")]])
    context.bot.send_message(chat_id=update.message.chat_id, text=info_text, reply_markup=keyboard, parse_mode="HTML")


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    wattpad_bot = WattpadBot()

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("info", info))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, wattpad_bot.handle_message))
    dp.add_handler(CallbackQueryHandler(wattpad_bot.handle_button_click))

    updater.start_polling()
    updater.idle()


def run_flask():
    flask_app.run(host='0.0.0.0', port=8000)


if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    main()
