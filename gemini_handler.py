import os
import logging
import time
import re
import datetime

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE,
    MODEL_NAME, RESPONSE_TIME_THRESHOLD
)
from group_config import get_group_prompt

logger = logging.getLogger(__name__)

# Directory per i log giornalieri dei messaggi
CHAT_LOGS_DIR = os.path.join("data", "chat_logs")
os.makedirs(CHAT_LOGS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Ricerca web (invariata)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_current_time_context() -> str:
    """Returns a formatted string representing the current date, time, and timezone context."""
    now = datetime.datetime.now().astimezone()
    return f"[Data/Ora Corrente: {now.strftime('%d/%m/%Y %H:%M %Z')}]\n"


def log_message_to_file(chat_id: int, role: str, text: str):
    """Scrive un messaggio nel file di log giornaliero della chat.

    Questo log viene usato durante il reset giornaliero per generare
    il riassunto completo della giornata, anche dopo che la cronologia
    in RAM è stata tagliata.
    """
    log_path = os.path.join(CHAT_LOGS_DIR, f"{chat_id}_today.txt")
    try:
        timestamp = datetime.datetime.now().strftime("%H:%M")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {role}: {text}\n")
    except Exception as e:
        logger.error(f"Errore scrittura log per chat {chat_id}: {e}")


def get_today_log(chat_id: int) -> str | None:
    """Legge il log giornaliero della chat. Restituisce None se vuoto/inesistente."""
    log_path = os.path.join(CHAT_LOGS_DIR, f"{chat_id}_today.txt")
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content if content else None
    except Exception:
        return None


def clear_today_log(chat_id: int):
    """Svuota il file di log giornaliero della chat."""
    log_path = os.path.join(CHAT_LOGS_DIR, f"{chat_id}_today.txt")
    try:
        if os.path.exists(log_path):
            os.remove(log_path)
    except Exception as e:
        logger.error(f"Errore cancellazione log per chat {chat_id}: {e}")


def delete_chat_data(chat_id: int):
    """Elimina tutti i dati su disco di una chat (log + summary)."""
    clear_today_log(chat_id)
    # Rimuovi anche i riassunti giornalieri
    from daily_reset import _get_chat_dir
    import shutil
    chat_dir = _get_chat_dir(chat_id)
    if os.path.exists(chat_dir):
        try:
            shutil.rmtree(chat_dir)
            logger.info(f"Dati chat {chat_id} eliminati da disco.")
        except Exception as e:
            logger.error(f"Errore eliminazione dati chat {chat_id}: {e}")


# ---------------------------------------------------------------------------
# GeminiHandler — gestione manuale della cronologia
# ---------------------------------------------------------------------------
class GeminiHandler:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY non impostata")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = MODEL_NAME

        # Cronologia in RAM: {chat_id: [{"role": "user"|"model", "parts": [...]}, ...]}
        self.conversations: dict[int, list[dict]] = {}

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

    def _build_system_instruction(self, chat_id: int) -> str:
        """Costruisce il prompt di sistema completo per una chat, includendo:
        1. Prompt personalizzato del gruppo (se presente) oppure prompt default
        2. Riassunto giornaliero precedente (se presente)
        """
        # 1. Prompt base: personalizzato o default
        custom_prompt = get_group_prompt(chat_id)
        if custom_prompt:
            system_instruction = DEFAULT_SYSTEM_MESSAGE + f"\n\n[ISTRUZIONI PERSONALIZZATE PER QUESTO GRUPPO]:\n{custom_prompt}\n"
        else:
            system_instruction = DEFAULT_SYSTEM_MESSAGE

        # 2. Riassunto giornaliero precedente
        from daily_reset import load_latest_summary
        daily_summary = load_latest_summary(chat_id)
        if daily_summary:
            system_instruction += f"\n\n{daily_summary}\n"

        return system_instruction

    def _get_history(self, chat_id: int) -> list[dict]:
        """Restituisce la cronologia della chat, creandola se non esiste."""
        if chat_id not in self.conversations:
            logger.info(f"Creata nuova sessione di gruppo/chat: {chat_id}")
            self.conversations[chat_id] = []
        return self.conversations[chat_id]

    def _trim_history(self, chat_id: int):
        """Taglia la prima metà della cronologia di una chat per ridurre i token.

        Viene chiamato automaticamente quando il tempo di risposta di Gemini
        supera RESPONSE_TIME_THRESHOLD secondi.
        """
        history = self.conversations.get(chat_id, [])
        if len(history) <= 2:
            return  # Non tagliare se ci sono solo 1-2 messaggi

        half = len(history) // 2
        trimmed = history[half:]
        self.conversations[chat_id] = trimmed
        logger.info(
            f"Chat {chat_id}: cronologia tagliata da {len(history)} a {len(trimmed)} messaggi "
            f"(tempo di risposta > {RESPONSE_TIME_THRESHOLD}s)"
        )

    def _prepare_user_content(self, chat_id, message_text, user_name, user_id, image=None):
        """Prepara il contenuto del messaggio utente per Gemini."""
        parts = []

        if image:
            parts.append(image)

        time_context = get_current_time_context()
        user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
        chat_info = f" nella chat {chat_id}" if chat_id is not None else ""

        if message_text:
            parts.append(f"{time_context}[{user_info} dice{chat_info}]: {message_text}")
        elif image:
            parts.append(f"{time_context}[{user_info} ha inviato un'immagine{chat_info}]")

        return parts

    def generate_response(self, chat_id, message_text, user_name, user_id=None, image=None):
        self._check_daily_reset()

        # Prepara il contenuto utente
        user_parts = self._prepare_user_content(chat_id, message_text, user_name, user_id, image)
        if not user_parts:
            return "Non so come rispondere a questo."

        # Aggiungi il messaggio utente alla cronologia
        history = self._get_history(chat_id)
        history.append({"role": "user", "parts": user_parts})

        # Log nel file giornaliero
        log_text = message_text or "[immagine]"
        log_message_to_file(chat_id, user_name, log_text)

        # Costruisci il prompt di sistema
        system_instruction = self._build_system_instruction(chat_id)

        try:
            logger.info(f"Invio richiesta a Gemini per chat {chat_id} da {user_name}")

            # Misura il tempo di risposta
            start_time = time.time()

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=TEMPERATURE,
                    tools=[search_web],
                ),
            )

            elapsed = time.time() - start_time
            self.daily_calls += 1

            if response.usage_metadata:
                self.daily_prompt_tokens += response.usage_metadata.prompt_token_count
                self.daily_response_tokens += response.usage_metadata.candidates_token_count
                self.daily_total_tokens += response.usage_metadata.total_token_count

            bot_text = response.text
            if not bot_text or not bot_text.strip():
                return "Non so come rispondere a questo."

            # Failsafe: strip any accidental speaker prefixes
            bot_text = re.sub(r'^\[[^\]]+\]:\s*', '', bot_text)
            bot_text = re.sub(r'^\[[^\]]+ dice\]:\s*', '', bot_text)
            # Strip leaked function calls (e.g. @save_user_memory(...))
            bot_text = re.sub(r'@?\w+\([^)]*\)\s*', '', bot_text)
            bot_text = bot_text.strip()

            # Aggiungi la risposta del bot alla cronologia
            history.append({"role": "model", "parts": [bot_text]})

            # Log risposta nel file giornaliero
            log_message_to_file(chat_id, "ToniAI", bot_text)

            # Controlla se il tempo di risposta ha superato la soglia
            if elapsed > RESPONSE_TIME_THRESHOLD:
                logger.warning(
                    f"Chat {chat_id}: risposta in {elapsed:.1f}s (>{RESPONSE_TIME_THRESHOLD}s), "
                    f"taglio cronologia…"
                )
                self._trim_history(chat_id)

            return bot_text

        except Exception as e:
            logger.error(f"Errore generazione risposta da Gemini: {e}")
            # Rimuovi il messaggio utente dalla cronologia se la chiamata è fallita
            if history and history[-1]["role"] == "user":
                history.pop()
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