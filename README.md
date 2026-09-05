# AI Analyst — SaaS

An AI-driven data analysis pipeline: ask a business question in plain
English, it plans the analysis, writes and validates SQL, pulls the data,
runs statistics/correlation/trend/outlier/segmentation analysis, and has an
LLM interpret each stage into plain-English insights and recommendations —
then bundles it all into a downloadable PDF report.

Real user accounts, subscription billing via Paymob (3 plans), persistent
report history in Firestore, rate limiting, structured logging, and an
automated test suite are all built in. No Docker — runs directly with
`uvicorn`, designed to deploy on Railway.

## Architecture

- **Business database** (`database.py`, `DB_*` env vars) — the customer's
  own Postgres data that gets queried and analyzed. Unrelated to the app's
  own storage.
- **App database: Firestore** (`firestore_db.py`) — this SaaS's own data:
  user accounts, subscriptions, payment history, report history, usage
  tracking, admin audit log. See the collection layout documented at the
  top of `firestore_db.py`.
- **LLM**: Hugging Face inference (`chains.py`, `HF_TOKEN`).
- **Payments**: Paymob (`paymob.py`, `billing.py`).
- **Frontend**: static HTML/CSS/JS (`Frontend/`), served by the same
  FastAPI app — no separate frontend deployment needed.

## Everything the user does is stored, and can be built on

Every report a user generates is saved to Firestore under
`users/{uid}/reports/{report_id}` (see `firestore_db.py`) — question, full
result JSON, timestamp. `GET /reports` lists them (used for the History
panel in the UI); `GET /report/{id}/pdf` regenerates the PDF from stored
data any time, no re-running the pipeline.

On top of that, `POST /analyze` now accepts an optional `prior_report_id`.
When set, the pipeline is given the earlier report's question and key
findings as context, so a follow-up question genuinely builds on the
previous answer instead of starting cold. The "Improve this ↻" button in
the UI wires this up automatically.

## Each user brings their own data — there's no shared app database

This isn't a single-tenant tool pointed at one business database. Every
user connects or uploads **their own** data, stored per-account, and picks
which dataset to analyze each time they ask a question. See
`datasources.py` and the `/datasets/*` endpoints in `main.py`.

Two ways in, both saved under `users/{uid}/datasets/{dataset_id}` in
Firestore:

- **`POST /datasets/upload`** (multipart: `name`, `file`) — accepts a
  `.csv`, `.xlsx`, or `.xls` file. It's parsed with pandas, chunked into
  Firestore-sized row batches (Firestore documents cap out around 1MB), and
  stored in a `rows` subcollection. At analysis time the rows are
  reconstructed into a DataFrame and loaded into a throwaway in-memory
  SQLite database — so the exact same SQL-generation pipeline that talks to
  a real Postgres database also works here, no separate code path needed.

- **`POST /datasets/connect`** (`name`, `db_type` [`postgres`|`mysql`],
  `host`, `port`, `database`, `user`, `password`, `sslmode`) — the user's
  own live database. The connection is tested immediately (a real `SELECT
  1`) before anything is saved, so bad credentials fail fast with a clear
  error instead of silently saving. The password is encrypted at rest with
  Fernet (`security.py`) using `DATASET_ENCRYPTION_KEY` — generate one with:

  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

  and put it in `.env`. Without it, a key is derived from your other app
  secrets (fine for local dev, but set a real one before storing real
  customer credentials).

`GET /datasets` lists a user's datasets (never returns the encrypted
password); `DELETE /datasets/{id}` removes one (and its stored rows, if
any). `POST /analyze` and `GET /schema` both now require a `dataset_id` —
the frontend's dataset picker (above the question box) handles this, and
the person can hold several named datasets and switch between them freely.

The `DB_HOST`/`DB_PORT`/etc. variables in `.env.example` are no longer
used by the running app — they only exist for `python pipeline.py`'s
manual local smoke test. Delete them from your real `.env` if you like;
nothing reads them at request time anymore.


## Firebase / Firestore setup

