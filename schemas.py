"""
Pydantic schemas for request validation and response serialization.
"""

from pydantic import BaseModel, Field
from datetime import date, datetime


# ── Transaction Schemas ──────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    buyer_pin: str
    seller_pin: str
    invoice_number: str
    amount: float = Field(gt=0)
    vat_amount: float = Field(ge=0)
    invoice_date: date


class TransactionOut(BaseModel):
    id: int
    buyer_pin: str
    seller_pin: str
    invoice_number: str
    amount: float
    vat_amount: float
    invoice_date: date
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Company Schemas ──────────────────────────────────────────────────────────

class CompanyOut(BaseModel):
    pin: str
    name: str
    sector: str
    risk_score: float
    transaction_count: int
    total_vat_claimed: float
    flagged: bool

    model_config = {"from_attributes": True}


# ── Fraud Ring Schemas ───────────────────────────────────────────────────────

class FraudRingOut(BaseModel):
    id: int
    ring_hash: str
    cycle_length: int
    total_amount: float
    total_vat: float
    member_pins: str
    transaction_ids: str
    confidence_score: float
    status: str
    detected_at: datetime

    model_config = {"from_attributes": True}


# ── Analysis Schemas ─────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    max_cycle_length: int = Field(default=8, ge=3, le=15)
    min_amount_threshold: float = Field(default=0.0, ge=0)


class AnalysisResult(BaseModel):
    run_id: int
    transactions_analyzed: int
    rings_detected: int
    total_fraud_amount: float
    duration_seconds: float
    rings: list[FraudRingOut]


# ── Dashboard Schemas ────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_transactions: int
    total_companies: int
    total_fraud_rings: int
    total_fraud_amount: float
    total_vat_at_risk: float
    flagged_companies: int
    avg_ring_length: float
    highest_risk_company: str | None


# ── Graph Data Schemas ───────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    name: str
    sector: str
    risk_score: float
    flagged: bool
    transaction_count: int
    vat_claimed: float


class GraphEdge(BaseModel):
    source: str
    target: str
    amount: float
    vat: float
    invoice: str
    status: str


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class UploadResult(BaseModel):
    transactions_imported: int
    companies_created: int
    duplicates_skipped: int
    errors: list[str]
