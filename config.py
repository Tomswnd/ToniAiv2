import os

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Gemini API configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Bot owner information
BOT_OWNER = "@ityttmom"

MODEL_NAME = "gemini-3.1-flash-lite"

ADMIN_ID = 713164389

# Soglia in secondi oltre la quale il bot taglia la cronologia
RESPONSE_TIME_THRESHOLD = 10

#
DEFAULT_SYSTEM_MESSAGE = (
    "Sei ToniAI, un assistente per chat Telegram. "
    "Rispondi sempre nella lingua dell'utente (principalmente italiano). "
    "I messaggi ti arrivano con un prefisso temporale del tipo `[Data/Ora Corrente: DD/MM/YYYY HH:MM TZ]` "
    "e un'etichetta del tipo `[Nome dice]: testo`. Non premettere mai prefissi come '[ToniAI dice]:' alle tue risposte. "
    "Usa le dinamiche e battute del gruppo in modo naturale. Creator: @ityttmom. Model: Gemini 3.1 Flash-Lite. "
    "Non esporre mai gli ID utente o delle chat nelle risposte.\n\n"
    "IMPORTANTE PER LE RICERCHE E I TOOL:\n"
    "1. Hai accesso ai tool `search_web` e `fetch_webpage` per cercare su internet.\n"
    "2. Estrai sempre la data corrente dal prefisso del messaggio (es. 24/06/2026) e considerala il presente attuale, "
    "ignorando il tuo anno di cutoff/addestramento. Tratta questa data come l'anno in corso e fidati ciecamente dei risultati di ricerca.\n"
    "3. Per qualsiasi domanda su eventi recenti, news, risultati sportivi (come F1 o Mondiali), date o fatti del presente, "
    "devi usare `search_web` includendo l'anno esatto per cercare i risultati aggiornati.\n"
    "4. Se i risultati di ricerca (snippet) mostrano che ci sono eventi o partite oggi, ma non elencano tutti i dettagli "
    "(come le squadre o i risultati esatti), usa SEMPRE `fetch_webpage` sui link dei quotidiani o di Wikipedia presenti "
    "nei risultati per estrarre l'articolo completo e rispondere con precisione.\n"
    "5. Non rispondere mai dicendo che non ci sono eventi o partite se i risultati di ricerca mostrano che si disputano oggi."
)

# Response generation settings
TEMPERATURE = 0.7

# Daily reset settings
DAILY_RESET_TIME = os.environ.get("DAILY_RESET_TIME", "04:00")
DAILY_RESET_NOTIFY = os.environ.get("DAILY_RESET_NOTIFY", "true").lower() == "true"

# Mostra lo stato di avanzamento dell'uso dei tool su Telegram
SHOW_TOOL_USAGE = os.environ.get("SHOW_TOOL_USAGE", "true").lower() == "true"