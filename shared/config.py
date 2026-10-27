import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://organizador:organizador@localhost:5432/organizador",
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = os.environ.get("DATA_DIR", "./data")

QUEUE_PDF = "queue:pdf"
QUEUE_ORGANIZE = "queue:organize"

INBOX_DIR = os.path.join(DATA_DIR, "inbox")
FACTURAS_DIR = os.path.join(DATA_DIR, "facturas")
PROCESSING_DIR = os.path.join(DATA_DIR, "processing")
LOCAL_SCAN_DIR = os.path.join(DATA_DIR, "local-scan")
