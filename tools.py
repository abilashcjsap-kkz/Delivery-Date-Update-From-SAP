"""Business tools exposed to Gemini function calling."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

TOOL_DECLARATIONS = [
    {
        "name": "get_delivery_options",
        "description": "Return fulfillment and delivery promise options for a material, quantity, and address.",
        "parameters": {
            "type": "object",
            "properties": {
                "material": {"type": "string"},
                "quantity": {"type": "number"},
                "address": {"type": "string"},
            },
            "required": ["material", "quantity", "address"],
        },
    }
]


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name != "get_delivery_options":
        raise ValueError(f"Unknown tool: {name}")

    material = str(args.get("material", "")).strip()
    quantity = float(args.get("quantity", 0))
    if not material or quantity <= 0:
        raise ValueError("Material and positive quantity are required.")

    delivery_date = (date.today() + timedelta(days=5)).isoformat()
    return {
        "material": material,
        "requested_qty": quantity,
        "options": [
            {
                "scenario": "FULL_STOCK_FROM_ONE_PLANT",
                "plant": "AUTO",
                "plant_name": "Best available SAP plant",
                "available_qty": quantity,
                "delivery_date": delivery_date,
                "reason": "Demo rule engine selected the earliest available full-stock option.",
            }
        ],
        "recommended_by_rule_engine": {
            "scenario": "FULL_STOCK_FROM_ONE_PLANT",
            "plant": "AUTO",
            "plant_name": "Best available SAP plant",
            "delivery_date": delivery_date,
        },
    }
