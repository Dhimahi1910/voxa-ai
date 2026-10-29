# Voice Calling Agent (voxai)

Python service that phones customers from a Google Sheet, talks to them through an AI voice agent, analyses the
transcript with an LLM, writes results back to the sheet, and manages retries, callbacks, meetings and emails.
Everything business-specific (company/agent name, what to collect, retry rules, email wording) is configuration.

## How it fits together

```
Google Sheet ──► calling_workflow ──► Edesy voice API ──(call ends)──► webhook / reconciler
                    ▲  select, dedupe, dial                                   │
 APScheduler ───────┘                                                          ▼
 (cron + 30s task tick)        process_call: fetch call ► LLM analysis (Pydantic) ► follow-up plan
                                                          │              │               │
                                                      PostgreSQL     Google Sheet     Gmail
                                              (calls, tasks, meetings, DNC, notifications)
```

| Layer | Where |
|---|---|
| API routes | `app/api/` |
| Business logic | `app/workflows/` (`calling`, `followup`, `meeting`) |
| Integrations | `app/services/` (voice, sheets, email, LLM) |
| Database | `app/models/`, `app/repositories/`, `alembic/` |
| Jobs | `app/scheduler/` |
| Rules & wording | `config/*.yaml`, `config/system_prompt.md` |

## Voice provider: Edesy (kept) — what is and isn't confirmed

Verified from the [Edesy docs](https://edesy.in/docs/voice-agent/api/trigger-call) and their
[OpenAPI spec](https://voice-agent.edesy.in/api/v1/openapi.json):

- `POST https://voice-agent.edesy.in/api/v1/calls` with `Authorization: Bearer vp_live_…`, body `agentId`, `phoneNumber`,
  optional `fromNumber`, `provider`, `variables` (injected into the prompt as `{name}`), `metadata`, `callbackUrl`.
  Returns `data.conversationId`, `data.callSid`, `status: "initiated"`.
- `GET /api/v1/calls/{id}` and `/calls/{id}/transcript` return details; summary/transcript can lag a few seconds.
- `PATCH /api/v1/agents/{id}` accepts `prompt`, `greetingMessage`, `language`, `webhookUrl`, …

**Not documented, so handled defensively (verify with one real test call):** the exact field names in the call-detail
response, and the webhook payload and signature. Therefore the webhook is only a *"call ended"* trigger; the app
re-fetches authoritative data via the API and normalises it tolerantly (`normalize_call` in `voice_service.py`).
Webhook authenticity uses your own `WEBHOOK_SECRET` (header `X-Webhook-Secret` or `?token=`), not a provider signature.
A reconciler polls any call whose webhook never arrives, so the webhook is optional locally.

Note: the old n8n workflow used `api.edesy.in` with different field names (`phone_number`, `agent_id`, `context`).
This app follows the documented `voice-agent.edesy.in` API instead.

**Credentials needed:** Edesy API key + agent ID; a Google service account JSON (Sheets; plus Gmail with domain-wide
delegation to send as `GMAIL_SENDER`); an LLM key (Gemini by default); a PostgreSQL URL for production.

## Run locally (no real calls, no real emails)

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # leave the safety switches as shipped (all off)
.venv/bin/alembic upgrade head  # creates ./voice_agent.sqlite3 (local default; set DATABASE_URL for PostgreSQL)
.venv/bin/python -m app.cli seed --name "Test Customer" --phone 9876543210 --email test@example.com
.venv/bin/python -m app.cli run calling_run     # simulated call -> analysis -> DB (dry run)
.venv/bin/python -m app.cli run due_tasks       # run any due retries/reminders
API_KEYS=devkey WEBHOOK_SECRET=devsecret .venv/bin/uvicorn app.main:app --workers 1
curl localhost:8000/health
curl -H "x-api-key: devkey" localhost:8000/api/customers
.venv/bin/python -m pytest              # all external services are mocked
```

Calls only happen inside `calling_hours` (default 09:00–19:00 IST, Mon–Sat); outside them a run places nothing.

## Safety switches (all default OFF)

| Variable | Effect when off |
|---|---|
| `ENABLE_REAL_CALLS` | A stand-in voice client simulates calls; nothing is dialled. |
| `ENABLE_EMAIL_SENDING` | Emails are rendered and recorded as `skipped`; nothing is sent. |
| `SHEETS_DRY_RUN` | Sheet reads work; writes are logged instead of performed. |
| `SCHEDULER_ENABLED` | No background jobs; trigger with `POST /api/jobs/trigger` or the CLI. |

## Going live checklist
1. Create the PostgreSQL database, set `DATABASE_URL`, run `alembic upgrade head`.
2. Share the sheet with the service account; set `GOOGLE_SHEETS_*`; edit `config/sheet_columns.yaml` to your headers.
3. Edit `config/business.yaml`, `config/system_prompt.md`, `config/email_templates.yaml`, `config/policy.yaml`.
4. `python -m app.cli push-prompt` previews the rendered prompt; `--confirm` pushes it to the Edesy agent.
5. Set `API_KEYS`, `WEBHOOK_SECRET`, and `PUBLIC_BASE_URL` (HTTPS) if you want webhooks.
6. Make **one** test call to your own number first (`POST /api/calls/start`), confirm the sheet row and transcript, then enable the scheduler.
7. Run a single worker (`--workers 1`): the scheduler runs in-process. The database still blocks duplicate calls if you ever run two.

## Reliability design
- **No duplicate calls:** an attempt row with a unique key is written *before* dialing; a partial unique index allows only one live call per customer; deterministic daily run ids; per-job and per-customer locks.
- **Dial is never auto-retried.** A network failure mid-dial becomes `unknown` and is not redialled (it may have rung). Provider rejections are `failed` (technical) and kept separate from customer outcomes (`Connected`, `Not Received`, `Not Responded`, `Rescheduled`, `Ended`).
- **Restart recovery:** retries, callbacks and reminders are rows in `scheduled_tasks`; stale `running` tasks are re-queued; the reconciler settles unfinished calls and re-syncs failed sheet writes.
- **Idempotent webhooks and emails:** unique event keys and notification keys; reprocessing a call is a no-op.
- **Do-not-call:** customers who ask are added to `do_not_call`, pending tasks are cancelled, and no calls or emails follow. A "Do Not Call" sheet column is also honoured.
- **AI output is validated** with Pydantic; missing details stay empty; a meeting is only "Scheduled" if a concrete future time was agreed; clear-cut outcomes (unanswered/silent) never depend on the LLM.

## API
`GET /health` (open) · `POST /api/calls/start` · `GET /api/calls/{id}` · `GET /api/customers[/{id}]` · `POST /api/dnc` ·
`POST /api/jobs/trigger` (`calling_run | due_tasks | reconcile_calls`) all require header `X-API-Key` (fail closed if `API_KEYS` is empty) ·
`POST /api/webhooks/voice` requires the webhook secret.

## Known limits
- Tested on SQLite only (no PostgreSQL in the dev environment); the schema uses portable types and a partial unique index PostgreSQL supports.
- Whether the customer "spoke" is inferred from speaker labels in the transcript; if the provider returns none, the LLM decides.
- Gmail sending uses a service account with domain-wide delegation (as the original workflow did); a personal Gmail needs an OAuth flow, which is not included.
- The default `requirements` in `config/business.yaml` are generic placeholders; replace them with what you actually want to collect.
