"""
A plain-dict, in-memory stand-in for firestore_db.FirestoreDB — same
method signatures, same return types (schemas.py dataclasses), so
main.py/billing.py/auth.py/ratelimit.py can't tell the difference. Used
by conftest.py to run the whole test suite with no real Firestore
project or network access.
"""
import uuid
from typing import List, Optional, Tuple

from schemas import PaymentTransaction, Report, Subscription, User
from utils import to_iso, utcnow


def _new_id() -> str:
    return str(uuid.uuid4())


class FakeFirestoreDB:
    def __init__(self):
        self.users = {}                 # uid -> dict
        self.transactions = {}          # uid -> {tid -> dict}
        self.order_index = {}           # order_id -> {user_id, transaction_id}
        self.reports = {}               # uid -> {rid -> dict}
        self.datasets = {}              # uid -> {did -> dict}
        self.dataset_rows = {}          # uid -> {did -> [row, ...]}
        self.usage = {}                 # uid -> {usage_id -> dict}
        self.admin_actions = []         # list of dicts

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
        self.users[uid] = {
            "email": email, "hashed_password": hashed_password, "full_name": full_name,
            "email_verified": email_verified, "auth_provider": auth_provider,
            "firebase_uid": firebase_uid, "photo_url": photo_url, "team_owner_id": None,
            "trial_plan": None, "trial_bonus_granted": False,
            "verification_token": None, "verification_token_expires": None,
            "reset_token": None, "reset_token_expires": None, "created_at": to_iso(utcnow()),
            "subscription": None,
        }
        return self.get_user_by_id(uid)

    def _user_obj(self, uid: str) -> Optional[User]:
        d = self.users.get(uid)
        if d is None:
            return None
        sub = d.get("subscription") or {}
        return User(
            id=uid, email=d["email"], hashed_password=d["hashed_password"], full_name=d["full_name"],
            email_verified=d["email_verified"],
            auth_provider=d.get("auth_provider", "password"),
            firebase_uid=d.get("firebase_uid"), photo_url=d.get("photo_url"),
            team_owner_id=d.get("team_owner_id"),
            trial_plan=d.get("trial_plan"), trial_bonus_granted=d.get("trial_bonus_granted", False),
            verification_token=d["verification_token"],
            verification_token_expires=d["verification_token_expires"], reset_token=d["reset_token"],
            reset_token_expires=d["reset_token_expires"], created_at=d["created_at"],
            subscription=Subscription(
                plan=sub.get("plan"), status=sub.get("status", "none"),
                started_at=sub.get("started_at"), expires_at=sub.get("expires_at"),
                canceled_at=sub.get("canceled_at"),
            ),
        )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        return self._user_obj(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        for uid, d in self.users.items():
            if d["email"] == email:
                return self._user_obj(uid)
        return None

    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[User]:
        for uid, d in self.users.items():
            if d.get("firebase_uid") == firebase_uid:
                return self._user_obj(uid)
        return None

    def get_or_create_oauth_user(
        self, firebase_uid: str, email: str, full_name: Optional[str], provider: str, photo_url: Optional[str] = None
    ) -> User:
        existing = self.get_user_by_firebase_uid(firebase_uid)
        if existing:
            return existing
        by_email = self.get_user_by_email(email) if email else None
        if by_email:
            self.update_user(by_email.id, firebase_uid=firebase_uid, email_verified=True,
                              photo_url=photo_url or by_email.photo_url)
            return self.get_user_by_id(by_email.id)
        return self.create_user(
            email=email, hashed_password="", full_name=full_name, email_verified=True,
            auth_provider=provider, firebase_uid=firebase_uid, photo_url=photo_url,
        )

    def get_user_by_verification_token(self, token: str) -> Optional[User]:
        for uid, d in self.users.items():
            if d.get("verification_token") == token:
                return self._user_obj(uid)
        return None

    def get_user_by_reset_token(self, token: str) -> Optional[User]:
        for uid, d in self.users.items():
            if d.get("reset_token") == token:
                return self._user_obj(uid)
        return None

    def update_user(self, user_id: str, **fields) -> None:
        self.users[user_id].update(fields)

    def update_subscription(self, user_id: str, subscription: Subscription) -> None:
        self.users[user_id]["subscription"] = {
            "plan": subscription.plan, "status": subscription.status,
            "started_at": subscription.started_at, "expires_at": subscription.expires_at,
            "canceled_at": subscription.canceled_at,
        }

    def list_users(self, limit: int, offset: int) -> Tuple[List[User], int]:
        ordered = sorted(self.users.keys(), key=lambda uid: self.users[uid]["created_at"], reverse=True)
        total = len(ordered)
        page = ordered[offset: offset + limit]
        return [self._user_obj(uid) for uid in page], total

    # ── Payment transactions ─────────────────────────────────────────────
    def create_transaction(self, user_id: str, plan: str, amount_cents: int, currency: str) -> PaymentTransaction:
        tid = _new_id()
        now = to_iso(utcnow())
        self.transactions.setdefault(user_id, {})[tid] = {
            "plan": plan, "amount_cents": amount_cents, "currency": currency, "status": "pending",
            "paymob_order_id": None, "paymob_transaction_id": None, "raw_webhook_payload": None,
            "created_at": now, "updated_at": now, "refunded_at": None,
        }
        return self.get_transaction(user_id, tid)

    def _txn_obj(self, user_id: str, tid: str) -> Optional[PaymentTransaction]:
        d = self.transactions.get(user_id, {}).get(tid)
        if d is None:
            return None
        return PaymentTransaction(id=tid, user_id=user_id, **d)

    def get_transaction(self, user_id: str, transaction_id: str) -> Optional[PaymentTransaction]:
        return self._txn_obj(user_id, transaction_id)

    def link_order_to_transaction(self, order_id: str, user_id: str, transaction_id: str) -> None:
        self.order_index[str(order_id)] = {"user_id": user_id, "transaction_id": transaction_id}

    def get_transaction_by_order_id(self, order_id: str) -> Optional[PaymentTransaction]:
        pointer = self.order_index.get(str(order_id))
        if not pointer:
            return None
        return self.get_transaction(pointer["user_id"], pointer["transaction_id"])

    def update_transaction(self, user_id: str, transaction_id: str, **fields) -> None:
        fields["updated_at"] = to_iso(utcnow())
        self.transactions[user_id][transaction_id].update(fields)

    def get_latest_successful_transaction(self, user_id: str) -> Optional[PaymentTransaction]:
        txns = self.transactions.get(user_id, {})
        ordered = sorted(txns.items(), key=lambda kv: kv[1]["created_at"], reverse=True)
        for tid, d in ordered:
            if d["status"] == "success":
                return self._txn_obj(user_id, tid)
        return None

    # ── Reports ────────────────────────────────────────────────────────
    def create_report(self, user_id: str, question: str, result_json: str) -> Report:
        rid = _new_id()
        self.reports.setdefault(user_id, {})[rid] = {
            "question": question, "result_json": result_json, "created_at": to_iso(utcnow()),
        }
        return self.get_report(user_id, rid)

    def get_report(self, user_id: str, report_id: str) -> Optional[Report]:
        d = self.reports.get(user_id, {}).get(report_id)
        if d is None:
            return None
        return Report(id=report_id, user_id=user_id, **d)

    def list_reports(self, user_id: str, limit: int, offset: int) -> Tuple[List[Report], int]:
        items = self.reports.get(user_id, {})
        ordered = sorted(items.keys(), key=lambda rid: items[rid]["created_at"], reverse=True)
        total = len(ordered)
        page = ordered[offset: offset + limit]
        return [self.get_report(user_id, rid) for rid in page], total

    # ── Usage tracking ────────────────────────────────────────────────────
    # ── Datasets ───────────────────────────────────────────────────────────
    def create_external_dataset(self, user_id, name, db_type, host, port, database, user, encrypted_password, sslmode="prefer"):
        did = _new_id()
        doc = {
            "name": name, "source_type": "external_db", "db_type": db_type,
            "host": host, "port": port, "database": database, "user": user,
            "encrypted_password": encrypted_password, "sslmode": sslmode,
            "created_at": to_iso(utcnow()),
        }
        self.datasets.setdefault(user_id, {})[did] = doc
        return {**doc, "id": did}

    def create_file_dataset(self, user_id, name, columns, row_chunks):
        did = _new_id()
        rows = [r for chunk in row_chunks for r in chunk]
        doc = {
            "name": name, "source_type": "file", "columns": columns,
            "row_count": len(rows), "created_at": to_iso(utcnow()),
        }
        self.datasets.setdefault(user_id, {})[did] = doc
        self.dataset_rows.setdefault(user_id, {})[did] = rows
        return {**doc, "id": did}

    def list_datasets(self, user_id):
        items = self.datasets.get(user_id, {})
        ordered = sorted(items.keys(), key=lambda did: items[did]["created_at"], reverse=True)
        return [{**items[did], "id": did} for did in ordered]

    def get_dataset(self, user_id, dataset_id):
        d = self.datasets.get(user_id, {}).get(dataset_id)
        return {**d, "id": dataset_id} if d else None

    def delete_dataset(self, user_id, dataset_id):
        self.datasets.get(user_id, {}).pop(dataset_id, None)
        self.dataset_rows.get(user_id, {}).pop(dataset_id, None)

    def get_dataset_rows(self, user_id, dataset_id):
        return self.dataset_rows.get(user_id, {}).get(dataset_id, [])

    # ── Team seats ───────────────────────────────────────────────────────
    def set_team_owner(self, user_id, owner_id):
        if user_id in self.users:
            self.users[user_id]["team_owner_id"] = owner_id

    def list_team_members(self, owner_id):
        return [self._user_obj(uid) for uid, d in self.users.items() if d.get("team_owner_id") == owner_id]

    # ── Usage tracking ────────────────────────────────────────────────────
    def record_analyze_usage(self, user_id: str) -> None:
        uid = _new_id()
        self.usage.setdefault(user_id, {})[uid] = {"created_at": to_iso(utcnow())}

    def count_recent_usage(self, user_id: str, since_iso: str) -> int:
        items = self.usage.get(user_id, {})
        return sum(1 for d in items.values() if d["created_at"] > since_iso)

    # ── Admin audit log ───────────────────────────────────────────────────
    def create_admin_action(self, admin_email: str, target_user_id: str, action: str, detail: str = "") -> None:
        self.admin_actions.append({
            "admin_email": admin_email, "target_user_id": target_user_id,
            "action": action, "detail": detail, "created_at": to_iso(utcnow()),
        })