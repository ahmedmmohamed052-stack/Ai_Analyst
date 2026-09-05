"""
FastAPI entrypoint for the AI Analyst SaaS.

Run locally:
    python main.py
    # or: uvicorn main:app --reload --host 127.0.0.1 --port 8000

On Railway: no Docker, no docker-compose. Railway runs this directly via
Procfile / railway.json:
    uvicorn main:app --host 0.0.0.0 --port $PORT
Railway injects $PORT itself — don't hardcode it.

Switch to a real server later by setting env vars:
    APP_MODE=server
    HOST=0.0.0.0
    ALLOWED_ORIGINS=https://yourdomain.com
No code changes needed — see config.py for everything APP_MODE controls.
"""
import datetime
import json
import os
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from auth import (
    create_owner_token_if_password_matches,
    create_token,
    generate_otp_code,
    generate_token_string,
    get_current_user,
    hash_password,
    require_admin,
    verify_firebase_id_token,
    verify_password,
)
from billing import (
    InvalidPlan,
    NoRefundableTransaction,
    TrialAlreadyUsed,
    admin_grant,
    cancel_subscription,
    get_active_subscription,
    get_effective_subscription,
    handle_failed_payment,
    handle_successful_payment,
    refund_latest_payment,
    start_checkout,
    start_trial,
)
from config import (
    ADMIN_EMAILS,
    ALLOWED_ORIGINS,
    APP_MODE,
    ENABLE_DOCS,
    EMAIL_VERIFICATION_TTL_HOURS,
    EMAIL_OTP_TTL_MINUTES,
    MAX_UPLOAD_ROWS,
    DATASET_ROW_CHUNK_SIZE,
    HOST,
    PASSWORD_RESET_TTL_MINUTES,
    PAYMOB_CONFIGURED,
    PLANS,
    TRIAL_PLANS,
    PORT,
    REQUIRE_EMAIL_VERIFICATION,
)
import pandas as pd

from datasources import (
    DataSourceError,
    build_external_datasource,
    build_file_datasource,
    test_external_connection,
    SUPPORTED_DB_TYPES,
)
from security import encrypt_secret
from email_utils import send_password_reset_email, send_verification_email
from firestore_db import FirestoreDB, get_db
from logging_config import logger
from paymob import PaymobNotConfigured, build_transaction_hmac_string, verify_webhook_hmac
from pdf_generator import generate_pipeline_pdf
from pipeline import run_pipeline
from ratelimit import check_and_record_usage
from schemas import Subscription, User
from utils import to_iso, utcnow


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"AI Analyst starting in {APP_MODE} mode.")
    # Skip the real Firestore fail-fast check when a test has overridden
    # get_db (app.dependency_overrides) — this call bypasses FastAPI's DI
    # system since it's not resolved through Depends().
    if get_db not in app.dependency_overrides:
        try:
            get_db()  # fail fast at startup if Firestore credentials are missing/bad
            logger.info("Firestore connection initialized.")
        except Exception as e:
            logger.error(f"Firestore initialization failed: {e}")
            raise
    yield


