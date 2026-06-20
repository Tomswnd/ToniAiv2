import logging
from config import BOT_OWNER, ADMIN_ID
from handlers import bot, ai_handler
from group_config import get_group_prompt, set_group_prompt, clear_group_prompt
from gemini_handler import delete_chat_data
from daily_reset import reset_single_chat, is_notify_enabled, set_notify

logger = logging.getLogger(__name__)


def _is_group_admin(message) -> bool:
    """Check if the sender is the bot admin or a group admin/creator."""
    if message.from_user.id == ADMIN_ID:
        return True
    if message.chat.type in ['group', 'supergroup']:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ['administrator', 'creator']
    return False


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
        "/reset - Salva resoconto personaggi e resetta la conversazione\n"
        "/forget - Cancella i dati della chat corrente\n"
        "/setprompt <testo> - Imposta un prompt personalizzato per il gruppo (admin)\n"
        "/viewprompt - Mostra il prompt personalizzato del gruppo\n"
        "/clearprompt - Rimuovi il prompt personalizzato del gruppo (admin)\n"
        "/togglenotify - Attiva/disattiva notifiche di reset (admin)\n"
        "/apistats - Statistiche di consumo API\n\n"
        f"Sviluppato da {BOT_OWNER} su Telegram."
    )

    if is_group_chat:
        help_message = "Inizia sempre il tuo messaggio con 'toniai' per farmi rispondere.\n\n" + help_message

    bot.reply_to(message, help_message)


@bot.message_handler(commands=['reset'])
def reset_command(message):
    """Generate a character summary, save it, optionally notify, then reset the conversation."""
    chat_id = message.chat.id

    if chat_id not in ai_handler.conversations:
        bot.reply_to(message, "Non c'è nessuna conversazione attiva da resettare.")
        return

    bot.send_chat_action(chat_id, 'typing')

    try:
        summary = reset_single_chat(chat_id, ai_handler, bot)
        if summary:
            bot.reply_to(message, "🔄 Resoconto personaggi salvato e conversazione resettata!")
        else:
            bot.reply_to(message, "🔄 Conversazione resettata (nessun resoconto generato).")
    except Exception as e:
        logger.error(f"Error during manual reset for chat {chat_id}: {e}")
        # Fallback: force-delete anyway
        if chat_id in ai_handler.conversations:
            del ai_handler.conversations[chat_id]
        bot.reply_to(message, "🔄 Conversazione resettata (errore durante il salvataggio del resoconto).")


@bot.message_handler(commands=['togglenotify'])
def toggle_notify_command(message):
    """Toggle daily-reset notifications on/off (admin only)."""
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "Comando disponibile solo per il creatore del bot.")
        return

    current = is_notify_enabled()
    set_notify(not current)
    new_state = "attivate ✅" if not current else "disattivate ❌"
    bot.reply_to(message, f"Notifiche di reset giornaliero: {new_state}")


@bot.message_handler(commands=['forget'])
def forget_command(message):
    """Delete all stored chat data for the current chat."""
    chat_id = message.chat.id
    delete_chat_data(chat_id)
    bot.reply_to(message, "🗑️ Dati della chat cancellati con successo.")


@bot.message_handler(commands=['setprompt'])
def setprompt_command(message):
    """Set a custom system instruction for this group (admin only)."""
    chat_id = message.chat.id

    # Only available in groups
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "Questo comando è disponibile solo nei gruppi.")
        return

    # Admin check
    if not _is_group_admin(message):
        bot.reply_to(message, "Comando disponibile solo per gli admin del gruppo.")
        return

    # Extract prompt text after the command
    prompt_text = message.text.split(None, 1)
    if len(prompt_text) < 2:
        bot.reply_to(message, "Uso: /setprompt <testo del prompt>")
        return
    prompt_text = prompt_text[1].strip()

    set_group_prompt(chat_id, prompt_text)

    # Force reload della conversazione
    if chat_id in ai_handler.conversations:
        del ai_handler.conversations[chat_id]

    bot.reply_to(message, "✅ Prompt personalizzato impostato con successo!")


@bot.message_handler(commands=['viewprompt'])
def viewprompt_command(message):
    """Show the current custom prompt for this group."""
    chat_id = message.chat.id

    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "Questo comando è disponibile solo nei gruppi.")
        return

    prompt = get_group_prompt(chat_id)
    if prompt:
        bot.reply_to(message, f"📝 Prompt personalizzato attuale:\n\n{prompt}")
    else:
        bot.reply_to(message, "Nessun prompt personalizzato impostato. Viene usato il prompt di default.")


@bot.message_handler(commands=['clearprompt'])
def clearprompt_command(message):
    """Clear the custom prompt for this group (admin only)."""
    chat_id = message.chat.id

    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "Questo comando è disponibile solo nei gruppi.")
        return

    if not _is_group_admin(message):
        bot.reply_to(message, "Comando disponibile solo per gli admin del gruppo.")
        return

    clear_group_prompt(chat_id)

    # Force reload della conversazione
    if chat_id in ai_handler.conversations:
        del ai_handler.conversations[chat_id]

    bot.reply_to(message, "🗑️ Prompt personalizzato rimosso. Verrà usato il prompt di default.")
