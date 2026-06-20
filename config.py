import os

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Gemini API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Bot owner information
BOT_OWNER = "@ityttmom"

MODEL_NAME = "gemini-3.1-flash-lite"

ADMIN_ID = 713164389

# Soglia in secondi oltre la quale il bot taglia la cronologia
RESPONSE_TIME_THRESHOLD = 10

#
DEFAULT_SYSTEM_MESSAGE = (
    "Telegram chat assistant. Be concise, direct, friendly. Reply in the user's language. "
    "Messages come as '[Name dice]: text'. Never prepend speaker labels to your replies. "
    "Use group gags/dynamics naturally when appropriate. "
    "Creator: {BOT_OWNER}. Model: Gemini 3.1 Flash-Lite. Never expose chat/user IDs."
)

# Response generation settings
TEMPERATURE = 0.7

# Daily reset settings
DAILY_RESET_TIME = os.environ.get("DAILY_RESET_TIME", "04:00")
DAILY_RESET_NOTIFY = os.environ.get("DAILY_RESET_NOTIFY", "true").lower() == "true"