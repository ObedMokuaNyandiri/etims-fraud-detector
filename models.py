"""
SQLAlchemy ORM models for the eTIMS Knowledge Graph Engine.
"""

import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Date, Index
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Company(Base):
    __tablename__ = "companies"

    pin: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(100), default="Unknown")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    total_vat_claimed: Mapped[float] = mapped_column(Float, default=0.0)
    flagged: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_buyer_pin", "buyer_pin"),
        Index("idx_seller_pin", "seller_pin"),
        Index("idx_invoice_date", "invoice_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_pin: Mapped[str] = mapped_column(String(20))
    seller_pin: Mapped[str] = mapped_column(String(20))
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True)
    amount: Mapped[float] = mapped_column(Float)
    vat_amount: Mapped[float] = mapped_column(Float)
    invoice_date: Mapped[datetime.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="VALID")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class FraudRing(Base):
    __tablename__ = "fraud_rings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ring_hash: Mapped[str] = mapped_column(String(64), unique=True)
    cycle_length: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[float] = mapped_column(Float)
    total_vat: Mapped[float] = mapped_column(Float)
    member_pins: Mapped[str] = mapped_column(Text)  # JSON array
    transaction_ids: Mapped[str] = mapped_column(Text)  # JSON array
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="DETECTED")
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    transactions_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    rings_detected: Mapped[int] = mapped_column(Integer, default=0)
    total_fraud_amount: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
