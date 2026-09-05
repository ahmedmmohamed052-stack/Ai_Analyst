"""
Paymob payment gateway integration (Egypt).

Left intentionally stubbed: PAYMOB_API_KEY / PAYMOB_INTEGRATION_ID /
PAYMOB_IFRAME_ID / PAYMOB_HMAC_SECRET are blank in .env until you have
real credentials from your Paymob merchant dashboard. Nothing else in the
app breaks while they're blank — these functions just raise a clear
"not configured" error if a payment is actually attempted.

Standard Paymob "Accept" flow, once you add the keys:
  1. Authenticate -> get an auth token
  2. Create an "order" for the amount being charged
  3. Request a "payment key" for that order + the integration id
  4. Redirect the user to the hosted iframe URL with that payment key
  5. Paymob calls your /payments/paymob/webhook with the transaction result
     (verify it with PAYMOB_HMAC_SECRET before trusting it)

Fill in the .env values and this module works with no code changes.
"""
import hashlib
import hmac
from typing import Optional

import requests

from config import (
    PAYMOB_API_KEY,
    PAYMOB_BASE_URL,
    PAYMOB_CONFIGURED,
    PAYMOB_CURRENCY,
    PAYMOB_HMAC_SECRET,
    PAYMOB_IFRAME_ID,
    PAYMOB_INTEGRATION_ID,
)


class PaymobNotConfigured(Exception):
    pass


def _require_configured():
    if not PAYMOB_CONFIGURED:
        raise PaymobNotConfigured(
            "Paymob is not configured yet. Set PAYMOB_API_KEY, "
            "PAYMOB_INTEGRATION_ID, PAYMOB_IFRAME_ID and PAYMOB_HMAC_SECRET "
            "in .env once you have them from your Paymob dashboard."
        )


def _authenticate() -> str:
    _require_configured()
    resp = requests.post(
        f"{PAYMOB_BASE_URL}/auth/tokens",
        json={"api_key": PAYMOB_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def _create_order(auth_token: str, amount_cents: int, merchant_order_id: Optional[str] = None) -> int:
    resp = requests.post(
        f"{PAYMOB_BASE_URL}/ecommerce/orders",
        json={
            "auth_token": auth_token,
            "delivery_needed": False,
            "amount_cents": amount_cents,
            "currency": PAYMOB_CURRENCY,
            "merchant_order_id": merchant_order_id,
            "items": [],
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _request_payment_key(auth_token: str, order_id: int, amount_cents: int, billing_data: dict) -> str:
    resp = requests.post(
        f"{PAYMOB_BASE_URL}/acceptance/payment_keys",
        json={
            "auth_token": auth_token,
            "amount_cents": amount_cents,
            "expiration": 3600,
            "order_id": order_id,
            "billing_data": billing_data,
            "currency": PAYMOB_CURRENCY,
            "integration_id": PAYMOB_INTEGRATION_ID,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def create_payment(amount_cents: int, billing_data: dict, merchant_order_id: Optional[str] = None) -> dict:
    """
    Full flow: authenticate -> create order -> get payment key.
    Returns the iframe URL to redirect/embed the user into, plus raw ids.
    """
    auth_token = _authenticate()
    order_id = _create_order(auth_token, amount_cents, merchant_order_id)
    payment_key = _request_payment_key(auth_token, order_id, amount_cents, billing_data)

    iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{PAYMOB_IFRAME_ID}?payment_token={payment_key}"

    return {
        "order_id": order_id,
        "payment_key": payment_key,
        "iframe_url": iframe_url,
    }


def refund_transaction(paymob_transaction_id: str, amount_cents: int) -> dict:
    """Refunds a previously successful Paymob transaction (full or partial —
    pass the amount to refund in amount_cents). Requires the same API key
    used to create the original payment."""
    _require_configured()
    if not paymob_transaction_id:
        raise ValueError("No Paymob transaction id on this payment — cannot refund.")

    auth_token = _authenticate()
    resp = requests.post(
        f"{PAYMOB_BASE_URL}/acceptance/void_refund/refund",
        json={
            "auth_token": auth_token,
            "transaction_id": paymob_transaction_id,
            "amount_cents": amount_cents,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def verify_webhook_hmac(received_hmac: str, ordered_fields: str) -> bool:
    """
    Paymob computes an HMAC over a specific concatenation of transaction
    fields (see their docs for the exact field order for each callback
    type) using PAYMOB_HMAC_SECRET. Pass that pre-concatenated string in
    as `ordered_fields` and compare against the hmac Paymob sent.
    """
    _require_configured()
    computed = hmac.new(
        PAYMOB_HMAC_SECRET.encode(), ordered_fields.encode(), hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed, received_hmac)


# Paymob's documented field order for the "TRANSACTION" webhook callback.
# The HMAC is computed over these fields' string values concatenated in
# exactly this order (booleans as lowercase "true"/"false", missing/null
# values as empty strings).
_TRANSACTION_HMAC_FIELDS = [
    "amount_cents", "created_at", "currency", "error_occured",
    "has_parent_transaction", "id", "integration_id", "is_3d_secure",
    "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
    "is_voided", "order.id", "owner", "pending", "source_data.pan",
    "source_data.sub_type", "source_data.type", "success",
]


def _dotted_get(obj: dict, dotted_key: str):
    value = obj
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def build_transaction_hmac_string(transaction_obj: dict) -> str:
    """Builds the ordered field string for a Paymob 'TRANSACTION' webhook
    payload's `obj`, ready to pass into verify_webhook_hmac()."""
    parts = []
    for key in _TRANSACTION_HMAC_FIELDS:
        value = _dotted_get(transaction_obj, key)
        if isinstance(value, bool):
            parts.append("true" if value else "false")
        elif value is None:
            parts.append("")
        else:
            parts.append(str(value))
    return "".join(parts)

