"""
Subscription billing tied to Paymob.

Flow:
  1. POST /billing/checkout {plan} -> creates a "pending" payment
     transaction (and marks the user's subscription "pending" if it
     wasn't already active), then asks Paymob for a payment iframe URL
     and returns it to the frontend. A pointer doc links the returned
     Paymob order id back to this transaction for the webhook.
  2. The user pays in Paymob's hosted iframe.
  3. Paymob calls POST /payments/paymob/webhook with the result. We verify
     the HMAC, look up the transaction via the order-id pointer, mark it
     success/failed, and on success activate (or extend) the subscription.

Renewal: a successful payment extends the subscription's expires_at from
its CURRENT expiry (not from "now") if it's still in the future — so
renewing early never loses paid time. If there's no active subscription,
it starts from now. The subscription is a single embedded field on the
user's Firestore document (one per user), not a separate collection —
there's nothing to "reuse the right row" here since there's only ever
one, which sidesteps the row-duplication bug an earlier SQL version had.
"""
import datetime
from typing import Optional

from config import PAYMOB_CURRENCY, PAYMOB_USD_TO_EGP_RATE, PLANS, TRIAL_PLANS
from firestore_db import FirestoreDB
from schemas import PaymentTransaction, Subscription, User
from utils import parse_iso, to_iso
from utils import utcnow as _utcnow


class InvalidPlan(Exception):
    pass


class NoRefundableTransaction(Exception):
    pass


class TrialAlreadyUsed(Exception):
    pass


def get_plan(plan_id: str) -> dict:
    plan = PLANS.get(plan_id)
    if not plan:
        raise InvalidPlan(f"Unknown plan '{plan_id}'. Valid plans: {list(PLANS)}")
    return plan


def _price_in_charge_currency(price_usd: float) -> int:
    """Returns the amount in cents/piastres, in whichever currency Paymob is
    configured to charge (config.PAYMOB_CURRENCY)."""
    if PAYMOB_CURRENCY.upper() == "USD":
        amount = price_usd
    else:
        amount = price_usd * PAYMOB_USD_TO_EGP_RATE
    return int(round(amount * 100))


def start_checkout(db: FirestoreDB, user: User, plan_id: str) -> dict:
    from paymob import PaymobNotConfigured, create_payment  # local import: keeps a
                                                              # missing Paymob config
                                                              # from breaking imports
                                                              # elsewhere

    plan = get_plan(plan_id)
    amount_cents = _price_in_charge_currency(plan["price_usd"])

    transaction = db.create_transaction(user.id, plan_id, amount_cents, PAYMOB_CURRENCY)

    if not user.subscription.is_active():
        user.subscription.status = "pending"
        db.update_subscription(user.id, user.subscription)

    try:
        result = create_payment(
            amount_cents=amount_cents,
            billing_data={
                "first_name": (user.full_name or "Customer").split(" ")[0],
                "last_name": " ".join((user.full_name or "Customer").split(" ")[1:]) or "N/A",
                "email": user.email,
                "phone_number": "+201000000000",
                "apartment": "NA", "floor": "NA", "street": "NA",
                "building": "NA", "shipping_method": "NA", "postal_code": "NA",
                "city": "NA", "country": "EG", "state": "NA",
            },
            merchant_order_id=transaction.id,
        )
    except PaymobNotConfigured:
        # Leave the transaction as "pending" — nothing to charge for yet.
        # The caller (main.py) turns this into a clean 503.
        raise

    order_id = str(result["order_id"])
    db.update_transaction(user.id, transaction.id, paymob_order_id=order_id)
    db.link_order_to_transaction(order_id, user.id, transaction.id)

    return {
        "transaction_id": transaction.id,
        "plan": plan_id,
        "amount_cents": amount_cents,
        "currency": PAYMOB_CURRENCY,
        "iframe_url": result["iframe_url"],
    }


def start_trial(db: FirestoreDB, user: User, plan_id: str) -> Subscription:
    """No card required. One trial per account, ever — the user picks which
    tier to try; trial limits (see config.TRIAL_PLANS) are lower than that
    plan's normal paid analyze_per_day. Converting to a PAID subscription
    for this same tier afterward grants a one-time bonus of extra days
    (see activate_subscription below)."""
    if plan_id not in TRIAL_PLANS:
        raise InvalidPlan(f"Unknown plan '{plan_id}'. Valid plans: {list(TRIAL_PLANS)}")
    if user.trial_plan is not None:
        raise TrialAlreadyUsed("You've already used your one free trial.")
    if user.subscription.is_active():
        raise TrialAlreadyUsed("You already have an active subscription.")

    trial = TRIAL_PLANS[plan_id]
    now = _utcnow()

    user.subscription.plan = plan_id
    user.subscription.status = "trial"
    user.subscription.started_at = to_iso(now)
    user.subscription.expires_at = to_iso(now + datetime.timedelta(days=trial["trial_days"]))
    user.subscription.canceled_at = None
    db.update_subscription(user.id, user.subscription)
    db.update_user(user.id, trial_plan=plan_id)
    return user.subscription


