"""
Plain dataclasses representing the app's data shapes. No ORM, no ties to
Firestore's document format — firestore_db.py converts Firestore documents
into these, and tests/fake_firestore.py does the same from a plain dict
store. The rest of the app (auth.py, billing.py, ratelimit.py, main.py)
only ever sees these.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Subscription:
    plan: Optional[str] = None
    status: str = "none"  # "none" | "pending" | "trial" | "active" | "canceled"
    started_at: Optional[str] = None   # ISO 8601 strings throughout —
    expires_at: Optional[str] = None   # Firestore stores real timestamps,
    canceled_at: Optional[str] = None  # but ISO strings keep this layer
                                        # simple and JSON-friendly.

    def is_active(self) -> bool:
        from utils import utcnow, parse_iso
        if self.status not in ("active", "trial") or not self.expires_at:
            return False
        return parse_iso(self.expires_at) > utcnow()

    def is_trial(self) -> bool:
        return self.status == "trial" and self.is_active()


@dataclass
class User:
    id: str
    email: str
    hashed_password: str = ""
    full_name: Optional[str] = None
    is_owner: bool = False  # synthetic dev/owner account — never a real Firestore doc
    email_verified: bool = False
    auth_provider: str = "password"  # "password" | "google" | "apple"
    firebase_uid: Optional[str] = None
    photo_url: Optional[str] = None
    # If set, this account is a teammate seat riding on another user's Pro
    # plan subscription (see /team/* endpoints) instead of having its own.
    team_owner_id: Optional[str] = None
    # Free trial tracking — one trial per account, ever, regardless of which
    # tier they pick. trial_plan is set the moment a trial starts and never
    # cleared (it's the historical record of which tier they tried, used to
    # decide conversion-bonus eligibility in billing.activate_subscription).
    trial_plan: Optional[str] = None
    trial_bonus_granted: bool = False
    verification_token: Optional[str] = None
    verification_token_expires: Optional[str] = None
    reset_token: Optional[str] = None
    reset_token_expires: Optional[str] = None
    created_at: Optional[str] = None
    subscription: Subscription = field(default_factory=Subscription)


@dataclass
class PaymentTransaction:
    id: str
    user_id: str
    plan: str
    amount_cents: int
    currency: str
    status: str = "pending"  # pending|success|failed|refunded
    paymob_order_id: Optional[str] = None
    paymob_transaction_id: Optional[str] = None
    raw_webhook_payload: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    refunded_at: Optional[str] = None


@dataclass
class Report:
    id: str
    user_id: str
    question: str
    result_json: str
    created_at: Optional[str] = None