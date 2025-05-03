from services.telegram_bot import TelegramBot
from handlers.conversation_handlers import get_conversation_handler
from utils.file_utils import ensure_directories_exist
from utils.logging_utils import logger

def main():
    # Ensure required directories exist
    ensure_directories_exist()
    
    try:
        # Initialize bot
        bot = TelegramBot()
        
        # Setup handlers
        conversation_handler = get_conversation_handler()
        bot.setup_handlers([conversation_handler])
        
        # Start bot
        logger.info("Starting bot...")
        bot.run()
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)

if __name__ == '__main__':
    main()