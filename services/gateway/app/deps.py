import os

from shared.db import Setting

EMAIL_SERVICE_URL = os.environ.get("EMAIL_SERVICE_URL", "http://email-service:8001")


def current_account(session) -> str:
    row = session.get(Setting, "imap_user")
    return (row.value or "").strip() if row else ""
