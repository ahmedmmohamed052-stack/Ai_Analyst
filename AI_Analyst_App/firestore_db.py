"""
Firestore-backed data access for the app's own data (users, subscriptions,
reports, payments) — separate from database.py, which connects to the
CUSTOMER's business database that gets queried for analysis.

Collection layout, chosen specifically to need ZERO manually-created
composite indexes in the Firestore console:

  users/{uid}
    email, hashed_password, full_name, email_verified,
    verification_token, verification_token_expires,
    reset_token, reset_token_expires, created_at,
    subscription: {plan, status, started_at, expires_at, canceled_at}

    users/{uid}/reports/{report_id}
      question, result_json, created_at
    users/{uid}/payment_transactions/{transaction_id}
      plan, amount_cents, currency, paymob_order_id, paymob_transaction_id,
      status, raw_webhook_payload, created_at, updated_at, refunded_at
    users/{uid}/analyze_usage/{usage_id}
      created_at

  payment_order_index/{paymob_order_id}
    user_id, transaction_id
    — a tiny pointer doc so the Paymob webhook (which only knows the
    order id, not which user) can jump straight to the right
    subcollection doc with a single get() instead of a cross-user query.

  admin_actions/{action_id}
    admin_email, target_user_id, action, detail, created_at

All per-user lists (reports, payment history, usage) live in
subcollections and are only ever ordered by created_at with no equality
filter alongside it — that combination is auto-indexed by Firestore with
no setup. Nothing in this app requires a composite index.
"""
import json
import uuid
from typing import List, Optional, Tuple

from config import FIREBASE_PROJECT_ID, FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_SERVICE_ACCOUNT_PATH
from schemas import PaymentTransaction, Report, Subscription, User
from utils import to_iso, utcnow


def _new_id() -> str:
    return str(uuid.uuid4())


def _init_firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        if FIREBASE_SERVICE_ACCOUNT_JSON:
            cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
        elif FIREBASE_SERVICE_ACCOUNT_PATH:
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
        else:
            raise RuntimeError(
                "No Firebase credentials configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
                "(the full service account JSON, as one env var — recommended for Railway) "
                "or FIREBASE_SERVICE_ACCOUNT_PATH (a path to the key file, for local dev). "
                "Generate one in Firebase Console -> Project Settings -> Service Accounts "
                "-> Generate new private key."
            )
        options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else {}
        firebase_admin.initialize_app(cred, options)

    return firestore.client()


def _user_from_doc(doc) -> Optional[User]:
    if not doc.exists:
        return None
    d = doc.to_dict()
    sub = d.get("subscription") or {}
    return User(
        id=doc.id,
        email=d.get("email", ""),
        hashed_password=d.get("hashed_password", ""),
        full_name=d.get("full_name"),
        email_verified=d.get("email_verified", False),
        auth_provider=d.get("auth_provider", "password"),
        firebase_uid=d.get("firebase_uid"),
        photo_url=d.get("photo_url"),
        team_owner_id=d.get("team_owner_id"),
        trial_plan=d.get("trial_plan"),
        trial_bonus_granted=d.get("trial_bonus_granted", False),
        verification_token=d.get("verification_token"),
        verification_token_expires=d.get("verification_token_expires"),
        reset_token=d.get("reset_token"),
        reset_token_expires=d.get("reset_token_expires"),
        created_at=d.get("created_at"),
        subscription=Subscription(
            plan=sub.get("plan"),
            status=sub.get("status", "none"),
            started_at=sub.get("started_at"),
            expires_at=sub.get("expires_at"),
            canceled_at=sub.get("canceled_at"),
        ),
    )


def _transaction_from_doc(doc, user_id: str) -> Optional[PaymentTransaction]:
    if not doc.exists:
        return None
    d = doc.to_dict()
    return PaymentTransaction(
        id=doc.id,
        user_id=user_id,
        plan=d.get("plan", ""),
        amount_cents=d.get("amount_cents", 0),
        currency=d.get("currency", ""),
        status=d.get("status", "pending"),
        paymob_order_id=d.get("paymob_order_id"),
        paymob_transaction_id=d.get("paymob_transaction_id"),
        raw_webhook_payload=d.get("raw_webhook_payload"),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
        refunded_at=d.get("refunded_at"),
    )


