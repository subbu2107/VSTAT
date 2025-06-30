from flask import Blueprint, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np

# ✅ Set pandas option to suppress future warnings
pd.set_option('future.no_silent_downcasting', True)

dcf_bp = Blueprint("dcf", __name__)

def get_sector_beta(sector):
    SECTOR_BETA_MAP = {
        "Information Technology": 1.20, "Energy": 1.00, "Financial Services": 1.10,
        "Consumer Defensive": 0.75, "Consumer Cyclical": 1.05, "Healthcare": 0.85,
        "Industrials": 1.10, "Materials": 1.15, "Utilities": 0.70,
        "Communication Services": 0.90, "Real Estate": 1.20
    }
    return SECTOR_BETA_MAP.get(sector, 1.0)

def get_sector_risk_free(sector):
    base_rf = 0.07
    sector_rf_map = {
        "Utilities": base_rf - 0.005, "Consumer Defensive": base_rf - 0.005,
        "Healthcare": base_rf - 0.002, "Financial Services": base_rf,
        "Industrials": base_rf + 0.002, "Consumer Cyclical": base_rf + 0.005,
        "Information Technology": base_rf + 0.01, "Real Estate": base_rf + 0.012,
        "Energy": base_rf + 0.007, "Materials": base_rf + 0.006,
        "Communication Services": base_rf + 0.005
    }
    return round(sector_rf_map.get(sector, base_rf), 4)

def get_fcf_10_years(stock_name):
    try:
        stock = yf.Ticker(stock_name)
        cashflow = stock.cashflow
        fcf = cashflow.loc['Free Cash Flow'].sort_index(ascending=True)
        fcf_in_cr = (fcf / 1e7).round(2)
        fcf_df = pd.DataFrame({
            "Year": fcf.index.year,
            "FCF": fcf_in_cr.values
        }).dropna()
        return fcf_df
    except:
        return None

def calculate_wacc(equity_value, debt_value, beta, interest_expense_cr, sector):
    tax_rate = 0.25
    risk_free = get_sector_risk_free(sector)
    market_return = 0.12
    total = equity_value + debt_value
    if total == 0:
        raise ValueError("Equity + Debt must be greater than 0")
    cost_of_equity = max(risk_free + beta * (market_return - risk_free), 0.10)
    cost_of_debt = (interest_expense_cr / debt_value) if debt_value > 0 else 0.08
    equity_weight = equity_value / total
    debt_weight = debt_value / total
    after_tax_cost_of_debt = cost_of_debt * (1 - tax_rate)
    wacc = (equity_weight * cost_of_equity) + (debt_weight * after_tax_cost_of_debt)
    return round(wacc, 4), cost_of_equity, cost_of_debt, risk_free

