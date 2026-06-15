import os
import logging
import time
from google import genai
from google.genai import types
import datetime

from config import GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE, MODEL_NAME
from user_memory import (
    save_user_memory,
    get_user_memories,
    save_group_memory,
    get_group_memories,
    delete_memory
)

logger = logging.getLogger(__name__)


def search_web(query: str) -> str:
    """Searches the web for the given query using DuckDuckGo and returns a summary of the results."""
    start = time.time()
    logger.info(f"[TOOL] search_web called with query: '{query}'")
    from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                elapsed = time.time() - start
                logger.info(f"[TOOL] search_web completed in {elapsed:.2f}s (no results)")
                return "Nessun risultato trovato sul web."
            
            output = []
            for r in results:
                title = r.get('title', 'Nessun titolo')
                link = r.get('href', '')
                body = r.get('body', 'Nessuna descrizione')
                output.append(f"Titolo: {title}\nLink: {link}\nDescrizione: {body}\n")
            elapsed = time.time() - start
            logger.info(f"[TOOL] search_web completed in {elapsed:.2f}s ({len(results)} results)")
            return "\n---\n".join(output)
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"[TOOL] search_web FAILED in {elapsed:.2f}s: {e}")
        return f"Impossibile completare la ricerca per errore tecnico: {str(e)}"


def get_current_time_context() -> str:
    """Returns a formatted string representing the current date, time, and timezone context."""
    now = datetime.datetime.now().astimezone()
    return f"[Data/Ora Corrente: {now.strftime('%d/%m/%Y %H:%M %Z')}]\n"


class GeminiHandler:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY non impostata")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = MODEL_NAME
        self.conversations = {}

        # Tracking giornaliero delle statistiche
        self.current_date = datetime.date.today()
        self.daily_calls = 0
        self.daily_prompt_tokens = 0
        self.daily_response_tokens = 0
        self.daily_total_tokens = 0

    def _check_daily_reset(self):
        today = datetime.date.today()
        if today > self.current_date:
            self.current_date = today
            self.daily_calls = 0
            self.daily_prompt_tokens = 0
            self.daily_response_tokens = 0
            self.daily_total_tokens = 0

    def get_conversation(self, chat_id):
        if chat_id not in self.conversations:
            logger.info(f"Creata nuova sessione di gruppo/chat: {chat_id}")
            
            # Recupera le memorie dal database all'inizio della conversazione
            is_group = chat_id < 0
            if is_group:
                memories_raw = get_group_memories(chat_id)
            else:
                memories_raw = get_user_memories(chat_id)
            
            system_instruction = DEFAULT_SYSTEM_MESSAGE
            # Se ci sono ricordi validi sul database, li aggiungiamo al prompt di inizio
            if "No memories found" not in memories_raw and "Error" not in memories_raw:
                system_instruction += f"\n\n[MEMORIE SALVATE IN PRECEDENZA PER QUESTA CHAT]:\n{memories_raw}\n"

            # Carica il resoconto giornaliero (profili personaggi) se disponibile
            from daily_reset import load_latest_summary
            daily_summary = load_latest_summary(chat_id)
            if daily_summary:
                system_instruction += f"\n\n{daily_summary}\n"

            self.conversations[chat_id] = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=TEMPERATURE,
                    tools=[
                        search_web,
                        save_user_memory,
                        save_group_memory,
                        delete_memory
                    ]
                )
            )
        return self.conversations[chat_id]

    def _prepare_inputs(self, chat_id, message_text, user_name, user_id):
        """Constructs contents list for Gemini input."""
        contents = []
        time_context = get_current_time_context()
        user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
        chat_info = f" nella chat {chat_id}" if chat_id is not None else ""

        if message_text:
            contents.append(f"{time_context}[{user_info} dice{chat_info}]: {message_text}")
        
        return contents

    def generate_response(self, chat_id, message_text, user_name, user_id=None, image=None):
        self._check_daily_reset()
        chat_session = self.get_conversation(chat_id)

        # Prepare inputs (multimodal or text context)
        contents = []
        if image:
            contents.append(image)

        inputs = self._prepare_inputs(chat_id, message_text, user_name, user_id)
        if inputs:
            contents.extend(inputs)
        elif image:
            # If user sent a photo without caption, add context note
            time_context = get_current_time_context()
            user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
            chat_info = f" nella chat {chat_id}" if chat_id is not None else ""
            contents.append(f"{time_context}[{user_info} ha inviato un'immagine{chat_info}]")

        try:
            history_len = len(chat_session._history) if hasattr(chat_session, '_history') else -1
            logger.info(f"[TIMING] Chat {chat_id} | User: {user_name} | History: {history_len} messages | Sending request...")
            start_time = time.time()

            response = chat_session.send_message(contents)

            elapsed = time.time() - start_time
            self.daily_calls += 1

            token_info = ""
            if response.usage_metadata:
                self.daily_prompt_tokens += response.usage_metadata.prompt_token_count
                self.daily_response_tokens += response.usage_metadata.candidates_token_count
                self.daily_total_tokens += response.usage_metadata.total_token_count
                token_info = f" | Tokens: {response.usage_metadata.prompt_token_count} in / {response.usage_metadata.candidates_token_count} out"

            logger.info(f"[TIMING] Chat {chat_id} | Response in {elapsed:.2f}s{token_info}")

            # Log if it was slow
            if elapsed > 10:
                logger.warning(f"[SLOW] Chat {chat_id} took {elapsed:.2f}s! History: {history_len} messages")

            bot_text = response.text
            if not bot_text or not bot_text.strip():
                return "Non so come rispondere a questo."

            # Failsafe: strip any accidental speaker prefixes
            import re
            bot_text = re.sub(r'^\[[^\]]+\]:\s*', '', bot_text)
            bot_text = re.sub(r'^\[[^\]]+ dice\]:\s*', '', bot_text)
            # Strip leaked function calls (e.g. @save_user_memory(...))
            bot_text = re.sub(r'@?\w+\([^)]*\)\s*', '', bot_text)
            return bot_text.strip()

        except Exception as e:
            elapsed = time.time() - start_time if 'start_time' in locals() else -1
            logger.error(f"Errore generazione risposta da Gemini (after {elapsed:.2f}s): {e}")
            return "Scusa, ho avuto un problema tecnico con l'IA."

    def get_stats(self):
        self._check_daily_reset()
        return {
            "calls": self.daily_calls,
            "prompt_tokens": self.daily_prompt_tokens,
            "response_tokens": self.daily_response_tokens,
            "total_tokens": self.daily_total_tokens,
            "model": self.model_name,
            "date": self.current_date.strftime("%d/%m/%Y")
        }