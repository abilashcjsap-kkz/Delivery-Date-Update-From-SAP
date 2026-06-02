import pytest

import app as flask_app
from sap_client import get_sales_orders, parse_sap_date


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


def test_parse_sap_date():
    assert parse_sap_date("/Date(1741564800000)/") == "2025-03-10"


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
