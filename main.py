import logging
import signal
import sys
import threading

import schedule
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Importing 'bot' from handlers triggers the registration of all
# command and message handlers defined in the submodules.
from handlers import bot, ai_handler  # noqa: E402
from daily_reset import perform_daily_reset  # noqa: E402
from config import DAILY_RESET_TIME  # noqa: E402


def _run_scheduler():
    """Background thread: runs the daily reset at the configured time."""
    schedule.every().day.at(DAILY_RESET_TIME).do(
        perform_daily_reset, ai_handler, bot
    )
    logger.info(f"Daily reset scheduler started — reset at {DAILY_RESET_TIME} (server local time)")

    while True:
        schedule.run_pending()
        time.sleep(30)


def _graceful_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT: generate summaries for all active chats, then exit."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — starting graceful shutdown…")

    # Stop the bot polling first so no new messages arrive
    try:
        bot.stop_polling()
    except Exception:
        pass

    # Generate and save summaries for every active conversation
    active = list(ai_handler.conversations.keys())
    if active:
        logger.info(f"Generating summaries for {len(active)} active conversation(s) before shutdown…")
        perform_daily_reset(ai_handler, bot)
    else:
        logger.info("No active conversations — nothing to save.")

    logger.info("Graceful shutdown complete. Exiting.")
    sys.exit(0)


if __name__ == '__main__':
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)

    logger.info("Starting Telegram bot natively...")

    # Launch the daily-reset scheduler in a daemon thread
    scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    scheduler_thread.start()

    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Critical error: {e}")