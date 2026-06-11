import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Importing 'bot' from handlers triggers the registration of all
# command and message handlers defined in the submodules.
from handlers import bot  # noqa: E402


if __name__ == '__main__':
    logger.info("Starting Telegram bot natively...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Critical error: {e}")