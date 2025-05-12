
import re
import tempfile
from datetime import datetime
from typing import Dict, Set
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
import aiohttp
import logging
import pypandoc
from flask import Flask, request, jsonify

# Load environment variables


# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Bot token from environment variable
TELEGRAM_TOKEN = "8079725112:AAF6lX0qvwz-dTkAkXmpHV1ZDdzcrxDBJWk"

class WattpadBot:
    def __init__(self):
        self.headers = {"user-agent": "WPDTelegramBot"}
        self.host = "https://wpd.rambhat.la"  # Base URL for download endpoints
        self.host = self.host.rstrip("/")  # Remove trailing slash
        self.temp_dir = tempfile.gettempdir()

        # Patterns to detect Wattpad URLs
        self.story_pattern = r"wattpad\.com/story/(\d+)"
        self.part_pattern = r"wattpad\.com/(\d+)"

    async def get_story_from_part(self, part_id: int) -> Dict:
        """Retrieve story data from a part ID."""
        async with aiohttp.ClientSession(
            headers=self.headers, raise_for_status=True
        ) as session:
            async with session.get(
                f"https://www.wattpad.com/api/v3/story_parts/{part_id}?fields=groupId,group(cover,readCount,voteCount,commentCount,modifyDate,numParts,language(name),user(name),completed,mature,title,parts(id))"
            ) as response:
                return await response.json()

    async def get_story(self, story_id: int) -> Dict:
        """Retrieve story data from a story ID."""
        async with aiohttp.ClientSession(
            headers=self.headers, raise_for_status=True
        ) as session:
            async with session.get(
                f"https://www.wattpad.com/api/v3/stories/{story_id}?fields=id,cover,readCount,voteCount,commentCount,modifyDate,numParts,language(name),user(name),completed,mature,title,parts(id)"
            ) as response:
                return await response.json()

    async def download_file(self, url: str, filename: str) -> str:
        """Download file from URL and save to temp directory."""
        filepath = os.path.join(self.temp_dir, filename)
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    return filepath
        return None

    def convert_epub_to_pdf(self, epub_path: str) -> str:
        """Convert EPUB file to PDF using pypandoc."""
        try:
            # Generate PDF path
            pdf_path = os.path.splitext(epub_path)[0] + ".pdf"
            
            # Convert using pypandoc
            output = pypandoc.convert_file(
                epub_path,
                'pdf',
                outputfile=pdf_path,
                extra_args=['--pdf-engine=xelatex']
            )
            
            return pdf_path
        except Exception as e:
            logger.error(f"Error converting EPUB to PDF: {e}")
            return None

    def format_story_info(self, story: Dict) -> str:
        """Format story information into a readable string."""
        info = f"📖 <b>{story['title']}</b>\n"
        info += f"👤 Author: {story['user']['name']}\n\n"

        info += f"👀 Reads: {story['readCount']:,}\n"
        info += f"⭐ Votes: {story['voteCount']:,}\n"
        info += f"🗨️ Comments: {story['commentCount']:,}\n\n"

        info += f"🔖 Parts: {story['numParts']}\n"
        info += f"🌏 Language: {story['language']['name']}\n\n"

        last_updated = int(
            datetime.strptime(story["modifyDate"], "%Y-%m-%dT%H:%M:%SZ").timestamp()
        )
        
        if story["completed"]:
            info += f"✅ Completed on {datetime.fromtimestamp(last_updated).strftime('%Y-%m-%d')}\n"
        else:
            info += f"🚧 Last updated on {datetime.fromtimestamp(last_updated).strftime('%Y-%m-%d')}\n"
            
        if story["mature"]:
            info += "🚸 Mature Content\n"

        return info

    def create_keyboard(self, story_id: int) -> InlineKeyboardMarkup:
        """Create an inline keyboard with download options."""
        keyboard = [
            [
                InlineKeyboardButton("📥 Download PDF", callback_data=f"download_{story_id}_pdf"),
                InlineKeyboardButton("🖼️ PDF with Images", callback_data=f"download_{story_id}_pdf_images"),
            ],
            [
                InlineKeyboardButton("🌐 View on Wattpad", url=f"https://wattpad.com/story/{story_id}")
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def handle_button_click(self, update: Update, context: CallbackContext) -> None:
        """Handle button click events for downloads."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if not data.startswith('download_'):
            return
            
        _, story_id, file_type = data.split('_')
        
        await query.edit_message_reply_markup(reply_markup=None)
        
        # Notify user that download is starting
        message = await query.message.reply_text("⏳ Downloading and converting story, please wait...")
        
        try:
            # Determine which URL to use based on file type
            if file_type == "pdf":
                url = f"{self.host}/download/{story_id}?bot=true&format=epub"
                filename = f"wattpad_{story_id}.epub"
                final_filename = f"wattpad_{story_id}.pdf"
            else:  # pdf_images
                url = f"{self.host}/download/{story_id}?bot=true&format=epub&download_images=true"
                filename = f"wattpad_{story_id}_with_images.epub"
                final_filename = f"wattpad_{story_id}_with_images.pdf"
            
            # Download the EPUB file
            epub_path = await self.download_file(url, filename)
            
            if epub_path:
                # Convert to PDF
                pdf_path = self.convert_epub_to_pdf(epub_path)
                
                if pdf_path:
                    # Send the PDF to user
                    with open(pdf_path, 'rb') as file:
                        await context.bot.send_document(
                            chat_id=query.message.chat_id,
                            document=InputFile(file, filename=final_filename),
                            caption=f"Here's your downloaded story in PDF format: {final_filename}"
                        )
                    
                    # Clean up
                    os.remove(epub_path)
                    os.remove(pdf_path)
                    await message.delete()
                else:
                    await message.edit_text("❌ Failed to convert the story to PDF.")
                    os.remove(epub_path)
            else:
                await message.edit_text("❌ Failed to download the story. Please try again later.")
                
        except Exception as e:
            logger.error(f"Error handling download: {e}")
            await message.edit_text("❌ An error occurred while processing the story.")
            # Clean up any remaining files
            if 'epub_path' in locals() and os.path.exists(epub_path):
                os.remove(epub_path)
            if 'pdf_path' in locals() and os.path.exists(pdf_path):
                os.remove(pdf_path)
            
    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Handle incoming messages that might contain Wattpad links."""
        message = update.message
        if message.from_user.is_bot:
            return

        text = message.text or message.caption
        if not text:
            return

        story_ids: Set[str] = set(re.findall(self.story_pattern, text))
        part_ids: Set[str] = set(re.findall(self.part_pattern, text))

        if not story_ids and not part_ids:
            return

        # Track processed parts to avoid duplicates
        processed_parts = set()
        processed_stories = set()
        responses = []

        # Process story IDs first
        for story_id in story_ids:
            try:
                data = await self.get_story(story_id)
                story_id_str = str(data["id"])
                
                if story_id_str in processed_stories:
                    continue
                
                formatted_info = self.format_story_info(data)
                keyboard = self.create_keyboard(story_id_str)
                
                # Store the image URL and send photo with caption
                cover_url = data["cover"]
                
                responses.append((formatted_info, cover_url, keyboard))
                processed_stories.add(story_id_str)
                
                # Add all parts from this story to skip list
                processed_parts.update(str(part["id"]) for part in data["parts"])
                
            except Exception as e:
                logger.error(f"Error processing story {story_id}: {e}")

        # Process part IDs that haven't been processed yet
        for part_id in part_ids:
            if part_id in processed_parts:
                continue
                
            try:
                data = await self.get_story_from_part(part_id)
                story = data["group"]
                story_id_str = str(story["id"])
                
                if story_id_str in processed_stories:
                    continue
                
                formatted_info = self.format_story_info(story)
                keyboard = self.create_keyboard(story_id_str)
                
                # Store the image URL and send photo with caption
                cover_url = story["cover"]
                
                responses.append((formatted_info, cover_url, keyboard))
                processed_stories.add(story_id_str)
                processed_parts.update(str(part["id"]) for part in story["parts"])
                
            except Exception as e:
                logger.error(f"Error processing part {part_id}: {e}")

        # Send all responses
        for info, cover_url, keyboard in responses:
            try:
                await message.reply_photo(
                    photo=cover_url,
                    caption=info,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Error sending response: {e}")
                # Fallback to text-only if photo fails
                await message.reply_text(
                    info, reply_markup=keyboard, parse_mode="HTML"
                )


@app.route('/')
def home():
    return "Wattpad Bot is running!"


async def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    help_text = (
        "Welcome to Wattpad Story Downloader Bot!\n\n"
        "Just send me a Wattpad story URL and I'll provide download options in PDF format.\n\n"
        "Example URLs I recognize:\n"
        "- https://www.wattpad.com/story/12345678\n"
        "- https://www.wattpad.com/98765432\n\n"
        "You can also use me in groups - I'll automatically detect Wattpad links!"
    )
    await update.message.reply_text(help_text)


async def info(update: Update, context: CallbackContext) -> None:
    """Send bot information."""
    info_text = (
        "📚 <b>Wattpad Story Downloader Bot</b>\n\n"
        "This bot helps you easily download Wattpad stories in PDF format.\n\n"
        "Features:\n"
        "- Convert Wattpad stories to PDF\n"
        "- Option to include images\n"
        "- Preserve story formatting\n\n"
        "Credits:\n"
        "- Original idea by AaronBenDaniel\n"
        "- PDF conversion implementation"
    )
    
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👨‍💻 Source Code", url="https://github.com/TheOnlyWayUp/WPDBot")]]
    )
    
    await update.message.reply_text(
        info_text, 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )


def main() -> None:
    """Start the bot and Flask server."""
    # Check if pandoc is installed
    try:
        pypandoc.get_pandoc_version()
    except OSError:
        logger.error("Pandoc is not installed. Please install pandoc first.")
        raise
    
    # Initialize bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    wattpad_bot = WattpadBot()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, wattpad_bot.handle_message
        )
    )
    application.add_handler(CallbackQueryHandler(wattpad_bot.handle_button_click))

    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Run Flask app
    port = "8080"
    app.run(host="0.0.0.0", port=port)