def _report_from_doc(doc, user_id: str) -> Optional[Report]:
    if not doc.exists:
        return None
    d = doc.to_dict()
    return Report(
        id=doc.id,
        user_id=user_id,
        question=d.get("question", ""),
        result_json=d.get("result_json", ""),
        created_at=d.get("created_at"),
    )


class FirestoreDB:
    def __init__(self):
        self._client = _init_firestore_client()

    # ── Users ──────────────────────────────────────────────────────────
    def create_user(
        self,
        email: str,
        hashed_password: str,
        full_name: Optional[str] = None,
        email_verified: bool = False,
        auth_provider: str = "password",
        firebase_uid: Optional[str] = None,
        photo_url: Optional[str] = None,
    ) -> User:
        uid = _new_id()
        doc = {
            "email": email,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "email_verified": email_verified,
            "auth_provider": auth_provider,
            "firebase_uid": firebase_uid,
            "photo_url": photo_url,
            "team_owner_id": None,
            "trial_plan": None,
            "trial_bonus_granted": False,
            "verification_token": None,
            "verification_token_expires": None,
            "reset_token": None,
            "reset_token_expires": None,
            "created_at": to_iso(utcnow()),
            "subscription": None,
        }
        self._client.collection("users").document(uid).set(doc)
        return self.get_user_by_id(uid)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return _user_from_doc(self._client.collection("users").document(user_id).get())

    def get_user_by_email(self, email: str) -> Optional[User]:
        docs = list(self._client.collection("users").where("email", "==", email).limit(1).stream())
        return _user_from_doc(docs[0]) if docs else None

    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[User]:
        docs = list(
            self._client.collection("users").where("firebase_uid", "==", firebase_uid).limit(1).stream()
        )
        return _user_from_doc(docs[0]) if docs else None

    def get_or_create_oauth_user(
        self, firebase_uid: str, email: str, full_name: Optional[str], provider: str, photo_url: Optional[str] = None
    ) -> User:
        """Used by /auth/firebase for Google/Apple sign-in. Firebase already verified the
        identity, so the account is created (or linked, if it signed up with a password
        first) pre-verified — no separate email code needed for these providers."""
        existing = self.get_user_by_firebase_uid(firebase_uid)
        if existing:
            return existing

        by_email = self.get_user_by_email(email) if email else None
        if by_email:
            # Same email already registered (e.g. via password) — link this provider
            # to that existing account rather than creating a duplicate.
            self.update_user(
                by_email.id,
                firebase_uid=firebase_uid,
                email_verified=True,
                photo_url=photo_url or by_email.photo_url,
            )
            return self.get_user_by_id(by_email.id)

        return self.create_user(
            email=email,
            hashed_password="",
            full_name=full_name,
            email_verified=True,
            auth_provider=provider,
            firebase_uid=firebase_uid,
            photo_url=photo_url,
        )

    def get_user_by_verification_token(self, token: str) -> Optional[User]:
        docs = list(
            self._client.collection("users").where("verification_token", "==", token).limit(1).stream()
        )
        return _user_from_doc(docs[0]) if docs else None

    def get_user_by_reset_token(self, token: str) -> Optional[User]:
        docs = list(self._client.collection("users").where("reset_token", "==", token).limit(1).stream())
        return _user_from_doc(docs[0]) if docs else None

    def update_user(self, user_id: str, **fields) -> None:
        self._client.collection("users").document(user_id).update(fields)

    def update_subscription(self, user_id: str, subscription: Subscription) -> None:
        self._client.collection("users").document(user_id).update({
            "subscription": {
                "plan": subscription.plan,
                "status": subscription.status,
                "started_at": subscription.started_at,
                "expires_at": subscription.expires_at,
                "canceled_at": subscription.canceled_at,
            }
        })

    def list_users(self, limit: int, offset: int) -> Tuple[List[User], int]:
        all_docs = list(self._client.collection("users").order_by("created_at", direction="DESCENDING").stream())
        total = len(all_docs)
        page = all_docs[offset: offset + limit]
        return [_user_from_doc(d) for d in page], total

    # ── Payment transactions (subcollection: users/{uid}/payment_transactions) ──
    def create_transaction(self, user_id: str, plan: str, amount_cents: int, currency: str) -> PaymentTransaction:
        tid = _new_id()
        now = to_iso(utcnow())
        doc = {
            "plan": plan, "amount_cents": amount_cents, "currency": currency,
            "status": "pending", "paymob_order_id": None, "paymob_transaction_id": None,
            "raw_webhook_payload": None, "created_at": now, "updated_at": now, "refunded_at": None,
        }
        self._client.collection("users").document(user_id).collection("payment_transactions").document(tid).set(doc)
        return self.get_transaction(user_id, tid)

    def get_transaction(self, user_id: str, transaction_id: str) -> Optional[PaymentTransaction]:
        ref = self._client.collection("users").document(user_id).collection("payment_transactions").document(transaction_id)
        return _transaction_from_doc(ref.get(), user_id)

    def link_order_to_transaction(self, order_id: str, user_id: str, transaction_id: str) -> None:
        self._client.collection("payment_order_index").document(str(order_id)).set(
            {"user_id": user_id, "transaction_id": transaction_id}
        )

    def get_transaction_by_order_id(self, order_id: str) -> Optional[PaymentTransaction]:
        pointer = self._client.collection("payment_order_index").document(str(order_id)).get()
        if not pointer.exists:
            return None
        p = pointer.to_dict()
        return self.get_transaction(p["user_id"], p["transaction_id"])

    def update_transaction(self, user_id: str, transaction_id: str, **fields) -> None:
        fields["updated_at"] = to_iso(utcnow())
        self._client.collection("users").document(user_id).collection("payment_transactions").document(transaction_id).update(fields)

    def get_latest_successful_transaction(self, user_id: str) -> Optional[PaymentTransaction]:
        docs = (
            self._client.collection("users").document(user_id).collection("payment_transactions")
            .order_by("created_at", direction="DESCENDING").stream()
        )
        for d in docs:
            txn = _transaction_from_doc(d, user_id)
            if txn.status == "success":
                return txn
        return None

    # ── Reports (subcollection: users/{uid}/reports) ─────────────────────
    def create_report(self, user_id: str, question: str, result_json: str) -> Report:
        rid = _new_id()
        doc = {"question": question, "result_json": result_json, "created_at": to_iso(utcnow())}
        self._client.collection("users").document(user_id).collection("reports").document(rid).set(doc)
        return self.get_report(user_id, rid)

    def get_report(self, user_id: str, report_id: str) -> Optional[Report]:
        ref = self._client.collection("users").document(user_id).collection("reports").document(report_id)
        return _report_from_doc(ref.get(), user_id)

    def list_reports(self, user_id: str, limit: int, offset: int) -> Tuple[List[Report], int]:
        all_docs = list(
            self._client.collection("users").document(user_id).collection("reports")
            .order_by("created_at", direction="DESCENDING").stream()
        )
        total = len(all_docs)
        page = all_docs[offset: offset + limit]
        return [_report_from_doc(d, user_id) for d in page], total

    # ── Datasets (subcollection: users/{uid}/datasets) ────────────────────
    # source_type == "external_db": db_type, host, port, database, user,
    #   encrypted_password, sslmode
    # source_type == "file": columns ([{name, dtype}]), row_count
    #   — actual rows live in a nested subcollection, see get_dataset_rows.
    def create_external_dataset(
        self, user_id: str, name: str, db_type: str, host: str, port: int,
        database: str, user: str, encrypted_password: str, sslmode: str = "prefer",
    ) -> dict:
        did = _new_id()
        doc = {
            "name": name, "source_type": "external_db", "db_type": db_type,
            "host": host, "port": port, "database": database, "user": user,
            "encrypted_password": encrypted_password, "sslmode": sslmode,
            "created_at": to_iso(utcnow()),
        }
        self._client.collection("users").document(user_id).collection("datasets").document(did).set(doc)
        return {**doc, "id": did}

    def create_file_dataset(
        self, user_id: str, name: str, columns: list, row_chunks: list,
    ) -> dict:
        """row_chunks is a list of lists-of-row-dicts, pre-split by the
        caller to stay under Firestore's per-document size limit."""
        did = _new_id()
        row_count = sum(len(chunk) for chunk in row_chunks)
        doc = {
            "name": name, "source_type": "file", "columns": columns,
            "row_count": row_count, "created_at": to_iso(utcnow()),
        }
        ds_ref = self._client.collection("users").document(user_id).collection("datasets").document(did)
        ds_ref.set(doc)
        rows_col = ds_ref.collection("rows")
        for i, chunk in enumerate(row_chunks):
            rows_col.document(str(i)).set({"rows": chunk})
        return {**doc, "id": did}

    def list_datasets(self, user_id: str) -> list:
        docs = list(
            self._client.collection("users").document(user_id).collection("datasets")
            .order_by("created_at", direction="DESCENDING").stream()
        )
        return [{**d.to_dict(), "id": d.id} for d in docs]

    def get_dataset(self, user_id: str, dataset_id: str) -> Optional[dict]:
        doc = self._client.collection("users").document(user_id).collection("datasets").document(dataset_id).get()
        if not doc.exists:
            return None
        return {**doc.to_dict(), "id": doc.id}

    def delete_dataset(self, user_id: str, dataset_id: str) -> None:
        ds_ref = self._client.collection("users").document(user_id).collection("datasets").document(dataset_id)
        for row_doc in ds_ref.collection("rows").stream():
            row_doc.reference.delete()
        ds_ref.delete()

    def get_dataset_rows(self, user_id: str, dataset_id: str) -> list:
        ds_ref = self._client.collection("users").document(user_id).collection("datasets").document(dataset_id)
        chunks = list(ds_ref.collection("rows").stream())
        rows = []
        for i in range(len(chunks)):
            chunk_doc = ds_ref.collection("rows").document(str(i)).get()
            if chunk_doc.exists:
                rows.extend(chunk_doc.to_dict().get("rows", []))
        return rows

    # ── Team seats (Pro plan: teammates riding on the owner's subscription) ─
    def set_team_owner(self, user_id: str, owner_id: Optional[str]) -> None:
        self._client.collection("users").document(user_id).update({"team_owner_id": owner_id})

    def list_team_members(self, owner_id: str) -> List[User]:
        docs = list(
            self._client.collection("users").where("team_owner_id", "==", owner_id).stream()
        )
        return [_user_from_doc(d) for d in docs]

    # ── Usage tracking (subcollection: users/{uid}/analyze_usage) ────────
    def record_analyze_usage(self, user_id: str) -> None:
        uid = _new_id()
        self._client.collection("users").document(user_id).collection("analyze_usage").document(uid).set(
            {"created_at": to_iso(utcnow())}
        )

    def count_recent_usage(self, user_id: str, since_iso: str) -> int:
        docs = (
            self._client.collection("users").document(user_id).collection("analyze_usage")
            .where("created_at", ">", since_iso).stream()
        )
        return sum(1 for _ in docs)

    # ── Admin audit log ───────────────────────────────────────────────────
    def create_admin_action(self, admin_email: str, target_user_id: str, action: str, detail: str = "") -> None:
        aid = _new_id()
        self._client.collection("admin_actions").document(aid).set({
            "admin_email": admin_email, "target_user_id": target_user_id,
            "action": action, "detail": detail, "created_at": to_iso(utcnow()),
        })


_instance: Optional[FirestoreDB] = None


def get_db() -> FirestoreDB:
    global _instance
    if _instance is None:
        _instance = FirestoreDB()
    return _instance