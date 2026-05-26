# Breathe ESG Ingestion, Normalization & Review Board Prototype

An enterprise-grade Django and React prototype built to ingest, normalize, and review environmental activity data from three realistic sources: SAP ERP (fuels/procurement), Utility billing portals (calendar-month proration), and Corporate Travel platforms (Concur JSON segments).

---

## 📄 Key Deliverables (Post-Submission Review Docs)

Per assignment requirements, all detailed architectural and research documentation is located in the root repository folder:

1. **[MODEL.md](file:///c:/Users/Deepak/Desktop/BreatheESG/MODEL.md)**: Detailed relational database schemas, multi-tenant segmentation, data lineages, and audit lock seal specifications.
2. **[DECISIONS.md](file:///c:/Users/Deepak/Desktop/BreatheESG/DECISIONS.md)**: Product and parsing ambiguities resolved, including German headers, meter plant mappings, and Haversine distance computations.
3. **[TRADEOFFS.md](file:///c:/Users/Deepak/Desktop/BreatheESG/TRADEOFFS.md)**: Three deliberate architectural tradeoffs made (OCR scanning limitations, OAuth live ERP syncing, and compliance-related manual corrections) and why.
4. **[SOURCES.md](file:///c:/Users/Deepak/Desktop/BreatheESG/SOURCES.md)**: Researched real-world format definitions (SAP ALV MB51 exports, PG&E billing logs, Concur JSON segments) and what edge cases break them in production.
5. **[walkthrough.md](file:///C:/Users/Deepak/.gemini/antigravity/brain/3116c900-a0ae-4dd7-bc36-e58f59e693b8/walkthrough.md)**: Sequential manual testing flow guide with mock data templates.

---

## 🚀 Quick Start Guide

Open two separate terminals in the repository root directory:

### 1. Start Django REST Backend Server
```bash
# Start Django Server
python manage.py runserver
```
*Backend runs at: http://127.0.0.1:8000*
*Admin Panel runs at: http://127.0.0.1:8000/admin/ (User: `admin`, Pass: `admin123`)*

To run backend unit tests:
```bash
python manage.py test esg_ingest
```

### 2. Start React Dev Server (Vite)
```bash
cd frontend
npm run dev
```
*Frontend runs at: http://localhost:5173 (or as output by Vite)*

---

## 📊 Mock Data Templates
Use these template files under the `mock_data/` directory to test the ingestion pipelines:
- `sap_raw_export.csv`: SAP ERP fuel and procurement movement logs featuring German headers and unit conversions.
- `utility_raw_export.csv`: PG&E-style utility portal billing sheet featuring calendar-month proration splits.
- `concur_raw_export.json`: Concur flight, hotel, and car itinerary segment collections.
