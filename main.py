import telebot
import logging
from config import TELEGRAM_TOKEN, BOT_OWNER
from gemini_handler import GeminiHandler
from chat_logger import chat_logger

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize the bot and the Gemini AI handler
bot = telebot.TeleBot(TELEGRAM_TOKEN)
ai_handler = GeminiHandler()


@bot.message_handler(commands=['start'])
def start_command(message):
    """Send a message when the command /start is issued."""
    user_first_name = message.from_user.first_name
    is_group_chat = message.chat.type in ['group', 'supergroup']

    # In groups, only respond if the command starts with 'toniai' or is a direct mention
    if is_group_chat:
        message_text = message.text or ""
        if not message_text.lower().startswith('toniai') and not message_text.startswith('/start@'):
            return

    welcome_message = (
        f"Ciao {user_first_name}! 👋\n\n"
        f"Sono un bot alimentato da intelligenza artificiale (Gemini 2.5 Flash).\n"
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

    if is_group_chat:
        message_text = message.text or ""
        if not message_text.lower().startswith('toniai') and not message_text.startswith('/help@'):
            return

    bot_info = bot.get_me()
    help_message = (
        "Ecco i comandi disponibili:\n\n"
        "/start - Inizia una conversazione\n"
        "/help - Mostra questa lista\n"
        "/reset - Cancella la cronologia della conversazione\n\n"
        f"Sviluppato da {BOT_OWNER} su Telegram."
    )

    if is_group_chat:
        help_message = "Inizia sempre il tuo messaggio con 'toniai' per farmi rispondere.\n\n" + help_message

    bot.reply_to(message, help_message)


@bot.message_handler(commands=['reset'])
def reset_command(message):
    """Reset the conversation history for a user."""
    is_group_chat = message.chat.type in ['group', 'supergroup']

    if is_group_chat:
        message_text = message.text or ""
        if not message_text.lower().startswith('toniai') and not message_text.startswith('/reset@'):
            return

    user_id = message.from_user.id
    response = ai_handler.reset_conversation(user_id)
    bot.reply_to(message, "Memoria cancellata. Iniziamo una nuova conversazione! 🔄")


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    """Handle incoming messages and generate responses."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_text = message.text or ""
    username = message.from_user.username
    first_name = message.from_user.first_name
    is_group_chat = message.chat.type in ['group', 'supergroup']

    # Group chat logic: require the "toniai" trigger
    if is_group_chat:
        # Check if the trigger is present
        if not message_text.lower().startswith("toniai"):
            return

        # Strip the trigger word ("toniai") from the beginning
        # We add a space after "toniai " to strip the space too, if they typed one
        trigger_len = len("toniai")
        message_text = message_text[trigger_len:].strip()

        # If they just typed "toniai" and nothing else
        if not message_text:
            bot.reply_to(message, "Ciao! Sono qui per aiutarti. Cosa vorresti sapere?")
            return

    bot.send_chat_action(chat_id, 'typing')
    logger.info(f"Elaborazione messaggio da utente {user_id}: '{message_text}'")

    try:
        # Generate response using Gemini
        response = ai_handler.generate_response(user_id, message_text)

        # Failsafe: if Gemini returns an empty string, don't crash Telegram
        if not response or not response.strip():
            logger.warning("Gemini returned an empty response.")
            response = "Scusa, non sono riuscito a elaborare una risposta."

        bot.reply_to(message, response)

        # Log the conversation locally
        chat_logger.log_message(
            user_id=user_id,
            user_message=message_text,
            bot_response=response,
            username=username,
            first_name=first_name
        )
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        bot.reply_to(message,
                     "Scusa, sto avendo problemi a connettermi all'intelligenza artificiale in questo momento. Riprova più tardi.")

if __name__ == '__main__':
    logger.info("Starting Telegram bot natively...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Critical error: {e}")