# Data Source Research & Real-World Realities (SOURCES.md)

This document outlines the real-world source formats we researched, the technical properties of our fabricated datasets, and the operational anomalies that would break a production deployment.

---

## 1. Source 1: SAP ERP Fuel and Procurement

### A. Real-World Research & Rationale
- **Format Selected**: Flat-file CSV representing an ALV Grid viewer export from transaction codes **`MB51`** (Material Document List) or **`MIGO`** (Goods Movements).
- **What We Learned**:
  - SAP column headers standardly default to German technical table field names: `MBLNR` (Material Document), `WERKS` (Plant), `BUDAT` (Posting Date), `MATNR` (Material Number), `MAKTX` (Material Description), `MENGE` (Quantity), `MEINS` (Base Unit), and `DMBTR` (Amount in Local Currency).
  - Quantities are stored based on inventory base units of measure. Fuel is frequently tracked in `L` (Liters) or `GAL` (Gallons), and procurement in `KG` (Kilograms) or `TO` (Metric Tons).
  - Dates standardly export as `YYYYMMDD` (raw database format) or European `DD.MM.YYYY`.
- **Mock Data Design**:
  - `sap_raw_export.csv` models these constraints. It uses columns like `WERKS`, `BUDAT`, `MENGE`, and `MEINS`. It includes European comma numbers (`5400,50`) and realistic plant codes (`DE01`, `US02`, `IN03`).
- **What Breaks in Production**:
  - Custom material descriptions: If an SAP administrator updates a material name from "Diesel Kraftstoff" to "DIESEL - ENGINE RUNTIME", simple string matching breaks.
  - Custom units of measure (e.g. `DR` for Drum, or `VL` for Volume List) without standard weight conversion ratios.

---

## 2. Source 2: Utility Electricity Data

### A. Real-World Research & Rationale
- **Format Selected**: Billing total CSV export from commercial customer portal scrapes or the standardized **Green Button Initiative** format.
- **What We Learned**:
  - Utility exports are organized by Service Agreement ID and Meter Number.
  - Billing cycles follow standard utility reading dates and almost never align with calendar months (e.g. billing from April 12 to May 11).
  - Invoices include peak demands (kW), total charges, and complex time-of-use (TOU) tariff rates.
- **Mock Data Design**:
  - `utility_raw_export.csv` models standard billing exports. It contains `SA-98103-MET-US02`, non-aligned billing periods (March 15 to April 14), and raw kWh values.
- **What Breaks in Production**:
  - Billing gaps or duplicate uploads: If a facilities manager uploads the same bill twice or misses a month, the system could double-count or under-count Scope 2 values.
  - Meter replacements: If a physical plant swaps out a malfunctioning utility meter, the new meter ID will not be recognized, triggering suspicious errors until updated.

---

## 3. Source 3: Corporate Travel (Flights, Hotels, Rentals)

### A. Real-World Research & Rationale
- **Format Selected**: JSON payload structure representing standard endpoints of the **SAP Concur Itinerary v4 API** or **Navan Travel segments**.
- **What We Learned**:
  - Concur structures itineraries as Trips composed of detailed booking segments: `AIR` (flights), `HOTEL` (lodging), and `CAR` (ground rentals).
  - Flights do not specify distance; they only provide departure and arrival IATA airport codes (`JFK` -> `LHR`) and cabin service classes (Economy, Business, First).
  - Hotels list check-in/check-out dates, room nights, and localized country codes to map to regional lodging multipliers.
- **Mock Data Design**:
  - `concur_raw_export.json` models this API response. It includes segments with departure/arrival locations (SFO, BLR, JFK, LHR), vehicle codes (SUV, HYBRID), and lodging night registers.
- **What Breaks in Production**:
  - Layover flights: A trip from BLR to JFK via LHR might register as a single long-haul flight or split into distinct segments, leading to double-counting distance.
  - Unmapped small regional airports: Flight codes from private airstrips or small regional locations will fail coordinates lookup, defaulting to zero distance.
