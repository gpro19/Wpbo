from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from wattpad import WattpadBot
from database import DatabaseManager
from config import QUOTA_PRICES, ADMIN_USERNAME

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

# Tambahkan handler lainnya di sini
