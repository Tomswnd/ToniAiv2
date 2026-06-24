"""
Gestione del tono/personalità del bot per singola chat.

Il tono scelto dall'utente sostituisce la parte iniziale del DEFAULT_SYSTEM_MESSAGE
(la descrizione della personalità del bot).  Il resto del system message
(istruzioni tecniche, tool, ecc.) rimane invariato.

I dati vengono salvati in data/chat_tones.json.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

DATA_DIR = "data"
TONES_PATH = os.path.join(DATA_DIR, "chat_tones.json")


def _load_all() -> dict:
    """Carica tutti i toni salvati dal file JSON."""
    if not os.path.exists(TONES_PATH):
        return {}
    try:
        with open(TONES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Errore caricamento chat_tones.json: {e}")
        return {}


def _save_all(data: dict):
    """Salva tutti i toni nel file JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(TONES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Errore salvataggio chat_tones.json: {e}")


def get_chat_tone(chat_id: int) -> str | None:
    """Restituisce il tono personalizzato della chat, o None se non impostato."""
    data = _load_all()
    return data.get(str(chat_id))


def set_chat_tone(chat_id: int, tone_text: str):
    """Imposta il tono personalizzato per una chat."""
    data = _load_all()
    data[str(chat_id)] = tone_text
    _save_all(data)


def clear_chat_tone(chat_id: int):
    """Rimuove il tono personalizzato di una chat (torna al default)."""
    data = _load_all()
    key = str(chat_id)
    if key in data:
        del data[key]
        _save_all(data)
