import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ── Run mode ─────────────────────────────────────────────────────────────
# "local"  -> binds to 127.0.0.1, docs enabled, permissive CORS for dev
# "server" -> binds to 0.0.0.0, expects HTTPS/reverse proxy in front,
#             docs can be disabled, CORS restricted to ALLOWED_ORIGINS
# Nothing else in the codebase needs to change to switch between the two —
# just flip APP_MODE (env var) and set the related values below.
APP_MODE = os.getenv("APP_MODE", "local").strip().lower()
IS_SERVER = APP_MODE == "server"

HOST = os.getenv("HOST", "0.0.0.0" if IS_SERVER else "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Comma-separated list, e.g. "https://app.example.com,https://www.example.com"
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

ENABLE_DOCS = _get_bool("ENABLE_DOCS", default=not IS_SERVER)

# ── Database ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "ai"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}

# ── Per-user datasets ────────────────────────────────────────────────────
# Each user connects their own external database or uploads their own file
# (see datasources.py, firestore_db.py's dataset methods, and the
# /datasets/* endpoints in main.py) — there is no single shared app
# database anymore. DB_CONFIG / DATABASE_URL above are unused; kept only
# so `python pipeline.py`'s manual smoke test still has something to point
# at locally if you want to run it directly against a scratch Postgres.
#
# External database credentials are stored per-dataset in Firestore with
# the password encrypted at rest using this key. Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# and set it as DATASET_ENCRYPTION_KEY. If you don't set one, a key is
# derived from JWT_SECRET/SESSION_SECRET below (fine for local dev, but
# set a real one before you have real customer DB credentials stored).
DATASET_ENCRYPTION_KEY = os.getenv("DATASET_ENCRYPTION_KEY", "")

# Max rows accepted from an uploaded CSV/Excel file, and how many rows are
# batched into each Firestore document (a single doc must stay well under
# Firestore's 1MB-per-document limit).
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "200000"))
DATASET_ROW_CHUNK_SIZE = int(os.getenv("DATASET_ROW_CHUNK_SIZE", "500"))

# ── LLM (Hugging Face inference) ────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-4-Scout-17B-16E-Instruct")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.5"))
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "1000"))

# ── Developer / SaaS access gate ─────────────────────────────────────────
# Lightweight password gate so you (the developer) can try the SaaS end to
# end before real user accounts / billing exist. Not a substitute for real
# auth once you have paying users — swap in proper user accounts later.
DEV_ACCESS_PASSWORD = os.getenv("DEV_ACCESS_PASSWORD", "")
# Secret used to sign session tokens issued after a successful password check.
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-dev-secret")
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "720"))  # 12h

# ── Paymob payment gateway (placeholders — fill in when you have keys) ───
# Leave these blank for now. The paymob.py module reads them lazily and will
# clearly error out only when a payment is actually attempted, so the rest
# of the app runs fine without them.
PAYMOB_API_KEY = os.getenv("PAYMOB_API_KEY", "")
PAYMOB_INTEGRATION_ID = os.getenv("PAYMOB_INTEGRATION_ID", "")
PAYMOB_IFRAME_ID = os.getenv("PAYMOB_IFRAME_ID", "")
PAYMOB_HMAC_SECRET = os.getenv("PAYMOB_HMAC_SECRET", "")
PAYMOB_BASE_URL = os.getenv("PAYMOB_BASE_URL", "https://accept.paymob.com/api")
PAYMOB_CURRENCY = os.getenv("PAYMOB_CURRENCY", "EGP")

PAYMOB_CONFIGURED = all([
    PAYMOB_API_KEY, PAYMOB_INTEGRATION_ID, PAYMOB_IFRAME_ID, PAYMOB_HMAC_SECRET
])

# Paymob's EGP integration is the common path for Egyptian merchants; if
# your integration charges in EGP but you price plans in USD, set a
# conversion rate here. If you have a USD-capable integration instead, set
# PAYMOB_CURRENCY=USD above and leave this at 1.
PAYMOB_USD_TO_EGP_RATE = float(os.getenv("PAYMOB_USD_TO_EGP_RATE", "48.5"))

