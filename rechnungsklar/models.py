from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class InvoiceLine:
    description: str | None = None
    quantity: str | None = None
    unit_price: Decimal | None = None
    net_amount: Decimal | None = None


@dataclass
class InvoiceData:
    invoice_number: str | None = None
    issue_date: str | None = None
    due_date: str | None = None
    seller_name: str | None = None
    seller_vat_id: str | None = None
    buyer_name: str | None = None
    buyer_vat_id: str | None = None
    iban: str | None = None
    currency: str | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    payable_amount: Decimal | None = None
    syntax: str = "Unbekannt"
    customization_id: str | None = None
    lines: list[InvoiceLine] = field(default_factory=list)


@dataclass
class InvoiceRecord:
    record_id: str
    filename: str
    original_bytes: bytes
    invoice: InvoiceData
    invoice_xml: bytes
    source_format: str
    created_at: datetime
    review_state: str = "Neu"
    review_note: str = ""
    is_demo: bool = False
    pdf_text: str = ""
    findings: list = field(default_factory=list)
    validation_source: str = "Lokale Vorprüfung"
    kosit_status: str | None = None
    kosit_report: str = ""
    kosit_error: str | None = None
