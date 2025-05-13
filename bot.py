import logging
from flask import Flask
import threading
from telegram.ext import Updater
from config import TELEGRAM_TOKEN, LOG_CHANNEL_ID
from database import DatabaseManager
from handlers import start_command

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi Flask
flask_app = Flask(__name__)

def main():
    """Fungsi utama untuk menjalankan bot"""
    db_manager = DatabaseManager()
    
    # Jalankan task reset harian di background
    reset_thread = threading.Thread(target=scheduled_reset, daemon=True)
    reset_thread.start()

    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Daftarkan handler
    dispatcher.add_handler(CommandHandler('start', start_command))

    # Jalankan Flask di thread terpisah
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False),
        daemon=True)
    flask_thread.start()

    logger.info("Bot starting...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
