import os
import logging
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, DEFAULT_SYSTEM_MESSAGE, TEMPERATURE

logger = logging.getLogger(__name__)


class GeminiHandler:
    """Class to handle interactions with the Gemini 2.5 Flash API"""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        # Initialize the new Google GenAI client
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"
        self.conversations = {}  # Dictionary to store chat sessions by user_id

    def get_conversation(self, user_id):
        """Get or create an active chat session for a user"""
        if user_id not in self.conversations:
            # Gemini has built-in chat history management
            self.conversations[user_id] = self.client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=DEFAULT_SYSTEM_MESSAGE,
                    temperature=TEMPERATURE,
                )
            )
        return self.conversations[user_id]

    def reset_conversation(self, user_id):
        """Reset a user's conversation history by creating a new chat session"""
        if user_id in self.conversations:
            del self.conversations[user_id]

        # Initialize a fresh chat
        self.get_conversation(user_id)
        return "Conversation history has been successfully reset."

    def generate_response(self, user_id, message_text):
        """Generate a response using Gemini API"""
        chat_session = self.get_conversation(user_id)

        try:
            logger.info(f"Sending request to Gemini for user {user_id}")
            response = chat_session.send_message(message_text)
            return response.text

        except Exception as e:
            logger.error(f"Error generating response from Gemini: {e}")
            return (
                "I'm sorry, but I am having trouble connecting to the AI right now. "
                "Please try again in a moment."
            )