You need a **service account key**, not your app's web `firebaseConfig`.
The `apiKey`/`appId`/`authDomain` values from a browser Firebase setup are
public, client-side values and don't work for a server backend.

1. Firebase Console -> your project -> gear icon -> **Project Settings** ->
   **Service Accounts** tab -> **Generate new private key**. This
   downloads a JSON file.
2. Provide it to the app one of two ways:
   - **`FIREBASE_SERVICE_ACCOUNT_JSON`** — paste the entire JSON file's
     contents as one environment variable. This is the one to use on
     Railway (its Variables tab handles multi-line values fine).
   - **`FIREBASE_SERVICE_ACCOUNT_PATH`** — a path to the key file on disk.
     Convenient for local dev; don't use this on Railway (the file won't
     exist in its build).
3. **Never commit the key file or its contents to git.** `.gitignore`
   already excludes `*serviceAccountKey*.json` and `*firebase-adminsdk*.json`
   patterns, but double-check before pushing.

Firestore collections are created automatically on first write — no schema
migration step, no manually-created indexes. The data layout was
specifically designed so every query Firestore needs is either a direct
document lookup or a single-field range/order query, which Firestore
auto-indexes with zero setup. See the docstring at the top of
`firestore_db.py` for the full collection layout and why.

**Important, tested honestly:** I don't have network access to
`*.googleapis.com` in the environment I built this in, so I could not run
a live end-to-end test against your actual Firestore project. I verified
your service account key parses and authenticates correctly with the
Firestore client library (confirmed with your real key, then deleted it
from my environment). What I could not verify here is the actual network
round-trip. Run `python scripts/smoke_test.py` after setting your real
`.env` — step 3 of 4 does a real write/read/delete against Firestore and
will tell you immediately if something's wrong.

## Sign-in: Google, Apple, and email + verification code

Three ways in, all producing the same app session token from `/auth/login`,
`/auth/signup`, or the new `/auth/firebase`:

- **Email + password** — `POST /auth/signup` now sends a **6-digit code**
  (not a link) to the user's email, valid for `EMAIL_OTP_TTL_MINUTES`
  (default 15). The user types it into the app, which calls
  `POST /auth/verify-email {"email", "code"}`. Resending is
  `POST /auth/resend-verification` (auth required).
- **Google / Apple** — handled client-side by the Firebase JS SDK
  (`Frontend/firebase-init.js`), since you already have both providers
  enabled in Firebase Console. The flow:
  1. User clicks "Continue with Google/Apple" → Firebase runs the
     provider's popup sign-in and returns an ID token.
  2. Frontend sends that ID token to `POST /auth/firebase {"id_token"}`.
  3. Backend verifies it server-side with `firebase_admin.auth.verify_id_token`
     (`auth.py::verify_firebase_id_token`) and creates or reuses an app
     account for that email (`firestore_db.py::get_or_create_oauth_user`).
     These accounts are marked `email_verified=True` immediately — Firebase
     already confirmed the identity, and Apple/Google logins created this
     way never need the code step.
  4. Backend returns the same kind of session token as password login.

**Before this works you need to fill in `Frontend/firebase-init.js`** with
your project's public web config (Firebase Console → Project Settings →
General → Your apps → Web app → SDK setup and configuration). That's the
`apiKey`/`authDomain`/`projectId`/`appId` object — safe to expose client-side,
and a completely different thing from the service-account key described
above (which stays server-side only, never in the frontend).

If a user originally signed up with email+password and later hits
"Continue with Google" using the same email, the two are linked into one
account rather than creating a duplicate.

## Subscription plans

| Plan | Price/mo | Analyses/day (~/mo) | Seats | Priority support |
|---|---|---|---|---|
| `starter` | $24 | 1 (~30) | 1 | No |
| `growth` | $69 | 5 (~150) | 1 | No |
| `pro` | $179 | 20 (~600) | up to 5 | Yes |

