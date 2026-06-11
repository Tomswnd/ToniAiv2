import logging
from config import BOT_OWNER, ADMIN_ID
from handlers import bot, ai_handler
from user_memory import delete_all_user_memories

logger = logging.getLogger(__name__)


@bot.message_handler(commands=['apistats'])
def admin_status(message):
    """Show API usage stats (admin only)."""
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "Comando disponibile solo per il creatore del bot.")
        return

    stats = ai_handler.get_stats()

    LIMIT_DAILY_REQUESTS = 500
    LIMIT_DAILY_TOKENS = 250000

    req_percent = (stats['calls'] / LIMIT_DAILY_REQUESTS) * 100
    tok_percent = (stats['total_tokens'] / LIMIT_DAILY_TOKENS) * 100

    response = (
        f"**ToniAI Admin Panel**\n"
        f"Billing Cycle: {stats['date']} (PT)\n\n"
        f"**Model:** `{stats['model']}`\n\n"
        f"**Requests (Today):** {stats['calls']} / {LIMIT_DAILY_REQUESTS} ({req_percent:.1f}%)\n"
        f"**Tokens (Today):** {stats['total_tokens']} / 250K ({tok_percent:.1f}%)\n"
        f"  - Input: {stats['prompt_tokens']}\n"
        f"  - Output: {stats['response_tokens']}\n"
        "\n_Note: RPM (Requests Per Minute) limit is 15._\n"
        "_Daily quotas reset at 09:00 AM (Italian Time)._"
    )

    bot.reply_to(message, response, parse_mode='Markdown')


@bot.message_handler(commands=['start'])
def start_command(message):
    """Send a message when the command /start is issued."""
    user_first_name = message.from_user.first_name
    is_group_chat = message.chat.type in ['group', 'supergroup']

    welcome_message = (
        f"Ciao {user_first_name}!\n\n"
        f"Sono un bot alimentato da intelligenza artificiale (Gemini 3.1 Flash-Lite).\n"
        f"Sono stato creato da {BOT_OWNER} su Telegram.\n\n"
    )

    if is_group_chat:
        welcome_message += (
            "In questa chat di gruppo risponderò solo ai messaggi che iniziano con 'toniai'.\n\n"
            "Esempio: toniai raccontami una storia\n\n"
            "Usa /help per vedere la guida."
        )
    else:
        welcome_message += "Puoi chiedermi qualsiasi cosa! Usa /reset per cancellare la memoria della conversazione."

    bot.reply_to(message, welcome_message)


@bot.message_handler(commands=['help'])
def help_command(message):
    """Send a message when the command /help is issued."""
    is_group_chat = message.chat.type in ['group', 'supergroup']

    help_message = (
        "Ecco i comandi disponibili:\n\n"
        "/start - Inizia una conversazione\n"
        "/help - Mostra questa lista\n"
        "/reset - Cancella la cronologia della conversazione (RAM)\n"
        "/forget - Dimentica tutte le informazioni memorizzate su di te (DB)\n"
        "/apistats - Statistiche di consumo API\n\n"
        f"Sviluppato da {BOT_OWNER} su Telegram."
    )

    if is_group_chat:
        help_message = "Inizia sempre il tuo messaggio con 'toniai' per farmi rispondere.\n\n" + help_message

    bot.reply_to(message, help_message)


@bot.message_handler(commands=['reset'])
def reset_command(message):
    """Reset the conversation history for the current chat."""
    chat_id = message.chat.id

    # Svuotiamo la memoria in RAM di Gemini per QUESTA chat
    if chat_id in ai_handler.conversations:
        del ai_handler.conversations[chat_id]

    bot.reply_to(message, "Memoria della chat (RAM) cancellata. Iniziamo una nuova conversazione!")


@bot.message_handler(commands=['forget'])
def forget_command(message):
    """Delete all stored user memories for the sender."""
    user_id = message.from_user.id
    deleted_count = delete_all_user_memories(user_id)
    if deleted_count > 0:
        bot.reply_to(
            message,
            f"Ho dimenticato tutte le informazioni memorizzate su di te ({deleted_count} ricordi rimossi)."
        )
    else:
        bot.reply_to(message, "Non ho alcuna informazione memorizzata su di te.")
