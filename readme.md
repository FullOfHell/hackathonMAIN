# Reltix / centrix Hackathon Project

## Launch the demo on Windows

After first-time setup, double-click **start-demo.cmd** or run it from the checkout in PowerShell.

```powershell
.\start-demo.cmd
```

Open the [resident portal](http://localhost:5173) once Vite says it is ready. The **centrix backend** window runs FastAPI on port 8000. The **centrix portal** window runs Vite on port 5173 and points it at that API for this session. From another directory, invoke the launcher by its quoted path, for example `& 'C:\Projects\centrix demo\start-demo.cmd'`.

To stop the demo, press **Ctrl+C in each server window**, confirm with **Y** if prompted, then close the windows. If you launch twice, the new windows show the port conflicts and the first servers keep running. The API also has a [health check](http://localhost:8000/api/health) and [interactive API docs](http://localhost:8000/docs).

### First-time setup

Install Git for Windows (including Git Bash), Python 3.10 or newer, and Node.js 22.12 or newer with npm. Run the setup script from the repository root in **Git Bash**.

```bash
bash scripts/setup.sh
```

Setup enables the Git hooks, creates the backend virtual environment, installs backend and frontend dependencies, and creates `backend/.env` if missing. The local demo uses synthetic data, a simulated HeatFix contractor and deterministic intake. The default setup works without API keys.

### Manual two-terminal fallback

Open two PowerShell terminals in the repository root. Start the backend in the first.

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Start the live portal in the second.

```powershell
cd frontend
$env:VITE_API_BASE_URL = 'http://localhost:8000'
npm.cmd run dev -- --port 5173 --strictPort
```

### Walk through a heating report

1. In **Report**, enter “No heat since last night.” Review the editable summary, answer any follow-up, choose the fields to share and select **Approve and send**.
2. In **HeatFix inbox**, find the job for that case, select **Accept**, then **Offer slots**. Return to **Report**, refresh the case, select a time and choose **Confirm appointment**.
3. In **HeatFix inbox**, refresh the job list, select **Start repair**, then **Complete repair**. Enter a repair summary and select **Save completion**.
4. Select **Submit demo invoice**, then **Confirm demo invoice**. Open **My cases** or **Manager** to check the same case and unit, read the repair outcome and download the synthetic invoice.

## Start here

Everyone - including AI coding tools - should read these files before changing the implementation:

1. [`AGENTS.md`](AGENTS.md) - shared scope, engineering rules, and collaboration conventions.
2. [`Docs/Reltix_Hackathon_Project_Plan.md`](Docs/Reltix_Hackathon_Project_Plan.md) - product plan, architecture, API contracts, backlog, and acceptance tests.
3. [`Docs/Reltix-Track-Description.pdf`](Docs/Reltix-Track-Description.pdf) - official Reltix challenge brief and final source of truth for track requirements.
4. [`Docs/SpecialFeatures.md`](Docs/SpecialFeatures.md) - differentiators to attempt only after the core flow works.
5. [`Docs/git-workflow.md`](Docs/git-workflow.md) - branch flow, push checks, CI, coverage and secret handling.
6. [`Docs/mentor-feedback.md`](Docs/mentor-feedback.md) - Reltix mentor answers and the product decisions they changed.
5. [`Docs/TODO.md`](Docs/TODO.md) - prioritized implementation checklist for the three-person team.

If these documents conflict, the official track description wins for challenge requirements. `AGENTS.md` wins for repository working conventions.

## MVP demo

This maintenance coordinator is the Reltix demo for the MAIN Summit AI Hackathon. It uses centrix property context to take a resident's heating report through booking, repair and invoicing on the same unit.

```text
resident reports no heating
  -> context-aware triage
  -> approval to share required data
  -> repair case created
  -> generic connector sends job to mock partner
  -> partner offers slots
  -> resident books a slot
  -> partner completes repair and attaches invoice
  -> centrix unit shows the full outcome and timeline
```

The prototype uses synthetic residents, properties, partners, and documents. It does not connect to the real centrix API or a real contractor.

## Planned architecture

- React + TypeScript for resident, partner, and property-manager views.
- FastAPI + SQLite as the source of truth for cases, state transitions, approvals, appointments, and documents.
- A provider-neutral partner connector with versioned, idempotent requests and callbacks.
- n8n for integration orchestration.
- Structured LLM extraction for issue intake; the model never invents booking or repair status.
- Resident channels: the portal plus a simulated text-message outbox with one-click links. No voice agent, since Reltix already has one (see [mentor feedback](Docs/mentor-feedback.md)).

The project plan describes the full demo. The implemented booking and callback contracts are in the [connector specification](Docs/connector-spec.md).

## Frontend development

The React and TypeScript portal is in `frontend/`. It includes tenant intake, an editable review, explicit sharing approval, a case timeline, and the HeatFix inbox.

```bash
cd frontend
npm install
npm run dev
```

For a persistent local development setting, copy `frontend/.env.example` to `frontend/.env.local` and restart Vite. The Windows launcher supplies the same API URL for its portal session. Leave `VITE_API_BASE_URL` unset for an offline fixture demo. Fixture reports reset on page reload.

Before opening a pull request, run:

```bash
npm run lint
npm run build
```

Shared frontend, backend and integration fixtures are stored in `shared/fixtures/`. Treat their shape as a team contract.

## Run the backend

From the repository root, use Python 3.10 or newer. In PowerShell run the following commands.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

In Bash, activate the virtual environment first.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                 # vertical-slice tests
python -m uvicorn app.main:app --reload --port 8000
```

Open the interactive API at `http://localhost:8000/docs`. Startup seeds new SQLite databases in `backend/data/app.db` and upgrades existing cases in place. Defaults run both the centrix stand-in and simulated HeatFix on port 8000. For other addresses or a custom shared secret, set `PUBLIC_BACKEND_URL`, `PARTNER_BASE_URL` and `PARTNER_WEBHOOK_SECRET` in the environment or in `backend/.env`. See the [environment template](.env.example).

For n8n Cloud, follow the [workflow setup](n8n/README.md) to connect the HeatFix endpoint and FastAPI.

The [structured intake endpoint](Docs/structured-intake-contract.md) uses deterministic extraction by default. Set `OPENAI_API_KEY` and `OPENAI_TEXT_MODEL` in `backend/.env` to enable model suggestions.

To enable optional voice dictation, set `OPENAI_API_KEY` and `OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe` in `backend/.env` and restart FastAPI. Open **Report** on localhost or HTTPS, allow microphone access, and record up to 30 seconds. Choose **Transcribe recording**, review the text, and select **Add transcript to report**. The normal review and sharing steps still apply. Use fictional reports for the demo.

Backend tests consume the canonical contract examples from `shared/fixtures/`.

For the P1 backend demo, submit “No heat at all” from the two seeded units using FastAPI's interactive API. Approve one report and inspect both case timelines and the single HeatFix job. The backend also holds invoices over €3,000 for manager approval and loads simulated partner registrations from `backend/seed/partner-registrations/`. See the [API walkthrough](Docs/connector-spec.md#building-heating-reports).

## Notifications

The backend writes one notification per recipient for each case milestone: request sent to the partner after the resident approves sharing (a saved report alone sends nothing), linked to a building repair, appointment offered and confirmed, repair progress, building heating incidents and invoices above €3,000. The portal box reads `GET /api/notifications?recipient_type=resident&recipient_id=c_202`. A noreply bot sends the same text plus a link by email or text message, as each recipient's preferences allow (`GET`/`PUT /api/recipients/{type}/{id}/notification-preferences`). The seed includes a synthetic owner, `o_101` (Maria Becker). Delivery failures are recorded on the notification and never stop the case flow.

### Choose where messages go

All settings live in `backend/.env`, a git-ignored file copied from the root [`.env.example`](.env.example). Explorer hides it because its name starts with a dot; open it in VS Code. Restart the backend after every change. `NOTIFY_TRANSPORT` is a comma list with one email transport and one text transport:

| `NOTIFY_TRANSPORT` | Email goes to | Text messages go to | Needs |
| --- | --- | --- | --- |
| `outbox` (default) | nowhere, recorded as `sent_simulated` | nowhere, recorded as `sent_simulated` | nothing |
| `smtp,ntfy` | Mailpit or a real mailbox | the ntfy phone app | Docker or a mail account; no tokens for ntfy |
| `smtp,telegram` | Mailpit or a real mailbox | a Telegram bot | a bot token |

A resident's **Preferred contact** in the portal (**Your home → Edit my details**) picks the default channel: Portal (in-app only), Email or Phone (text messages). Preferences saved through the API override these defaults per category. Each delivery is listed under `deliveries` in `GET /api/notifications` as `sent`, `sent_simulated`, `skipped` (with the reason) or `failed` (with the error).

### Email with Mailpit (local, no account)

1. Start Mailpit: `docker run -d --name mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit`.
2. In `backend/.env` set `NOTIFY_TRANSPORT=smtp` (or `smtp,ntfy`), `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_STARTTLS=false` and leave `SMTP_USER` and `SMTP_PASSWORD` empty.
3. Restart the backend, choose **Email** as your preferred contact and make sure your profile has an email address.
4. Report or advance a repair and open `http://localhost:8025`. Mailpit catches every message; nothing reaches a real mailbox.

Start Mailpit again later with `docker start mailpit`.

### Email to a real Gmail inbox

1. Turn on 2-Step Verification for the Google account, then create an app password at `https://myaccount.google.com/apppasswords`. Google shows a 16-character password once.
2. In `backend/.env` set:
   ```
   NOTIFY_TRANSPORT=smtp,ntfy
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_STARTTLS=true
   SMTP_USER=your.address@gmail.com
   SMTP_PASSWORD=the app password, without spaces
   NOTIFY_FROM=centrix <your.address@gmail.com>
   ```
   Gmail sends from the signed-in account, so `NOTIFY_FROM` must use that address. Type the password into the file yourself; `.env` is git-ignored, so never copy it into `.env.example`.
3. Restart the backend, set your profile email to the inbox you want to receive at, and choose **Email**. Check the spam folder for the first message.

Other providers work the same way with their own SMTP host, port and password.

### Text messages with ntfy (no account or token)

1. Install the free [ntfy](https://ntfy.sh/) app on your phone.
2. In `backend/.env` set `NOTIFY_TRANSPORT=smtp,ntfy` (keep `NTFY_SERVER=https://ntfy.sh`) and restart the backend.
3. Choose **Phone** as your preferred contact.
4. Open `GET /api/recipients/resident/c_202/notification-preferences` in `http://localhost:8000/docs` and copy `ntfy_topic`, for example `centrix-N5Kz…`. Each recipient gets one random topic, which stays the same until the database is reset.
5. In the app tap **+**, paste the exact topic and keep the server `ntfy.sh`.
6. Report or advance a repair. On Android, turn on **Instant delivery** for the subscription; otherwise pushes can arrive minutes late.

ntfy topics are public, so the long random name is the only protection. Use synthetic data only. To check delivery without the app, open `https://ntfy.sh/<topic>` in a browser.

### Text messages with a Telegram bot (after you have a token)

1. In Telegram, message **@BotFather**, send `/newbot`, choose a name and a username ending in `bot`, and copy the token it replies with.
2. In `backend/.env` set `TELEGRAM_BOT_TOKEN=<token>` and `NOTIFY_TRANSPORT=smtp,telegram`, then restart the backend. When both `ntfy` and `telegram` are listed, ntfy wins.
3. Open your bot in Telegram, tap **Start** and send it any message. A bot can only message people who wrote to it first.
4. Open `https://api.telegram.org/bot<token>/getUpdates` in a browser and copy the number from `"chat":{"id":…}`.
5. Store it with `PUT /api/recipients/resident/c_202/notification-preferences` and the body `{"telegram_chat_id": "<chat id>", "categories": []}`. Fields you leave out keep their values.
6. Choose **Phone** as your preferred contact and report or advance a repair.

Links in messages point to `PUBLIC_FRONTEND_URL` (default `http://localhost:5173`), which opens only on the computer running the portal. To open them from a phone on the same Wi-Fi, set it to the computer's network address, for example `http://192.168.1.20:5173`.

## Three-person workflow

- Create short-lived branches such as `frontend/tenant-flow`, `backend/case-api`, or `integration/partner-connector`.
- Keep shared schemas and example payloads in version control and agree on changes before altering their shape.
- Open small pull requests and state which acceptance test they enable.
- Do not commit `.env` files, API keys, tokens, real personal data, or generated dependency folders.
- Merge only code that preserves the deterministic typed demo path.
