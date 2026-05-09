import os
import json
import logging
import datetime
import shutil # Aggiunto per pulizia cartelle
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

CHATS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chats")

class ChatLogger:
    """Handles recording, retrieving, and deleting user conversations."""

    def __init__(self):
        self._ensure_dir()

    def _ensure_dir(self):
        """Creates the chats directory if it doesn't exist."""
        if not os.path.exists(CHATS_DIR):
            os.makedirs(CHATS_DIR)
            logger.info(f"Created chat directory: {CHATS_DIR}")

    def log_message(self, user_id: int, user_message: str, bot_response: str,
                    username: Optional[str] = None, first_name: Optional[str] = None) -> bool:
        """Saves a single exchange to a JSON file specific to the user."""
        try:
            chat_file = os.path.join(CHATS_DIR, f"chat_{user_id}.json")
            timestamp = datetime.datetime.now().isoformat()

            message_data = {
                "timestamp": timestamp,
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "user_message": user_message,
                "bot_response": bot_response
            }

            messages = []
            if os.path.exists(chat_file):
                with open(chat_file, 'r', encoding='utf-8') as f:
                    try:
                        messages = json.load(f)
                    except json.JSONDecodeError:
                        messages = []

            messages.append(message_data)

            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logger.error(f"Error logging message: {e}")
            return False

    def delete_log(self, chat_id: int):
        """Deletes the specific log file for a chat/user."""
        try:
            chat_file = os.path.join(CHATS_DIR, f"chat_{chat_id}.json")
            if os.path.exists(chat_file):
                os.remove(chat_file)
                logger.info(f"File di log eliminato: {chat_file}")
                return True
        except Exception as e:
            logger.error(f"Errore durante l'eliminazione del file log {chat_id}: {e}")
        return False

    def delete_all_logs(self):
        """Wipes all files in the chats directory."""
        try:
            for filename in os.listdir(CHATS_DIR):
                file_path = os.path.join(CHATS_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            logger.info("Tutti i log della cartella chats sono stati eliminati.")
            return True
        except Exception as e:
            logger.error(f"Errore durante la pulizia totale della cartella log: {e}")
            return False

chat_logger = ChatLogger()