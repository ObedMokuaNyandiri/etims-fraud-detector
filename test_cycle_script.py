import requests
import time

base_url = 'http://127.0.0.1:8000/api'

# Create a 4-node cycle
transactions = [
    {
        "buyer_pin": "P052222222B",
        "seller_pin": "P051111111A",
        "amount": 1000,
        "vat_amount": 160,
        "invoice_number": "INV-01",
        "invoice_date": "2026-09-01",
    },
    {
        "buyer_pin": "P053333333C",
        "seller_pin": "P052222222B",
        "amount": 1000,
        "vat_amount": 160,
        "invoice_number": "INV-02",
        "invoice_date": "2026-09-02",
    },
    {
        "buyer_pin": "P054444444D",
        "seller_pin": "P053333333C",
        "amount": 1000,
        "vat_amount": 160,
        "invoice_number": "INV-03",
        "invoice_date": "2026-09-03",
    },
    {
        "buyer_pin": "P051111111A",
        "seller_pin": "P054444444D",
        "amount": 1000,
        "vat_amount": 160,
        "invoice_number": "INV-04",
        "invoice_date": "2026-09-04",
    }
]

import csv
with open('test_cycle.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)

print("Created CSV")
