# Rechnungsklar

**A German e-invoice intake and review desk built with Streamlit.**

Rechnungsklar reads structured invoice data from XRechnung XML and ZUGFeRD PDFs, presents the important fields in a human-readable view, gives local field-extraction hints, and packages the original file with a review note. An optional KoSIT daemon can perform a standards-based validation pass.

## Open and run it in VS Code on WSL Ubuntu

Use Python 3.11 or newer inside Ubuntu/WSL.

1. Connect VS Code to **WSL: Ubuntu** using the Remote - WSL extension.
2. Open the project folder at `/home/gontr/code/Gilles177/rechnungsklar`.
3. Open a VS Code terminal and create the environment and install dependencies:

   ```bash
   bash setup.sh
   ```

4. Start the app:

   ```bash
   source .venv/bin/activate
   streamlit run app.py
   ```

The app opens at the local address Streamlit prints in the terminal. Choose one of the sample invoices in the sidebar to explore the inbox, details, review status, and exports. VS Code is configured to use `.venv/bin/python` as the project interpreter.

## What works in this first version

- Reads UBL-style Invoice/CreditNote XML and CII CrossIndustryInvoice XML.
- Extracts embedded invoice XML and readable text from ZUGFeRD PDFs.
- Shows supplier/customer data, dates, IBAN, totals, and line items where present.
- Flags important fields that the parser could not find. These are **local field checks**, not EN 16931 validation.
- Provides conservative PDF-text presence hints for supplier, invoice number, and amount. A missing hint means “look at this manually”; it does not prove that the PDF and XML differ.
- Lets you assign a simple review state and note.
- Exports the inbox to CSV or an individual review bundle containing the unchanged original, extracted invoice data, and any KoSIT report.
- Keeps records in Streamlit session state only; it does not write uploaded invoices to a database or local archive.

## Optional KoSIT integration

Without configuration, the app runs only its local field-extraction pre-check. It does not claim to validate XRechnung or EN 16931 rules.

To enable a standards-based check, run the KoSIT Validator daemon with a matching XRechnung scenario and repository. Obtain the validator and configuration releases from the [KoSIT Validator project](https://github.com/itplr-kosit/validator) and the [XRechnung configuration project](https://github.com/itplr-kosit/validator-configuration-xrechnung). Example command, adjusted to the paths and versions you installed:

```powershell
java -jar C:\tools\kosit\validator-<version>-standalone.jar `
  -s C:\tools\xrechnung\scenarios.xml `
  -r C:\tools\xrechnung `
  -D -H 127.0.0.1 -P 8080 --disable-gui
```

In a second terminal, set the service URL and start the app:

```powershell
$env:KOSIT_VALIDATOR_URL = "http://127.0.0.1:8080"
streamlit run app.py
```

Or add a private Streamlit secret in `.streamlit/secrets.toml`:

```toml
KOSIT_VALIDATOR_URL = "http://127.0.0.1:8080"
```

The app sends the extracted XML payload—not the original PDF—to the configured service. It displays KoSIT's HTTP acceptance/rejection status and returned report. A KoSIT result means accepted or rejected by the configured scenario and version; it is not tax advice or a guarantee of tax recognition.

The KoSIT daemon does not provide client authentication by itself. Keep it bound to localhost for local use. For a hosted app, use a private network and an authenticated/restricted proxy; do not expose an unauthenticated validator endpoint to the public internet. A Streamlit deployment and KoSIT daemon must be able to reach each other.

## Public demo and real invoices

The app is a portfolio prototype. Sample data is synthetic. Do not upload real customer invoices to a public demo. Uploaded files remain in the running Streamlit session's memory and are not stored by this app, but a public host is still not an appropriate place for confidential business documents. A production service needs access control, tenant isolation, secure storage, retention/deletion controls, backups, monitoring, and reviewed data-processing terms.

## Product and legal boundaries

- A plain PDF without structured invoice data is not converted into an e-invoice.
- The local pre-check only reports which key values were extracted.
- KoSIT validates against the configuration connected to it; the configuration version should be pinned and visible for a real product.
- A technical validation result does not decide tax treatment or guarantee that an invoice is legally correct.
- For a hybrid ZUGFeRD invoice, the structured XML is the key machine-readable part. Review the visible PDF and XML together when a value looks unusual.
- The CSV and ZIP exports are review aids, not a GoBD-compliant archive or accounting-system integration.

## Project structure

```text
app.py                  Streamlit interface and in-session workflow
rechnungsklar/
  models.py             Invoice and review data structures
  parser.py             Safe XML and ZUGFeRD PDF extraction
  validation.py         Local checks and optional KoSIT HTTP client
  exports.py            CSV and review-bundle generation
requirements.txt        Python dependencies
```

## Next build steps

1. Add representative synthetic fixtures for UBL, CII, and ZUGFeRD profiles.
2. Map KoSIT report rules to concise German explanations while preserving raw rule IDs.
3. Add an explicit, narrow XML/PDF comparison workflow and human confirmation.
4. Interview German Handwerk businesses and bookkeepers before choosing a customer niche or accounting export.
5. Only then add authentication, persistence, email intake, and production-grade storage.
