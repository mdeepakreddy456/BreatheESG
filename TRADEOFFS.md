# Technical Tradeoffs & Architectural Choices (TRADEOFFS.md)

This document describes the three features we deliberately did not build for this prototype and details the architectural, compliance, and engineering rationale for those decisions.

---

## 1. Scanned Utility PDF OCR Engine (Optical Character Recognition)
- **What it is**: An automated scanner that ingests PDF copies of electricity bills, runs OCR layout analysis, and extracts consumption keys.
- **Why we chose not to build it**:
  - **Fragility**: PDF bill formats change frequently. A PG&E bill template differs completely from Consolidated Edison or National Grid, and simple logo shifts can break regular expressions.
  - **Proto Limitation**: Developing a reliable, production-grade OCR parser requires expensive third-party vision APIs (like Google Cloud Document AI or AWS Textract).
  - **Tradeoff**: In the real world, enterprise facilities teams already have access to portal exports (like Green Button CSVs or automated EDI billing records). Standardizing our utility engine around Green Button CSVs ensures a highly robust parsing engine that never breaks due to document formatting changes.

---

## 2. Direct Live ERP Connectors (Concur API / SAP BAPI Webhooks)
- **What it is**: Active webhooks and credentials vaults connecting the app directly to active SAP systems or Concur travel servers.
- **Why we chose not to build it**:
  - **Access & Security**: Live ERP servers require complex corporate firewall clearance, credential encryption vaults, and private OAuth sandboxes. A live sync would not be testable by evaluators without access keys.
  - **Tradeoff**: By standardizing the interface around ALV flat-file CSVs (for SAP) and standardized itinerary JSON pushes (for travel), we support highly realistic schemas while keeping the prototype decoupled, secure, and fully testable locally or on public clouds (Render/Railway).

---

## 3. Automated Anomaly Auto-Corrections
- **What it is**: An artificial intelligence model or rule engine that automatically corrects suspicious rows (e.g., auto-correcting quantity spikes or guessing missing plant codes).
- **Why we chose not to build it**:
  - **Compliance Violation**: In professional financial and environmental auditing (under frameworks like CSRD or SEC guidelines), **automated modification of active records is a major compliance failure**.
  - **Audit Trails**: Every modification of a carbon balance ledger *must* be manually verified by a human analyst and stamped with a detailed, auditable change comment.
  - **Tradeoff**: We built an anomaly *detection* engine rather than an auto-corrector. This highlights anomalies dynamically (using red glowing tags in React) and prompts analysts to review the inline "Original vs Normalized" lineage view before writing their mandatory change justification. This design maintains strict compliance standards.
