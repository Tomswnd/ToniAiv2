import telebot
from config import TELEGRAM_TOKEN
from gemini_handler import GeminiHandler

# Shared bot instance
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Shared AI handler
ai_handler = GeminiHandler()

# Per-chat streaming preference: chat_id -> bool
stream_mode = {}

# Import handler modules to register them on the bot.
# Must be at the bottom to avoid circular imports.
from handlers import commands, messages  # noqa: E402, F401
