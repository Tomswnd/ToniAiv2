# ToniAI

Bot Telegram alimentato da Gemini 3.1 Flash-Lite. Conversazioni interattive, memoria persistente dei personaggi e personalizzazione per gruppo.

## Come funziona

### Conversazione

In **chat privata** il bot risponde a qualsiasi messaggio. Nei **gruppi** risponde solo ai messaggi che iniziano con `toniai` (es. `toniai che tempo fa domani?`). Supporta anche foto con didascalia e risposte (reply) ai messaggi di altri utenti.

### Memoria

Il bot mantiene una cronologia della conversazione in RAM. Ogni messaggio scambiato viene anche scritto su un file di log giornaliero (`data/chat_logs/{chat_id}_today.txt`).

Ogni notte alle 4:00 (configurabile), il bot genera un resoconto strutturato dei personaggi della chat: personalita, interessi, abitudini, gag, dinamiche di gruppo. Questo resoconto viene salvato in `data/daily_summaries/{chat_id}/latest.json` e caricato automaticamente come contesto nelle conversazioni successive.

Il risultato e che il bot ricorda chi siete e come interagire con voi, anche dopo un riavvio.

### Gestione automatica della velocita

Se la conversazione diventa lunga e il tempo di risposta di Gemini supera i 10 secondi, il bot taglia automaticamente la prima meta dei messaggi piu vecchi dalla cronologia attiva. Il log giornaliero su disco non viene toccato, quindi il riassunto di fine giornata resta completo.

### Personalizzazione per gruppo

Ogni gruppo puo avere istruzioni personalizzate che modificano lo stile del bot. Queste vengono salvate in `data/group_configs.json` e applicate sopra al prompt di sistema predefinito.

## Comandi

| Comando | Descrizione | Chi puo usarlo |
|---------|-------------|----------------|
| `/start` | Messaggio di benvenuto | Tutti |
| `/help` | Lista comandi | Tutti |
| `/reset` | Salva il resoconto personaggi e resetta la conversazione | Tutti |
| `/forget` | Cancella tutti i dati della chat corrente (log e profili) | Tutti |
| `/setprompt <testo>` | Imposta un prompt personalizzato per il gruppo | Admin del gruppo |
| `/viewprompt` | Mostra il prompt personalizzato attivo | Tutti |
| `/clearprompt` | Rimuove il prompt personalizzato | Admin del gruppo |
| `/togglenotify` | Attiva/disattiva le notifiche del reset giornaliero | Owner del bot |
| `/apistats` | Statistiche di utilizzo API | Owner del bot |

## Setup e Deploy

### Prerequisiti

- Docker e Docker Compose
- Un token Telegram (ottienilo da [@BotFather](https://t.me/BotFather))
- Una API key di Google Gemini (ottienila da [Google AI Studio](https://aistudio.google.com/))

### Configurazione

1. Clona il repository:

```bash
git clone <url-repo>
cd ToniAi
```

2. Crea il file `.env` nella root del progetto:

```env
TELEGRAM_TOKEN=il-tuo-token-telegram
GEMINI_API_KEY=la-tua-api-key-gemini
```

3. (Opzionale) Modifica le costanti in `config.py`:

| Costante | Default | Descrizione |
|----------|---------|-------------|
| `BOT_OWNER` | `@ityttmom` | Username Telegram del creatore |
| `MODEL_NAME` | `gemini-3.1-flash-lite` | Modello Gemini da usare |
| `ADMIN_ID` | `713164389` | ID Telegram dell'admin (per comandi riservati) |
| `RESPONSE_TIME_THRESHOLD` | `10` | Secondi oltre i quali la cronologia viene tagliata |
| `TEMPERATURE` | `0.7` | Temperatura di generazione delle risposte |

4. (Opzionale) Variabili d'ambiente aggiuntive nel `.env`:

```env
DAILY_RESET_TIME=04:00
DAILY_RESET_NOTIFY=true
TZ=Europe/Rome
```

### Avvio con Docker

```bash
docker-compose up -d --build
```

Il bot si avvia in background. I dati persistenti (log giornalieri, riassunti, configurazioni gruppi) vengono salvati nella cartella `data/` montata come volume.

### Avvio senza Docker

```bash
pip install -r requirements.txt
python main.py
```

### Aggiornamento

Prima di aggiornare il codice, puoi salvare manualmente il riassunto di una chat attiva:

```bash
# Con Docker
docker exec -it toniai_bot python force_save_summary.py <chat_id>

# Senza Docker
python force_save_summary.py <chat_id>
```

Poi ricostruisci il container:

```bash
docker-compose up -d --build
```

### Logs

```bash
docker logs -f toniai_bot
```

## Struttura del progetto

```
ToniAi/
  config.py              # Configurazione (token, prompt, costanti)
  main.py                # Entry point, avvio bot e scheduler
  gemini_handler.py      # Gestione conversazioni, cronologia, chiamate Gemini
  group_config.py        # Lettura/scrittura configurazioni per gruppo
  daily_reset.py         # Reset giornaliero e generazione riassunti
  force_save_summary.py  # Script per forzare il salvataggio di un riassunto
  handlers/
    __init__.py          # Inizializzazione bot e handler Gemini
    commands.py          # Handler comandi Telegram
    messages.py          # Handler messaggi e foto
  data/                  # Dati persistenti (volume Docker)
    chat_logs/           # Log giornalieri delle conversazioni
    daily_summaries/     # Riassunti personaggi per chat
    group_configs.json   # Prompt personalizzati per gruppo
```
