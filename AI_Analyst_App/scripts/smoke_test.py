"""
Run this once you've filled in real values in .env (Firebase credentials
and HF_TOKEN) to confirm the two things that can't be verified in a
sandboxed dev environment: an actual Firestore connection and an actual
Hugging Face model call. (There's no shared business database to check
anymore — each user connects or uploads their own; see /datasets/* in
main.py and README.md.)

Usage:
    cd AI_Analyst_App
    python scripts/smoke_test.py

Exits non-zero with a clear message on the first failure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("1/3 - checking Firestore connection (write, read, delete a test doc)...")
    try:
        from firestore_db import get_db
        db = get_db()
        user = db.create_user(email="__smoke_test__@example.com", hashed_password="x")
        fetched = db.get_user_by_id(user.id)
        assert fetched and fetched.email == "__smoke_test__@example.com"
        db._client.collection("users").document(user.id).delete()
        print("    OK: Firestore read/write works, test doc cleaned up.")
    except Exception as e:
        print(f"    FAILED: {e}")
        print(
            "    Check FIREBASE_SERVICE_ACCOUNT_JSON (or FIREBASE_SERVICE_ACCOUNT_PATH) "
            "in .env. Also confirm outbound network access to *.googleapis.com is allowed "
            "wherever this runs — some sandboxed/restricted environments block it."
        )
        sys.exit(1)

    print("2/3 - making one real Hugging Face call...")
    from chains import client
    from config import MAX_NEW_TOKENS, TEMPERATURE
    try:
        response = client.chat_completion(
            messages=[{"role": "user", "content": "Reply with exactly the word OK and nothing else."}],
            max_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
        )
        text = response.choices[0].message.content
        print(f"    Model responded: {text[:80]!r}")
        print("    OK: Hugging Face credentials work.")
    except Exception as e:
        print(f"    FAILED: {e}")
        print("    Check HF_TOKEN and MODEL_NAME in .env.")
        sys.exit(1)

    print("\nAll checks passed. Once a user connects a database or uploads a")
    print("file (POST /datasets/connect or /datasets/upload), try a real")
    print("question:")
    print('    curl -X POST http://127.0.0.1:8000/analyze -H "Authorization: Bearer <token>" \\')
    print('         -H "Content-Type: application/json" -d \'{"question": "...", "dataset_id": "..."}\'')


if __name__ == "__main__":
    main()
