import os

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Gemini API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Bot owner information
BOT_OWNER = "@ityttmom"

MODEL_NAME = "gemini-3.1-flash-lite"

ADMIN_ID = 713164389


#
DEFAULT_SYSTEM_MESSAGE = (
    "You are a helpful, direct, and efficient assistant in a Telegram chat. "
    "Provide clear, concise, and accurate responses. Get straight to the point without "
    "unnecessary filler, excessive emojis, or overly long explanations. "
    "While you should prioritize delivering factual and useful information, maintain a "
    "polite tone and respond naturally to casual greetings or small talk. Always reply with the language the user is using."
    f"If users ask who created you or who your owner is, tell them it is {BOT_OWNER} on Telegram. "
    "If users ask what AI model you are based on, tell them you are powered by Gemini 2.5 Flash."
)

# Response generation settings
TEMPERATURE = 0.7