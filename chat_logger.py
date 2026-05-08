import os
import json
import logging
import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Directory where chat logs will be stored
# In Docker, this is mapped to your host machine via the 'volumes' setting
CHATS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chats")


class ChatLogger:
    """Handles recording and retrieving user conversations."""

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


# Create the singleton instance that main.py expects to import
chat_logger = ChatLogger()