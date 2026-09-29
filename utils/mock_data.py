"""
Mock data generator for eTIMS Knowledge Graph Engine.

Generates realistic Kenyan business transaction data including:
  - Legitimate supply-chain transactions
  - Embedded VAT ring fraud patterns (3-node, 4-node, 5-node cycles)
  - Realistic company names and KRA PINs
"""

import csv
import io
import random
from datetime import date, timedelta

# ── Kenyan business names and sectors ────────────────────────────────────────

SECTORS = [
    "Construction", "Agriculture", "Manufacturing", "Wholesale Trade",
    "Retail Trade", "Transport", "ICT Services", "Real Estate",
    "Mining & Quarrying", "Financial Services", "Healthcare",
    "Education", "Hospitality", "Energy", "Professional Services",
]

PREFIXES = [
    "Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Thika",
    "Nyeri", "Malindi", "Kitale", "Machakos", "Nanyuki", "Garissa",
    "Athi River", "Ruiru", "Juja", "Kiambu", "Limuru", "Kajiado",
]

SUFFIXES = [
    "Trading Co.", "Enterprises Ltd", "Suppliers Ltd", "Holdings Ltd",
    "Industries Ltd", "Solutions Ltd", "Investments Ltd", "Group PLC",
    "Construction Ltd", "Logistics Ltd", "Distributors Ltd", "Agencies",
    "Hardware Ltd", "General Merchants", "Imports & Exports Ltd",
]


def _generate_pin() -> str:
    """Generate a realistic KRA PIN (format: P0XXXXXXXXX)."""
    prefix = random.choice(["P", "A"])
    digits = "".join(str(random.randint(0, 9)) for _ in range(9))
    suffix = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{prefix}0{digits}{suffix}"


def _generate_company_name() -> str:
    """Generate a realistic Kenyan company name."""
    return f"{random.choice(PREFIXES)} {random.choice(SUFFIXES)}"


def _generate_invoice_number(idx: int) -> str:
    """Generate an eTIMS-style invoice number."""
    return f"ETIMS-{random.randint(1000, 9999)}-{idx:06d}"


def generate_mock_data(
    num_companies: int = 40,
    num_legitimate_txns: int = 150,
    num_fraud_rings: int = 4,
    seed: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Generate mock eTIMS transaction data with embedded fraud rings.

    Returns:
        (companies, transactions, embedded_rings)
        - companies: list of {pin, name, sector}
        - transactions: list of transaction dicts
        - embedded_rings: metadata about planted fraud rings
    """
    random.seed(seed)

    # ── Generate companies ─────────────────────────────────────────────────
    companies = []
    pins = []
    for _ in range(num_companies):
        pin = _generate_pin()
        while pin in pins:
            pin = _generate_pin()
        pins.append(pin)
        companies.append({
            "pin": pin,
            "name": _generate_company_name(),
            "sector": random.choice(SECTORS),
        })

    transactions = []
    tx_idx = 1
    base_date = date(2025, 1, 1)

    # ── Generate legitimate transactions (random supplier chains) ────────
    for _ in range(num_legitimate_txns):
        buyer_idx, seller_idx = random.sample(range(num_companies), 2)
        amount = round(random.uniform(50_000, 5_000_000), 2)
        vat = round(amount * 0.16, 2)
        inv_date = base_date + timedelta(days=random.randint(0, 365))

        transactions.append({
            "buyer_pin": companies[buyer_idx]["pin"],
            "seller_pin": companies[seller_idx]["pin"],
            "invoice_number": _generate_invoice_number(tx_idx),
            "amount": amount,
            "vat_amount": vat,
            "invoice_date": inv_date.isoformat(),
        })
        tx_idx += 1

    # ── Plant fraud rings ────────────────────────────────────────────────
    embedded_rings = []
    ring_configs = [
        {"size": 3, "base_amount": 50_000_000},   # Ksh 50M ring
        {"size": 4, "base_amount": 25_000_000},   # Ksh 25M ring
        {"size": 3, "base_amount": 80_000_000},   # Ksh 80M ring
        {"size": 5, "base_amount": 15_000_000},   # Ksh 15M ring
    ]

    for ring_idx, config in enumerate(ring_configs[:num_fraud_rings]):
        ring_size = config["size"]
        base_amount = config["base_amount"]

        # Select distinct companies for this ring
        ring_companies_idx = random.sample(range(num_companies), ring_size)
        ring_pins = [companies[i]["pin"] for i in ring_companies_idx]
        ring_names = [companies[i]["name"] for i in ring_companies_idx]

        ring_txns = []
        for i in range(ring_size):
            seller = ring_pins[i]
            buyer = ring_pins[(i + 1) % ring_size]
            # Slight variation in amounts to look less suspicious
            amount = round(base_amount * random.uniform(0.90, 1.10), 2)
            vat = round(amount * 0.16, 2)
            inv_date = base_date + timedelta(days=random.randint(60, 300))

            tx = {
                "buyer_pin": buyer,
                "seller_pin": seller,
                "invoice_number": _generate_invoice_number(tx_idx),
                "amount": amount,
                "vat_amount": vat,
                "invoice_date": inv_date.isoformat(),
            }
            transactions.append(tx)
            ring_txns.append(tx)
            tx_idx += 1

        embedded_rings.append({
            "ring_id": ring_idx + 1,
            "size": ring_size,
            "members": ring_pins,
            "member_names": ring_names,
            "total_amount": sum(t["amount"] for t in ring_txns),
            "total_vat": sum(t["vat_amount"] for t in ring_txns),
        })

    # Shuffle transactions so fraud isn't at the end
    random.shuffle(transactions)

    return companies, transactions, embedded_rings


def generate_csv_string(
    num_companies: int = 40,
    num_legitimate_txns: int = 150,
    num_fraud_rings: int = 4,
    seed: int = 42,
) -> tuple[str, list[dict], list[dict]]:
    """
    Generate mock data and return as a CSV string.

    Returns:
        (csv_string, companies, embedded_rings)
    """
    companies, transactions, rings = generate_mock_data(
        num_companies=num_companies,
        num_legitimate_txns=num_legitimate_txns,
        num_fraud_rings=num_fraud_rings,
        seed=seed,
    )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["buyer_pin", "seller_pin", "invoice_number", "amount", "vat_amount", "invoice_date"],
    )
    writer.writeheader()
    writer.writerows(transactions)

    return output.getvalue(), companies, rings