app = FastAPI(
    title="AI Analyst",
    description="Ask a business question in plain English, get an AI-driven data analysis pipeline back.",
    version="3.0.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(f'{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)')
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ── Schemas ──────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: Optional[EmailStr] = None
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AnalyzeRequest(BaseModel):
    question: str
    dataset_id: str
    # When set, this is a follow-up refining an earlier report — the pipeline
    # is given that report's question + result as context so the AI can
    # improve on its own prior answer instead of starting from scratch.
    prior_report_id: Optional[str] = None


class ConnectDatabaseRequest(BaseModel):
    name: str
    db_type: str  # "postgres" | "mysql"
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"


class VerifyEmailCodeRequest(BaseModel):
    email: EmailStr
    code: str


class FirebaseLoginRequest(BaseModel):
    id_token: str


class CheckoutRequest(BaseModel):
    plan: str


class StartTrialRequest(BaseModel):
    plan: str


class TeamInviteRequest(BaseModel):
    email: EmailStr


class RequestPasswordReset(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str


class AdminGrantRequest(BaseModel):
    plan: str
    days: Optional[int] = None


# ── Health / meta ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": APP_MODE,
        "paymob_configured": PAYMOB_CONFIGURED,
    }


@app.get("/plans")
def plans():
    return {
        plan_id: {
            "label": p["label"],
            "price_usd": p["price_usd"],
            "duration_days": p["duration_days"],
            "analyze_per_day": p["analyze_per_day"],
            "max_seats": p["max_seats"],
            "priority_support": p["priority_support"],
        }
        for plan_id, p in PLANS.items()
    }


# ── Auth: real accounts ───────────────────────────────────────────────────
@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: FirestoreDB = Depends(get_db)):
    existing = db.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(409, "An account with this email already exists.")

    code = generate_otp_code()
    user = db.create_user(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name or None,
    )
    db.update_user(
        user.id,
        verification_token=code,
        verification_token_expires=to_iso(utcnow() + datetime.timedelta(minutes=EMAIL_OTP_TTL_MINUTES)),
    )

    send_verification_email(user.email, code)
    logger.info(f"New signup: {user.email}")
    return TokenResponse(access_token=create_token(user.id))


@app.post("/auth/verify-email")
def verify_email(payload: VerifyEmailCodeRequest, db: FirestoreDB = Depends(get_db)):
    user = db.get_user_by_email(payload.email)
    if (
        not user
        or not user.verification_token
        or not user.verification_token_expires
        or user.verification_token != payload.code.strip()
    ):
        raise HTTPException(400, "That code is incorrect or has expired.")
    if datetime.datetime.fromisoformat(user.verification_token_expires) < utcnow():
        raise HTTPException(400, "That code is incorrect or has expired.")

    db.update_user(user.id, email_verified=True, verification_token=None, verification_token_expires=None)
    return {"verified": True}


@app.post("/auth/resend-verification")
def resend_verification(user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    if getattr(user, "is_owner", False):
        raise HTTPException(400, "The owner account doesn't need email verification.")
    if user.email_verified:
        return {"already_verified": True}

    code = generate_otp_code()
    db.update_user(
        user.id,
        verification_token=code,
        verification_token_expires=to_iso(utcnow() + datetime.timedelta(minutes=EMAIL_OTP_TTL_MINUTES)),
    )
    send_verification_email(user.email, code)
    return {"sent": True}


@app.post("/auth/request-password-reset")
def request_password_reset(payload: RequestPasswordReset, db: FirestoreDB = Depends(get_db)):
    user = db.get_user_by_email(payload.email)
    # Always return the same response whether or not the account exists,
    # so this endpoint can't be used to enumerate registered emails.
    if user:
        token = generate_token_string()
        db.update_user(
            user.id,
            reset_token=token,
            reset_token_expires=to_iso(utcnow() + datetime.timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)),
        )
        send_password_reset_email(user.email, token)
    return {"sent": True}


@app.post("/auth/reset-password")
def reset_password(payload: ResetPassword, db: FirestoreDB = Depends(get_db)):
    user = db.get_user_by_reset_token(payload.token)
    if not user or not user.reset_token_expires:
        raise HTTPException(400, "Reset link is invalid or has expired.")
    if datetime.datetime.fromisoformat(user.reset_token_expires) < utcnow():
        raise HTTPException(400, "Reset link is invalid or has expired.")

    db.update_user(
        user.id,
        hashed_password=hash_password(payload.new_password),
        reset_token=None,
        reset_token_expires=None,
    )
    return {"reset": True}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: FirestoreDB = Depends(get_db)):
    # Developer shortcut: DEV_ACCESS_PASSWORD (if set) logs in as the owner
    # account regardless of email, bypassing the subscription gate.
    owner_token = create_owner_token_if_password_matches(payload.password)
    if owner_token:
        return TokenResponse(access_token=owner_token)

    if not payload.email:
        raise HTTPException(401, "Email and password required.")

    user = db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password.")

    return TokenResponse(access_token=create_token(user.id))


