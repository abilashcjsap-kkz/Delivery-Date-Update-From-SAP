# Delivery-Date-Update-From-SAP

Flask application for fetching SAP S/4HANA sales orders through `API_SALES_ORDER_SRV`, selecting order items, and generating a Gemini-assisted delivery date promise.

## Required environment variables

- `SAP_BASE_URL` - SAP host, for example `http://sap-host:8000`.
- `SAP_USERNAME` / `SAP_PASSWORD` - optional basic-auth credentials for SAP OData.
- `GEMINI_API_KEY` - optional Gemini key. Without it, the app returns deterministic fallback delivery promises.

## Run locally

```bash
pip install flask requests pytest
python app.py
```

Open `http://localhost:5000`, enter a sales order number, created date, or created by user, select item rows, enter the delivery address, and generate the delivery date.
