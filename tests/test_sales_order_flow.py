import importlib

import pytest

from config import GEMINI_MODEL, load_dotenv
from sap_client import get_sales_orders, get_ship_to_addresses, parse_sap_date


SAMPLE_SALES_ORDER = {
    "d": {
        "results": [
            {
                "SalesOrder": "1",
                "SalesOrderType": "ZGTO",
                "SoldToParty": "5100586",
                "CreationDate": "/Date(1741564800000)/",
                "CreatedByUser": "CFNANJA",
                "SalesOrderDate": "/Date(1741564800000)/",
                "RequestedDeliveryDate": "/Date(1741564800000)/",
                "PurchaseOrderByCustomer": "676069",
                "TotalNetAmount": "33609.14",
                "TransactionCurrency": "INR",
                "OverallTotalDeliveryStatus": "C",
                "to_Item": {
                    "results": [
                        {
                            "SalesOrder": "1",
                            "SalesOrderItem": "10",
                            "HigherLevelItem": "0",
                            "SalesOrderItemCategory": "TAN",
                            "SalesOrderItemText": "Comfy Dry Extra Long Hanger Pack NP3",
                            "Material": "6000000195",
                            "RequestedQuantity": "1296",
                            "RequestedQuantityUnit": "PAC",
                            "ProductionPlant": "CBGL",
                            "ShippingPoint": "OBGL",
                            "NetAmount": "33609.14",
                            "TransactionCurrency": "INR",
                            "DeliveryStatus": "A",
                            "SalesDocumentRjcnReason": "Z3",
                        }
                    ]
                },
            }
        ]
    }
}


SAMPLE_SHIP_TO = {
    "d": {
        "results": [
            {
                "Addrnumber": "24044",
                "Partner": "6100000",
                "Name1": "M/s. Abacus Pharma (Africa) Limited",
                "City1": "Kampala",
                "City2": "Lugogo",
                "PostCode1": "010102",
                "Street": "UMA Show Grounds",
                "Building": "Plot Nos. 28B, 32B,",
                "Country": "UG",
                "Region": "C",
                "TelNumber": "919999999999",
            }
        ]
    }
}


def test_parse_sap_date():
    assert parse_sap_date("/Date(1741564800000)/") == "2025-03-10"


def test_default_gemini_model_is_25_flash():
    assert GEMINI_MODEL == "gemini-2.5-flash"


def test_load_dotenv_keeps_existing_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SAP_BASE_URL=http://from-file.example:8000\nGEMINI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "already-exported")
    monkeypatch.delenv("SAP_BASE_URL", raising=False)

    load_dotenv(env_file)

    assert importlib.import_module("os").environ["SAP_BASE_URL"] == "http://from-file.example:8000"
    assert importlib.import_module("os").environ["GEMINI_API_KEY"] == "already-exported"


def test_get_ship_to_addresses_normalizes_address(monkeypatch):
    captured = {}

    def fake_sap_get(path, params):
        captured["path"] = path
        captured["params"] = params
        return SAMPLE_SHIP_TO

    monkeypatch.setattr("sap_client._sap_get", fake_sap_get)

    result = get_ship_to_addresses(partner="6100000")

    assert result["count"] == 1
    assert "ZI_SHIP_TO_CDS/ZI_SHIP_TO" in captured["path"]
    assert captured["params"]["$top"] == 20
    assert "Partner eq '6100000'" in captured["params"]["$filter"]
    address = result["shipToAddresses"][0]
    assert address["partner"] == "6100000"
    assert address["name"] == "M/s. Abacus Pharma (Africa) Limited"
    assert "Kampala" in address["address"]
    assert "UG" in address["address"]


def test_get_sales_orders_normalizes_expanded_items(monkeypatch):
    captured = {}

    def fake_sap_get(path, params):
        captured["path"] = path
        captured["params"] = params
        return SAMPLE_SALES_ORDER

    monkeypatch.setattr("sap_client._sap_get", fake_sap_get)

    result = get_sales_orders(sales_order="1", creation_date="2025-03-10", created_by="cfnanja")

    assert result["count"] == 1
    assert captured["params"]["$expand"] == "to_Item"
    assert "SalesOrder eq '1'" in captured["params"]["$filter"]
    assert "CreatedByUser eq 'CFNANJA'" in captured["params"]["$filter"]
    order = result["salesOrders"][0]
    assert order["salesOrder"] == "1"
    assert order["creationDate"] == "2025-03-10"
    assert order["items"][0]["material"] == "6000000195"
    assert order["items"][0]["quantity"] == "1296"


