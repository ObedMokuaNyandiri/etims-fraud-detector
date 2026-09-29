"""
eTIMS Knowledge Graph Engine — Main Application

FastAPI entry point with:
  - CORS middleware
  - Static file serving (SPA)
  - API router mounting
  - Mock data generation endpoint
  - Startup DB initialization
"""

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, get_db
from models import Company, Transaction
from api.transactions import router as tx_router
from api.analysis import router as analysis_router
from api.dashboard import router as dashboard_router
from utils.mock_data import generate_mock_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    os.makedirs("data", exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title="eTIMS Knowledge Graph Engine",
    description="Detects circular VAT ring fraud in Kenya's eTIMS invoice ecosystem using graph theory.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount API routers ────────────────────────────────────────────────────────
app.include_router(tx_router)
app.include_router(analysis_router)
app.include_router(dashboard_router)


# ── Mock data endpoint ───────────────────────────────────────────────────────
@app.post("/api/mock/generate", tags=["Mock Data"])
async def generate_mock(
    num_companies: int = 40,
    num_transactions: int = 150,
    num_rings: int = 4,
    seed: int = 42,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate mock eTIMS transaction data with embedded fraud rings.
    Useful for demos and testing.
    """
    # Check if data already exists
    existing = await db.execute(select(Transaction.id).limit(1))
    if existing.scalar():
        return JSONResponse(
            status_code=409,
            content={"detail": "Data already exists. Clear the database first.", "hint": "Delete data/etims.db and restart."},
        )

    companies, transactions, rings = generate_mock_data(
        num_companies=num_companies,
        num_legitimate_txns=num_transactions,
        num_fraud_rings=num_rings,
        seed=seed,
    )

    # Persist companies
    for comp in companies:
        db.add(Company(
            pin=comp["pin"],
            name=comp["name"],
            sector=comp["sector"],
        ))

    await db.flush()

    # Persist transactions
    from datetime import date as date_type
    for tx in transactions:
        inv_date = tx["invoice_date"]
        if isinstance(inv_date, str):
            from datetime import datetime
            inv_date = datetime.strptime(inv_date, "%Y-%m-%d").date()

        db.add(Transaction(
            buyer_pin=tx["buyer_pin"],
            seller_pin=tx["seller_pin"],
            invoice_number=tx["invoice_number"],
            amount=tx["amount"],
            vat_amount=tx["vat_amount"],
            invoice_date=inv_date,
        ))

    await db.commit()

    # Update company counts
    from sqlalchemy import func
    for comp in companies:
        pin = comp["pin"]
        buy_count = await db.execute(
            select(func.count()).where(Transaction.buyer_pin == pin)
        )
        sell_count = await db.execute(
            select(func.count()).where(Transaction.seller_pin == pin)
        )
        vat_total = await db.execute(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0)).where(
                Transaction.buyer_pin == pin
            )
        )
        total_txns = buy_count.scalar() + sell_count.scalar()
        total_vat = vat_total.scalar()

        await db.execute(
            Company.__table__.update()
            .where(Company.pin == pin)
            .values(transaction_count=total_txns, total_vat_claimed=total_vat)
        )

    await db.commit()

    return {
        "message": "Mock data generated successfully",
        "companies_created": len(companies),
        "transactions_created": len(transactions),
        "fraud_rings_embedded": len(rings),
        "embedded_rings": rings,
    }


# ── Static files & SPA fallback ─────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_spa():
    """Serve the SPA entry point."""
    return FileResponse("static/index.html")
