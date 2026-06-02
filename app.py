from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request

from agent import run_gemini_agent
from sap_client import (
    get_best_ship_to_address,
    get_customer_address,
    get_materials,
    get_sales_orders,
    get_ship_to_addresses,
)

app = Flask(__name__)


def _clean_line_items(lines: List[Dict[str, Any]], sales_order: str = "") -> List[Dict[str, Any]]:
    clean_lines = []
    for line in lines:
        material = str(line.get("material", "")).strip()
        if not material:
            continue
        try:
            qty = float(line.get("quantity", 0))
        except Exception:
            qty = 0
        if qty <= 0:
            continue
        clean_lines.append({
            "salesOrder": line.get("salesOrder") or sales_order,
            "salesOrderItem": line.get("salesOrderItem", ""),
            "material": material,
            "quantity": qty,
            "description": line.get("description", ""),
            "unit": line.get("unit", ""),
            "plant": line.get("plant", ""),
        })
    return clean_lines


def _delivery_date_from_tool_output(output: Dict[str, Any]) -> str:
    rec = output.get("recommended_by_rule_engine") or {}
    return (
        rec.get("delivery_date")
        or rec.get("final_delivery_date")
        or rec.get("estimated_customer_delivery_date")
        or rec.get("estimated_delivery_date")
        or ""
    )


def _line_delivery_results(lines: List[Dict[str, Any]], tool_trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    delivery_traces = [trace for trace in tool_trace if trace.get("tool") == "get_delivery_options"]
    for index, line in enumerate(lines):
        trace = delivery_traces[index] if index < len(delivery_traces) else {}
        output = trace.get("output") if isinstance(trace.get("output"), dict) else {}
        error = output.get("error", "") if isinstance(output, dict) else ""
        results.append({
            **line,
            "deliveryDate": _delivery_date_from_tool_output(output) if isinstance(output, dict) else "",
            "validationStatus": "Error" if error else "Validated",
            "validationMessage": error or "Delivery date validated using SAP ship-to address and Gemini AI planning.",
            "recommendedOption": output.get("recommended_by_rule_engine", {}) if isinstance(output, dict) else {},
        })
    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/sales-order/<sales_order>")
def sales_order_detail(sales_order: str):
    return render_template("sales_order_detail.html", sales_order=sales_order)


@app.route("/api/materials")
def api_materials():
    try:
        search = request.args.get("search", "")
        return jsonify({"source": "S4", "materials": get_materials(search=search, top=500)})
    except Exception as e:
        return jsonify({"source": "ERROR", "materials": [], "error": str(e)}), 500


@app.route("/api/sales-orders")
def api_sales_orders():
    try:
        sales_order = request.args.get("salesOrder", "")
        creation_date = request.args.get("creationDate", "")
        created_by = request.args.get("createdBy", "")
        if not any([sales_order, creation_date, created_by]):
            return jsonify({"error": "Enter sales order number, created date, or created by user."}), 400
        return jsonify(get_sales_orders(sales_order=sales_order, creation_date=creation_date, created_by=created_by))
    except Exception as e:
        return jsonify({"source": "ERROR", "salesOrders": [], "error": str(e)}), 500


@app.route("/api/sales-orders/<sales_order>")
def api_sales_order_detail(sales_order: str):
    try:
        result = get_sales_orders(sales_order=sales_order, top=1)
        orders = result.get("salesOrders", [])
        if not orders:
            return jsonify({"error": f"Sales order {sales_order} not found."}), 404
        return jsonify({"source": result.get("source", "S4"), "salesOrder": orders[0]})
    except Exception as e:
        return jsonify({"source": "ERROR", "error": str(e)}), 500


@app.route("/api/ship-to-addresses")
def api_ship_to_addresses():
    try:
        partner = request.args.get("partner", "")
        return jsonify(get_ship_to_addresses(partner=partner, top=20))
    except Exception as e:
        return jsonify({"source": "ERROR", "shipToAddresses": [], "error": str(e)}), 500


@app.route("/api/customer/<customer_number>")
def api_customer(customer_number: str):
    try:
        return jsonify(get_customer_address(customer_number))
    except Exception as e:
        return jsonify({"found": False, "error": str(e)}), 500


@app.route("/api/delivery-validation", methods=["POST"])
def api_delivery_validation():
    body = request.get_json(force=True) or {}
    sales_order = body.get("salesOrder", "")
    customer = body.get("customer", "")
    customer_number = body.get("customerNumber", "")
    address = (body.get("address") or "").strip()
    lines = _clean_line_items(body.get("lines") or [], sales_order=sales_order)

    if not lines:
        return jsonify({"error": "Sales order has no valid material line items for delivery validation."}), 400

    ship_to = {"found": bool(address), "address": address}
    if not address:
        ship_to = get_best_ship_to_address(customer_number)
        if not ship_to.get("found"):
            return jsonify({"error": ship_to.get("message") or "Ship-to address not found."}), 400
        address = ship_to.get("address", "")
        customer = customer or ship_to.get("name", "") or customer_number

    result = run_gemini_agent(customer, address, lines, customer_number=customer_number)
    line_results = _line_delivery_results(lines, result["tool_trace"])
    return jsonify({
        "salesOrder": sales_order,
        "customer": customer,
        "customerNumber": customer_number,
        "shipToAddress": ship_to,
        "address": address,
        "lineResults": line_results,
        "answer": result["answer"],
        "toolTrace": result["tool_trace"],
        "turns": result["turns"],
        "mode": result.get("mode"),
    })


@app.route("/api/quote", methods=["POST"])
def api_quote():
    body = request.get_json(force=True) or {}
    sales_order = body.get("salesOrder", "")
    customer = body.get("customer", "")
    customer_number = body.get("customerNumber", "")
    address_mode = body.get("addressMode", "free_text")
    address = (body.get("address") or "").strip()
    lines = _clean_line_items(body.get("lines") or [], sales_order=sales_order)

    if address_mode == "customer_number" and customer_number and not address:
        cust = get_customer_address(customer_number)
        if cust.get("found"):
            customer = customer or cust.get("name") or customer_number
            address = cust.get("address", "")
        else:
            return jsonify({"error": cust.get("message") or "Customer address not found"}), 400

    if not address:
        return jsonify({"error": "Delivery address is required. Enter address or provide a configured customer number."}), 400
    if not lines:
        return jsonify({"error": "Select at least one sales order item."}), 400

    result = run_gemini_agent(customer, address, lines, customer_number=customer_number)
    return jsonify({
        "salesOrder": sales_order,
        "customer": customer,
        "customerNumber": customer_number,
        "address": address,
        "lines": lines,
        "lineResults": _line_delivery_results(lines, result["tool_trace"]),
        "answer": result["answer"],
        "toolTrace": result["tool_trace"],
        "turns": result["turns"],
        "mode": result.get("mode"),
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