# ── Application database: Firestore (users, subscriptions, reports, payments) ──
# This is SEPARATE from DB_CONFIG above, which is the customer's own
# business database that gets queried for analysis. This app's own data
# (accounts, billing, report history) lives in Firestore instead.
#
# Two ways to provide credentials — pick one:
#   FIREBASE_SERVICE_ACCOUNT_JSON  — the *entire* service account JSON key,
#     pasted as one env var. Recommended for Railway (Variables tab).
#   FIREBASE_SERVICE_ACCOUNT_PATH  — a path to the key file on disk.
#     Convenient for local dev.
# Generate a key in Firebase Console -> Project Settings -> Service
# Accounts -> Generate new private key. The apiKey/appId in your web app's
# firebaseConfig are NOT usable here — those are for browser clients, not
# a server-side Admin SDK connection.
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
# Usually inferred from the service account key automatically; only needed
# if you want to override it explicitly.
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")

# ── Auth (real user accounts) ─────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-to-a-long-random-string")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", str(60 * 24 * 7)))  # 7 days

# ── Subscription plans (USD) ──────────────────────────────────────────────
# analyze_per_day: how many /analyze calls this plan allows per rolling 24h,
# per seat. max_seats: how many total user accounts (owner + invited
# teammates) can run under one subscription — see /team/* endpoints in
# main.py. Override any of these via env if you want to tune without a
# code change (e.g. PLAN_GROWTH_LIMIT=10).
PLANS = {
    "starter": {
        "label": "Starter", "price_usd": 24.0, "duration_days": 30,
        "analyze_per_day": int(os.getenv("PLAN_STARTER_LIMIT", "1")),
        "max_seats": 1, "priority_support": False,
    },
    "growth": {
        "label": "Growth", "price_usd": 69.0, "duration_days": 30,
        "analyze_per_day": int(os.getenv("PLAN_GROWTH_LIMIT", "5")),
        "max_seats": 1, "priority_support": False,
    },
    "pro": {
        "label": "Pro / Team", "price_usd": 179.0, "duration_days": 30,
        "analyze_per_day": int(os.getenv("PLAN_PRO_LIMIT", "20")),
        "max_seats": int(os.getenv("PLAN_PRO_SEATS", "5")), "priority_support": True,
    },
}

# ── Free trials (no card required) ────────────────────────────────────────
# One trial per account, ever — user picks which tier to try (see
# POST /billing/start-trial in main.py / billing.start_trial). Trial limits
# are intentionally lower than the plan's paid analyze_per_day; converting
# to a paid subscription for the SAME tier right after its trial grants a
# one-time bonus of extra days added on top of the normal paid duration
# (see billing.activate_subscription).
TRIAL_PLANS = {
    "starter": {"trial_days": 14, "trial_analyze_per_day": 1, "convert_bonus_days": 0},
    "growth": {"trial_days": 14, "trial_analyze_per_day": 2, "convert_bonus_days": 7},
    "pro": {"trial_days": 14, "trial_analyze_per_day": 3, "convert_bonus_days": 14},
}

# Fallback cap for accounts with no matching plan entry (shouldn't normally
# happen — every active subscription has a plan from PLANS above).
DEFAULT_ANALYZE_PER_DAY = int(os.getenv("MAX_ANALYZE_PER_DAY", "20"))

# ── Logging / error monitoring ────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SENTRY_DSN = os.getenv("SENTRY_DSN", "")  # optional; leave blank to disable


# ── Email (verification + password reset) ─────────────────────────────────
# If SMTP_HOST is blank, emails are logged to the console instead of sent —
# fine for local dev. Fill these in for real delivery (e.g. via SendGrid,
# Mailgun, Amazon SES, or your own mail server's SMTP credentials).
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "no-reply@ai-analyst.local")
SMTP_USE_TLS = _get_bool("SMTP_USE_TLS", default=True)

# Public base URL of this app, used to build links in verification/reset
# emails (e.g. "https://yourdomain.com"). Defaults to the local dev URL.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}")

EMAIL_VERIFICATION_TTL_HOURS = int(os.getenv("EMAIL_VERIFICATION_TTL_HOURS", "48"))
# How long a 6-digit email verification code stays valid for.
EMAIL_OTP_TTL_MINUTES = int(os.getenv("EMAIL_OTP_TTL_MINUTES", "15"))
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))

# Require a verified email before a user can subscribe or run analyses.
# Off by default so local/dev testing isn't blocked by SMTP not being
# configured — turn on once real email delivery works.
REQUIRE_EMAIL_VERIFICATION = _get_bool("REQUIRE_EMAIL_VERIFICATION", default=False)

# ── Admin access ────────────────────────────────────────────────────────
# Comma-separated emails that get admin endpoints (list/grant/revoke users)
# once they've signed up normally. No separate role system to manage —
# just add your own email here.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}