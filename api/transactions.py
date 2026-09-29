"""
Transaction API endpoints — Upload, list, and manage eTIMS transactions.
"""

import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Transaction, Company
from schemas import TransactionOut, UploadResult
from utils.csv_parser import parse_csv

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.post("/upload", response_model=UploadResult)
async def upload_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CSV file of eTIMS transactions.
    Parses, validates, and persists records to the database.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    content = await file.read()
    result = parse_csv(content)

    if result.errors and not result.records:
        raise HTTPException(status_code=422, detail={"errors": result.errors})

    imported = 0
    companies_created = 0
    existing_pins: set[str] = set()

    # Get existing PINs
    existing = await db.execute(select(Company.pin))
    existing_pins = {row[0] for row in existing.fetchall()}

    # Get existing invoice numbers to skip true duplicates
    existing_inv = await db.execute(select(Transaction.invoice_number))
    existing_invoices = {row[0] for row in existing_inv.fetchall()}

    for record in result.records:
        if record["invoice_number"] in existing_invoices:
            result.duplicates += 1
            continue

        # Ensure buyer company exists
        for pin_key in ["buyer_pin", "seller_pin"]:
            pin = record[pin_key]
            if pin not in existing_pins:
                company = Company(
                    pin=pin,
                    name=f"Company {pin}",
                    sector="Unknown",
                )
                db.add(company)
                existing_pins.add(pin)
                companies_created += 1

        tx = Transaction(**record)
        db.add(tx)
        existing_invoices.add(record["invoice_number"])
        imported += 1

    await db.commit()

    # Update company transaction counts and VAT totals
    for pin in existing_pins:
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

    return UploadResult(
        transactions_imported=imported,
        companies_created=companies_created,
        duplicates_skipped=result.duplicates,
        errors=result.errors[:20],  # Limit error output
    )


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: str | None = None,
    buyer_pin: str | None = None,
    seller_pin: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List transactions with optional filters and pagination."""
    query = select(Transaction)

    if status:
        query = query.where(Transaction.status == status.upper())
    if buyer_pin:
        query = query.where(Transaction.buyer_pin == buyer_pin.upper())
    if seller_pin:
        query = query.where(Transaction.seller_pin == seller_pin.upper())

    query = query.order_by(Transaction.id.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{tx_id}", response_model=TransactionOut)
async def get_transaction(tx_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single transaction by ID."""
    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx
