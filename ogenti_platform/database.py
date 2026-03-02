"""Ogenti Platform — Database Models"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, LargeBinary, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from .config import DATABASE_URL

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), default="")
    tier = Column(String(20), default="free")  # free / starter / pro / enterprise
    credits = Column(Integer, default=100)  # starting credits
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    training_jobs = relationship("TrainingJob", back_populates="user", cascade="all, delete-orphan")
    adapters = relationship("Adapter", back_populates="user", cascade="all, delete-orphan")


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(12), nullable=False)  # og_xxxx... (shown to user)
    name = Column(String(100), default="Default Key")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)  # purchase / usage / refund / bonus
    amount_cents = Column(Integer, default=0)  # money amount in cents (for purchases)
    credits = Column(Integer, default=0)  # credits added or deducted
    description = Column(String(500), default="")
    stripe_payment_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="transactions")


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="queued")  # queued / running / completed / failed / cancelled
    model = Column(String(50), nullable=False)
    dataset = Column(String(50), nullable=False)
    episodes = Column(Integer, nullable=False)
    credits_used = Column(Integer, default=0)
    credits_estimated = Column(Integer, default=0)
    current_phase = Column(String(50), default="queued")
    current_episode = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)
    compression = Column(Float, default=0.0)
    adapter_url = Column(String(500), nullable=True)  # download URL when done
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="training_jobs")


class Adapter(Base):
    """Encrypted .ogt adapter — keys stored server-side only."""
    __tablename__ = "adapters"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    base_model = Column(String(50), nullable=False)
    encryption_key = Column(LargeBinary(32), nullable=False)  # AES-256 key (never leaves server)
    training_job_id = Column(Integer, ForeignKey("training_jobs.id"), nullable=True)
    file_size = Column(Integer, default=0)  # .ogt file size in bytes
    file_path = Column(String(500), nullable=True)  # server-local .ogt path
    status = Column(String(20), default="active")  # active / disabled / deleted
    inference_count = Column(Integer, default=0)  # total inference calls
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="adapters")
    training_job = relationship("TrainingJob", backref="adapter")


# ── Engine & Session ──
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency: yields a DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
