import json
from typing import Any, Dict, List

import requests

from config import GEMINI_API_KEY, GEMINI_URL
from tools import TOOL_DECLARATIONS, execute_tool


def _fallback_answer(customer: str, address: str, lines: List[Dict[str, Any]], tool_trace: List[Dict[str, Any]]) -> str:
    if not tool_trace:
        return "No SAP tool results were available. Check SAP connection and Gemini API key."
    last = tool_trace[-1]["output"]
    if isinstance(last, dict) and "options" in last:
        rec = last.get("recommended_by_rule_engine") or {}
        material = last.get("material")
        qty = last.get("requested_qty")
        if not rec:
            return f"No feasible delivery option was found for material {material}, quantity {qty}."
        scenario = rec.get("scenario", "DELIVERY_OPTION")
        if scenario == "FULL_STOCK_FROM_ONE_PLANT":
            return (
                f"Recommended: ship {qty} of material {material} from plant {rec.get('plant')} "
                f"({rec.get('plant_name','')}). Estimated delivery date: {rec.get('delivery_date')}. "
                "Reason: this plant has sufficient stock and is the best ranked available option."
            )
        if scenario == "SPLIT_SHIPMENT":
            return f"Recommended: split shipment for material {material}. Final estimated delivery date: {rec.get('final_delivery_date')}."
        if scenario == "OPEN_PURCHASE_ORDER":
            return f"Recommended: use incoming PO {rec.get('purchase_order')}. Estimated delivery after supply date: {rec.get('estimated_customer_delivery_date')}."
        return f"Recommended procurement option for material {material}. Estimated delivery: {rec.get('estimated_delivery_date')}."
    return "SAP tools executed successfully. Review the tool trace for fulfillment options."


def run_gemini_agent(customer: str, address: str, lines: List[Dict[str, Any]], customer_number: str = "") -> Dict[str, Any]:
    """Gemini function-calling supply-chain planner."""
    tool_trace: List[Dict[str, Any]] = []

    for line in lines:
        try:
            out = execute_tool("get_delivery_options", {
                "material": line["material"],
                "quantity": float(line["quantity"]),
                "address": address,
            })
            tool_trace.append({"tool": "get_delivery_options", "input": line, "output": out})
        except Exception as e:
            tool_trace.append({"tool": "get_delivery_options", "input": line, "output": {"error": str(e)}})

    if not GEMINI_API_KEY:
        return {
            "answer": _fallback_answer(customer, address, lines, tool_trace),
            "tool_trace": tool_trace,
            "turns": 0,
            "mode": "fallback_no_gemini_key",
        }

    system_prompt = """
You are an Agentic AI Supply Chain Delivery Promise Planner connected to SAP S/4HANA OData tools.

Business goal:
Provide an Amazon-style delivery promise to the customer and explain the fulfillment strategy.

Rules:
- Use get_delivery_options for each selected sales order material before giving a final recommendation.
- Prefer the earliest reliable customer delivery date.
- Mention sales order item, plant, quantity, delivery date, and reason when available.
- Keep final answer concise and customer friendly.
- Return useful detail for a demo, but do not expose credentials or internal URLs.
"""

    order_prompt = {
        "customer": customer,
        "customer_number": customer_number,
        "delivery_address": address,
        "lines": lines,
        "already_collected_tool_results": tool_trace,
        "required_output": [
            "Amazon-style delivery promise",
            "recommended fulfillment plan",
            "split shipment if useful",
            "alternate options",
            "brief AI reasoning",
        ],
    }

    messages: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": system_prompt + "\n\nOrder JSON:\n" + json.dumps(order_prompt, indent=2)}]}
    ]

    max_turns = 8
    for turn in range(max_turns):
        payload = {
            "contents": messages,
            "tools": [{"function_declarations": TOOL_DECLARATIONS}],
            "generationConfig": {"temperature": 0.15, "topP": 0.8},
        }
        try:
            resp = requests.post(GEMINI_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=40)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {
                "answer": _fallback_answer(customer, address, lines, tool_trace) + f"\n\nGemini call failed: {e}",
                "tool_trace": tool_trace,
                "turns": turn,
                "mode": "fallback_gemini_error",
            }

        candidate = data.get("candidates", [{}])[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        messages.append({"role": "model", "parts": parts})

        tool_calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not tool_calls:
            final_text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()
            return {
                "answer": final_text or _fallback_answer(customer, address, lines, tool_trace),
                "tool_trace": tool_trace,
                "turns": turn + 1,
                "mode": "gemini_agentic",
            }

        function_responses = []
        for fc in tool_calls:
            name = fc.get("name")
            args = fc.get("args", {}) or {}
            try:
                result = execute_tool(name, args)
            except Exception as e:
                result = {"error": str(e)}
            tool_trace.append({"tool": name, "input": args, "output": result})
            function_responses.append({"functionResponse": {"name": name, "response": result}})

        messages.append({"role": "user", "parts": function_responses})

    return {
        "answer": _fallback_answer(customer, address, lines, tool_trace) + "\n\nAgent reached maximum turns.",
        "tool_trace": tool_trace,
        "turns": max_turns,
        "mode": "max_turns",
    }