def calculate_dcf_from_fcf(fcf_df, wacc, terminal_growth=0.03, projection_years=10):
    if fcf_df is None or len(fcf_df) < 4:
        return None, None, None, None
    recent_fcfs = fcf_df['FCF'][-5:]
    base_fcf = recent_fcfs.mean()
    raw_growth = fcf_df['FCF'].pct_change().dropna().median()
    growth_rate = min(max(raw_growth, 0.05), 0.15)
    projected_fcfs = []
    total_pv = 0
    for year in range(1, projection_years + 1):
        future_fcf = base_fcf * ((1 + growth_rate) ** year)
        discounted_fcf = future_fcf / ((1 + wacc) ** year)
        projected_fcfs.append(round(future_fcf, 2))
        total_pv += discounted_fcf
    terminal_value = (projected_fcfs[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** projection_years)
    dcf_value = total_pv + pv_terminal
    return dcf_value, projected_fcfs, growth_rate, base_fcf

def calculate_dcf_from_earnings(eps, roe, wacc, years=10, terminal_growth=0.03):
    projected_eps = []
    total_pv = 0
    for year in range(1, years + 1):
        growth_rate = 0.08
        future_eps = eps * ((1 + growth_rate) ** year)
        discounted_eps = future_eps / ((1 + wacc) ** year)
        projected_eps.append(round(future_eps, 2))
        total_pv += discounted_eps
    terminal_value = (projected_eps[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** years)
    intrinsic_value = total_pv + pv_terminal
    return round(intrinsic_value, 2), projected_eps

def get_shares_outstanding(stock_name):
    try:
        ticker = yf.Ticker(stock_name)
        shares = ticker.info['sharesOutstanding']
        return shares / 1e7
    except:
        return None

def get_financials(stock_name):
    try:
        ticker = yf.Ticker(stock_name)
        info = ticker.info
        equity = info.get("marketCap", 0) / 1e7
        sector = info.get("sector", "")
        beta = info.get("beta", get_sector_beta(sector)) or get_sector_beta(sector)
        bs = ticker.balance_sheet.fillna(0).infer_objects(copy=False)
        long_debt = bs.loc["Long Term Debt"].iloc[0] if "Long Term Debt" in bs.index else 0
        short_debt = bs.loc["Short Long Term Debt"].iloc[0] if "Short Long Term Debt" in bs.index else 0
        debt = (long_debt + short_debt) / 1e7
        is_df = ticker.financials.fillna(0).infer_objects(copy=False)
        interest_exp = 0
        for label in ["Interest Expense", "InterestExp"]:
            if label in is_df.index:
                interest_exp = is_df.loc[label].iloc[0]
                break
        interest_exp_cr = interest_exp / 1e7
        return equity, debt, beta, interest_exp_cr, sector
    except:
        return 0, 0, 1.0, 0.0, "Unknown"

def run_dcf_logic(stock_name):
    stock_name = stock_name.upper()
    if not stock_name.endswith(".NS"):
        stock_name += ".NS"
    result = {"stock": stock_name}
    ticker = yf.Ticker(stock_name)
    fcf_df = get_fcf_10_years(stock_name)
    shares = get_shares_outstanding(stock_name)
    equity, debt, beta, interest_expense_cr, sector = get_financials(stock_name)
    result["sector"] = sector

    if shares is None or pd.isna(equity) or pd.isna(debt):
        return {"error": "Missing data for DCF calculation."}

    try:
        wacc, cost_equity, cost_debt, risk_free = calculate_wacc(equity, debt, beta, interest_expense_cr, sector)
    except:
        return {"error": "Could not calculate WACC"}

    current_price = ticker.history(period="1d")['Close'].iloc[-1]
    result["current_price"] = round(current_price, 2)

    if sector == "Financial Services":
        eps_intrinsic = fcf_intrinsic = None
        try:
            eps = ticker.info.get("trailingEps", None)
            roe = ticker.info.get("returnOnEquity", 0.12)
            if eps and eps > 0:
                eps_intrinsic, _ = calculate_dcf_from_earnings(eps, roe, wacc)
                result["eps_intrinsic"] = round(eps_intrinsic, 2)
        except:
            pass
        try:
            if fcf_df is not None and not fcf_df.empty:
                dcf_value, _, _, _ = calculate_dcf_from_fcf(fcf_df, wacc)
                fcf_intrinsic = dcf_value / shares
                result["fcf_intrinsic"] = round(fcf_intrinsic, 2)
        except:
            pass
        valid_intrinsics = [(v, n) for v, n in [(eps_intrinsic, "EPS"), (fcf_intrinsic, "FCF")] if v is not None]
        if not valid_intrinsics:
            return {"error": "No valid intrinsic value calculated"}
        final_intrinsic, method = min(valid_intrinsics, key=lambda x: abs(x[0] - current_price))
        raw_upside = ((final_intrinsic - current_price) / current_price) * 100
        final_intrinsic = 0.45 * current_price if raw_upside < -80 else final_intrinsic
        upside = -55.0 if raw_upside < -80 else raw_upside
        result.update({
            "final_intrinsic": round(final_intrinsic, 2),
            "method": method,
            "upside_percent": round(upside, 2),
            "verdict": "✅ Undervalued" if final_intrinsic > current_price else "❌ Overvalued"
        })
        return result

    dcf_value, projected_fcfs, growth_rate, base_fcf = calculate_dcf_from_fcf(fcf_df, wacc)
    if dcf_value is None:
        return {"error": "DCF calculation failed"}

    intrinsic_value = dcf_value / shares
    raw_upside = ((intrinsic_value - current_price) / current_price) * 100
    intrinsic_value = 0.45 * current_price if raw_upside < -80 else intrinsic_value
    upside = -55.0 if raw_upside < -80 else raw_upside

    result.update({
        "base_fcf": round(base_fcf, 2),
        "growth_rate": round(growth_rate * 100, 2),
        "projected_fcfs": projected_fcfs,
        "shares_cr": round(shares, 2),
        "equity_cr": round(equity, 2),
        "debt_cr": round(debt, 2),
        "beta": round(beta, 2),
        "interest_expense_cr": round(interest_expense_cr, 2),
        "risk_free_rate": round(risk_free * 100, 2),
        "cost_of_equity": round(cost_equity * 100, 2),
        "cost_of_debt": round(cost_debt * 100, 2),
        "wacc": round(wacc * 100, 2),
        "dcf_value_cr": round(dcf_value, 2),
        "intrinsic_per_share": round(intrinsic_value, 2),
        "upside_percent": round(upside, 2),
        "verdict": "✅ Undervalued" if intrinsic_value > current_price else "❌ Overvalued"
    })

    return result

@dcf_bp.route("/", methods=["GET"])
def dcf_route():
    stock = request.args.get("stock", "")
    return jsonify(run_dcf_logic(stock))
