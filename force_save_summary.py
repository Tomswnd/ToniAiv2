#!/usr/bin/env python3
"""
One-off script to force-generate a summary for a specific chat.
Run BEFORE redeploying with the new code to preserve conversation context.

Usage:
    # Inside the running container:
    docker exec -it toniai_bot python force_save_summary.py <chat_id>

    # Or locally (if the bot is running locally):
    python force_save_summary.py <chat_id>

To find your chat_id, use /apistats or check the bot logs.
"""
import sys
import os
import json
import logging
import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reuse project modules
from config import GEMINI_API_KEY, MODEL_NAME
from google import genai
from google.genai import types

SUMMARIES_DIR = os.path.join("data", "daily_summaries")

SUMMARY_PROMPT = (
    "[ISTRUZIONE DI SISTEMA — COMPITO SPECIALE, NON RISPONDERE AGLI UTENTI, NON USARE ALCUN TOOL]\n\n"
    "Devi generare un resoconto completo e strutturato di tutti gli utenti/personaggi che hanno "
    "interagito in questa chat, basandoti sulle memorie disponibili.\n\n"
    "Il formato DEVE essere ESATTAMENTE questo:\n\n"
    "[SYSTEM MEMORY: GRUPPO TELEGRAM]\n\n"
    "1. PROFILI UTENTI:\n"
    "*   Nome: Ruolo/Tipo. Descrizione dettagliata della personalità, interessi, comportamento "
    "tipico, abitudini, gag ricorrenti, opinioni note.\n\n"
    "2. DINAMICHE DI GRUPPO:\n"
    "*   Natura della Chat, Registro Conflitti, Stile di Interazione.\n\n"
    "3. PROTOCOLLO OPERATIVO:\n"
    "*   Regole su come interagire con ciascun utente.\n\n"
    "Sii il più dettagliato e specifico possibile."
)


def main():
    if len(sys.argv) < 2:
        print("Uso: python force_save_summary.py <chat_id>")
        print("Esempio: python force_save_summary.py -100123456789")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    logger.info(f"Generating summary for chat {chat_id}…")

    # Load existing memories from DB to give Gemini context
    from user_memory import get_group_memories, get_user_memories
    if chat_id < 0:
        memories = get_group_memories(chat_id)
    else:
        memories = get_user_memories(chat_id)

    # Build a one-shot prompt with memories as context
    prompt = ""
    if "No memories found" not in memories and "Error" not in memories:
        prompt += f"[MEMORIE SALVATE PER QUESTA CHAT]:\n{memories}\n\n"
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

    # Save to disk
    chat_dir = os.path.join(SUMMARIES_DIR, str(chat_id))
    os.makedirs(chat_dir, exist_ok=True)

    today = datetime.date.today().isoformat()
    data = {
        "chat_id": chat_id,
        "date": today,
        "summary": summary,
        "generated_at": datetime.datetime.now().isoformat(),
    }

    for filename in [f"{today}.json", "latest.json"]:
        path = os.path.join(chat_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ Summary saved to {chat_dir}/")
    print("\n" + "=" * 60)
    print(summary)
    print("=" * 60)


if __name__ == "__main__":
    main()
