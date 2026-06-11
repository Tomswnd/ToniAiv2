import re
import time
import logging
from handlers import bot, ai_handler

logger = logging.getLogger(__name__)


def clean_bot_text(text):
    """Strip accidental speaker prefixes from bot responses."""
    text = re.sub(r'^\[[^\]]+\]:\s*', '', text)
    text = re.sub(r'^\[[^\]]+ dice\]:\s*', '', text)
    return text.strip()


def send_streaming_response(message, chat_id, prompt_text, first_name, image=None):
    """
    Send a streaming response: posts a placeholder, then edits it
    progressively as Gemini generates tokens.
    Returns the final response text.
    """
    # Send initial placeholder as a reply
    sent_msg = bot.reply_to(message, "💭")

    last_update_time = time.time()
    last_text_length = 0
    final_text = ""
    MIN_UPDATE_INTERVAL = 1.5   # seconds between edits (Telegram rate-limit safe)
    MIN_CHARS_DELTA = 60        # minimum new chars before editing

    try:
        for accumulated_text in ai_handler.generate_response_stream(
            chat_id, prompt_text, first_name, user_id=message.from_user.id, image=image
        ):
            final_text = accumulated_text
            now = time.time()
            text_delta = len(accumulated_text) - last_text_length

            # Update message periodically to stay within Telegram rate limits
            if now - last_update_time >= MIN_UPDATE_INTERVAL and text_delta >= MIN_CHARS_DELTA:
                try:
                    display_text = clean_bot_text(accumulated_text)
                    if display_text:
                        bot.edit_message_text(
                            display_text + " ▌",
                            chat_id=chat_id,
                            message_id=sent_msg.message_id
                        )
                    last_update_time = now
                    last_text_length = len(accumulated_text)
                except Exception as e:
                    logger.warning(f"Errore edit streaming: {e}")

        # Final cleanup and edit (without cursor)
        final_text = clean_bot_text(final_text)
        if not final_text:
            final_text = "Non so come rispondere a questo."

        try:
            bot.edit_message_text(
                final_text,
                chat_id=chat_id,
                message_id=sent_msg.message_id
            )
        except Exception as e:
            logger.warning(f"Errore edit finale streaming: {e}")

        return final_text

    except Exception as e:
        logger.error(f"Errore streaming response: {e}")
        error_text = "Scusa, ho avuto un problema tecnico con l'IA."
        try:
            bot.edit_message_text(
                error_text,
                chat_id=chat_id,
                message_id=sent_msg.message_id
            )
        except Exception:
            pass
        return error_text
