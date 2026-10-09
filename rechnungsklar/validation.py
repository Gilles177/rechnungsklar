from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import re
from decimal import Decimal, InvalidOperation

import requests

from .models import InvoiceRecord


@dataclass
class Finding:
    severity: str
    title: str
    message: str
    code: str = ""


@dataclass
class ValidationResult:
    findings: list[Finding]
    source: str = "Lokale Vorprüfung"
    kosit_status: str | None = None
    kosit_report: str = ""
    kosit_error: str | None = None


def local_preflight(record: InvoiceRecord) -> list[Finding]:
    """Check whether key values were extracted; this is not EN 16931 validation."""
    invoice = record.invoice
    findings: list[Finding] = []
    required_fields = [
        (invoice.invoice_number, "Rechnungsnummer", "Die Rechnungsnummer wurde aus dem strukturierten Teil nicht erkannt."),
        (invoice.seller_name, "Lieferant", "Der Lieferantenname wurde nicht erkannt. Bitte XML und PDF manuell prüfen."),
        (invoice.issue_date, "Rechnungsdatum", "Das Rechnungsdatum wurde nicht erkannt."),
        (invoice.currency, "Währung", "Die Rechnungswährung wurde nicht erkannt."),
        (invoice.payable_amount, "Zahlbetrag", "Der Zahlbetrag wurde nicht erkannt."),
    ]
    for value, label, message in required_fields:
        if value is None or value == "":
            findings.append(
                Finding(
                    severity="error",
                    title=f"{label} fehlt in der Ansicht",
                    message=message,
                    code=f"LOCAL-MISSING-{label.upper().replace(' ', '-')}",
                )
            )

    if not invoice.buyer_name:
        findings.append(
            Finding(
                severity="warning",
                title="Rechnungsempfänger nicht erkannt",
                message="Bitte kontrollieren, ob der Empfänger in den strukturierten Daten vorhanden ist.",
                code="LOCAL-MISSING-BUYER",
            )
        )

    if invoice.due_date is None:
        findings.append(
            Finding(
                severity="info",
                title="Kein Fälligkeitsdatum erkannt",
                message="In der Rechnung wurde kein separates Zahlungsziel gefunden.",
                code="LOCAL-NO-DUE-DATE",
            )
        )

    if not findings:
        findings.append(
            Finding(
                severity="info",
                title="Wichtige Anzeigefelder erkannt",
                message="Die wichtigsten Rechnungswerte konnten aus der XML-Datei ausgelesen werden. Das ist keine EN 16931- oder Steuerprüfung.",
                code="LOCAL-FIELDS-READ",
            )
        )
    return findings


def run_validation(record: InvoiceRecord, *, force_kosit: bool = False) -> ValidationResult:
    """Run a transparent local preflight and optionally call a KoSIT daemon."""
    findings = local_preflight(record)
    validator_url = os.getenv("KOSIT_VALIDATOR_URL", "").strip().rstrip("/")
    if not force_kosit:
        return ValidationResult(findings=findings)
    if not validator_url:
        return ValidationResult(
            findings=findings,
            kosit_error="KOSIT_VALIDATOR_URL ist nicht konfiguriert. Die lokale Vorprüfung wurde trotzdem ausgeführt.",
        )

    target_url = f"{validator_url}/rechnungsklar-invoice.xml"
    try:
        response = requests.post(
            target_url,
            data=record.invoice_xml,
            headers={"Content-Type": "application/xml; charset=utf-8", "Accept": "application/xml, text/plain, */*"},
            timeout=(4, 45),
        )
        report = response.text[:50000]
        if response.status_code == 200:
            status = "Vom KoSIT-Szenario akzeptiert"
        elif response.status_code == 406:
            status = "Vom KoSIT-Szenario zurückgewiesen"
        else:
            status = f"KoSIT antwortete mit HTTP {response.status_code}"
        error = None if response.status_code in {200, 406} else "KoSIT hat kein übliches Prüfresultat zurückgegeben. Details stehen im Prüfbericht."
        return ValidationResult(
            findings=findings,
            source="KoSIT",
            kosit_status=status,
            kosit_report=report,
            kosit_error=error,
        )
    except requests.RequestException as exc:
        return ValidationResult(
            findings=findings,
            source="Lokale Vorprüfung",
            kosit_error=f"KoSIT-Dienst nicht erreichbar: {exc.__class__.__name__}. Die lokale Vorprüfung bleibt verfügbar.",
        )


def finding_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(finding) for finding in findings]


def pdf_review_hints(record: InvoiceRecord) -> list[dict[str, str]]:
    """Compare a few known values to extractable PDF text without treating OCR as truth."""
    text = record.pdf_text or ""
    if not text.strip():
        return []

    def compact(value: str) -> str:
        return re.sub(r"[^\w]", "", value.casefold(), flags=re.UNICODE)

    results: list[dict[str, str]] = []
    for label, value in (
        ("Lieferant", record.invoice.seller_name),
        ("Rechnungsnummer", record.invoice.invoice_number),
    ):
        if not value:
            continue
        found = compact(value) in compact(text)
        results.append(
            {
                "Feld": label,
                "Hinweis": "Im PDF-Text gefunden" if found else "Nicht erkannt – visuell prüfen",
                "Status": "Erkannt" if found else "Prüfen",
            }
        )

    expected = record.invoice.payable_amount
    if expected is not None:
        amount_pattern = re.compile(r"(?<!\d)(-?(?:\d{1,3}(?:[ .,'’]\d{3})+|\d+)[,.]\d{2})(?!\d)")
        detected: set[Decimal] = set()
        for match in amount_pattern.finditer(text):
            neighborhood = text[max(0, match.start() - 6): min(len(text), match.end() + 8)].casefold()
            if "€" not in neighborhood and "eur" not in neighborhood:
                continue
            raw = match.group(1).replace(" ", "").replace("'", "").replace("’", "")
            sign = "-" if raw.startswith("-") else ""
            raw = raw.lstrip("-")
            digits = re.sub(r"\D", "", raw)
            if len(digits) < 3:
                continue
            try:
                detected.add(Decimal(f"{sign}{digits[:-2]}.{digits[-2:]}"))
            except InvalidOperation:
                continue

        if expected.quantize(Decimal("0.01")) in detected:
            results.append({"Feld": "Zahlbetrag", "Hinweis": "Im PDF-Text mit EUR-Bezug gefunden", "Status": "Erkannt"})
        elif detected:
            examples = ", ".join(f"{amount:.2f}" for amount in sorted(detected)[:3])
            results.append(
                {
                    "Feld": "Zahlbetrag",
                    "Hinweis": f"Strukturierter Wert {_format_amount(expected)} wurde nicht erkannt; PDF-Werte: {examples}. Bitte manuell vergleichen.",
                    "Status": "Prüfen",
                }
            )
        else:
            results.append(
                {
                    "Feld": "Zahlbetrag",
                    "Hinweis": "Kein eindeutig markierter EUR-Betrag im PDF-Text erkannt. Bitte Darstellung manuell vergleichen.",
                    "Status": "Nicht geprüft",
                }
            )
    return results


def _format_amount(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
