# Technical Design Decisions & Resolutions (DECISIONS.md)

This document outlines the product ambiguities we resolved, the specific boundaries of each source pipeline, and key clarifying questions we would present to our Product Manager.

---

## 1. Ambiguities Resolved & Solutions

### A. SAP German Column Headers & Inconsistent Formats
- **Ambiguity**: SAP ALV exports can contain German column titles (`WERKS`, `BUDAT`, `MENGE`, `MEINS`, `MAKTX`, `DMBTR`, `WAERS`), European number formats (e.g., `12.500,00` instead of `12500.00`), and varying date representations (`YYYYMMDD` vs `DD.MM.YYYY`).
- **Resolution**:
  - Built a column mapping dictionary inside our SAP parser to treat English and German fields interchangeably (e.g. checking `WERKS` or `Werks` or `Plant`).
  - Implemented string decimal cleanups to swap European comma separators to standard periods before conversion.
  - Coded a polymorphic date parser that checks date formats dynamically (using splitting rules and length checkers).

### B. Utility Meter to Facility Mapping
- **Ambiguity**: Facilities teams export portal CSV records containing Service Agreement IDs and Meter Numbers. These documents never explicitly mention plant codes like `US02` or `DE01`.
- **Resolution**: 
  - Designed a dynamic substring resolver. If a Meter Number or Service ID contains a plant identifier (e.g., `SA-98103-MET-US02` or `MET-DE01`), the engine automatically links it to the matching `Facility` record.
  - If no match is found, the system **intentionally keeps it blank** but sets the review status to `SUSPICIOUS`, highlighting it as an **"Unmapped Facility Anomaly"** in React. The analyst can then review it and select the correct operating plant via a simple dropdown menu.

### C. Travel Distance Calculation via Haversine Formula
- **Ambiguity**: Corporate travel bookings (e.g., Concur dumps) do not include passenger miles/kilometers. They only supply departure and arrival IATA airport codes (e.g. `SFO` -> `BLR`).
- **Resolution**: 
  - Integrated a standard GPS coordinate dictionary mapping 15 main international hub airports.
  - Implemented the **Haversine formula** to calculate the Great Circle Distance.
  - If a booking includes a flight code not in our coordinate map, the engine flags it as `SUSPICIOUS` ("Airport coordinates not found") and defaults the distance to zero. The analyst can inspect it and manually input the calculated distance in kilometers via the Drawer edit panel, ensuring absolute coverage.

---

## 2. Subset Handled vs Ignored

We focused on building high-fidelity parsers for realistic export templates, prioritizing data integrity over superficial CRUD coverage.

| Source | Segment / Field Handled | Segment / Field Ignored |
| :--- | :--- | :--- |
| **SAP** | Material movements list (ALV CSV), German headers, fuel conversion (`GAL`/`M3` to `L`), procurement factors (`KG`/`TO` of steel/concrete). | IDoc parsing, active BAPI remote service execution, inventory adjustment slips. |
| **Utility** | Billing portal CSVs, billing dates, kWh usage, monthly proration calendar split, grid-specific Scope 2 coefficients. | Scanned PDF bill parsing (requires optical character recognition / OCR layouts), gas therms, peak demand (kW) peak pricing structures. |
| **Travel** | JSON dumps, Flight segments (with cabin class multipliers), Hotel night counts (country factors), Car rental vehicles. | Travel insurance, meal expenditures, parking tickets, toll receipts, flight layovers. |

---

## 3. Product Manager Questions

If we were refining this prototype for the enterprise launch, we would align with the PM on:

1. **Standardizing Emission Factors**: "What specific global carbon framework (e.g. DEFRA 2024, US EPA eGRID, or Greenhouse Gas Protocol) should we lock as the default reference index? Should we support annual factor updates with historical locks?"
2. **Facility Master Database**: "Should our plant database be managed as a static lookup file, or do we need a complete CRUD admin panel to manage facilities, regional grid coefficients, and local electricity meters?"
3. **Proration Alignment**: "Should utility bills overlapping fiscal quarters (e.g., Q1/Q2 boundary) be prorated dynamically down to the hour, or is our daily calendar-month fractional split the approved methodology for environmental audits?"
4. **cryptographic sealing Authority**: "When analysts bulk-lock records for auditor sign-off, should we integrate with corporate identity providers (e.g., Okta/SAML) to tie the SHA256 seal to a verified digital signature?"