@app.post("/auth/firebase", response_model=TokenResponse)
def firebase_login(payload: FirebaseLoginRequest, db: FirestoreDB = Depends(get_db)):
    """Log in or sign up via Google / Apple. The frontend uses the Firebase JS
    SDK to run the provider's sign-in flow and get an ID token, then sends it
    here — we verify it server-side and issue our own app session token, same
    as password login. Firebase has already confirmed the identity, so these
    accounts are marked email_verified immediately."""
    try:
        claims = verify_firebase_id_token(payload.id_token)
    except Exception:
        raise HTTPException(401, "Could not verify sign-in — please try again.")

    firebase_uid = claims.get("uid") or claims.get("sub")
    email = claims.get("email", "")
    if not firebase_uid or not email:
        raise HTTPException(400, "That account has no email on file.")

    provider = "google"
    sign_in_provider = (claims.get("firebase", {}) or {}).get("sign_in_provider", "")
    if "apple" in sign_in_provider:
        provider = "apple"

    user = db.get_or_create_oauth_user(
        firebase_uid=firebase_uid,
        email=email,
        full_name=claims.get("name"),
        provider=provider,
        photo_url=claims.get("picture"),
    )
    return TokenResponse(access_token=create_token(user.id))


@app.get("/me")
def me(user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    if getattr(user, "is_owner", False):
        return {"email": user.email, "is_owner": True, "email_verified": True, "subscription": None}

    effective_sub = get_effective_subscription(db, user)
    team_role = None
    if user.team_owner_id:
        team_role = "member"
    elif effective_sub and PLANS.get(effective_sub.plan, {}).get("max_seats", 1) > 1:
        team_role = "owner"

    return {
        "email": user.email,
        "full_name": user.full_name,
        "is_owner": False,
        "email_verified": user.email_verified,
        "auth_provider": user.auth_provider,
        "photo_url": user.photo_url,
        "is_admin": user.email.lower() in ADMIN_EMAILS,
        "subscription": (
            {
                "plan": effective_sub.plan,
                "status": effective_sub.status,
                "expires_at": effective_sub.expires_at,
            }
            if effective_sub else None
        ),
        "trial_used": user.trial_plan is not None,
        "team_role": team_role,
    }


# ── Billing ──────────────────────────────────────────────────────────────
@app.post("/billing/checkout")
def checkout(payload: CheckoutRequest, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    if getattr(user, "is_owner", False):
        raise HTTPException(400, "The owner account doesn't need a subscription.")
    if REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(403, "Please verify your email before subscribing.")

    try:
        result = start_checkout(db, user, payload.plan)
    except InvalidPlan as e:
        raise HTTPException(400, str(e))
    except PaymobNotConfigured as e:
        raise HTTPException(503, str(e))

    return result


@app.get("/trials")
def trials():
    """Free-trial terms per tier — shown alongside /plans so the frontend
    can offer 'Start free trial' next to 'Choose' without a card."""
    return TRIAL_PLANS


@app.post("/billing/start-trial")
def start_trial_endpoint(
    payload: StartTrialRequest, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)
):
    if getattr(user, "is_owner", False):
        raise HTTPException(400, "The owner account doesn't need a trial.")
    if user.team_owner_id:
        raise HTTPException(400, "You're already using a teammate seat on someone else's plan.")
    try:
        subscription = start_trial(db, user, payload.plan)
    except InvalidPlan as e:
        raise HTTPException(400, str(e))
    except TrialAlreadyUsed as e:
        raise HTTPException(400, str(e))
    return {"plan": subscription.plan, "status": subscription.status, "expires_at": subscription.expires_at}


@app.post("/billing/cancel")
def cancel(user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    """Self-service cancel — ends access immediately. Does not refund money;
    see /admin/users/{id}/refund for that."""
    if getattr(user, "is_owner", False):
        raise HTTPException(400, "The owner account has no subscription to cancel.")
    try:
        cancel_subscription(db, user.id)
    except NoRefundableTransaction as e:
        raise HTTPException(400, str(e))
    return {"canceled": True}


# ── Team seats (Pro plan) ───────────────────────────────────────────────
def _require_team_owner(user: User, db: FirestoreDB) -> Subscription:
    if user.team_owner_id:
        raise HTTPException(400, "You're a teammate on someone else's plan, not a team owner.")
    sub = get_active_subscription(db, user.id)
    # Trials are single-seat regardless of which tier is being tried — team
    # invites need a real paid Pro subscription, not a Pro trial.
    max_seats = PLANS.get(sub.plan, {}).get("max_seats", 1) if (sub and sub.status == "active") else 1
    if not sub or sub.status != "active" or max_seats <= 1:
        raise HTTPException(402, "Team seats require an active (paid) Pro plan subscription.")
    return sub


@app.get("/team/members")
def list_team_members(user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    sub = _require_team_owner(user, db)
    members = db.list_team_members(user.id)
    return {
        "max_seats": PLANS[sub.plan]["max_seats"],
        "used_seats": 1 + len(members),  # the owner counts as a seat
        "members": [{"id": m.id, "email": m.email, "full_name": m.full_name} for m in members],
    }


@app.post("/team/invite")
def invite_team_member(
    payload: TeamInviteRequest, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)
):
    sub = _require_team_owner(user, db)
    max_seats = PLANS[sub.plan]["max_seats"]

    existing_members = db.list_team_members(user.id)
    if 1 + len(existing_members) >= max_seats:
        raise HTTPException(400, f"Your plan supports up to {max_seats} seats — remove one before inviting another.")

    invitee = db.get_user_by_email(payload.email)
    if not invitee:
        raise HTTPException(
            404, "That person needs to create an AI Analyst account first, then you can add them to your team."
        )
    if invitee.id == user.id:
        raise HTTPException(400, "You can't invite yourself.")
    if invitee.team_owner_id:
        raise HTTPException(400, "That person is already on a team.")

    db.set_team_owner(invitee.id, user.id)
    return {"added": True, "email": invitee.email}


@app.delete("/team/members/{member_id}")
def remove_team_member(
    member_id: str, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)
):
    _require_team_owner(user, db)
    member = db.get_user_by_id(member_id)
    if not member or member.team_owner_id != user.id:
        raise HTTPException(404, "That person isn't on your team.")
    db.set_team_owner(member_id, None)
    return {"removed": True}


@app.post("/payments/paymob/webhook")
async def paymob_webhook(request: Request, db: FirestoreDB = Depends(get_db)):
    body = await request.json()
    obj = body.get("obj", body)  # Paymob nests transaction fields under "obj"

    received_hmac = request.query_params.get("hmac", "")
    if not received_hmac:
        raise HTTPException(400, "Missing hmac query parameter.")

    ordered_fields = build_transaction_hmac_string(obj)
    try:
        valid = verify_webhook_hmac(received_hmac, ordered_fields)
    except PaymobNotConfigured:
        raise HTTPException(503, "Paymob is not configured.")

    if not valid:
        logger.warning("Rejected Paymob webhook: HMAC mismatch.")
        raise HTTPException(400, "Invalid HMAC signature.")

    order_id = str(obj.get("order", {}).get("id", ""))
    success = bool(obj.get("success"))

    transaction = db.get_transaction_by_order_id(order_id)
    if not transaction:
        logger.warning(f"Paymob webhook for unknown order_id={order_id}")
        return {"received": True}  # ack anyway so Paymob doesn't retry forever

    if transaction.status != "pending":
        return {"received": True, "note": "Transaction already finalized."}

    db.update_transaction(
        transaction.user_id, transaction.id,
        paymob_transaction_id=str(obj.get("id", "")),
        raw_webhook_payload=json.dumps(obj),
    )
    transaction = db.get_transaction(transaction.user_id, transaction.id)

    if success:
        handle_successful_payment(db, transaction)
        logger.info(f"Payment succeeded: user={transaction.user_id} plan={transaction.plan}")
    else:
        handle_failed_payment(db, transaction)
        logger.info(f"Payment failed: user={transaction.user_id} plan={transaction.plan}")

    return {"received": True}


# ── Subscription gate ────────────────────────────────────────────────────
def require_active_subscription(
    user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)
) -> User:
    if getattr(user, "is_owner", False):
        return user
    if REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(403, "Please verify your email before running analyses.")
    if not get_effective_subscription(db, user):
        raise HTTPException(402, "An active subscription is required. See /plans and /billing/checkout.")
    return user


