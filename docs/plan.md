# Telegram Mini App — UI Upgrade Plan

## The Problem with Pure Chat UI

The current bot is text-only. For a dealership context this creates friction:

- **Slot booking** — the agent returns a bullet list of available times. The user has to read it, choose one, and type a reply. A calendar picker does this in 2 taps.
- **Car comparison** — comparing HR-V vs CR-V via chat messages is awkward. A side-by-side card view is instantly clearer.
- **Callback form** — asking for name, phone, car model, and issue across 4 separate messages feels like an interrogation. A single form is faster and less error-prone.
- **Parts search** — scrolling through a text list of parts with prices is harder to scan than a filterable grid.

The AI chat remains the **primary interface**. The Mini App handles the 4 specific workflows where visual UI is dramatically better than text.

---

## Architecture

```
Telegram Chat (aiogram)
    │
    ├── AI agent handles all text conversations (unchanged)
    │
    └── For specific intents (booking, form, catalog) →
        sends web_app button → opens Mini App
            │
            └── Mini App calls FastAPI backend
                    │
                    ├── GET /api/slots?specialization=...
                    ├── GET /api/models
                    ├── GET /api/parts?q=...
                    └── POST /api/callback
```

**Mini App = React SPA** served as a static build from FastAPI (`/mini-app`).
**FastAPI** already exists — just needs 4 new endpoints added to `app/main.py`.
**Bot** sends a `web_app` inline button at the right moment in conversation.
**Mini App → Bot** communication via `Telegram.WebApp.sendData()` — bot receives the result and confirms to user.

No new services, no new hosting — the existing `api` Docker service covers it.

---

## Screen 1 — Slot Booking Calendar

**Trigger:** agent calls `read_db_slots` and finds available slots → sends a "Обрати час" button.

**UI:**
- Month calendar view with available days highlighted
- Tap a day → time slots appear as pill buttons (e.g. `10:00`, `14:30`)
- Tap a time → confirmation screen showing master name + specialization
- "Підтвердити запис" MainButton → `sendData({slot_id, master_name, time})`
- Bot receives data, sends confirmation message to user and notification to `STAFF_CHAT_ID`

**Why better than text:** User sees the whole week at a glance. No need to read a list and type a choice.

---

## Screen 2 — Callback Request Form

**Trigger:** user says they want a callback / leaves a phone number → agent sends "Заповнити форму" button instead of asking 4 questions one by one.

**UI:**
- Single-screen form: Name, Phone (with UA format hint), Car model (dropdown of Honda/Acura models), Issue (textarea)
- Telegram `MainButton` = "Надіслати" — disabled until phone is filled
- On submit → `sendData({name, phone, car_model, issue})`
- Bot forwards to `STAFF_CHAT_ID` (replaces current `request_callback` tool for this flow)

**Why better than text:** One screen, validated inputs, no back-and-forth. Phone field can use `inputmode="tel"`.

---

## Screen 3 — Car Model Catalog

**Trigger:** `/menu` → "Моделі та комплектації" button, or agent detects a comparison question.

**UI:**
- Card grid: Honda logo + model name + starting price + thumbnail (or emoji placeholder)
- Tap a card → detail screen: specs table, trim levels, short description pulled from knowledge base via `/api/models/{id}`
- "Порівняти" button → select 2 models → side-by-side spec table
- "Записатись на тест-драйв" → opens Screen 1 (slot booking) filtered to sales consultant

**Why better than text:** Visual browsing. Comparison table is impossible to read clearly in chat.

---

## Screen 4 — Parts Search

**Trigger:** user asks about parts prices → agent sends "Знайти запчастину" button.

**UI:**
- Search input with instant filtering
- Results as cards: part name, price in UAH, compatible models (chips)
- Tap a card → detail with full compatible model list
- "Уточнити наявність" button → opens Screen 2 (callback form) pre-filled with part name as issue

**Why better than text:** Searchable, filterable, scannable. Much better than reading a text list.

---

## Telegram Theme Compliance

Mini App must use `tg.themeParams` — background, text, button colors from Telegram's active theme. This makes it look native in both light and dark mode. Never hardcode colors.

```js
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand(); // full-height
document.body.style.backgroundColor = tg.themeParams.bg_color;
```

---

## Backend — FastAPI Endpoints to Add

All read-only. No auth beyond Telegram `initData` validation.

| Endpoint | Description |
|---|---|
| `GET /api/slots?specialization=` | Available slots (same logic as `read_db_slots`) |
| `POST /api/callback` | Save callback request, notify `STAFF_CHAT_ID` |
| `GET /api/models` | List of car models from knowledge base |
| `GET /api/parts?q=` | Parts search (same logic as `read_parts_price`) |

Add `initData` validation middleware to all `/api/*` routes — verify the HMAC signature Telegram sends with every Mini App request.

---

## Bot Changes

When agent would normally call `read_db_slots` and return a list → instead send a `web_app` button:

```python
InlineKeyboardButton(
    text="📅 Обрати зручний час",
    web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}/slots?spec={specialization}")
)
```

Same pattern for callback form and parts search. The chat agent stays for everything else.

---

## Implementation Order

1. **FastAPI endpoints** — `/api/slots`, `/api/parts`, `/api/callback`, `/api/models`
2. **initData validation middleware** — security before anything is public
3. **Screen 2 (Callback form)** — simplest, highest impact, no calendar complexity
4. **Screen 1 (Slot calendar)** — highest UX improvement for core use case
5. **Screen 4 (Parts search)** — straightforward search UI
6. **Screen 3 (Car catalog)** — most complex, needs content in knowledge base
7. **Bot integration** — wire `web_app` buttons into agent responses and `/menu`
8. **Dockerfile** — add static build step for Mini App frontend

---

## New Config Keys

```env
MINI_APP_URL=https://your-domain.com/mini-app   # public HTTPS URL (required by Telegram)
```

Mini App must be served over HTTPS. The existing `api` service behind a reverse proxy (nginx + Let's Encrypt) covers this.

---

## What Stays as Text Chat

Everything that's conversational:
- General questions about cars, services, pricing context
- Multi-turn troubleshooting
- Anything the RAG agent handles well

The Mini App only takes over when structured data entry or visual browsing is clearly better.
