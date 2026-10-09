from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable

import fitz
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .models import InvoiceData, InvoiceLine


class InvoiceParseError(ValueError):
    """Raised when an upload is not a supported structured invoice."""


@dataclass
class ParsedDocument:
    invoice: InvoiceData
    invoice_xml: bytes
    source_format: str
    pdf_text: str = ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.split(":")[-1]


def _path_matches(root, path: tuple[str, ...]):
    if not path:
        return []
    if _local_name(root.tag) == path[0]:
        current = [root]
    else:
        current = [node for node in root.iter() if _local_name(node.tag) == path[0]]
    for part in path[1:]:
        current = [child for node in current for child in list(node) if _local_name(child.tag) == part]
        if not current:
            break
    return current


def _first_text(root, paths: Iterable[tuple[str, ...]]) -> str | None:
    for path in paths:
        for node in _path_matches(root, path):
            value = "".join(node.itertext()).strip()
            if value:
                return value
    return None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    normalized = value.strip().replace(" ", "")
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    elif "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    if len(value) >= 10 and value[4:5] == "-":
        return value[:10]
    return value


def _parse_xml(xml_bytes: bytes) -> tuple[InvoiceData, str]:
    try:
        root = SafeET.fromstring(xml_bytes)
    except (SafeET.ParseError, DefusedXmlException, ValueError) as exc:
        raise InvoiceParseError(f"Die XML-Datei kann nicht sicher gelesen werden ({exc}).") from exc

    root_name = _local_name(root.tag)
    if root_name not in {"Invoice", "CreditNote", "CrossIndustryInvoice"}:
        raise InvoiceParseError(f"Nicht unterstützter XML-Dokumenttyp: {root_name}.")

    is_cii = root_name == "CrossIndustryInvoice"
    if is_cii:
        number_paths = [("ExchangedDocument", "ID")]
        issue_paths = [("ExchangedDocument", "IssueDateTime", "DateTimeString")]
        due_paths = [("SpecifiedTradePaymentTerms", "DueDateDateTime", "DateTimeString")]
        seller_paths = [
            ("SellerTradeParty", "Name"),
            ("SellerTradeParty", "SpecifiedLegalOrganization", "TradingBusinessName"),
        ]
        seller_vat_paths = [("SellerTradeParty", "SpecifiedTaxRegistration", "ID")]
        buyer_paths = [("BuyerTradeParty", "Name")]
        buyer_vat_paths = [("BuyerTradeParty", "SpecifiedTaxRegistration", "ID")]
        currency_paths = [("ApplicableHeaderTradeSettlement", "InvoiceCurrencyCode")]
        net_paths = [("SpecifiedTradeSettlementHeaderMonetarySummation", "TaxBasisTotalAmount")]
        tax_paths = [("SpecifiedTradeSettlementHeaderMonetarySummation", "TaxTotalAmount")]
        total_paths = [("SpecifiedTradeSettlementHeaderMonetarySummation", "DuePayableAmount"),
                       ("SpecifiedTradeSettlementHeaderMonetarySummation", "GrandTotalAmount")]
        iban_paths = [("PayeePartyCreditorFinancialAccount", "IBANID")]
        line_names = {"IncludedSupplyChainTradeLineItem"}
        line_description_paths = [("SpecifiedTradeProduct", "Name")]
        line_quantity_paths = [("SpecifiedLineTradeDelivery", "BilledQuantity")]
        line_price_paths = [("GrossPriceProductTradePrice", "ChargeAmount"),
                            ("NetPriceProductTradePrice", "ChargeAmount")]
        line_total_paths = [("SpecifiedLineTradeSettlement", "SpecifiedTradeSettlementLineMonetarySummation", "LineTotalAmount")]
    else:
        number_paths = [(root_name, "ID"), ("ID",)]
        issue_paths = [(root_name, "IssueDate"), ("IssueDate",)]
        due_paths = [(root_name, "DueDate"), ("DueDate",)]
        supplier_path = "AccountingSupplierParty" if root_name == "Invoice" else "AccountingSupplierParty"
        buyer_path = "AccountingCustomerParty"
        seller_paths = [
            (supplier_path, "Party", "PartyLegalEntity", "RegistrationName"),
            (supplier_path, "Party", "PartyName", "Name"),
            (supplier_path, "Party", "Name"),
        ]
        seller_vat_paths = [(supplier_path, "Party", "PartyTaxScheme", "CompanyID")]
        buyer_paths = [
            (buyer_path, "Party", "PartyLegalEntity", "RegistrationName"),
            (buyer_path, "Party", "PartyName", "Name"),
            (buyer_path, "Party", "Name"),
        ]
        buyer_vat_paths = [(buyer_path, "Party", "PartyTaxScheme", "CompanyID")]
        currency_paths = [(root_name, "DocumentCurrencyCode"), ("DocumentCurrencyCode",)]
        net_paths = [("LegalMonetaryTotal", "TaxExclusiveAmount")]
        tax_paths = [("TaxTotal", "TaxAmount")]
        total_paths = [("LegalMonetaryTotal", "PayableAmount"), ("LegalMonetaryTotal", "TaxInclusiveAmount")]
        iban_paths = [("PayeeFinancialAccount", "ID")]
        line_names = {"InvoiceLine", "CreditNoteLine"}
        line_description_paths = [("Item", "Name")]
        line_quantity_paths = [("InvoicedQuantity",), ("CreditedQuantity",)]
        line_price_paths = [("Price", "PriceAmount")]
        line_total_paths = [("LineExtensionAmount",)]

    seller_name = _first_text(root, seller_paths)
    seller_vat = _first_text(root, seller_vat_paths)
    buyer_name = _first_text(root, buyer_paths)
    buyer_vat = _first_text(root, buyer_vat_paths)
    currency = _first_text(root, currency_paths)
    customization = _first_text(root, [(root_name, "CustomizationID"), ("CustomizationID",)])

    iban = _first_text(root, iban_paths)
    if iban:
        iban = "".join(iban.split())

    lines: list[InvoiceLine] = []
    for node in root.iter():
        if _local_name(node.tag) not in line_names:
            continue
        lines.append(
            InvoiceLine(
                description=_first_text(node, line_description_paths),
                quantity=_first_text(node, line_quantity_paths),
                unit_price=_decimal(_first_text(node, line_price_paths)),
                net_amount=_decimal(_first_text(node, line_total_paths)),
            )
        )

    invoice = InvoiceData(
        invoice_number=_first_text(root, number_paths),
        issue_date=_date(_first_text(root, issue_paths)),
        due_date=_date(_first_text(root, due_paths)),
        seller_name=seller_name,
        seller_vat_id=seller_vat,
        buyer_name=buyer_name,
        buyer_vat_id=buyer_vat,
        iban=iban,
        currency=currency,
        net_amount=_decimal(_first_text(root, net_paths)),
        tax_amount=_decimal(_first_text(root, tax_paths)),
        payable_amount=_decimal(_first_text(root, total_paths)),
        syntax="CII" if is_cii else "UBL",
        customization_id=customization,
        lines=lines,
    )
    return invoice, root_name


