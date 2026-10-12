# kundenname_split (Python)

monday.com integration app that keeps **Kundenname (Teil 1)** at 100 characters or less. When an item is created and the name is longer than 100 characters, the app cuts it at a sensible point and moves the overflow into **Kundenname (Teil 2)**.

Copy of the Kunden board's `customer_name_split` app, run as its own app so the two boards don't share settings. The split logic is the same; the only difference is that columns are always set by id in the environment variables (no title lookup).

On the board the Teil 1 column's header reads **Kundenname (voll)**; its description says "Customer Name (Part 1)". Its id is `text_mkt92ar9`.

Stack: FastAPI, PyJWT, httpx. Tests: pytest.

## How the split works

| Step | Rule |
|---|---|
| 1 | Name is normalised (NFC, repeated spaces collapsed, trimmed). Length counted in real characters, so `ü` is 1 |
| 2 | 100 chars or less → nothing happens |
| 3 | Over 100 → cut at the **last space** at or before char 100 |
| 4 | No usable space → cut after the last `, ; / - & .` |
| 5 | Still nothing (one 100+ char token) → hard cut at 100 |
| 6 | Boundaries that would leave part 1 under 50 chars are ignored |

Both columns are written in one mutation. Writing part 1 back fires the trigger again, but that value is ≤ 100 so the second run is a no‑op. No infinite loop.

## Project layout

```
app/
  main.py      FastAPI app, POST / and /monday/split-name, GET /health
  split.py     split_customer_name(), pure logic, no I/O
  monday.py    GraphQL read and single mutation write
  auth.py      JWT verification dependency (Signing Secret)
  config.py    env settings (secrets and column ids come from env vars only)
tests/
  test_split.py     split logic cases
  test_endpoint.py  endpoint cases against a mocked monday API
```

## Setup in the monday Developer Center

1. **Create app** → name it e.g. `kundenname_split`. Copy the **Signing Secret** from General settings.
2. **Host on monday → Server-side code → Environment variables** (region EU): add the variables from [Config](#config). They're set on the app, not a version.
3. Deploy the code (see below), then copy the **Version URL** from **Server-side code → General**.
4. **Features → Create feature → Automation Block**:
   - Block name `Split Kundenname`, Block type **Action**, async **off**, ✅ Connect to monday code
   - Input fields: `boardId` (display name `board id`) and `itemId` (display name `Item id`), both with source **Sentence**
   - Output fields: none
   - Execution URL: the Version URL
   - Workflow builder **Off**, Automation builder **On**
   - Sentence: `Split Kundenname for {Item id} in {board id}`
   - **Save changes**
5. OAuth scopes: none needed (the app uses `MONDAY_API_TOKEN`).
6. On the board → **Automate → Create custom automation** → **When an item is created** → action **Split Kundenname** → map Item and Board from the trigger.

## Deploy

```bash
mapps code:push -i <APP_VERSION_ID>
```

The app version id is the number after `app_versions/` in the Developer Center URL.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in MONDAY_SIGNING_SECRET and MONDAY_API_TOKEN
pytest -q
set -a && source .env && set +a
uvicorn app.main:app --reload --port 8080
```

## Config

Everything is set in the environment variables; nothing board-specific is in the code.

| Env var | Default | Purpose |
|---|---|---|
| `MONDAY_API_TOKEN` | required | Personal API token sent as `Authorization` on every GraphQL call. The app writes as this token's owner, who must have access to the board. `MONDAY_API_KEY` also works |
| `MONDAY_SIGNING_SECRET` | required | General settings → Signing Secret. Verifies the JWT monday sends; without it every call fails |
| `SOURCE_COLUMN_ID` | required | Column the name is entered in and shortened: `text_mkt92ar9` (Kundenname (Teil 1)) |
| `TARGET_COLUMN_ID` | required | Column the overflow goes to: `text_mksb1npw` (Kundenname (Teil 2)) |
| `DEFAULT_BOARD_ID` | unset | Board used when the automation doesn't send `boardId` |
| `MAX_NAME_LENGTH` | `100` | Limit for Teil 1 |
| `TEIL2_MAX_LENGTH` | unset | Logs a warning if Teil 2 overflows this |
| `MONDAY_API_VERSION` | `2025-04` | monday GraphQL API version |
| `PORT` | `8080` | HTTP port. monday code sets it itself |

On startup the app logs `Config OK` or `Missing required config: ...`; check that line in the logs after each deploy. If the column ids are missing, runs fail with **Columns not configured** in the automation's activity log.

Values are cached until the process restarts, so redeploy after changing one.

## Secrets

* **Inbound** (monday → app): every call carries a JWT signed with the app's Signing Secret. `auth.py` verifies it and rejects anything else with a 401.
* **Outbound** (app → monday): every GraphQL call sends the fixed `MONDAY_API_TOKEN`.

`config.get_secret()` reads a plain env var first (local, Docker, tests), then monday-code's Secrets and Environment variables through the `monday-code` SDK.

## Behaviour notes

* Teil 2 is **overwritten** with the overflow when a split happens. The previous value is logged.
* If a name is later shortened to ≤ 100, Teil 2 is left alone.
* Errors come back in monday's format, so they show in the automation's activity log.
