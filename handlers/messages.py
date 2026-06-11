import logging
from handlers import bot, ai_handler

logger = logging.getLogger(__name__)


def get_reply_context(message):
    """
    Extracts quoted user, quoted text, and downloads the quoted image if present.
    Returns: (context_text, quoted_image)
    """
    quoted_image = None
    context_text = ""

    if message.reply_to_message:
        quoted_msg = message.reply_to_message
        quoted_user = quoted_msg.from_user.first_name if quoted_msg.from_user else "Qualcuno"
        quoted_text = quoted_msg.text or quoted_msg.caption or ""

        # Check if the quoted message contains a photo
        if quoted_msg.photo:
            try:
                photo = quoted_msg.photo[-1]
                file_info = bot.get_file(photo.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                import io
                from PIL import Image
                quoted_image = Image.open(io.BytesIO(downloaded_file))
            except Exception as e:
                logger.error(f"Error downloading quoted photo: {e}")

        if quoted_text:
            context_text = f"[In risposta a {quoted_user} che ha scritto: \"{quoted_text}\"]\n\n"
        elif quoted_msg.photo:
            context_text = f"[In risposta alla foto inviata da {quoted_user}]\n\n"
        else:
            context_text = f"[In risposta a un messaggio di {quoted_user}]\n\n"

    return context_text, quoted_image


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Handle incoming photos, download them, and generate responses using Gemini."""
    import io
    from PIL import Image

    user_id = message.from_user.id
    chat_id = message.chat.id
    caption_text = message.caption or ""
    username = message.from_user.username
    first_name = message.from_user.first_name
    is_group_chat = message.chat.type in ['group', 'supergroup']

    # Group chat logic: require the "toniai" trigger in caption
    if is_group_chat:
        if not caption_text.lower().startswith("toniai"):
            return
        # Strip the trigger word ("toniai") from the beginning
        trigger_len = len("toniai")
        caption_text = caption_text[trigger_len:].strip()
    else:
        # Private chat: trigger is not required, but strip it if user starts caption with it
        if caption_text.lower().startswith("toniai"):
            trigger_len = len("toniai")
            caption_text = caption_text[trigger_len:].strip()

    bot.send_chat_action(chat_id, 'typing')
    logger.info(f"Elaborazione foto da chat {chat_id} (Utente: {first_name})")

    try:
        # Download the largest photo version
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Open the image using PIL
        image = Image.open(io.BytesIO(downloaded_file))

        # Get reply context (e.g. if replying to someone else's message)
        context_text, _ = get_reply_context(message)
        prompt_text = context_text + caption_text

        # Classic mode
        response = ai_handler.generate_response(chat_id, prompt_text, first_name, user_id=user_id, image=image)

        # Failsafe: if Gemini returns empty response
        if not response or not response.strip():
            logger.warning("Gemini returned an empty response for photo.")
            response = "Scusa, non sono riuscito a elaborare una risposta."

        bot.reply_to(message, response)

    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        bot.reply_to(message, "Scusa, sto avendo problemi a elaborare questa immagine.")


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
    logger.info(f"Elaborazione messaggio da chat {chat_id} (Utente: {first_name})")

    try:
        # Get reply context
        context_text, quoted_image = get_reply_context(message)
        prompt_text = context_text + message_text

        # Classic mode
        response = ai_handler.generate_response(chat_id, prompt_text, first_name, user_id=user_id, image=quoted_image)

        # Failsafe: if Gemini returns an empty string, don't crash Telegram
        if not response or not response.strip():
            logger.warning("Gemini returned an empty response.")
            response = "Scusa, non sono riuscito a elaborare una risposta."

        bot.reply_to(message, response)

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        bot.reply_to(message,
                     "Scusa, sto avendo problemi a connettermi all'intelligenza artificiale in questo momento. Riprova più tardi.")
