"""
Gestione configurazione per-gruppo.

Ogni gruppo può avere un prompt di sistema personalizzato, salvato
in data/group_configs.json.  Il file viene letto/scritto atomicamente.
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

CONFIG_DIR = "data"
CONFIG_PATH = os.path.join(CONFIG_DIR, "group_configs.json")


def _load_all() -> dict:
    """Carica tutte le configurazioni dal file JSON."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Errore caricamento group_configs.json: {e}")
        return {}


def _save_all(data: dict):
    """Salva tutte le configurazioni nel file JSON."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Errore salvataggio group_configs.json: {e}")


def get_group_prompt(chat_id: int) -> str | None:
    """Restituisce il prompt personalizzato del gruppo, o None se non impostato."""
    data = _load_all()
    entry = data.get(str(chat_id))
    if entry and isinstance(entry, dict):
        return entry.get("system_instruction")
    return None


def set_group_prompt(chat_id: int, prompt: str):
    """Imposta il prompt personalizzato per un gruppo."""
    data = _load_all()
    if str(chat_id) not in data:
        data[str(chat_id)] = {}
    data[str(chat_id)]["system_instruction"] = prompt
    _save_all(data)


def clear_group_prompt(chat_id: int):
    """Rimuove il prompt personalizzato di un gruppo (torna al default)."""
    data = _load_all()
    key = str(chat_id)
    if key in data and "system_instruction" in data[key]:
        del data[key]["system_instruction"]
        # Rimuovi la chiave del gruppo se è rimasta vuota
        if not data[key]:
            del data[key]
        _save_all(data)