Defined in `config.py` (`PLANS`), tunable via env vars without a code
change (`PLAN_STARTER_LIMIT`, `PLAN_GROWTH_LIMIT`, `PLAN_PRO_LIMIT`,
`PLAN_PRO_SEATS`).

**These are launch prices, not scientifically-derived ones** — they assume
a rough cost-per-analysis that hasn't been measured against real Inference
Providers billing yet. Before scaling paid signups, check your actual
$-per-`/analyze`-call (each call fans out into ~10 chained LLM requests)
against these limits and adjust before they bite you on margin.

### Free trials (no card required)

Every tier has a free trial — the user picks which one to try, no payment
info needed. One trial per account, ever, regardless of which tier.

| Plan | Trial length | Trial analyses/day | Bonus days if you convert to paid |
|---|---|---|---|
| `starter` | 14 days | 1 | — |
| `growth` | 14 days | 2 | +7 days |
| `pro` | 14 days | 3 | +14 days |

Trial limits are deliberately lower than the plan's paid daily limit
(e.g. growth trial is 2/day vs. growth paid's 5/day) — enough to
demonstrate value without giving away full usage for free. See
`config.TRIAL_PLANS`, `billing.start_trial()`, and
`POST /billing/start-trial` / `GET /trials` in `main.py`.

**The conversion bonus** only applies the first time someone subscribes
(for real money) to the *exact same tier* they trialed, and only once —
renewing that plan again later doesn't stack another bonus
(`User.trial_bonus_granted` tracks this). Trialing `growth` then paying
for `pro` gets a plain 30-day pro subscription, no bonus; trialing
`growth` then paying for `growth` gets 30 + 7 = 37 days.

Trials don't unlock team seats — `/team/*` endpoints require a real paid
Pro subscription (`status == "active"`, not `"trial"`), even though a
pro trial otherwise behaves like an active subscription for `/analyze`
purposes.

### Team seats (Pro plan)

A Pro subscriber can invite up to `max_seats` teammates to use *their*
subscription — teammates don't pay separately or need their own plan.
See `/team/members` (GET), `/team/invite` (POST, by email — the invitee
must already have an AI Analyst account), and `/team/members/{id}`
(DELETE) in `main.py`. A teammate's access resolves through
`billing.get_effective_subscription()`, which looks at the team owner's
subscription instead of the teammate's own (they don't have one). Usage
limits are enforced **per seat**, not pooled — each teammate gets their
own full daily allowance sized off the owner's plan, which is simpler to
reason about than a shared pool while still bounding total team spend to
`seats × plan limit` per day.

## How billing works

1. `POST /billing/checkout {"plan": "starter"}` — creates a pending
   payment transaction, asks Paymob for a payment iframe URL, returns it.
2. User pays on Paymob's hosted page.
3. Paymob calls `POST /payments/paymob/webhook?hmac=...`. The HMAC is
   verified against `PAYMOB_HMAC_SECRET` before anything is trusted.
4. On success, the subscription is activated — renewals extend from the
   current expiry, not from "now", so paying early never loses time
   already paid for (`billing.py::activate_subscription`, covered by
   `tests/test_billing.py::test_renewal_extends_from_existing_expiry_not_from_now`).
5. On failure, the transaction is marked failed.

`DEV_ACCESS_PASSWORD` logs you in as an "owner" pseudo-account that
bypasses billing and rate limits entirely, so you can try the whole app
without paying yourself. Leave it blank once you have real customers.

Self-service cancel: `POST /billing/cancel` ends access immediately (no
refund). Admin refund: `POST /admin/users/{id}/refund` calls Paymob's
refund API and revokes access — gated by `ADMIN_EMAILS`.

## Running locally

```bash
cd AI_Analyst_App
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt

cp ../.env.example .env
# edit .env: at minimum set HF_TOKEN, your local Postgres DB_* values,
# and FIREBASE_SERVICE_ACCOUNT_PATH pointing at your downloaded key file.

python main.py
# -> http://127.0.0.1:8000  (frontend + API)
# -> http://127.0.0.1:8000/docs  (interactive API docs)
```

