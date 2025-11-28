from flask import Blueprint, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np

relative_bp = Blueprint("relative", __name__)

# ✅ Sector mappings
SECTOR_PEER_MAP = {
    'Consumer Defensive': ['ITC.NS', 'HINDUNILVR.NS', 'NESTLEIND.NS', 'BRITANNIA.NS', 'TATACONSUM.NS'],
    'Consumer Cyclical': ['TATAMOTORS.NS', 'EICHERMOT.NS', 'BAJAJ-AUTO.NS', 'HEROMOTOCO.NS', 'M&M.NS', 'MARUTI.NS'],
    'Financial Services': ['HDFCBANK.NS', 'ICICIBANK.NS', 'KOTAKBANK.NS', 'AXISBANK.NS', 'SBIN.NS', 'BAJFINANCE.NS', 'BAJAJFINSV.NS', 'HDFC.NS'],
    'Information Technology': ['TCS.NS', 'INFY.NS', 'WIPRO.NS', 'TECHM.NS', 'HCLTECH.NS'],
    'Energy': ['RELIANCE.NS', 'ONGC.NS', 'BPCL.NS', 'IOC.NS', 'NTPC.NS', 'POWERGRID.NS'],
    'Healthcare': ['SUNPHARMA.NS', 'CIPLA.NS', 'DRREDDY.NS', 'DIVISLAB.NS', 'APOLLOHOSP.NS'],
    'Industrials': ['LTI.NS', 'LTIM.NS', 'L&T.NS', 'ADANIENT.NS'],
    'Materials': ['ULTRACEMCO.NS', 'GRASIM.NS', 'SHREECEM.NS', 'JSWSTEEL.NS', 'TATASTEEL.NS', 'HINDALCO.NS'],
    'Utilities': ['POWERGRID.NS', 'NTPC.NS'],
    'Telecommunication': ['BHARTIARTL.NS'],
    'Real Estate': ['DLF.NS']
}

SECTOR_ALIASES = {
    "Financial Services": ["bank", "finance", "nbfc", "lending", "credit", "insurance"],
    "Information Technology": ["tech", "software", "it services"],
    "Healthcare": ["pharma", "hospital", "biotech", "health"],
    "Energy": ["oil", "gas", "power", "energy"],
    "Industrials": ["infrastructure", "construction", "engineering", "industrial"],
    "Consumer Defensive": ["fmcg", "consumer staples", "defensive"],
    "Consumer Cyclical": ["auto", "discretionary", "cyclical"],
    "Utilities": ["electric", "utility", "water", "grid"],
    "Real Estate": ["property", "realty", "estate"],
    "Materials": ["cement", "steel", "metal", "materials"],
    "Telecommunication": ["telecom", "communication"]
}

def normalize_sector(sector):
    lower_sector = sector.lower()
    for standard, aliases in SECTOR_ALIASES.items():
        if any(alias in lower_sector for alias in aliases):
            return standard
    return sector

def get_pe_pb_based_value(ticker, peer_list):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        eps = info.get("trailingEps", np.nan)
        bvps = info.get("bookValue", np.nan)
        current_price = stock.history(period="1d")['Close'].iloc[-1]
        if pd.isna(eps) or pd.isna(bvps):
            return None, current_price

        hist = stock.history(period="max", interval="1mo")
        hist = hist[hist['Close'] > 5]
        hist["P/E"] = hist["Close"] / eps
        hist["P/B"] = hist["Close"] / bvps
        hist = hist.replace([np.inf, -np.inf], np.nan).dropna(subset=["P/E", "P/B"])
        avg_pe_10y = hist["P/E"].mean()
        avg_pb_10y = hist["P/B"].mean()
        val1 = avg_pe_10y * eps
        val2 = avg_pb_10y * bvps

        sector_pes, sector_pbs = [], []
        for peer in peer_list:
            peer_info = yf.Ticker(peer).info
            sector_pes.append(peer_info.get("trailingPE", np.nan))
            sector_pbs.append(peer_info.get("priceToBook", np.nan))

        avg_pe_sector = np.nanmean(sector_pes)
        avg_pb_sector = np.nanmean(sector_pbs)
        val3 = avg_pe_sector * eps if not np.isnan(avg_pe_sector) else 0
        val4 = avg_pb_sector * bvps if not np.isnan(avg_pb_sector) else 0

        values = [val1, val2, val3, val4]
        weights = [0.325, 0.275, 0.225, 0.175]

        pe_val = val1
        pb_val = val2
        avg_simple = np.nanmean([pe_val, pb_val])
        weighted_sum = sum(v * w for v, w in zip(values, weights) if not np.isnan(v))
        total_weight = sum(w for v, w in zip(values, weights) if not np.isnan(v))
        final_fair_value = round(weighted_sum / total_weight, 2) if total_weight > 0 else None

        if final_fair_value is not None and final_fair_value > 1.9 * current_price:
            final_fair_value = round(avg_simple, 2)

        return final_fair_value, current_price
    except:
        return None, None

# ✅ Route function handles jsonify
@relative_bp.route("/", methods=["GET"])
def relative_route():
    symbol = request.args.get("stock", "")
    result = run_relative_logic(symbol)
    return jsonify(result)

# ✅ Logic function returns dict only
def run_relative_logic(symbol):
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        symbol += ".NS"
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        sector = info.get('sector', None)
        if not sector:
            return {"error": "Sector not found."}

        sector = normalize_sector(sector)
        peers = SECTOR_PEER_MAP.get(sector, [])
        if not peers:
            return {"error": f"No peers mapped for sector '{sector}'."}

        fair_value, current_price = get_pe_pb_based_value(symbol, peers)
        pe = info.get("trailingPE", None)
        pb = info.get("priceToBook", None)
        verdict = "✅ Undervalued" if fair_value and current_price and fair_value > current_price else "❌ Overvalued"

        return {
            "Stock": symbol,
            "Sector": sector,
            "IntrinsicValue": fair_value,
            "CurrentPrice": current_price,
            "P/E": pe,
            "P/B": pb,
            "Verdict": verdict
        }
    except Exception as e:
        return {"error": str(e)}
