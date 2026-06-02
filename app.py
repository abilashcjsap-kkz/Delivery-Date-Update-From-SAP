from flask import Flask, jsonify, render_template, request

from agent import run_gemini_agent
from sap_client import get_customer_address, get_materials, get_sales_orders

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


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


@app.route("/api/customer/<customer_number>")
def api_customer(customer_number: str):
    try:
        return jsonify(get_customer_address(customer_number))
    except Exception as e:
        return jsonify({"found": False, "error": str(e)}), 500


@app.route("/api/quote", methods=["POST"])
def api_quote():
    body = request.get_json(force=True) or {}
    sales_order = body.get("salesOrder", "")
    customer = body.get("customer", "")
    customer_number = body.get("customerNumber", "")
    address_mode = body.get("addressMode", "free_text")
    address = (body.get("address") or "").strip()
    lines = body.get("lines") or []

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

    if not clean_lines:
        return jsonify({"error": "Select valid sales order items with material and quantity."}), 400

    result = run_gemini_agent(customer, address, clean_lines, customer_number=customer_number)
    return jsonify({
        "salesOrder": sales_order,
        "customer": customer,
        "customerNumber": customer_number,
        "address": address,
        "lines": clean_lines,
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
