from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from shared.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    params: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True)
    sender_email: Mapped[str] = mapped_column(String(320), default="")
    sender_name: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    date_received: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    account: Mapped[str] = mapped_column(String(320), default="")

    documents: Mapped[list["Document"]] = relationship(back_populates="email")


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    source: Mapped[str] = mapped_column(String(20), default="content")

    documents: Mapped[list["Document"]] = relationship(back_populates="place")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True)
    original_name: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000), default="")
    source_type: Mapped[str] = mapped_column(String(20), default="attachment")
    link_url: Mapped[str] = mapped_column(Text, default="")
    ext: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"), nullable=True)
    place_name_raw: Mapped[str] = mapped_column(String(300), default="")
    doc_kind: Mapped[str] = mapped_column(String(30), default="desconocido")
    flow: Mapped[str] = mapped_column(String(20), default="neutral")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="COP")
    orig_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    orig_currency: Mapped[str] = mapped_column(String(10), default="")
    doc_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    account: Mapped[str] = mapped_column(String(320), default="")
    emisor_name: Mapped[str] = mapped_column(String(300), default="")
    receptor_name: Mapped[str] = mapped_column(String(300), default="")
    cuche_key: Mapped[str] = mapped_column(String(64), default="")
    full_text: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    email: Mapped["Email | None"] = relationship(back_populates="documents")
    place: Mapped["Place | None"] = relationship(back_populates="documents")


_engine = None
_SessionLocal = None

_MIGRATIONS: list[tuple[str, str]] = [
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS account VARCHAR(320) NOT NULL DEFAULT ''",
    ),
    (
        "emails",
        "ALTER TABLE emails ADD COLUMN IF NOT EXISTS account VARCHAR(320) NOT NULL DEFAULT ''",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS emisor_name VARCHAR(300) NOT NULL DEFAULT ''",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS receptor_name VARCHAR(300) NOT NULL DEFAULT ''",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS orig_amount DOUBLE PRECISION NULL",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS orig_currency VARCHAR(10) NOT NULL DEFAULT ''",
    ),
    (
        "documents",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS cuche_key VARCHAR(64) NOT NULL DEFAULT ''",
    ),
    (
        "documents",
        "CREATE INDEX IF NOT EXISTS idx_documents_cuche_key ON documents(cuche_key) WHERE cuche_key != ''",
    ),
]

# Backfill unico: si NINGUN documento tiene cuenta todavia y hay imap_user
# configurado, se etiqueta todo el historico con esa cuenta. El guard
# NOT EXISTS hace que solo corra mientras todas las cuentas esten vacias.
_BACKFILL_ACCOUNT = [
    """
    UPDATE documents SET account = (SELECT value FROM settings WHERE key = 'imap_user')
    WHERE account = ''
      AND EXISTS (SELECT 1 FROM settings WHERE key = 'imap_user' AND value <> '')
      AND NOT EXISTS (SELECT 1 FROM documents WHERE account <> '')
    """,
    """
    UPDATE emails SET account = (SELECT value FROM settings WHERE key = 'imap_user')
    WHERE account = ''
      AND EXISTS (SELECT 1 FROM settings WHERE key = 'imap_user' AND value <> '')
      AND NOT EXISTS (SELECT 1 FROM emails WHERE account <> '')
    """,
]


def _run_migrations(engine) -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        for _table, statement in _MIGRATIONS:
            try:
                conn.execute(text(statement))
                conn.commit()
            except Exception:  # noqa: BLE001
                conn.rollback()
        for statement in _BACKFILL_ACCOUNT:
            try:
                conn.execute(text(statement))
                conn.commit()
            except Exception:  # noqa: BLE001
                conn.rollback()


def get_engine(url: str | None = None):
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(url or DATABASE_URL, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory(url: str | None = None):
    get_engine(url)
    return _SessionLocal


def init_db(url: str | None = None) -> None:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    _run_migrations(engine)
