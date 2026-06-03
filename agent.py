import json
from typing import Any, Dict, List

from config import GEMINI_API_KEY, GEMINI_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_URL
from tools import TOOL_DECLARATIONS, execute_tool


def _post_json(url: str, **kwargs: Any):
    import requests

    return requests.post(url, **kwargs)


def _fallback_answer(customer: str, address: str, lines: List[Dict[str, Any]], tool_trace: List[Dict[str, Any]]) -> str:
    if not tool_trace:
        return "No SAP tool results were available. Check SAP connection and Gemini/OpenAI API keys."
    last_delivery_trace = next((trace for trace in reversed(tool_trace) if trace.get("tool") == "get_delivery_options"), None)
    last = last_delivery_trace["output"] if last_delivery_trace else tool_trace[-1].get("output")
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


def _system_prompt() -> str:
    return """
You are an Agentic AI Supply Chain Delivery Promise Planner connected to SAP S/4HANA OData tools.

Business goal:
Provide an Amazon-style delivery promise to the customer and explain the fulfillment strategy.

Rules:
- Use get_delivery_options results for each selected sales order material before giving a final recommendation.
- Prefer the earliest reliable customer delivery date.
- Mention sales order item, plant, quantity, delivery date, and reason when available.
- Keep final answer concise and customer friendly.
- Return useful detail for a demo, but do not expose credentials or internal URLs.
"""


def _order_prompt(customer: str, address: str, lines: List[Dict[str, Any]], customer_number: str, tool_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
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


def _extract_openai_text(data: Dict[str, Any]) -> str:
    if data.get("output_text"):
        return str(data["output_text"]).strip()

    text_parts: List[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                text_parts.append(str(content["text"]))
    return " ".join(text_parts).strip()


def _call_openai_fallback(
    customer: str,
    address: str,
    lines: List[Dict[str, Any]],
    customer_number: str,
    tool_trace: List[Dict[str, Any]],
    reason: str,
    turns: int,
) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {
            "answer": _fallback_answer(customer, address, lines, tool_trace) + f"\n\nGemini was rate limited ({reason}), and OPENAI_API_KEY is not configured.",
            "tool_trace": tool_trace,
            "turns": turns,
            "mode": "fallback_gemini_429_no_openai_key",
        }

    prompt = _system_prompt() + "\n\nOrder JSON:\n" + json.dumps(
        _order_prompt(customer, address, lines, customer_number, tool_trace),
        indent=2,
    )
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.15,
    }
    try:
        response = _post_json(
            OPENAI_URL,
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=40,
        )
        response.raise_for_status()
        data = response.json()
        final_text = _extract_openai_text(data)
        tool_trace.append({
            "tool": "openai_fallback",
            "input": {"reason": reason, "model": OPENAI_MODEL},
            "output": {"response_id": data.get("id"), "status": data.get("status"), "used_model": data.get("model", OPENAI_MODEL)},
        })
        return {
            "answer": final_text or _fallback_answer(customer, address, lines, tool_trace),
            "tool_trace": tool_trace,
            "turns": turns,
            "mode": "openai_fallback_after_gemini_429",
        }
    except Exception as e:
        tool_trace.append({
            "tool": "openai_fallback",
            "input": {"reason": reason, "model": OPENAI_MODEL},
            "output": {"error": str(e)},
        })
        return {
            "answer": _fallback_answer(customer, address, lines, tool_trace) + f"\n\nGemini was rate limited ({reason}), and OpenAI fallback failed: {e}",
            "tool_trace": tool_trace,
            "turns": turns,
            "mode": "fallback_openai_error_after_gemini_429",
        }


def run_gemini_agent(customer: str, address: str, lines: List[Dict[str, Any]], customer_number: str = "") -> Dict[str, Any]:
    """Gemini function-calling supply-chain planner with OpenAI fallback for Gemini 429 rate limits."""
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

    system_prompt = _system_prompt()
    order_prompt = _order_prompt(customer, address, lines, customer_number, tool_trace)

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
            resp = _post_json(GEMINI_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=40)
            if resp.status_code == 429:
                return _call_openai_fallback(
                    customer,
                    address,
                    lines,
                    customer_number,
                    tool_trace,
                    reason="Gemini returned HTTP 429 rate limit",
                    turns=turn,
                )
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
