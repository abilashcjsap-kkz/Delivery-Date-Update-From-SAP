# Delivery-Date-Update-From-SAP

Flask application for fetching SAP S/4HANA sales orders through `API_SALES_ORDER_SRV`, selecting order items, and generating a Gemini-assisted delivery date promise.

## Configuration

The app now includes both `.env` and `.env.example` at the project root. Edit `.env` and replace the placeholder values before running locally.

```dotenv
SAP_BASE_URL=http://AHCLS4ADQA.amrutanjan.com:8000
SAP_USERNAME=your_sap_username
SAP_PASSWORD=your_sap_password
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-1.5-flash
```

Notes:

- `SAP_BASE_URL` should be only the SAP host/base URL. The app appends `/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder` automatically.
- `GEMINI_API_KEY` is optional for fallback/demo mode, but required for live Gemini responses.
- Environment variables already exported in your shell take priority over `.env` values.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`, enter a sales order number, created date, or created by user, select item rows, enter the delivery address, and generate the delivery date.
