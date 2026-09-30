"""
CSV Parser for eTIMS transaction data.

Expected CSV columns:
  buyer_pin, seller_pin, invoice_number, amount, vat_amount, invoice_date

Handles:
  - Column name normalization
  - Date parsing (multiple formats)
  - Amount sanitization
  - Duplicate detection
  - Error collection
"""

import csv
import io
from datetime import date, datetime
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duplicates: int = 0


# Map common column name variations to canonical names
COLUMN_ALIASES = {
    "buyer_pin": ["buyer_pin", "buyerpin", "buyer", "buyer_kra_pin", "purchaser_pin"],
    "seller_pin": ["seller_pin", "sellerpin", "seller", "seller_kra_pin", "supplier_pin"],
    "buyer_name": ["buyer_name", "buyername", "purchaser_name"],
    "seller_name": ["seller_name", "sellername", "supplier_name"],
    "invoice_number": ["invoice_number", "invoice_no", "invoicenumber", "inv_no", "etims_invoice", "receipt_signature"],
    "amount": ["amount", "invoice_amount", "total_amount", "gross_amount", "value", "total_amount_kes"],
    "taxable_value": ["taxable_value", "taxable_value_kes", "taxable_amount"],
    "vat_amount": ["vat_amount", "vat", "tax_amount", "vat_value", "input_vat", "vat_amount_kes"],
    "invoice_date": ["invoice_date", "date", "inv_date", "transaction_date", "txn_date", "issue_date"],
    "hs_code": ["hs_code", "hscode"],
    "description": ["description", "desc", "item_description"],
}


def _normalize_column(col: str) -> str | None:
    """Map a raw column header to its canonical name."""
    col_lower = col.strip().lower().replace(" ", "_")
    for canonical, aliases in COLUMN_ALIASES.items():
        if col_lower in aliases:
            return canonical
    return None


def _parse_date(value: str) -> date | None:
    """Try multiple date formats."""
    if not value: return None
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> float | None:
    """Parse monetary amounts, handling commas and currency symbols."""
    if not value: return None
    try:
        cleaned = str(value).strip().replace(",", "").replace("KSh", "").replace("Ksh", "").replace("KES", "").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def parse_csv(file_content: str | bytes) -> ParseResult:
    """
    Parse CSV content into validated transaction records.

    Returns a ParseResult with records, errors, and duplicate count.
    """
    result = ParseResult()
    seen_invoices: set[str] = set()

    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8-sig")  # Handle BOM

    reader = csv.DictReader(io.StringIO(file_content))

    if not reader.fieldnames:
        result.errors.append("CSV file is empty or has no headers.")
        return result

    # Map raw headers to canonical names
    col_map = {}
    for raw_col in reader.fieldnames:
        canonical = _normalize_column(raw_col)
        if canonical:
            col_map[raw_col] = canonical

    required = {"buyer_pin", "seller_pin", "invoice_number", "amount", "vat_amount", "invoice_date"}
    found = set(col_map.values())
    missing = required - found
    if missing:
        result.errors.append(f"Missing required columns: {', '.join(missing)}")
        return result

    # Invert map for lookup
    reverse_map = {v: k for k, v in col_map.items()}

    for row_num, row in enumerate(reader, start=2):
        try:
            buyer_val = row[reverse_map["buyer_pin"]]
            if buyer_val and str(buyer_val).strip().startswith("#"):
                continue

            invoice_val = row[reverse_map["invoice_number"]]
            invoice = str(invoice_val).strip() if invoice_val else ""
            if not invoice:
                result.errors.append(f"Row {row_num}: Empty invoice number")
                continue

            if invoice in seen_invoices:
                result.duplicates += 1
                continue
            seen_invoices.add(invoice)

            buyer_val = row[reverse_map["buyer_pin"]]
            buyer = str(buyer_val).strip().upper() if buyer_val else ""
            
            seller_val = row[reverse_map["seller_pin"]]
            seller = str(seller_val).strip().upper() if seller_val else ""

            if not buyer or not seller:
                result.errors.append(f"Row {row_num}: Empty buyer or seller PIN")
                continue

            if buyer == seller:
                result.errors.append(f"Row {row_num}: Self-invoicing detected ({buyer})")
                continue

            amount = _parse_amount(row[reverse_map["amount"]])
            if amount is None or amount <= 0:
                result.errors.append(f"Row {row_num}: Invalid amount")
                continue

            vat = _parse_amount(row[reverse_map["vat_amount"]])
            if vat is None or vat < 0:
                result.errors.append(f"Row {row_num}: Invalid VAT amount")
                continue

            inv_date = _parse_date(row[reverse_map["invoice_date"]])
            if inv_date is None:
                result.errors.append(f"Row {row_num}: Invalid date format")
                continue

            rec = {
                "buyer_pin": buyer,
                "seller_pin": seller,
                "invoice_number": invoice,
                "amount": amount,
                "vat_amount": vat,
                "invoice_date": inv_date,
            }

            if "buyer_name" in reverse_map:
                val = row[reverse_map["buyer_name"]]
                rec["buyer_name"] = str(val).strip() if val else ""
            if "seller_name" in reverse_map:
                val = row[reverse_map["seller_name"]]
                rec["seller_name"] = str(val).strip() if val else ""
            if "hs_code" in reverse_map:
                val = row[reverse_map["hs_code"]]
                rec["hs_code"] = str(val).strip() if val else ""
            if "description" in reverse_map:
                val = row[reverse_map["description"]]
                rec["description"] = str(val).strip() if val else ""
            if "taxable_value" in reverse_map:
                rec["taxable_value"] = _parse_amount(row[reverse_map["taxable_value"]])

            result.records.append(rec)

        except Exception as e:
            result.errors.append(f"Row {row_num}: {str(e)}")

    return result
