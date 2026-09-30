import os
import json
import time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from sqlalchemy import select, func, update

from database import init_db, SessionLocal
from models import Company, Transaction, FraudRing, AnalysisRun
from graph_engine import GraphEngine
from utils.csv_parser import parse_csv

app = Flask(__name__, static_folder='static')
CORS(app)

# Ensure data dir exists
os.makedirs("data", exist_ok=True)
init_db()

@app.route('/')
def serve_spa():
    return send_file('static/index.html')

# ── Transactions API ────────────────────────────────────────────────────────
@app.route('/api/transactions/upload', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"detail": "No file part"}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({"detail": "Only CSV files are accepted"}), 400
        
    content = file.read()
    result = parse_csv(content)
    
    if result.errors and not result.records:
        return jsonify({"detail": result.errors}), 422
        
    imported = 0
    companies_created = 0
    
    with SessionLocal() as db:
        # User requested that each new upload completely resets the state
        if result.records:
            db.execute(Transaction.__table__.delete())
            db.execute(Company.__table__.delete())
            db.execute(FraudRing.__table__.delete())
            db.execute(AnalysisRun.__table__.delete())
            db.commit()

        existing_pins_query = db.execute(select(Company.pin))
        existing_pins = {row[0] for row in existing_pins_query.fetchall()}
        
        existing_inv_query = db.execute(select(Transaction.invoice_number))
        existing_invoices = {row[0] for row in existing_inv_query.fetchall()}
        
        for record in result.records:
            if record["invoice_number"] in existing_invoices:
                result.duplicates += 1
                continue
                
            for pin_key, name_key in [("buyer_pin", "buyer_name"), ("seller_pin", "seller_name")]:
                pin = record[pin_key]
                if pin not in existing_pins:
                    name = record.get(name_key) or f"Company {pin}"
                    company = Company(pin=pin, name=name, sector="Unknown")
                    db.add(company)
                    existing_pins.add(pin)
                    companies_created += 1
                    
            # Remove transient keys not mapped to Transaction model
            record.pop("buyer_name", None)
            record.pop("seller_name", None)
                    
            tx = Transaction(**record)
            db.add(tx)
            existing_invoices.add(record["invoice_number"])
            imported += 1
            
        db.commit()
        
        # Update counts
        for pin in existing_pins:
            buy_count = db.execute(select(func.count()).where(Transaction.buyer_pin == pin)).scalar()
            sell_count = db.execute(select(func.count()).where(Transaction.seller_pin == pin)).scalar()
            vat_total = db.execute(select(func.coalesce(func.sum(Transaction.vat_amount), 0)).where(Transaction.buyer_pin == pin)).scalar()
            
            db.execute(
                update(Company)
                .where(Company.pin == pin)
                .values(transaction_count=buy_count+sell_count, total_vat_claimed=vat_total)
            )
        db.commit()
        
    return jsonify({
        "transactions_imported": imported,
        "companies_created": companies_created,
        "duplicates_skipped": result.duplicates,
        "errors": result.errors[:20]
    })

# ── Analysis API ────────────────────────────────────────────────────────────
def _build_graph(db):
    engine = GraphEngine()
    result = db.execute(select(Transaction))
    for tx in result.scalars().all():
        engine.add_transaction(
            buyer_pin=tx.buyer_pin,
            seller_pin=tx.seller_pin,
            amount=tx.amount,
            vat_amount=tx.vat_amount,
            transaction_id=tx.id,
            invoice_number=tx.invoice_number,
            invoice_date=tx.invoice_date,
        )
    return engine

@app.route('/api/analysis/detect', methods=['POST'])
def detect_fraud_rings():
    data = request.json or {}
    max_length = data.get('max_cycle_length', 8)
    min_amount = data.get('min_amount_threshold', 0)
    
    start_time = time.time()
    
    with SessionLocal() as db:
        engine = _build_graph(db)
        if engine.graph.number_of_nodes() == 0:
            return jsonify({"detail": "No transactions loaded. Upload data first."}), 400
            
        detected_rings = engine.detect_cycles(max_length=max_length, min_amount=min_amount)
        risk_scores = engine.compute_risk_scores()
        
        for ring in detected_rings:
            existing = db.execute(select(FraudRing).where(FraudRing.ring_hash == ring.ring_hash)).scalar_one_or_none()
            if existing:
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
            
        flagged_pins = set()
        for ring in detected_rings:
            flagged_pins.update(ring.members)
            
        for pin, scores in risk_scores.items():
            db.execute(
                update(Company)
                .where(Company.pin == pin)
                .values(risk_score=scores["risk_score"], flagged=(pin in flagged_pins))
            )
            
        flagged_tx_ids = set()
        for ring in detected_rings:
            flagged_tx_ids.update(ring.transaction_ids)
            
        if flagged_tx_ids:
            db.execute(
                update(Transaction)
                .where(Transaction.id.in_(flagged_tx_ids))
                .values(status="FLAGGED")
            )
            
        duration = time.time() - start_time
        
        run = AnalysisRun(
            transactions_analyzed=engine.graph.number_of_edges(),
            rings_detected=len(detected_rings),
            total_fraud_amount=sum(r.total_amount for r in detected_rings),
            duration_seconds=round(duration, 3),
        )
        db.add(run)
        db.commit()
        
        return jsonify({
            "run_id": run.id,
            "transactions_analyzed": run.transactions_analyzed,
            "rings_detected": run.rings_detected,
            "total_fraud_amount": run.total_fraud_amount,
            "duration_seconds": run.duration_seconds
        })

