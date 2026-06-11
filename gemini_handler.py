import os
import logging
import zoneinfo
from google import genai
from google.genai import types
import datetime
from chat_logger import chat_logger

from config import GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE, MODEL_NAME

logger = logging.getLogger(__name__)


def search_web(query: str) -> str:
    """Searches the web for the given query using DuckDuckGo and returns a summary of the results.

    Args:
        query: The search query to look up on the web.
    """
    from duckduckgo_search import DDGS
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Esecuzione ricerca web gratuita per: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "Nessun risultato trovato sul web."
            
            output = []
            for r in results:
                title = r.get('title', 'Nessun titolo')
                link = r.get('href', '')
                body = r.get('body', 'Nessuna descrizione')
                output.append(f"Titolo: {title}\nLink: {link}\nDescrizione: {body}\n")
            return "\n---\n".join(output)
    except Exception as e:
        logger.error(f"Errore durante la ricerca DuckDuckGo: {e}")
        return f"Impossibile completare la ricerca per errore tecnico: {str(e)}"


def get_current_time_context() -> str:
    """Returns a formatted string representing the current date, time, and timezone context."""
    import datetime
    now = datetime.datetime.now().astimezone()
    tz_name = now.tzname() or ""
    offset = now.strftime("%z")
    
    # Format timezone offset from e.g. +0200 to UTC+02:00
    if len(offset) == 5:
        offset_formatted = f"UTC{offset[:3]}:{offset[3:]}"
    else:
        offset_formatted = "UTC"
        
    tz_info = f"{tz_name}, {offset_formatted}" if tz_name else offset_formatted
    current_time = now.strftime("%d/%m/%Y %H:%M")
    return f"[Data/Ora Corrente: {current_time} ({tz_info})]\n"


class GeminiHandler:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY non impostata")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = MODEL_NAME
        self.conversations = {}

        # Impostiamo il fuso orario di Google (Pacific Time)
        self.google_tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        self.current_date = datetime.datetime.now(self.google_tz).date()

        # Tracking giornaliero basato sull'orario della California
        self.current_pt_date = datetime.datetime.now(self.google_tz).date()
        self.daily_calls = 0
        self.daily_prompt_tokens = 0
        self.daily_response_tokens = 0
        self.daily_total_tokens = 0

    def _check_daily_reset(self):
        now = datetime.datetime.now(self.google_tz)
        if now.date() > self.current_date:
            self.current_date = now.date()
            self.daily_calls = 0
            self.daily_prompt_tokens = 0
            self.daily_response_tokens = 0
            self.daily_total_tokens = 0

            # Svuota tutte le sessioni dalla RAM
            # self.conversations.clear()

            # Svuota l'intera cartella dei file di log
            # try:
            #     # chat_logger.delete_all_logs()
            # except AttributeError:
            #     pass

            # logger.info("Reset giornaliero eseguito: quote, memoria e cartella log azzerati.")

    def get_conversation(self, chat_id):
        # La chiave ora è l'ID della chat, non dell'utente
        if chat_id not in self.conversations:
            logger.info(f"Creata nuova sessione di gruppo/chat: {chat_id}")
            self.conversations[chat_id] = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=DEFAULT_SYSTEM_MESSAGE,
                    temperature=TEMPERATURE,
                    tools=[search_web]
                )
            )
        return self.conversations[chat_id]
    def reset_conversation(self, user_id):
        """Reset a user's conversation history by creating a new chat session"""
        if user_id in self.conversations:
            del self.conversations[user_id]

        # Initialize a fresh chat
        self.get_conversation(user_id)
        return "Conversation history has been successfully reset."

    def generate_response(self, chat_id, message_text, user_name, image=None):
        self._check_daily_reset()

        # Passiamo il chat_id
        chat_session = self.get_conversation(chat_id)

        # Build contents list for multimodal input
        contents = []
        if image:
            contents.append(image)

        time_context = get_current_time_context()

        if message_text:
            formatted_message = f"{time_context}[{user_name} dice]: {message_text}"
            contents.append(formatted_message)
        elif image:
            # If user sent a photo without caption, add a context note
            formatted_message = f"{time_context}[{user_name} ha inviato un'immagine]"
            contents.append(formatted_message)
        else:
            formatted_message = ""

        try:
            logger.info(f"Invio richiesta a Gemini per chat {chat_id} da {user_name}")
            if image:
                response = chat_session.send_message(contents)
            else:
                response = chat_session.send_message(formatted_message)
            self.daily_calls += 1

            if response.usage_metadata:
                self.daily_prompt_tokens += response.usage_metadata.prompt_token_count
                self.daily_response_tokens += response.usage_metadata.candidates_token_count
                self.daily_total_tokens += response.usage_metadata.total_token_count

            bot_text = response.text
            if not bot_text or bot_text.strip() == "":
                return "Non so come rispondere a questo."

            # Failsafe: strip any accidental speaker prefixes (e.g. "[ToniAI dice]:", "[Tommaso dice]:")
            import re
            bot_text = re.sub(r'^\[[^\]]+\]:\s*', '', bot_text)
            bot_text = re.sub(r'^\[[^\]]+ dice\]:\s*', '', bot_text)

            return bot_text.strip()

        except Exception as e:
            logger.error(f"Errore generazione risposta da Gemini: {e}")
            return "Scusa, ho avuto un problema tecnico con l'IA."

    def generate_response_stream(self, chat_id, message_text, user_name, image=None):
        """Generator that yields accumulated response text as it streams from Gemini."""
        self._check_daily_reset()

        chat_session = self.get_conversation(chat_id)

        # Build contents list for multimodal input
        contents = []
        if image:
            contents.append(image)

        time_context = get_current_time_context()

        if message_text:
            formatted_message = f"{time_context}[{user_name} dice]: {message_text}"
            contents.append(formatted_message)
        elif image:
            formatted_message = f"{time_context}[{user_name} ha inviato un'immagine]"
            contents.append(formatted_message)
        else:
            formatted_message = ""

        try:
            logger.info(f"Invio richiesta streaming a Gemini per chat {chat_id} da {user_name}")
            if image:
                stream = chat_session.send_message_stream(contents)
            else:
                stream = chat_session.send_message_stream(formatted_message)

            self.daily_calls += 1
            accumulated_text = ""
            last_usage = None

            for chunk in stream:
                if chunk.text:
                    accumulated_text += chunk.text
                    yield accumulated_text
                if chunk.usage_metadata:
                    last_usage = chunk.usage_metadata

            # Track usage from the final metadata only (to avoid double-counting)
            if last_usage:
                self.daily_prompt_tokens += getattr(last_usage, 'prompt_token_count', 0) or 0
                self.daily_response_tokens += getattr(last_usage, 'candidates_token_count', 0) or 0
                self.daily_total_tokens += getattr(last_usage, 'total_token_count', 0) or 0

            if not accumulated_text.strip():
                yield "Non so come rispondere a questo."

        except Exception as e:
            logger.error(f"Errore generazione risposta streaming da Gemini: {e}")
            yield "Scusa, ho avuto un problema tecnico con l'IA."

    def get_stats(self):
        self._check_daily_reset()
        return {
            "calls": self.daily_calls,
            "prompt_tokens": self.daily_prompt_tokens,
            "response_tokens": self.daily_response_tokens,
            "total_tokens": self.daily_total_tokens,
            "model": self.model_name,
            "date": self.current_pt_date.strftime("%d/%m/%Y") # Data del Pacifico
        }