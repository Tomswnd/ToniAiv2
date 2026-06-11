import logging
from config import BOT_OWNER, ADMIN_ID
from handlers import bot, ai_handler, stream_mode
from chat_logger import chat_logger

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


@bot.message_handler(commands=['stream'])
def stream_command(message):
    """Toggle streaming mode for the current chat."""
    chat_id = message.chat.id
    current = stream_mode.get(chat_id, False)
    stream_mode[chat_id] = not current

    if stream_mode[chat_id]:
        bot.reply_to(message, "✅ Modalità streaming attivata!\nLe risposte verranno mostrate in tempo reale.")
    else:
        bot.reply_to(message, "❌ Modalità streaming disattivata.\nLe risposte verranno inviate complete.")


@bot.message_handler(commands=['help'])
def help_command(message):
    """Send a message when the command /help is issued."""
    is_group_chat = message.chat.type in ['group', 'supergroup']

    help_message = (
        "Ecco i comandi disponibili:\n\n"
        "/start - Inizia una conversazione\n"
        "/help - Mostra questa lista\n"
        "/reset - Cancella la cronologia della conversazione\n"
        "/stream - Attiva/disattiva risposte in tempo reale\n"
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

    # 1. Svuotiamo la memoria in RAM di Gemini per QUESTA chat
    if chat_id in ai_handler.conversations:
        del ai_handler.conversations[chat_id]

    # 2. Eliminiamo il file fisico dalla cartella dei log
    try:
        chat_logger.delete_log(chat_id)
    except AttributeError:
        pass  # Ignora l'errore se la funzione non è ancora stata creata

    bot.reply_to(message, "Memoria e log cancellati. Iniziamo una nuova conversazione!")
