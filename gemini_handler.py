import os
import logging
import zoneinfo
from google import genai
from google.genai import types
import datetime
from chat_logger import chat_logger

from config import GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE, MODEL_NAME

logger = logging.getLogger(__name__)


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

    def generate_response(self, chat_id, message_text, user_name):
        self._check_daily_reset()

        # Passiamo il chat_id
        chat_session = self.get_conversation(chat_id)

        # TRUCCO: Inseriamo il nome dell'utente nel messaggio inviato a Gemini
        # Così il bot saprà sempre "chi" sta parlando nel gruppo.
        formatted_message = f"[{user_name} dice]: {message_text}"

        try:
            logger.info(f"Invio richiesta a Gemini per chat {chat_id} da {user_name}")
            response = chat_session.send_message(formatted_message)
            self.daily_calls += 1

            if response.usage_metadata:
                self.daily_prompt_tokens += response.usage_metadata.prompt_token_count
                self.daily_response_tokens += response.usage_metadata.candidates_token_count
                self.daily_total_tokens += response.usage_metadata.total_token_count

            bot_text = response.text
            if not bot_text or bot_text.strip() == "":
                return "Non so come rispondere a questo."

            return bot_text

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
            "date": self.current_pt_date.strftime("%d/%m/%Y") # Data del Pacifico
        }