Use `DEV_ACCESS_PASSWORD` in `.env` and log in with just a password (no
email) to bypass billing entirely while developing.

## Running the tests

```bash
cd AI_Analyst_App
pip install -r ../requirements.txt   # includes pytest + httpx
pytest
```

52 tests, no real credentials or network access needed — the LLM, the
business database, and Paymob's network calls are mocked, and the app's
own data layer runs against `tests/fake_firestore.py`: an in-memory
implementation that mirrors `firestore_db.FirestoreDB`'s exact method
signatures, wired in via FastAPI's `dependency_overrides`. Real Firestore
connectivity is a separate, one-time check — see `scripts/smoke_test.py`.

Covers: signup/login/duplicate email/wrong password, email verification
and password reset (both read the dev-fallback console log for the link,
no real inbox needed), protected-route auth, plan listing, checkout,
webhook HMAC verification, subscription activation and renewal math,
failed-payment handling, self-service cancel, admin list/grant/revoke/
refund, the `/analyze` billing gate, per-plan rate limiting (including the
owner bypass), report persistence, pagination, per-user isolation, PDF
export, and structural checks on every prompt in `prompts.py`.

## Verifying against real credentials

```bash
cd AI_Analyst_App
# fill in real DB_*, FIREBASE_*, and HF_TOKEN in .env first
python scripts/smoke_test.py
```

Four checks: business DB connection, business DB schema read, a real
Firestore write/read/delete, and one real Hugging Face call. Tells you
exactly which credential is wrong if something fails.

## Deploying on Railway

No Docker. Railway runs the app directly via Nixpacks + the start command
in `railway.json` / `Procfile`:

```
cd AI_Analyst_App && uvicorn main:app --host 0.0.0.0 --port $PORT
```

Steps:

1. **Push this repo to GitHub**, then in Railway: New Project -> Deploy
   from GitHub repo.
2. **Add a Postgres plugin** in Railway for the business database (the
   customer data the AI queries). Railway gives you `PGHOST`, `PGPORT`,
   `PGUSER`, `PGPASSWORD`, `PGDATABASE` — map these to `DB_HOST`,
   `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` in your service's
   Variables tab (Railway doesn't auto-map these, since this app uses
   its own `DB_*` names to stay database-agnostic).
3. **Set every variable from `.env.example`** in Railway's Variables tab
   — nothing reads a `.env` file in production, Railway injects real
   process env vars. At minimum: `HF_TOKEN`, `DB_*`,
   `FIREBASE_SERVICE_ACCOUNT_JSON` (paste the whole key JSON as one
   value), `JWT_SECRET`, `ADMIN_EMAILS`.
4. **Set `APP_MODE=server`.** Makes the app bind `0.0.0.0`, which Railway
   requires.
5. **Don't set `PORT` yourself** — Railway injects it, and the app already
   reads `$PORT`.
6. Railway gives you a public domain and HTTPS automatically — no reverse
   proxy or certificate setup needed.
7. **Rotate the Hugging Face token and DB password** that were in the
   originally uploaded project — unrelated to hosting, still true.
8. Once deployed, run the smoke test from your own machine against the
   same credentials to confirm real connectivity before announcing the app.

**Free/low tiers:** if your Railway plan sleeps the service after
inactivity, the first request after a sleep — especially an `/analyze`
call, which is already slow (10-15 LLM calls) — could time out. Watch for
this and consider a paid tier if it becomes an issue.

## Admin access

Set `ADMIN_EMAILS` (comma-separated) in your env vars. Any account that
signs up normally with one of those emails gets:

- `GET /admin/users` — list all users, paginated, with subscription status
- `POST /admin/users/{id}/grant` — manually grant access (comps, support)
- `POST /admin/users/{id}/revoke` — immediately end a user's access
- `POST /admin/users/{id}/refund` — refund their latest payment via
  Paymob and revoke access

Every admin action is logged to Firestore's `admin_actions` collection
with the admin's email, target user, action, and detail.

## Project layout

