"""
Daily per-user cap on /analyze calls, sized by the user's actual plan.
Each call fans out into many LLM requests (one per interpretation stage),
so this is the main cost control against a runaway bill.

Team seats (Pro plan): each invited teammate gets their own full daily
allowance sized off the team owner's plan — usage is tracked per seat,
not pooled across the team. Simpler to reason about than a shared pool,
and still bounds total spend to (seats × owner's plan limit) per day.

Backed by a Firestore subcollection (users/{uid}/analyze_usage) rather
than an in-memory counter, so it survives restarts and works correctly
across multiple app instances (Railway can and will run more than one).
"""
import datetime

from fastapi import HTTPException, status

from billing import get_effective_subscription
from config import DEFAULT_ANALYZE_PER_DAY, PLANS, TRIAL_PLANS
from firestore_db import FirestoreDB
from schemas import User
from utils import to_iso, utcnow


def _limit_for(db: FirestoreDB, user: User) -> int:
    subscription = get_effective_subscription(db, user)
    if not subscription:
        return DEFAULT_ANALYZE_PER_DAY
    if subscription.status == "trial" and subscription.plan in TRIAL_PLANS:
        return TRIAL_PLANS[subscription.plan]["trial_analyze_per_day"]
    if subscription.plan in PLANS:
        return PLANS[subscription.plan]["analyze_per_day"]
    return DEFAULT_ANALYZE_PER_DAY


def check_and_record_usage(db: FirestoreDB, user: User) -> None:
    if getattr(user, "is_owner", False):
        return  # the dev/owner account is exempt from the cap

    limit = _limit_for(db, user)

    since = to_iso(utcnow() - datetime.timedelta(hours=24))
    count = db.count_recent_usage(user.id, since)

    if count >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Daily analysis limit reached ({limit} per 24h on your plan). Try again later.",
        )

    db.record_analyze_usage(user.id)