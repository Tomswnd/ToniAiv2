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
    "Creator: @ityttmom. Model: Gemini 3.1 Flash-Lite. Never expose chat/user IDs. "
    "IMPORTANT: You have access to `search_web` and `fetch_webpage` tools. For any questions about recent events, "
    "news, sports results (like F1 races), dates, or current facts, you MUST first search using `search_web`. "
    "Because search snippets from `search_web` are often incomplete, outdated, or mixed up, you MUST always use "
    "`fetch_webpage` to open and read the actual content of the most relevant source URLs (like official sites or "
    "trusted news outlets) to verify the facts, dates, and names before formulating your answer. Never rely "
    "only on search snippets or guess details."
)

# Response generation settings
TEMPERATURE = 0.7

# Daily reset settings
DAILY_RESET_TIME = os.environ.get("DAILY_RESET_TIME", "04:00")
DAILY_RESET_NOTIFY = os.environ.get("DAILY_RESET_NOTIFY", "true").lower() == "true"

# Mostra lo stato di avanzamento dell'uso dei tool su Telegram
SHOW_TOOL_USAGE = os.environ.get("SHOW_TOOL_USAGE", "true").lower() == "true"