@pytest.fixture
def client(monkeypatch):
    flask = pytest.importorskip("flask")
    del flask
    flask_app = importlib.import_module("app")
    flask_app.app.config.update(TESTING=True)
    return flask_app.app.test_client()


def test_sales_orders_endpoint_requires_filter(client):
    response = client.get("/api/sales-orders")
    assert response.status_code == 400
    assert "Enter sales order" in response.get_json()["error"]


def test_quote_accepts_selected_sales_order_items(client, monkeypatch):
    def fake_agent(customer, address, lines, customer_number=""):
        return {
            "answer": "Delivery date is 2026-06-07",
            "tool_trace": [{"tool": "get_delivery_options", "input": lines[0], "output": {}}],
            "turns": 0,
            "mode": "test",
        }

    monkeypatch.setattr("app.run_gemini_agent", fake_agent)

    response = client.post(
        "/api/quote",
        json={
            "salesOrder": "1",
            "customerNumber": "5100586",
            "address": "Bengaluru, India",
            "lines": [
                {
                    "salesOrder": "1",
                    "salesOrderItem": "10",
                    "material": "6000000195",
                    "quantity": "1296",
                    "description": "Comfy Dry Extra Long Hanger Pack NP3",
                    "unit": "PAC",
                    "plant": "CBGL",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["salesOrder"] == "1"
    assert data["lines"][0]["salesOrderItem"] == "10"
    assert data["answer"] == "Delivery date is 2026-06-07"


def test_delivery_validation_autopopulates_line_results(client, monkeypatch):
    def fake_ship_to(customer_number):
        return {"found": True, "partner": customer_number, "name": "Ship To", "address": "Ship To Street, City"}

    def fake_agent(customer, address, lines, customer_number=""):
        return {
            "answer": "Delivery dates populated",
            "tool_trace": [
                {
                    "tool": "get_delivery_options",
                    "input": lines[0],
                    "output": {
                        "recommended_by_rule_engine": {
                            "scenario": "FULL_STOCK_FROM_ONE_PLANT",
                            "delivery_date": "2026-06-07",
                        }
                    },
                }
            ],
            "turns": 1,
            "mode": "test",
        }

    monkeypatch.setattr("app.get_best_ship_to_address", fake_ship_to)
    monkeypatch.setattr("app.run_gemini_agent", fake_agent)

    response = client.post(
        "/api/delivery-validation",
        json={
            "salesOrder": "1",
            "customerNumber": "6100000",
            "lines": [
                {
                    "salesOrder": "1",
                    "salesOrderItem": "10",
                    "material": "6000000195",
                    "quantity": "1296",
                    "description": "Comfy Dry Extra Long Hanger Pack NP3",
                    "unit": "PAC",
                    "plant": "CBGL",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["shipToAddress"]["partner"] == "6100000"
    assert data["lineResults"][0]["deliveryDate"] == "2026-06-07"
    assert data["lineResults"][0]["validationStatus"] == "Validated"


def test_gemini_429_uses_openai_fallback(monkeypatch):
    agent = importlib.import_module("agent")
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        if "generativelanguage" in url:
            return FakeResponse(429, {"error": {"message": "rate limit"}})
        return FakeResponse(
            200,
            {
                "id": "resp_test",
                "status": "completed",
                "model": "gpt-4.1-mini",
                "output_text": "OpenAI fallback delivery promise",
            },
        )

    monkeypatch.setattr(agent, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(agent, "OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr(agent, "OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(agent, "_post_json", fake_post)

    result = agent.run_gemini_agent(
        "Customer",
        "Ship To Street",
        [{"salesOrderItem": "10", "material": "6000000195", "quantity": 10}],
        customer_number="6100000",
    )

    assert result["mode"] == "openai_fallback_after_gemini_429"
    assert result["answer"] == "OpenAI fallback delivery promise"
    assert calls[0]["url"].startswith("https://generativelanguage.googleapis.com")
    assert calls[1]["url"] == agent.OPENAI_URL
    assert calls[1]["kwargs"]["headers"]["Authorization"] == "Bearer openai-key"
    assert result["tool_trace"][-1]["tool"] == "openai_fallback"
