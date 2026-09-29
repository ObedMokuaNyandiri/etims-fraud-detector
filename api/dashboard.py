"""
Dashboard API endpoints — Aggregate stats, timeline, and reporting.
"""

import json
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Transaction, Company, FraudRing, AnalysisRun
from schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregate dashboard statistics."""
    total_tx = await db.execute(select(func.count()).select_from(Transaction))
    total_co = await db.execute(select(func.count()).select_from(Company))
    total_rings = await db.execute(select(func.count()).select_from(FraudRing))
    fraud_amount = await db.execute(
        select(func.coalesce(func.sum(FraudRing.total_amount), 0))
    )
    vat_at_risk = await db.execute(
        select(func.coalesce(func.sum(FraudRing.total_vat), 0))
    )
    flagged = await db.execute(
        select(func.count()).select_from(Company).where(Company.flagged == True)
    )

    # Average ring length
    avg_ring = await db.execute(
        select(func.coalesce(func.avg(FraudRing.cycle_length), 0))
    )

    # Highest risk company
    highest_risk = await db.execute(
        select(Company.name)
        .order_by(Company.risk_score.desc())
        .limit(1)
    )
    top_company = highest_risk.scalar()

    return DashboardStats(
        total_transactions=total_tx.scalar(),
        total_companies=total_co.scalar(),
        total_fraud_rings=total_rings.scalar(),
        total_fraud_amount=fraud_amount.scalar(),
        total_vat_at_risk=vat_at_risk.scalar(),
        flagged_companies=flagged.scalar(),
        avg_ring_length=round(avg_ring.scalar(), 1),
        highest_risk_company=top_company,
    )


@router.get("/timeline")
async def get_analysis_timeline(db: AsyncSession = Depends(get_db)):
    """Get the history of analysis runs."""
    result = await db.execute(
        select(AnalysisRun).order_by(AnalysisRun.run_at.desc()).limit(20)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "run_at": r.run_at.isoformat(),
            "transactions_analyzed": r.transactions_analyzed,
            "rings_detected": r.rings_detected,
            "total_fraud_amount": r.total_fraud_amount,
            "duration_seconds": r.duration_seconds,
        }
        for r in runs
    ]


@router.get("/top-risks")
async def get_top_risk_companies(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Get the highest risk companies."""
    result = await db.execute(
        select(Company)
        .order_by(Company.risk_score.desc())
        .limit(limit)
    )
    companies = result.scalars().all()
    return [
        {
            "pin": c.pin,
            "name": c.name,
            "sector": c.sector,
            "risk_score": c.risk_score,
            "transaction_count": c.transaction_count,
            "total_vat_claimed": c.total_vat_claimed,
            "flagged": c.flagged,
        }
        for c in companies
    ]
