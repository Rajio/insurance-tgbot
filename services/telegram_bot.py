from telegram.ext import ApplicationBuilder
from config.settings import settings

class TelegramBot:
    """Main Telegram bot application"""
    
    def __init__(self):
        self.application = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()
    
    def setup_handlers(self, handlers):
        """Add all conversation handlers to the application"""
        for handler in handlers:
            self.application.add_handler(handler)
    
    def run(self):
        """Start the bot"""
        self.application.run_polling()