# ── Datasets: each user connects their own DB or uploads their own file ──
def get_datasource_for_dataset(user_id: str, dataset_id: str, db: FirestoreDB):
    dataset = db.get_dataset(user_id, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    try:
        if dataset["source_type"] == "external_db":
            return build_external_datasource(dataset)
        rows = db.get_dataset_rows(user_id, dataset_id)
        return build_file_datasource(rows)
    except DataSourceError as e:
        raise HTTPException(422, str(e))


@app.get("/datasets")
def list_datasets(user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    datasets = db.list_datasets(user.id)
    # never leak encrypted_password, even as ciphertext
    return [
        {k: v for k, v in d.items() if k != "encrypted_password"}
        for d in datasets
    ]


@app.post("/datasets/connect")
def connect_database(
    payload: ConnectDatabaseRequest,
    user: User = Depends(get_current_user),
    db: FirestoreDB = Depends(get_db),
):
    if payload.db_type not in SUPPORTED_DB_TYPES:
        raise HTTPException(400, f"db_type must be one of {SUPPORTED_DB_TYPES}.")

    try:
        test_external_connection(
            payload.db_type, payload.host, payload.port, payload.database,
            payload.user, payload.password, payload.sslmode,
        )
    except DataSourceError as e:
        raise HTTPException(400, f"Could not connect with those credentials: {e}")

    encrypted = encrypt_secret(payload.password)
    dataset = db.create_external_dataset(
        user.id, payload.name, payload.db_type, payload.host, payload.port,
        payload.database, payload.user, encrypted, payload.sslmode,
    )
    dataset.pop("encrypted_password", None)
    return dataset


@app.post("/datasets/upload")
def upload_dataset(
    name: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: FirestoreDB = Depends(get_db),
):
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(file.file)
        else:
            raise HTTPException(400, "Only .csv, .xlsx, or .xls files are supported.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not read that file: {e}")

    if df.empty:
        raise HTTPException(400, "That file has no rows.")
    if len(df) > MAX_UPLOAD_ROWS:
        raise HTTPException(400, f"That file has more than {MAX_UPLOAD_ROWS} rows — trim it and try again.")

    # Firestore doesn't store NaN/NaT — normalize to None, and make sure
    # everything is JSON-safe (Timestamps -> ISO strings, numpy scalars -> py).
    df = df.where(pd.notnull(df), None)
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].apply(lambda v: v.isoformat() if v is not None else None)
    records = json.loads(df.to_json(orient="records"))

    columns = [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns]
    row_chunks = [
        records[i:i + DATASET_ROW_CHUNK_SIZE]
        for i in range(0, len(records), DATASET_ROW_CHUNK_SIZE)
    ]
    dataset = db.create_file_dataset(user.id, name, columns, row_chunks)
    return dataset


@app.delete("/datasets/{dataset_id}")
def delete_dataset(
    dataset_id: str, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)
):
    if not db.get_dataset(user.id, dataset_id):
        raise HTTPException(404, "Dataset not found.")
    db.delete_dataset(user.id, dataset_id)
    return {"deleted": True}


