# Delivery-Date-Update-From-SAP

Flask application for fetching SAP S/4HANA sales orders through `API_SALES_ORDER_SRV`, selecting order items, and generating a Gemini-assisted delivery date promise.

## Configuration

The app now includes both `.env` and `.env.example` at the project root. Edit `.env` and replace the placeholder values before running locally.

```dotenv
SAP_BASE_URL=http://AHCLS4ADQA.amrutanjan.com:8000
SAP_USERNAME=your_sap_username
SAP_PASSWORD=your_sap_password
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

Notes:

- `SAP_BASE_URL` should be only the SAP host/base URL. The app appends `/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder` automatically.
- `GEMINI_API_KEY` is optional for fallback/demo mode, but required for live Gemini responses.
- `OPENAI_API_KEY` is used only as an AI fallback when Gemini returns HTTP 429 rate-limit responses. The fallback uses OpenAI's Responses API.
- Environment variables already exported in your shell take priority over `.env` values.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`, enter a sales order number, created date, or created by user, and click **Fetch Sales Details**. The search results display sales order basic details, including net value and delivery status. Click **View Items** for a sales order to open the item-detail page; the app fetches ship-to details from `ZI_SHIP_TO_CDS/ZI_SHIP_TO`, validates each line, auto-populates delivery dates with Gemini AI planning, falls back to OpenAI when Gemini returns HTTP 429, and lets you show or hide the tool trace.
