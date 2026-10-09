from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from zipfile import ZIP_DEFLATED, ZipFile

from .models import InvoiceRecord
from .validation import finding_dicts


def _cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def inbox_csv(records: list[InvoiceRecord]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        ["Dateiname", "Format", "Lieferant", "Rechnungsnummer", "Rechnungsdatum", "Fällig am", "Währung", "Zahlbetrag", "Status", "Hinweise", "Notiz"]
    )
    for record in records:
        invoice = record.invoice
        writer.writerow(
            [
                _cell(record.filename),
                _cell(record.source_format),
                _cell(invoice.seller_name),
                _cell(invoice.invoice_number),
                _cell(invoice.issue_date),
                _cell(invoice.due_date),
                _cell(invoice.currency),
                _cell(invoice.payable_amount),
                _cell(record.review_state),
                _cell(sum(f.severity == "error" for f in record.findings)),
                _cell(record.review_note),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def build_review_bundle(record: InvoiceRecord) -> bytes:
    invoice = asdict(record.invoice)
    report = {
        "product": "Rechnungsklar portfolio prototype",
        "purpose": "Review aid; not a GoBD archive, legal opinion, or tax certificate.",
        "source_file": record.filename,
        "source_format": record.source_format,
        "review_state": record.review_state,
        "review_note": record.review_note,
        "validation_source": record.validation_source,
        "kosit_status": record.kosit_status,
        "findings": finding_dicts(record.findings),
        "invoice": invoice,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(record.filename, record.original_bytes)
        archive.writestr("rechnungsklar-pruefnotiz.json", encoded)
        if record.kosit_report:
            archive.writestr("kosit-pruefbericht.xml", record.kosit_report.encode("utf-8"))
    return output.getvalue()