# ── Core analysis pipeline ───────────────────────────────────────────────
@app.get("/schema")
def schema(
    dataset_id: str,
    user: User = Depends(require_active_subscription),
    db: FirestoreDB = Depends(get_db),
):
    data_source = get_datasource_for_dataset(user.id, dataset_id, db)
    try:
        return data_source.get_schema()
    except DataSourceError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Could not read schema: {e}")


@app.post("/analyze")
def analyze(
    payload: AnalyzeRequest,
    user: User = Depends(require_active_subscription),
    db: FirestoreDB = Depends(get_db),
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "Question cannot be empty.")

    data_source = get_datasource_for_dataset(user.id, payload.dataset_id, db)

    check_and_record_usage(db, user)

    pipeline_question = question
    if payload.prior_report_id:
        prior = db.get_report(user.id, payload.prior_report_id)
        if prior:
            try:
                prior_result = json.loads(prior.result_json)
            except Exception:
                prior_result = {}
            prior_summary = prior_result.get("insights") or prior_result.get("recommendations") or ""
            pipeline_question = (
                f"This is a follow-up that should improve on a previous analysis.\n"
                f"Previous question: {prior.question}\n"
                f"Previous key findings: {prior_summary}\n\n"
                f"New request: {question}"
            )

    try:
        result = run_pipeline(pipeline_question, data_source)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"Pipeline failed for user={user.id}: {e}")
        raise HTTPException(422, f"Analysis failed: {e}")

    report = db.create_report(user.id, question, json.dumps(result))
    return {"report_id": report.id, **result}