def parse_invoice_file(filename: str, payload: bytes) -> ParsedDocument:
    """Parse an XRechnung XML file or a ZUGFeRD PDF with embedded XML."""
    if not payload:
        raise InvoiceParseError("Die Datei ist leer.")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix == "xml":
        invoice, root_name = _parse_xml(payload)
        if invoice.syntax == "CII":
            source_format = "CII · strukturierte Rechnung"
        elif "xrechnung" in (invoice.customization_id or "").lower():
            source_format = "XRechnung · UBL"
        else:
            source_format = "UBL · strukturierte Rechnung"
        return ParsedDocument(invoice=invoice, invoice_xml=payload, source_format=source_format)

    if suffix != "pdf":
        raise InvoiceParseError("Unterstützt werden XML-Dateien und PDF-Dateien mit eingebettetem Rechnungs-XML.")

    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception as exc:
        raise InvoiceParseError("Das PDF konnte nicht geöffnet werden.") from exc

    try:
        pdf_text = "\n".join(
            document.load_page(page_number).get_text("text")
            for page_number in range(min(document.page_count, 12))
        )
        xml_candidates: list[tuple[str, bytes]] = []
        for name in document.embfile_names():
            try:
                embedded = document.embfile_get(name)
            except Exception:
                continue
            if embedded.lstrip().startswith(b"<"):
                xml_candidates.append((name, embedded))
    finally:
        document.close()

    if not xml_candidates:
        raise InvoiceParseError("Im PDF wurde kein eingebettetes Rechnungs-XML gefunden. Ein normales PDF ist keine strukturierte E-Rechnung.")

    parse_errors: list[str] = []
    for _embedded_name, xml_bytes in xml_candidates:
        try:
            invoice, root_name = _parse_xml(xml_bytes)
            syntax = "CII" if root_name == "CrossIndustryInvoice" else "UBL"
            return ParsedDocument(
                invoice=invoice,
                invoice_xml=xml_bytes,
                source_format=f"ZUGFeRD · {syntax} aus PDF",
                pdf_text=pdf_text,
            )
        except InvoiceParseError as exc:
            parse_errors.append(str(exc))
    reason = parse_errors[0] if parse_errors else "kein gültiges Rechnungs-XML"
    raise InvoiceParseError(f"Das eingebettete XML konnte nicht gelesen werden: {reason}")
