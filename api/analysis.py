"""
Analysis API endpoints — Run cycle detection, view fraud rings, get graph data.
"""

import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Transaction, Company, FraudRing, AnalysisRun
from schemas import (
    AnalysisRequest,
    AnalysisResult,
    FraudRingOut,
    CompanyOut,
    GraphData,
    GraphNode,
    GraphEdge,
)
from graph_engine import GraphEngine

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


async def _build_graph(db: AsyncSession) -> GraphEngine:
    """Load all transactions into a fresh graph engine."""
    engine = GraphEngine()
    result = await db.execute(select(Transaction))
    for tx in result.scalars().all():
        engine.add_transaction(
            buyer_pin=tx.buyer_pin,
            seller_pin=tx.seller_pin,
            amount=tx.amount,
            vat_amount=tx.vat_amount,
            transaction_id=tx.id,
            invoice_number=tx.invoice_number,
        )
    return engine


@router.post("/detect", response_model=AnalysisResult)
async def detect_fraud_rings(
    params: AnalysisRequest = AnalysisRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the cycle-detection algorithm on all loaded transactions.
    Finds circular invoicing patterns and scores them by fraud likelihood.
    """
    start_time = time.time()

    # Build graph from all transactions
    engine = await _build_graph(db)

    if engine.graph.number_of_nodes() == 0:
        raise HTTPException(
            status_code=400,
            detail="No transactions loaded. Upload data first.",
        )

    # Run Johnson's cycle detection
    detected_rings = engine.detect_cycles(
        max_length=params.max_cycle_length,
        min_amount=params.min_amount_threshold,
    )

    # Compute risk scores for all companies
    risk_scores = engine.compute_risk_scores()

    # Persist rings
    new_rings = []
    for ring in detected_rings:
        # Check if ring already exists
        existing = await db.execute(
            select(FraudRing).where(FraudRing.ring_hash == ring.ring_hash)
        )
        if existing.scalar_one_or_none():
            continue

        fraud_ring = FraudRing(
            ring_hash=ring.ring_hash,
            cycle_length=len(ring.members),
            total_amount=ring.total_amount,
            total_vat=ring.total_vat,
            member_pins=json.dumps(ring.members),
            transaction_ids=json.dumps(ring.transaction_ids),
            confidence_score=ring.confidence,
        )
        db.add(fraud_ring)
        new_rings.append(fraud_ring)

    # Update company risk scores and flag members of detected rings
    flagged_pins = set()
    for ring in detected_rings:
        flagged_pins.update(ring.members)

    for pin, scores in risk_scores.items():
        await db.execute(
            update(Company)
            .where(Company.pin == pin)
            .values(
                risk_score=scores["risk_score"],
                flagged=pin in flagged_pins,
            )
        )

    # Flag transactions involved in rings
    flagged_tx_ids = set()
    for ring in detected_rings:
        flagged_tx_ids.update(ring.transaction_ids)

    if flagged_tx_ids:
        await db.execute(
            update(Transaction)
            .where(Transaction.id.in_(flagged_tx_ids))
            .values(status="FLAGGED")
        )

    duration = time.time() - start_time

    # Log the analysis run
    run = AnalysisRun(
        transactions_analyzed=engine.graph.number_of_edges(),
        rings_detected=len(detected_rings),
        total_fraud_amount=sum(r.total_amount for r in detected_rings),
        duration_seconds=round(duration, 3),
    )
    db.add(run)
    await db.commit()

    # Refresh to get IDs
    for r in new_rings:
        await db.refresh(r)

    # Fetch all rings for response
    all_rings = await db.execute(
        select(FraudRing).order_by(FraudRing.total_amount.desc())
    )

    return AnalysisResult(
        run_id=run.id,
        transactions_analyzed=run.transactions_analyzed,
        rings_detected=run.rings_detected,
        total_fraud_amount=run.total_fraud_amount,
        duration_seconds=run.duration_seconds,
        rings=[FraudRingOut.model_validate(r) for r in all_rings.scalars().all()],
    )


@router.get("/rings", response_model=list[FraudRingOut])
async def list_fraud_rings(
    status: str | None = None,
    min_amount: float = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all detected fraud rings, optionally filtered."""
    query = select(FraudRing)
    if status:
        query = query.where(FraudRing.status == status.upper())
    if min_amount > 0:
        query = query.where(FraudRing.total_amount >= min_amount)
    query = query.order_by(FraudRing.total_amount.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/rings/{ring_id}", response_model=FraudRingOut)
async def get_fraud_ring(ring_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed info on a specific fraud ring."""
    result = await db.execute(select(FraudRing).where(FraudRing.id == ring_id))
    ring = result.scalar_one_or_none()
    if not ring:
        raise HTTPException(status_code=404, detail="Fraud ring not found")
    return ring


@router.get("/graph", response_model=GraphData)
async def get_graph_data(
    ring_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get graph data for D3.js visualization.
    Optionally filter to a specific fraud ring's subgraph.
    """
    engine = await _build_graph(db)

    # Get company details
    companies_result = await db.execute(select(Company))
    companies = {c.pin: c for c in companies_result.scalars().all()}

    # If ring_id specified, filter to ring members + their direct connections
    filter_pins = None
    if ring_id is not None:
        ring_result = await db.execute(
            select(FraudRing).where(FraudRing.id == ring_id)
        )
        ring = ring_result.scalar_one_or_none()
        if ring:
            filter_pins = set(json.loads(ring.member_pins))
            # Include 1-hop neighbors for context
            for pin in list(filter_pins):
                if pin in engine.graph:
                    filter_pins.update(engine.graph.predecessors(pin))
                    filter_pins.update(engine.graph.successors(pin))

    graph_raw = engine.get_graph_data()

    nodes = []
    included_ids = set()
    for n in graph_raw["nodes"]:
        if filter_pins and n["id"] not in filter_pins:
            continue
        company = companies.get(n["id"])
        nodes.append(GraphNode(
            id=n["id"],
            name=company.name if company else n["id"],
            sector=company.sector if company else "Unknown",
            risk_score=company.risk_score if company else 0.0,
            flagged=company.flagged if company else False,
            transaction_count=company.transaction_count if company else 0,
            vat_claimed=company.total_vat_claimed if company else 0.0,
        ))
        included_ids.add(n["id"])

    edges = []
    for e in graph_raw["edges"]:
        if e["source"] in included_ids and e["target"] in included_ids:
            # Get status from transactions
            tx_result = await db.execute(
                select(Transaction.status)
                .where(Transaction.seller_pin == e["source"])
                .where(Transaction.buyer_pin == e["target"])
                .limit(1)
            )
            status = tx_result.scalar() or "VALID"

            edges.append(GraphEdge(
                source=e["source"],
                target=e["target"],
                amount=e["amount"],
                vat=e["vat"],
                invoice=e.get("invoices", [""])[0] if e.get("invoices") else "",
                status=status,
            ))

    return GraphData(nodes=nodes, edges=edges)


@router.get("/company/{pin}", response_model=CompanyOut)
async def get_company_profile(pin: str, db: AsyncSession = Depends(get_db)):
    """Get risk profile for a specific company."""
    result = await db.execute(select(Company).where(Company.pin == pin.upper()))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