```
AI_Analyst_App/
  main.py             FastAPI app: auth, billing, analyze, reports, webhook, admin
  pipeline.py          the analysis pipeline itself
  auth.py              password hashing, signed session tokens, admin check
  billing.py            plan catalog, Paymob checkout, subscription/refund logic
  paymob.py             Paymob API client + webhook HMAC verification + refunds
  ratelimit.py           per-plan daily cap on /analyze
  logging_config.py      structured logging + optional Sentry
  email_utils.py          verification/reset emails (console fallback if no SMTP)
  firestore_db.py          Firestore data access layer (the app's own data)
  schemas.py                plain dataclasses shared by firestore_db.py and the test fake
  utils.py                  shared utcnow()/to_iso()/parse_iso() helpers
  config.py                 all settings, env-driven
  database.py                Postgres access to the CUSTOMER's business data
  analysis.py                 pandas/numpy/scipy computations
  chains.py                    LLM calls per pipeline stage
  prompts.py                    prompt templates for each stage
  security.py                   SQL validation (read-only, keyword blocklist)
  pdf_generator.py                PDF report builder (fpdf2)
  scripts/smoke_test.py            one-command real-credential verification
  tests/                            pytest suite (52 tests)
    fake_firestore.py                in-memory Firestore stand-in for tests
Frontend/                            static web UI (served by the API)
Procfile / railway.json              Railway start command, no Docker
requirements.txt
.env.example
```

## What changed across every round of work on this project

**Round 1 — correctness pass:** removed hardcoded Postgres password and a
live Hugging Face token that were committed in the original upload
(rotate that token). Fixed a broken `test_db.py`, a stray invalid escape
sequence, split a one-shot script into a real pipeline module + FastAPI
server, added local/server mode switching, a Paymob stub, a dev password
gate, PDF export, and a basic frontend.

**Round 2 — prompt correctness pass:** found 9 of 12 core prompts were
silently duplicated in `prompts.py` (Python used whichever definition
came second — in 5 cases, the worse one). Found `moreanalysis_prompt` was
one 650-line string with 8 other fully-written prompts pasted inside it,
never closed as their own strings, completely unusable. Extracted and
repaired all 8, added 2 more, rewired `chains.py` so each analysis type
gets its own focused LLM call, fixed `pdf_generator.py` silently dropping
that whole section, modernized deprecated fpdf2 calls.

**Round 3 — production-readiness pass:** real per-user accounts (bcrypt,
signed tokens, per-user isolation), subscription billing tied to Paymob
with correct renewal math, persistent report history, a database-backed
daily rate limit, structured logging with optional Sentry, a 35-test
suite that caught two real bugs (a subscription-renewal bug creating
duplicate rows, and deprecated API calls), and a smoke-test script.

**Round 4 — feature completion pass:** per-plan rate limits (20/40/80 per
day), full email verification + password reset flow (console fallback
when SMTP isn't configured), admin endpoints (list/grant/revoke/refund)
gated by `ADMIN_EMAILS`, self-service cancellation, report pagination,
and a startup warning about dev-only databases in server mode. Test
suite grew to 52.

**Round 5 — this round:** removed Docker entirely per request — runs with
plain `uvicorn`, `Procfile`/`railway.json` for Railway. Replaced the SQL
app-database layer with Firestore: designed the collection layout
specifically to need zero manually-created composite indexes
(subcollections for per-user data, a lightweight pointer collection for
the Paymob webhook lookup). Rewrote `auth.py`, `billing.py`,
`ratelimit.py`, and `main.py` against the new `firestore_db.py` layer.
Built `tests/fake_firestore.py` mirroring the real interface exactly so
the 52-test suite still runs hermetically. Verified your real service
account key parses and authenticates correctly with the Firestore client
library — the actual network round-trip couldn't be tested from this
sandboxed environment (no access to `*.googleapis.com` here), so
`scripts/smoke_test.py` now includes a real Firestore write/read/delete
check for you to run once deployed. The key file was deleted from this
environment immediately after use.