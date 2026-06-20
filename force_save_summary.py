#!/usr/bin/env python3
"""
One-off script to force-generate a summary for a specific chat.
Uses the today log file and previous summary instead of user_memory DB.

Usage:
    # Inside the running container:
    docker exec -it toniai_bot python force_save_summary.py <chat_id>

    # Or locally (if the bot is running locally):
    python force_save_summary.py <chat_id>

To find your chat_id, use /apistats or check the bot logs.
"""
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reuse project modules
from config import GEMINI_API_KEY, MODEL_NAME
from google import genai
from google.genai import types
from gemini_handler import get_today_log, clear_today_log
from daily_reset import load_latest_summary, save_summary, SUMMARY_PROMPT


def main():
    if len(sys.argv) < 2:
        print("Uso: python force_save_summary.py <chat_id>")
        print("Esempio: python force_save_summary.py -100123456789")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    logger.info(f"Generating summary for chat {chat_id}…")

    # Load previous summary (if any)
    previous_summary = load_latest_summary(chat_id)

    # Load today's chat log
    today_log = get_today_log(chat_id)

    # Build the one-shot prompt
    prompt = ""
    if previous_summary:
        prompt += f"[RESOCONTO PRECEDENTE]:\n{previous_summary}\n\n"
    if today_log:
        prompt += f"[LOG CHAT DI OGGI]:\n{today_log}\n\n"

    if not previous_summary and not today_log:
        logger.error("Nessun dato disponibile (né resoconto precedente né log di oggi).")
        sys.exit(1)

    prompt += SUMMARY_PROMPT

    # One-shot Gemini call
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3),
    )

    if not response or not response.text:
        logger.error("Gemini returned empty response!")
        sys.exit(1)

    summary = response.text.strip()

    # Save using daily_reset's save_summary
    save_summary(chat_id, summary)
    logger.info(f"✅ Summary saved for chat {chat_id}")

    # Clear the today log after saving
    clear_today_log(chat_id)
    logger.info(f"🧹 Today log cleared for chat {chat_id}")

    print("\n" + "=" * 60)
    print(summary)
    print("=" * 60)


if __name__ == "__main__":
    main()
