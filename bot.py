import re
import tempfile
import os
from datetime import datetime
from typing import Dict
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

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask
flask_app = Flask(__name__)
TELEGRAM_TOKEN = "8079725112:AAF6lX0qvwz-dTkAkXmpHV1ZDdzcrxDBJWk"  # Ganti dengan token Anda

class WattpadBot:
    def __init__(self):
        self.headers = {"user-agent": "WPDTelegramBot"}
        self.host = "https://wpd.rambhat.la"
        self.temp_dir = tempfile.gettempdir()
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
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return filepath
        return None

    def format_story_info(self, story: Dict) -> str:
        info = f"📖 <b>{story['title']}</b>\n"
        info += f"👤 Author: {story['user']['name']}\n"
        info += f"👀 Reads: {story['readCount']:,}\n"
        info += f"⭐ Votes: {story['voteCount']:,}\n"
        info += f"🔖 Parts: {story['numParts']}\n"
        
        last_updated = datetime.strptime(story["modifyDate"], "%Y-%m-%dT%H:%M:%SZ")
        info += f"📅 Last Updated: {last_updated.strftime('%Y-%m-%d')}\n"
        if story["completed"]:
            info += "✅ Completed\n"
        if story["mature"]:
            info += "🔞 Mature Content\n"
        return info

    def create_keyboard(self, story_id: int) -> InlineKeyboardMarkup:
        # Ganti "_" di story_id dengan "-" untuk hindari split error
        safe_story_id = str(story_id).replace("_", "-")
        
        keyboard = [
            [
                InlineKeyboardButton("📥 Download EPUB", callback_data=f"download_{safe_story_id}_epub"),
                InlineKeyboardButton("🖼️ EPUB with Images", callback_data=f"download_{safe_story_id}_epub-images"),  # Pakai "-"
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
        if not data.startswith("download_"):
            return

        # Handle split dengan maxsplit=2 (format: "download_{story_id}_{file_type}")
        parts = data.split("_", maxsplit=2)
        if len(parts) != 3:
            query.message.reply_text("⚠️ Invalid download request.")
            return

        _, story_id, file_type = parts
        story_id = story_id.replace("-", "_")  # Kembalikan ke format asli
        
        # Konversi "epub-images" ke "epub_images" untuk URL
        if file_type == "epub-images":
            file_type = "epub_images"

        msg = query.message.reply_text("⏳ Downloading...")
        
        try:
            story = self.get_story(story_id)
            title = re.sub(r'[\\/*?:"<>|]', "_", story["title"])
            
            if file_type == "epub":
                url = f"{self.host}/download/{story_id}?bot=true&format=epub"
                filename = f"{title}.epub"
            elif file_type == "epub_images":
                url = f"{self.host}/download/{story_id}?bot=true&format=epub&download_images=true"
                filename = f"{title}_with_images.epub"
            else:
                msg.edit_text("❌ Invalid file type.")
                return

            filepath = self.download_file(url, filename)
            if filepath:
                with open(filepath, "rb") as file:
                    context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=InputFile(file, filename=filename),
                        caption=f"📚 {story['title']}"
                    )
                os.remove(filepath)
                msg.delete()
            else:
                msg.edit_text("❌ Failed to download. Try again.")
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            msg.edit_text("🚨 An error occurred. Please try later.")
            if "filepath" in locals() and os.path.exists(filepath):
                os.remove(filepath)

    def handle_message(self, update: Update, context: CallbackContext) -> None:
        message = update.message
        if not message or message.from_user.is_bot:
            return

        text = message.text or message.caption
        if not text:
            return

        story_ids = set(re.findall(self.story_pattern, text))
        part_ids = set(re.findall(self.part_pattern, text))

        for story_id in story_ids:
            try:
                story = self.get_story(story_id)
                message.reply_photo(
                    photo=story["cover"],
                    caption=self.format_story_info(story),
                    reply_markup=self.create_keyboard(story["id"]),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Story error: {e}")

        for part_id in part_ids:
            try:
                part_data = self.get_story_from_part(part_id)
                story = part_data["group"]
                message.reply_photo(
                    photo=story["cover"],
                    caption=self.format_story_info(story),
                    reply_markup=self.create_keyboard(story["id"]),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Part error: {e}")

@flask_app.route("/")
def home():
    return "Wattpad Bot is running!"

def start(update: Update, context: CallbackContext):
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔍 Send a Wattpad story URL to download it as EPUB!"
    )

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    bot = WattpadBot()

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, bot.handle_message))
    dispatcher.add_handler(CallbackQueryHandler(bot.handle_button_click))

    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8000), daemon=True).start()
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