def activate_subscription(
    db: FirestoreDB, user_id: str, subscription: Subscription, plan_id: str,
    trial_plan: Optional[str] = None, trial_bonus_granted: bool = False,
) -> Subscription:
    plan = get_plan(plan_id)
    now = _utcnow()

    # Renewal: extend from the current expiry if it's still in the future
    # (so paying early never loses time already paid for); otherwise (new
    # subscription, or an expired one being renewed) start from now. A
    # trial's own expiry doesn't count as "time already paid for" — paying
    # for the same tier a trial was running on always starts the paid
    # clock fresh from now, on top of which the conversion bonus (below) is
    # added.
    current_expiry = parse_iso(subscription.expires_at) if subscription.expires_at else None
    base = current_expiry if (current_expiry and current_expiry > now and subscription.status == "active") else now
    duration_days = plan["duration_days"]

    # One-time conversion bonus: subscribing (for real money) to the exact
    # tier you free-trialed, the first time you do it, adds extra free days
    # on top of the normal paid duration.
    if trial_plan == plan_id and not trial_bonus_granted:
        duration_days += TRIAL_PLANS.get(plan_id, {}).get("convert_bonus_days", 0)
        db.update_user(user_id, trial_bonus_granted=True)

    new_expiry = base + datetime.timedelta(days=duration_days)

    subscription.plan = plan_id
    subscription.status = "active"
    subscription.started_at = subscription.started_at or to_iso(now)
    subscription.expires_at = to_iso(new_expiry)
    db.update_subscription(user_id, subscription)
    return subscription


def handle_successful_payment(db: FirestoreDB, transaction: PaymentTransaction) -> None:
    db.update_transaction(transaction.user_id, transaction.id, status="success")
    user = db.get_user_by_id(transaction.user_id)
    if user:
        activate_subscription(
            db, user.id, user.subscription, transaction.plan,
            trial_plan=user.trial_plan, trial_bonus_granted=user.trial_bonus_granted,
        )


def handle_failed_payment(db: FirestoreDB, transaction: PaymentTransaction) -> None:
    db.update_transaction(transaction.user_id, transaction.id, status="failed")
    user = db.get_user_by_id(transaction.user_id)
    if user and user.subscription.status == "pending":
        user.subscription.status = "canceled"
        db.update_subscription(user.id, user.subscription)


def get_active_subscription(db: FirestoreDB, user_id: str) -> Optional[Subscription]:
    user = db.get_user_by_id(user_id)
    if user and user.subscription.is_active():
        return user.subscription
    return None


def get_effective_subscription(db: FirestoreDB, user: User) -> Optional[Subscription]:
    """Like get_active_subscription, but for a teammate seat (user.team_owner_id
    set), resolves to the TEAM OWNER's subscription instead of the seat's own
    (a seat never has its own billing — see /team/* endpoints in main.py)."""
    if user.team_owner_id:
        return get_active_subscription(db, user.team_owner_id)
    return get_active_subscription(db, user.id)


def cancel_subscription(db: FirestoreDB, user_id: str) -> Subscription:
    """Immediately ends access — used for both a self-service cancel and an
    admin revoke. Does not touch Paymob; see refund_latest_payment() for
    actually returning money."""
    user = db.get_user_by_id(user_id)
    if not user or not user.subscription.is_active():
        raise NoRefundableTransaction("No active subscription to cancel.")

    now = _utcnow()
    user.subscription.status = "canceled"
    user.subscription.canceled_at = to_iso(now)
    user.subscription.expires_at = to_iso(now)  # access ends now, not at the original expiry
    db.update_subscription(user_id, user.subscription)
    return user.subscription


def refund_latest_payment(db: FirestoreDB, user_id: str) -> PaymentTransaction:
    """Refunds the user's most recent successful payment via Paymob, and
    cancels their subscription immediately."""
    from paymob import refund_transaction  # local import: avoids a hard dependency
                                            # on Paymob being configured for callers
                                            # that never hit this path

    transaction = db.get_latest_successful_transaction(user_id)
    if not transaction:
        raise NoRefundableTransaction("No successful payment found to refund.")

    refund_transaction(
        paymob_transaction_id=transaction.paymob_transaction_id,
        amount_cents=transaction.amount_cents,
    )

    db.update_transaction(user_id, transaction.id, status="refunded", refunded_at=to_iso(_utcnow()))
    transaction.status = "refunded"

    try:
        cancel_subscription(db, user_id)
    except NoRefundableTransaction:
        pass  # subscription was already inactive — refund still recorded above

    return transaction


def admin_grant(db: FirestoreDB, user: User, plan_id: str, days: Optional[int] = None) -> Subscription:
    """Manually grants access without a real payment — for comps, support
    cases, or testing. Records nothing in payment history since no money
    moved; the caller writes an AdminAction audit entry separately."""
    plan = get_plan(plan_id)
    duration_days = days if days is not None else plan["duration_days"]

    now = _utcnow()
    current_expiry = parse_iso(user.subscription.expires_at) if user.subscription.expires_at else None
    base = current_expiry if (current_expiry and current_expiry > now) else now

    user.subscription.plan = plan_id
    user.subscription.status = "active"
    user.subscription.started_at = user.subscription.started_at or to_iso(now)
    user.subscription.expires_at = to_iso(base + datetime.timedelta(days=duration_days))
    db.update_subscription(user.id, user.subscription)
    return user.subscription