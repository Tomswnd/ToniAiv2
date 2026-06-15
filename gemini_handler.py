import os
import logging
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
    logger.info(f"Esecuzione ricerca web per: '{query}'")
    from duckduckgo_search import DDGS
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    def _do_search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=3))

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            results = future.result(timeout=3)

            if not results:
                return "Nessun risultato trovato sul web."
            
            output = []
            for r in results:
                title = r.get('title', 'Nessun titolo')
                link = r.get('href', '')
                body = r.get('body', 'Nessuna descrizione')
                output.append(f"Titolo: {title}\nLink: {link}\nDescrizione: {body}\n")
            return "\n---\n".join(output)
    except TimeoutError:
        logger.warning(f"Ricerca web per '{query}' scaduta dopo 3 secondi")
        return "La ricerca web ha impiegato troppo tempo ed è stata annullata."
    except Exception as e:
        logger.error(f"Errore durante la ricerca DuckDuckGo: {e}")
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
            logger.info(f"Invio richiesta a Gemini per chat {chat_id} da {user_name}")
            response = chat_session.send_message(contents)
            self.daily_calls += 1

            if response.usage_metadata:
                self.daily_prompt_tokens += response.usage_metadata.prompt_token_count
                self.daily_response_tokens += response.usage_metadata.candidates_token_count
                self.daily_total_tokens += response.usage_metadata.total_token_count

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
            logger.error(f"Errore generazione risposta da Gemini: {e}")
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