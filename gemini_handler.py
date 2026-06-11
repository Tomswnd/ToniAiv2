import os
import logging
import zoneinfo
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

    def get_conversation(self, chat_id):
        # La chiave ora è l'ID della chat, non dell'utente
        if chat_id not in self.conversations:
            logger.info(f"Creata nuova sessione di gruppo/chat: {chat_id}")
            self.conversations[chat_id] = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=DEFAULT_SYSTEM_MESSAGE,
                    temperature=TEMPERATURE,
                    tools=[
                        search_web,
                        save_user_memory,
                        get_user_memories,
                        save_group_memory,
                        get_group_memories,
                        delete_memory
                    ]
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

    def generate_response(self, chat_id, message_text, user_name, user_id=None, image=None):
        self._check_daily_reset()

        # Passiamo il chat_id
        chat_session = self.get_conversation(chat_id)

        # Build contents list for multimodal input
        contents = []
        if image:
            contents.append(image)

        time_context = get_current_time_context()

        # Format user label with user ID and chat ID so Gemini knows the IDs contextually
        user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
        chat_info = f" nella chat {chat_id}" if chat_id is not None else ""

        if message_text:
            formatted_message = f"{time_context}[{user_info} dice{chat_info}]: {message_text}"
            contents.append(formatted_message)
        elif image:
            # If user sent a photo without caption, add a context note
            formatted_message = f"{time_context}[{user_info} ha inviato un'immagine{chat_info}]"
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

    def generate_response_stream(self, chat_id, message_text, user_name, user_id=None, image=None):
        """Generator that yields accumulated response text as it streams from Gemini."""
        self._check_daily_reset()

        chat_session = self.get_conversation(chat_id)

        # Build contents list for multimodal input
        contents = []
        if image:
            contents.append(image)

        time_context = get_current_time_context()

        # Format user label with user ID and chat ID so Gemini knows the IDs contextually
        user_info = f"{user_name} (ID: {user_id})" if user_id is not None else user_name
        chat_info = f" nella chat {chat_id}" if chat_id is not None else ""

        if message_text:
            formatted_message = f"{time_context}[{user_info} dice{chat_info}]: {message_text}"
            contents.append(formatted_message)
        elif image:
            formatted_message = f"{time_context}[{user_info} ha inviato un'immagine{chat_info}]"
            contents.append(formatted_message)
        else:
            formatted_message = ""

        try:
            logger.info(f"Invio richiesta streaming a Gemini per chat {chat_id} da {user_name}")

            # Use request-specific config to disable automatic function calling so we can manually resolve the flow in a stream
            stream_config = types.GenerateContentConfig(
                system_instruction=DEFAULT_SYSTEM_MESSAGE,
                temperature=TEMPERATURE,
                tools=[
                    search_web,
                    save_user_memory,
                    get_user_memories,
                    save_group_memory,
                    get_group_memories,
                    delete_memory
                ],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )

            message_to_send = contents if image else formatted_message
            accumulated_text = ""
            last_usage = None

            while True:
                stream = chat_session.send_message_stream(message_to_send, config=stream_config)
                self.daily_calls += 1

                function_calls_to_resolve = []
                for chunk in stream:
                    if chunk.function_calls:
                        function_calls_to_resolve.extend(chunk.function_calls)
                    if chunk.text:
                        accumulated_text += chunk.text
                        yield accumulated_text
                    if chunk.usage_metadata:
                        last_usage = chunk.usage_metadata

                if not function_calls_to_resolve:
                    # No more function calls, we are done
                    break

                # Resolve all function calls returned in this turn
                tool_parts = []
                for call in function_calls_to_resolve:
                    func_name = call.name
                    func_args = call.args
                    logger.info(f"Rilevato Function Call in stream (manuale): {func_name} con argomenti {func_args}")

                    try:
                        if func_name == "search_web":
                            res = search_web(**func_args)
                        elif func_name == "save_user_memory":
                            res = save_user_memory(**func_args)
                        elif func_name == "get_user_memories":
                            res = get_user_memories(**func_args)
                        elif func_name == "save_group_memory":
                            res = save_group_memory(**func_args)
                        elif func_name == "get_group_memories":
                            res = get_group_memories(**func_args)
                        elif func_name == "delete_memory":
                            res = delete_memory(**func_args)
                        else:
                            res = f"Errore: funzione {func_name} sconosciuta."
                    except Exception as ex:
                        logger.error(f"Errore esecuzione manuale tool {func_name}: {ex}")
                        res = f"Errore esecuzione tool: {ex}"

                    tool_parts.append(
                        types.Part.from_function_response(
                            name=func_name,
                            response={"result": res}
                        )
                    )

                # Set the tool response as the message for the next iteration of the stream
                message_to_send = types.Content(role="tool", parts=tool_parts)

            # Track usage from the final metadata
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