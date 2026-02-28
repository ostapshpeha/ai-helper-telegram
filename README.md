# Honda/Acura Dealership AI Assistant

Telegram bot for a Honda and Acura dealership. Helps customers check available service slots, get spare parts prices, and request a callback — all in Ukrainian.

Built with **PydanticAI + Gemini**, **MongoDB Atlas** (vector search), and **aiogram v3**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Agent | PydanticAI + Google Gemini (`gemini-3-flash-preview`) |
| Embeddings | `gemini-embedding-001` via Google GenAI SDK |
| Vector DB | MongoDB Atlas — `$vectorSearch` on `knowledge_chunks` |
| ODM | Beanie 2.x + Motor (async) |
| Bot framework | aiogram v3 (long polling) |
| API server | FastAPI + Uvicorn (minimal, `/health` only) |
| Config | pydantic-settings, `.env` file |
| Package manager | Poetry (in-project `.venv`) |

---

## Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/docs/#installation)
- MongoDB Atlas cluster with:
  - A database and collections provisioned (see [Migrations](#migrations))
  - A **Vector Search index** named `vector_index` on `knowledge_chunks.embedding` (768 dimensions)
- A Telegram bot token ([BotFather](https://t.me/BotFather))
- A Google Gemini API key ([Google AI Studio](https://aistudio.google.com/))

---

## Local Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd ai-helper-telegram
poetry install
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
MONGO_DB_URL=mongodb+srv://<user>:<password>@<cluster>.mongodb.net
MONGO_DB_NAME=honda_db

GEMINI_API_KEY=your_gemini_api_key

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
STAFF_CHAT_ID=0          # Telegram chat ID where callback requests are forwarded
ADMIN_IDS=[123456789]    # List of Telegram user IDs with admin commands (/ban, /unban)
```

### 3. Run database migrations

Creates `mechanics`, `service_slots`, `car_parts`, and other collections:

```bash
poetry run python run_migrations.py
```

### 4. Seed test data (optional)

Populates mechanics and service slots for local testing:

```bash
poetry run python app/seed.py
```

### 5. Populate the vector knowledge base

The knowledge base (`data/info.md`) is gitignored — it contains dealership-specific service and pricing information. Add your own `data/info.md`, then embed it:

```bash
poetry run python embed_data.py
```

This chunks `info.md`, generates embeddings via Gemini, and writes them to the `knowledge_chunks` collection in Atlas.

> **Note:** The Atlas Vector Search index must be live before the bot can answer knowledge-base queries.
> Index config: name `vector_index`, field `embedding`, dimensions `768`, similarity `cosine`.

### 6. Run the Telegram bot

```bash
poetry run python run_bot.py
```

### 7. Run the FastAPI server (optional)

Exposes a `/health` endpoint; intended for future webhook or admin use:

```bash
poetry run uvicorn app.main:app --reload
```

---

## Project Structure

```
ai-helper-telegram/
├── app/
│   ├── core/
│   │   ├── config.py          # pydantic-settings — reads .env
│   │   ├── database.py        # Motor + Beanie init
│   │   └── logging.py
│   ├── models/
│   │   ├── service.py         # Mechanic, ServiceSlot, Parts, ClientInfo
│   │   ├── knowledge.py       # KnowledgeChunk (vector search)
│   │   └── ligtning.py        # ChatLog, FeedbackScore (Agent Lightning)
│   ├── services/
│   │   ├── ai_agent.py        # PydanticAI agent + 4 tools
│   │   ├── chat_history.py    # Persists chat turns to MongoDB
│   │   └── moderation.py      # Ban, rate limit, content violation checks
│   ├── api/
│   │   └── routers.py
│   ├── migrations/            # Beanie migration files
│   ├── main.py                # FastAPI app
│   └── seed.py                # Test data seeder
├── data/
│   └── info.md                # Dealership knowledge base (gitignored — add your own)
├── run_bot.py                 # Telegram bot entry point
├── run_migrations.py          # Migration runner
├── embed_data.py              # Chunks info.md and uploads embeddings to Atlas
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env                       # Local secrets (gitignored)
```

---

## Agent Tools

The AI agent has four tools:

| Tool | Description |
|---|---|
| `read_knowledge_base` | Vector search on `knowledge_chunks` — cars, services, pricing context |
| `read_db_slots` | Fetches available `ServiceSlot` documents from MongoDB |
| `read_parts_price` | Regex search on `Parts` collection, returns price in UAH |
| `request_callback` | Forwards customer phone number to `STAFF_CHAT_ID` via Telegram |

---

## Admin Commands

Available in Telegram to users listed in `ADMIN_IDS`:

```
/ban <user_id> [reason]   — ban a user
/unban <user_id>          — unban a user
```

---

## Moderation

Each incoming message passes through these checks in order:

1. **Ban check** — blocked users receive a one-line rejection
2. **Rate limit** — max N messages per minute per user
3. **Message length** — capped at 1 000 characters
4. **Content violation** — keyword filter; repeated violations trigger auto-ban

---

## Planned

- **Agent Lightning loop** — daily background job that retrains the agent on thumbs-down chats (`FeedbackScore.NEGATIVE` in `ChatLog`)
- **MongoDB-backed session history** — replace the in-memory `user_sessions` dict
- **Webhook mode** — replace long polling with a FastAPI webhook endpoint
