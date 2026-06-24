import os
import logging
import time
import re
import datetime
import threading

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE,
    MODEL_NAME, RESPONSE_TIME_THRESHOLD, SHOW_TOOL_USAGE
)
from group_config import get_group_prompt

logger = logging.getLogger(__name__)

# Directory per i log giornalieri dei messaggi
CHAT_LOGS_DIR = os.path.join("data", "chat_logs")
os.makedirs(CHAT_LOGS_DIR, exist_ok=True)


# Context per memorizzare chat_id e message_id su base thread (per aggiornamento stato)
thread_context = threading.local()


def update_tool_status(text: str):
    """Invia o modifica un messaggio su Telegram per mostrare lo stato di avanzamento dei tool (senza emoji)."""
    if not SHOW_TOOL_USAGE:
        return

    chat_id = getattr(thread_context, 'chat_id', None)
    reply_to_message_id = getattr(thread_context, 'reply_to_message_id', None)

    if not chat_id or not reply_to_message_id:
        return

    status_message_id = getattr(thread_context, 'status_message_id', None)

    # Importazione dinamica del bot per evitare import circolari
    from handlers import bot

    try:
        if status_message_id is None:
            msg = bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id
            )
            thread_context.status_message_id = msg.message_id
        else:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=text
            )
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento dello stato su Telegram: {e}")


# ---------------------------------------------------------------------------
# Ricerca e Scraping Web
# ---------------------------------------------------------------------------
def search_web(query: str) -> str:
    """Searches the web for the given query using DuckDuckGo. Returns search results AND the full
    text content of the first relevant result, to ensure accurate and detailed answers."""
    logger.info(f"Esecuzione ricerca web per: '{query}'")
    update_tool_status(f"Ricerca su Internet in corso per: \"{query}\"...")

    from ddgs import DDGS
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    def _do_search():
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=5))

    # Step 1: Esegui la ricerca
    results = None
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            results = future.result(timeout=4)
    except TimeoutError:
        logger.warning(f"Ricerca web per '{query}' scaduta")
        return "La ricerca web ha impiegato troppo tempo ed è stata annullata."
    except Exception as e:
        logger.error(f"Errore durante la ricerca DuckDuckGo: {e}")
        return f"Impossibile completare la ricerca per errore tecnico: {str(e)}"

    if not results:
        return "Nessun risultato trovato sul web."

    # Step 2: Costruisci lo snippet dei risultati
    output = []
    for r in results:
        title = r.get('title', 'Nessun titolo')
        link = r.get('href', '')
        body = r.get('body', 'Nessuna descrizione')
        output.append(f"Titolo: {title}\nLink: {link}\nDescrizione: {body}\n")
    results_text = "\n---\n".join(output)

    # Step 3: Leggi automaticamente la pagina del primo risultato
    first_url = results[0].get('href', '')
    if not first_url:
        logger.warning("Nessun URL disponibile nel primo risultato, restituzione solo snippet.")
        return results_text

    logger.info(f"Lettura automatica della prima pagina: {first_url}")
    update_tool_status(f"Lettura della pagina web: {first_url}...")
    try:
        page_content = fetch_webpage(first_url)
        logger.info(f"Pagina {first_url} letta con successo ({len(page_content)} caratteri)")
    except Exception as e:
        logger.error(f"Errore nella lettura automatica di {first_url}: {e}")
        page_content = f"Impossibile leggere la pagina ({str(e)})"

    return (
        f"=== RISULTATI DI RICERCA ===\n{results_text}\n\n"
        f"=== CONTENUTO DELLA PAGINA PIU' RILEVANTE ({first_url}) ===\n{page_content}"
    )


def fetch_webpage(url: str) -> str:
    """Fetches the main text content from a web page URL to get detailed context."""
    logger.info(f"Esecuzione recupero pagina web per: '{url}'")
    update_tool_status(f"Lettura della pagina web: {url}...")

    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("Librerie 'requests' o 'beautifulsoup4' non installate.")
        return "Errore di configurazione del sistema: mancano le librerie per leggere le pagine web."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code != 200:
            return f"Impossibile caricare la pagina. Codice di stato HTTP: {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')

        # Rimuove script, stili e tag strutturali irrilevanti per il testo principale
        for element in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
            element.decompose()

        text = soup.get_text(separator=' ')

        # Pulisce gli spazi vuoti multipli
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        # Tronca a 6000 caratteri per evitare di superare il limite di token di Gemini
        max_chars = 6000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Testo troncato per motivi di spazio/token]"

        if not text.strip():
            return "La pagina web non contiene testo leggibile."

        return text
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout durante il recupero di {url}")
        return "Tempo di attesa scaduto durante il caricamento della pagina."
    except Exception as e:
        logger.error(f"Errore nel recupero di {url}: {e}")
        return f"Errore nel caricamento della pagina: {str(e)}"


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

        # Cronologia in RAM: {chat_id: list[types.Content]}
        self.conversations: dict[int, list[types.Content]] = {}

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

    def _prepare_user_content(self, chat_id, message_text, user_name, user_id, image=None) -> list[types.Part]:
        """Prepara il contenuto del messaggio utente per Gemini."""
        parts = []

        if image:
            import io
            img_byte_arr = io.BytesIO()
            fmt = image.format if image.format else 'JPEG'
            image.save(img_byte_arr, format=fmt)
            image_bytes = img_byte_arr.getvalue()
            mime_type = f"image/{fmt.lower()}"
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        time_context = get_current_time_context()
        user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
        chat_info = f" nella chat {chat_id}" if chat_id is not None else ""

        if message_text:
            parts.append(types.Part.from_text(text=f"{time_context}[{user_info} dice{chat_info}]: {message_text}"))
        elif image:
            parts.append(types.Part.from_text(text=f"{time_context}[{user_info} ha inviato un'immagine{chat_info}]"))

        return parts

    def generate_response(self, chat_id, message_text, user_name, user_id=None, image=None):
        self._check_daily_reset()

        # Prepara il contenuto utente
        user_parts = self._prepare_user_content(chat_id, message_text, user_name, user_id, image)
        if not user_parts:
            return "Non so come rispondere a questo."

        # Aggiungi il messaggio utente alla cronologia
        history = self._get_history(chat_id)
        history.append(types.Content(role="user", parts=user_parts))

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
                    tools=[search_web, fetch_webpage],
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
            history.append(types.Content(role="model", parts=[types.Part.from_text(text=bot_text)]))

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
            if history and history[-1].role == "user":
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