@app.route('/api/analysis/rings', methods=['GET'])
def list_fraud_rings():
    with SessionLocal() as db:
        rings = db.execute(select(FraudRing).order_by(FraudRing.total_amount.desc())).scalars().all()
        return jsonify([{
            "id": r.id,
            "ring_hash": r.ring_hash,
            "cycle_length": r.cycle_length,
            "total_amount": r.total_amount,
            "total_vat": r.total_vat,
            "member_pins": r.member_pins,
            "transaction_ids": r.transaction_ids,
            "confidence_score": r.confidence_score,
            "status": r.status,
            "detected_at": r.detected_at.isoformat()
        } for r in rings])

@app.route('/api/analysis/rings/<int:ring_id>', methods=['GET'])
def get_fraud_ring(ring_id):
    with SessionLocal() as db:
        r = db.execute(select(FraudRing).where(FraudRing.id == ring_id)).scalar_one_or_none()
        if not r:
            return jsonify({"detail": "Not found"}), 404
        return jsonify({
            "id": r.id,
            "ring_hash": r.ring_hash,
            "cycle_length": r.cycle_length,
            "total_amount": r.total_amount,
            "total_vat": r.total_vat,
            "member_pins": r.member_pins,
            "transaction_ids": r.transaction_ids,
            "confidence_score": r.confidence_score,
            "status": r.status,
            "detected_at": r.detected_at.isoformat()
        })

@app.route('/api/analysis/graph', methods=['GET'])
def get_graph_data():
    ring_id = request.args.get('ring_id', type=int)
    
    with SessionLocal() as db:
        engine = _build_graph(db)
        companies = {c.pin: c for c in db.execute(select(Company)).scalars().all()}
        
        filter_pins = None
        if ring_id is not None:
            ring = db.execute(select(FraudRing).where(FraudRing.id == ring_id)).scalar_one_or_none()
            if ring:
                filter_pins = set(json.loads(ring.member_pins))
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
            c = companies.get(n["id"])
            nodes.append({
                "id": n["id"],
                "name": c.name if c else n["id"],
                "sector": c.sector if c else "Unknown",
                "risk_score": c.risk_score if c else 0.0,
                "flagged": c.flagged if c else False,
                "transaction_count": c.transaction_count if c else 0,
                "vat_claimed": c.total_vat_claimed if c else 0.0,
            })
            included_ids.add(n["id"])
            
        edges = []
        for e in graph_raw["edges"]:
            if e["source"] in included_ids and e["target"] in included_ids:
                status = db.execute(
                    select(Transaction.status)
                    .where(Transaction.seller_pin == e["source"])
                    .where(Transaction.buyer_pin == e["target"])
                    .limit(1)
                ).scalar() or "VALID"
                
                edges.append({
                    "source": e["source"],
                    "target": e["target"],
                    "amount": e["amount"],
                    "vat": e["vat"],
                    "invoice": e.get("invoices", [""])[0] if e.get("invoices") else "",
                    "status": status,
                })
                
        return jsonify({"nodes": nodes, "edges": edges})

# ── Dashboard API ───────────────────────────────────────────────────────────
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    with SessionLocal() as db:
        total_tx = db.execute(select(func.count()).select_from(Transaction)).scalar()
        total_co = db.execute(select(func.count()).select_from(Company)).scalar()
        total_rings = db.execute(select(func.count()).select_from(FraudRing)).scalar()
        fraud_amount = db.execute(select(func.coalesce(func.sum(FraudRing.total_amount), 0))).scalar()
        vat_at_risk = db.execute(select(func.coalesce(func.sum(FraudRing.total_vat), 0))).scalar()
        flagged = db.execute(select(func.count()).select_from(Company).where(Company.flagged == True)).scalar()
        avg_ring = db.execute(select(func.coalesce(func.avg(FraudRing.cycle_length), 0))).scalar()
        top_company = db.execute(select(Company.name).order_by(Company.risk_score.desc()).limit(1)).scalar()
        
        return jsonify({
            "total_transactions": total_tx,
            "total_companies": total_co,
            "total_fraud_rings": total_rings,
            "total_fraud_amount": fraud_amount,
            "total_vat_at_risk": vat_at_risk,
            "flagged_companies": flagged,
            "avg_ring_length": round(avg_ring, 1),
            "highest_risk_company": top_company,
        })

@app.route('/api/dashboard/top-risks', methods=['GET'])
def get_top_risk_companies():
    limit = request.args.get('limit', 10, type=int)
    with SessionLocal() as db:
        companies = db.execute(select(Company).order_by(Company.risk_score.desc()).limit(limit)).scalars().all()
        return jsonify([{
            "pin": c.pin,
            "name": c.name,
            "sector": c.sector,
            "risk_score": c.risk_score,
            "transaction_count": c.transaction_count,
            "total_vat_claimed": c.total_vat_claimed,
            "flagged": c.flagged,
        } for c in companies])

@app.route('/api/dashboard/timeline', methods=['GET'])
def get_timeline():
    with SessionLocal() as db:
        runs = db.execute(select(AnalysisRun).order_by(AnalysisRun.run_at.desc()).limit(20)).scalars().all()
        return jsonify([{
            "id": r.id,
            "run_at": r.run_at.isoformat(),
            "transactions_analyzed": r.transactions_analyzed,
            "rings_detected": r.rings_detected,
            "total_fraud_amount": r.total_fraud_amount,
            "duration_seconds": r.duration_seconds,
        } for r in runs])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