@app.get("/reports")
def list_reports(
    user: User = Depends(get_current_user),
    db: FirestoreDB = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    limit = max(1, min(limit, 100))  # cap page size so no one can request the entire history
    offset = max(0, offset)

    reports, total = db.list_reports(user.id, limit, offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{"id": r.id, "question": r.question, "created_at": r.created_at} for r in reports],
    }


@app.get("/report/{report_id}/pdf")
def report_pdf(report_id: str, user: User = Depends(get_current_user), db: FirestoreDB = Depends(get_db)):
    report = db.get_report(user.id, report_id)
    if not report:
        raise HTTPException(404, "Report not found.")

    result = json.loads(report.result_json)
    tmp_path = os.path.join(tempfile.gettempdir(), f"{report_id}.pdf")
    generate_pipeline_pdf(result, filename=tmp_path)
    return FileResponse(tmp_path, media_type="application/pdf", filename="AI_Analyst_Report.pdf")


# ── Admin (list/grant/revoke/refund) ─────────────────────────────────────
# Gated by ADMIN_EMAILS in .env (or the owner account) — see auth.require_admin.
@app.get("/admin/users")
def admin_list_users(
    admin: User = Depends(require_admin),
    db: FirestoreDB = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    users, total = db.list_users(limit, offset)
    items = []
    for u in users:
        sub = u.subscription if u.subscription.is_active() else None
        items.append({
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "email_verified": u.email_verified,
            "created_at": u.created_at,
            "subscription": ({"plan": sub.plan, "expires_at": sub.expires_at} if sub else None),
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.post("/admin/users/{user_id}/grant")
def admin_grant_access(
    user_id: str,
    payload: AdminGrantRequest,
    admin: User = Depends(require_admin),
    db: FirestoreDB = Depends(get_db),
):
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")

    try:
        subscription = admin_grant(db, target, payload.plan, payload.days)
    except InvalidPlan as e:
        raise HTTPException(400, str(e))

    db.create_admin_action(admin.email, target.id, "grant", f"plan={payload.plan} days={payload.days}")
    logger.info(f"Admin {admin.email} granted {payload.plan} to {target.email}")

    return {"plan": subscription.plan, "expires_at": subscription.expires_at}


@app.post("/admin/users/{user_id}/revoke")
def admin_revoke_access(
    user_id: str,
    admin: User = Depends(require_admin),
    db: FirestoreDB = Depends(get_db),
):
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")

    try:
        cancel_subscription(db, target.id)
    except NoRefundableTransaction as e:
        raise HTTPException(400, str(e))

    db.create_admin_action(admin.email, target.id, "revoke")
    logger.info(f"Admin {admin.email} revoked access for {target.email}")
    return {"revoked": True}


@app.post("/admin/users/{user_id}/refund")
def admin_refund(
    user_id: str,
    admin: User = Depends(require_admin),
    db: FirestoreDB = Depends(get_db),
):
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")

    try:
        transaction = refund_latest_payment(db, target.id)
    except NoRefundableTransaction as e:
        raise HTTPException(400, str(e))
    except PaymobNotConfigured as e:
        raise HTTPException(503, str(e))

    db.create_admin_action(
        admin.email, target.id, "refund",
        f"transaction_id={transaction.id} amount_cents={transaction.amount_cents}",
    )
    logger.info(f"Admin {admin.email} refunded {target.email} (txn {transaction.id})")
    return {"refunded": True, "transaction_id": transaction.id}


# ── Frontend (static files) ──────────────────────────────────────────────
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=(APP_MODE == "local"))