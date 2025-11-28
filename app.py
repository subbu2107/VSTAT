from flask import Flask, jsonify, request, render_template
from dcf import dcf_bp, run_dcf_logic
from relative import relative_bp, run_relative_logic
from news import news_bp, fetch_all_headlines

app = Flask(__name__)

# Register Blueprints
app.register_blueprint(dcf_bp, url_prefix="/dcf")
app.register_blueprint(relative_bp, url_prefix="/relative")
app.register_blueprint(news_bp, url_prefix="/news")

@app.route("/")
def input_form():
    stock = request.args.get("stock", "").upper()
    headlines = fetch_all_headlines()

    if stock:
        dcf_data = run_dcf_logic(stock)
        relative_data = run_relative_logic(stock)

        def safe_json(data):
            return data.json if hasattr(data, "json") else data

        stock_data = {
            "Stock": stock,
            "DCF": safe_json(dcf_data),
            "RelativeValuation": safe_json(relative_data)
        }
    else:
        stock_data = None

    return render_template("index.html", headlines=headlines, stock_data=stock_data)

@app.route("/combined")
def combined():
    stock = request.args.get("stock", "").upper()
    if not stock:
        return jsonify({"error": "Missing stock parameter"}), 400

    dcf_result = run_dcf_logic(stock)
    relative_result = run_relative_logic(stock)

    def clean_json(obj):
        return obj.json if hasattr(obj, "json") else obj

    return jsonify({
        "Stock": stock,
        "DCF": clean_json(dcf_result),
        "RelativeValuation": clean_json(relative_result)
    })

if __name__ == "__main__":
    app.run(debug=True)
