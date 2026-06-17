import os
import json
import logging
import datetime

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, MODEL_NAME, DAILY_RESET_NOTIFY

logger = logging.getLogger(__name__)

SUMMARIES_DIR = os.path.join("data", "daily_summaries")

# ---------------------------------------------------------------------------
# Runtime notification toggle (defaults to config value, changeable via bot)
# ---------------------------------------------------------------------------
_notify_override = None


def set_notify(enabled):
    """Toggle notification on/off at runtime."""
    global _notify_override
    _notify_override = enabled


def is_notify_enabled():
    """Check if notification is currently enabled."""
    if _notify_override is not None:
        return _notify_override
    return DAILY_RESET_NOTIFY


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = (
    "[SYSTEM TASK — DO NOT REPLY TO USERS, DO NOT USE ANY TOOL]\n\n"
    "Generate a COMPACT memory file of this chat. Be extremely concise — use short phrases, "
    "abbreviations, no filler words. Every token counts.\n\n"
    "Format:\n"
    "[MEM]\n"
    "USERS:\n"
    "- Name: key traits, interests, habits, gags (comma-separated, no sentences)\n"
    "GROUP: one-line dynamic summary\n"
    "TONE: how to interact with this group\n\n"
    "Rules:\n"
    "- MAX 1500 characters total\n"
    "- Use commas not sentences\n"
    "- Only genuinely useful/memorable facts\n"
    "- Skip trivial info\n"
    "- Merge previous memories with new observations\n"
    "- If no meaningful interactions, keep previous memories as-is but still compress them"
)

DIFF_PROMPT_TEMPLATE = (
    "[ISTRUZIONE DI SISTEMA — COMPITO SPECIALE]\n\n"
    "Confronta questi due resoconti di un gruppo Telegram e genera un breve riassunto "
    "delle DIFFERENZE. Evidenzia SOLO ciò che è stato aggiunto o modificato rispetto "
    "al resoconto precedente.\n\n"
    "RESOCONTO PRECEDENTE:\n{previous}\n\n"
    "RESOCONTO ATTUALE:\n{current}\n\n"
    "Genera un messaggio breve e leggibile per Telegram (usa emoji) con questo formato:\n"
    "📋 Aggiornamento Memoria Giornaliera\n\n"
    "🆕 Novità:\n"
    "- (nuove informazioni scoperte oggi)\n\n"
    "✏️ Aggiornamenti:\n"
    "- (informazioni modificate/aggiornate rispetto a ieri)\n\n"
    "Se non ci sono differenze significative, scrivi semplicemente che la memoria è stata "
    "confermata senza variazioni rilevanti."
)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------
def _get_chat_dir(chat_id):
    """Returns (and creates) the directory for a specific chat's summaries."""
    chat_dir = os.path.join(SUMMARIES_DIR, str(chat_id))
    os.makedirs(chat_dir, exist_ok=True)
    return chat_dir


def save_summary(chat_id, summary_text):
    """Saves the summary to disk: a dated copy (history) and latest.json."""
    chat_dir = _get_chat_dir(chat_id)
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()

    data = {
        "chat_id": chat_id,
        "date": today,
        "summary": summary_text,
        "generated_at": now,
    }

    # Dated copy for history
    dated_path = os.path.join(chat_dir, f"{today}.json")
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Overwrite latest pointer
    latest_path = os.path.join(chat_dir, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Summary saved for chat {chat_id} → {dated_path}")
    return dated_path


def load_latest_summary(chat_id):
    """Loads the most recent summary for a chat.  Returns the text or None."""
    latest_path = os.path.join(_get_chat_dir(chat_id), "latest.json")
    if not os.path.exists(latest_path):
        return None
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("summary")
    except Exception as e:
        logger.error(f"Error loading latest summary for chat {chat_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------
def generate_summary(chat_session):
    """Asks the *existing* chat session to produce a structured summary."""
    try:
        response = chat_session.send_message(SUMMARY_PROMPT)
        if response and response.text:
            return response.text.strip()
        return None
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return None


def generate_diff_report(current_summary, previous_summary):
    """One-shot Gemini call that compares two summaries and returns a diff."""
    if not previous_summary:
        return (
            "📋 Aggiornamento Memoria Giornaliera\n\n"
            "🆕 Primo resoconto generato! La memoria del gruppo è stata inizializzata."
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = DIFF_PROMPT_TEMPLATE.format(
            previous=previous_summary,
            current=current_summary,
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        )
        if response and response.text:
            return response.text.strip()
        return "📋 Memoria giornaliera aggiornata."
    except Exception as e:
        logger.error(f"Error generating diff report: {e}")
        return "📋 Memoria giornaliera aggiornata."


# ---------------------------------------------------------------------------
# Core reset logic
# ---------------------------------------------------------------------------
def reset_single_chat(chat_id, gemini_handler, bot=None, notify=None):
    """
    Resets a single chat: generate summary → save → optionally notify → clear RAM.

    Returns the generated summary text, or None on failure.
    """
    if notify is None:
        notify = is_notify_enabled()

    chat_session = gemini_handler.conversations.get(chat_id)
    if not chat_session:
        return None

    # Previous summary (before we overwrite it)
    previous_summary = load_latest_summary(chat_id)

    # Generate new summary from current conversation context
    logger.info(f"Generating summary for chat {chat_id}…")
    summary = generate_summary(chat_session)

    if summary:
        save_summary(chat_id, summary)

        # Diff notification
        if notify and bot:
            try:
                diff_report = generate_diff_report(summary, previous_summary)
                bot.send_message(chat_id, diff_report, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error sending diff notification to {chat_id}: {e}")
                # Retry without Markdown in case of formatting issues
                try:
                    bot.send_message(chat_id, diff_report)
                except Exception:
                    pass
    else:
        logger.warning(f"Failed to generate summary for chat {chat_id}")

    # Clear the conversation from RAM
    del gemini_handler.conversations[chat_id]
    logger.info(f"Conversation {chat_id} reset successfully.")
    return summary


def perform_daily_reset(gemini_handler, bot=None):
    """
    Iterates over ALL active conversations and resets each one.
    Called automatically by the scheduler every day.
    """
    chat_ids = list(gemini_handler.conversations.keys())

    if not chat_ids:
        logger.info("Daily reset: no active conversations to process.")
        return

    logger.info(f"Daily reset: processing {len(chat_ids)} conversation(s)…")

    for chat_id in chat_ids:
        try:
            reset_single_chat(chat_id, gemini_handler, bot)
        except Exception as e:
            logger.error(f"Error during daily reset for chat {chat_id}: {e}")

    logger.info("Daily reset completed.")
