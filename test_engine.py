import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://localhost:8000"

CSV_DATA = """buyer_pin,seller_pin,invoice_number,amount,vat_amount,invoice_date
# -- BACKGROUND NOISE (Legitimate Transactions) --
P000000001A,P000000002B,INV-LEGIT-001,1500000,240000,2025-01-10
P000000002B,P000000003C,INV-LEGIT-002,2000000,320000,2025-01-15
P000000004D,P000000005E,INV-LEGIT-003,500000,80000,2025-02-01
P000000001A,P000000005E,INV-LEGIT-004,1200000,192000,2025-02-20

# -- TOPOLOGY 1: 3-Node Carousel (Ksh 100M) --
# ShellCo A (Missing Trader) -> BufferCo B -> BrokerCo C -> ShellCo A
P000FRAUD1A,P000FRAUD1B,INV-RING1-001,100000000,16000000,2025-03-01
P000FRAUD1B,P000FRAUD1C,INV-RING1-002,102000000,16320000,2025-03-05
P000FRAUD1C,P000FRAUD1A,INV-RING1-003,98000000,15680000,2025-03-10

# -- TOPOLOGY 2: 5-Node Extended Loop (Ksh 50M) --
# X -> Y -> Z -> W -> V -> X
P000FRAUD2X,P000FRAUD2Y,INV-RING2-001,50000000,8000000,2025-04-01
P000FRAUD2Y,P000FRAUD2Z,INV-RING2-002,51000000,8160000,2025-04-02
P000FRAUD2Z,P000FRAUD2W,INV-RING2-003,49000000,7840000,2025-04-03
P000FRAUD2W,P000FRAUD2V,INV-RING2-004,50500000,8080000,2025-04-04
P000FRAUD2V,P000FRAUD2X,INV-RING2-005,49500000,7920000,2025-04-05
"""

def request_json(url, method="GET", data=None, files=None):
    if files:
        # Simple multipart/form-data encoding for CSV
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"test_data.csv\"\r\n"
            f"Content-Type: text/csv\r\n\r\n"
            f"{files['file']}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    elif data:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    else:
        req = urllib.request.Request(url, method=method)
        
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))

def test_engine():
    print("🚀 Starting E2E Testing for eTIMS Knowledge Graph Engine")
    print("-" * 60)
    
    try:
        # Step 1: Upload CSV Data
        print("📤 Uploading realistic test data to /api/transactions/upload...")
        upload_json = request_json(f"{BASE_URL}/api/transactions/upload", files={"file": CSV_DATA})
        print(f"✅ Upload Success: {upload_json['transactions_imported']} transactions imported, {upload_json['companies_created']} companies created.")
        
        # Step 2: Trigger Cycle Detection
        print("\n🔍 Running Cycle Detection Algorithm (/api/analysis/detect)...")
        detect_json = request_json(f"{BASE_URL}/api/analysis/detect", method="POST", data={"max_cycle_length": 8, "min_amount_threshold": 10000})
        print(f"✅ Detection Success: Analyzed in {detect_json['duration_seconds']}s")
        print(f"🚨 Found {detect_json['rings_detected']} Fraud Rings exposing KSh {detect_json['total_fraud_amount']:,.2f}")
        
        # Step 3: Fetch Ring Details
        print("\n📊 Fetching detailed ring data...")
        rings = request_json(f"{BASE_URL}/api/analysis/rings")
        for idx, ring in enumerate(rings, 1):
            print(f"\nRing {idx}:")
            print(f"  - Nodes (Cycle Length): {ring['cycle_length']}")
            print(f"  - Exposed Amount: KSh {ring['total_amount']:,.2f}")
            print(f"  - VAT at Risk: KSh {ring['total_vat']:,.2f}")
            print(f"  - Confidence Score: {ring['confidence_score'] * 100:.1f}%")
            print(f"  - Members: {', '.join(json.loads(ring['member_pins']))}")
            
        # Step 4: Validate Risk Scores (PageRank/Betweenness)
        print("\n🛡️ Validating risk scores for top companies...")
        top_risks = request_json(f"{BASE_URL}/api/dashboard/top-risks?limit=5")
        for company in top_risks:
            print(f"  - PIN: {company['pin']:<12} | Risk Score: {company['risk_score']*100:>5.1f}% | Flagged: {company['flagged']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_engine()
