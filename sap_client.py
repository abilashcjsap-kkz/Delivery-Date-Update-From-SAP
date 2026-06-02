"""SAP S/4HANA OData helper functions."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import SAP_BASE_URL, SAP_PASSWORD, SAP_TIMEOUT_SECONDS, SAP_USERNAME

SALES_ORDER_PATH = "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder"


def _sap_auth() -> Optional[tuple[str, str]]:
    if SAP_USERNAME and SAP_PASSWORD:
        return SAP_USERNAME, SAP_PASSWORD
    return None


def _sap_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not SAP_BASE_URL:
        raise RuntimeError("SAP_BASE_URL is not configured.")

    import requests

    url = f"{SAP_BASE_URL}{path}"
    response = requests.get(
        url,
        params=params,
        auth=_sap_auth(),
        headers={"Accept": "application/json"},
        timeout=SAP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _escape_odata_value(value: str) -> str:
    return value.replace("'", "''")


def _build_sales_order_filter(
    sales_order: str = "",
    creation_date: str = "",
    created_by: str = "",
) -> str:
    filters: List[str] = []
    if sales_order:
        filters.append(f"SalesOrder eq '{_escape_odata_value(sales_order.strip())}'")
    if created_by:
        filters.append(f"CreatedByUser eq '{_escape_odata_value(created_by.strip().upper())}'")
    if creation_date:
        # SAP Gateway V2 commonly accepts datetime'YYYY-MM-DDT00:00:00' for Edm.DateTime filters.
        filters.append(f"CreationDate eq datetime'{creation_date.strip()}T00:00:00'")
    return " and ".join(filters)


def parse_sap_date(value: Any) -> str:
    """Convert SAP /Date(milliseconds)/ values to YYYY-MM-DD strings."""
    if not value or not isinstance(value, str):
        return ""
    match = re.search(r"/Date\((-?\d+)", value)
    if not match:
        return value
    milliseconds = int(match.group(1))
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).date().isoformat()


def _odata_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    d_node = payload.get("d", {})
    if isinstance(d_node, dict):
        results = d_node.get("results")
        if isinstance(results, list):
            return results
        if d_node:
            return [d_node]
    return []


def _normalize_sales_order(raw: Dict[str, Any]) -> Dict[str, Any]:
    item_node = raw.get("to_Item") or {}
    raw_items = item_node.get("results", []) if isinstance(item_node, dict) else []
    items = []
    for item in raw_items:
        items.append(
            {
                "salesOrder": item.get("SalesOrder", ""),
                "salesOrderItem": item.get("SalesOrderItem", ""),
                "higherLevelItem": item.get("HigherLevelItem", ""),
                "category": item.get("SalesOrderItemCategory", ""),
                "material": item.get("Material", ""),
                "description": item.get("SalesOrderItemText", ""),
                "quantity": item.get("RequestedQuantity", ""),
                "unit": item.get("RequestedQuantityUnit") or item.get("RequestedQuantitySAPUnit", ""),
                "plant": item.get("ProductionPlant", ""),
                "shippingPoint": item.get("ShippingPoint", ""),
                "netAmount": item.get("NetAmount", ""),
                "currency": item.get("TransactionCurrency", ""),
                "deliveryStatus": item.get("DeliveryStatus", ""),
                "rejectionReason": item.get("SalesDocumentRjcnReason", ""),
            }
        )

    return {
        "salesOrder": raw.get("SalesOrder", ""),
        "salesOrderType": raw.get("SalesOrderType", ""),
        "soldToParty": raw.get("SoldToParty", ""),
        "creationDate": parse_sap_date(raw.get("CreationDate")),
        "createdBy": raw.get("CreatedByUser", ""),
        "salesOrderDate": parse_sap_date(raw.get("SalesOrderDate")),
        "requestedDeliveryDate": parse_sap_date(raw.get("RequestedDeliveryDate")),
        "purchaseOrderByCustomer": raw.get("PurchaseOrderByCustomer", ""),
        "totalNetAmount": raw.get("TotalNetAmount", ""),
        "currency": raw.get("TransactionCurrency", ""),
        "overallDeliveryStatus": raw.get("OverallTotalDeliveryStatus", ""),
        "items": items,
    }


def get_sales_orders(
    sales_order: str = "",
    creation_date: str = "",
    created_by: str = "",
    top: int = 20,
) -> Dict[str, Any]:
    """Fetch sales orders with expanded item details from SAP S/4HANA."""
    params: Dict[str, Any] = {"$expand": "to_Item", "$format": "json", "$top": top}
    filter_text = _build_sales_order_filter(sales_order, creation_date, created_by)
    if filter_text:
        params["$filter"] = filter_text

    payload = _sap_get(SALES_ORDER_PATH, params=params)
    orders = [_normalize_sales_order(order) for order in _odata_results(payload)]
    return {"source": "S4", "salesOrders": orders, "count": len(orders)}


def get_materials(search: str = "", top: int = 500) -> List[Dict[str, Any]]:
    """Placeholder material lookup retained for backwards-compatible screens."""
    return []


def get_customer_address(customer_number: str) -> Dict[str, Any]:
    """Placeholder customer address lookup retained for quote compatibility."""
    if not customer_number:
        return {"found": False, "message": "Customer number is required."}
    return {"found": False, "message": "Customer address lookup is not configured."}
