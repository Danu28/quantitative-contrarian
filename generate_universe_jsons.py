"""Generate universe JSON configs from existing constituent lists."""
import json, os, sys
sys.path.insert(0, "reverse_engineer")
from constituents import get_nifty_50_symbols

NIFTY50_NAMES = {
    "RELIANCE.NS": "Reliance Industries", "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank", "INFY.NS": "Infosys", "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever", "ITC.NS": "ITC", "SBIN.NS": "State Bank of India",
    "BHARTIARTL.NS": "Bharti Airtel", "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "LT.NS": "Larsen & Toubro", "WIPRO.NS": "Wipro", "AXISBANK.NS": "Axis Bank",
    "BAJFINANCE.NS": "Bajaj Finance", "MARUTI.NS": "Maruti Suzuki India",
    "SUNPHARMA.NS": "Sun Pharmaceutical Industries", "TITAN.NS": "Titan Company",
    "ULTRACEMCO.NS": "UltraTech Cement", "NTPC.NS": "NTPC", "POWERGRID.NS": "Power Grid Corporation",
    "M&M.NS": "Mahindra & Mahindra", "ASIANPAINT.NS": "Asian Paints", "HCLTECH.NS": "HCL Technologies",
    "NESTLEIND.NS": "Nestlé India", "JSWSTEEL.NS": "JSW Steel", "TATASTEEL.NS": "Tata Steel",
    "ADANIPORTS.NS": "Adani Ports & SEZ", "COALINDIA.NS": "Coal India", "GRASIM.NS": "Grasim Industries",
    "BAJAJ-AUTO.NS": "Bajaj Auto", "HEROMOTOCO.NS": "Hero MotoCorp", "EICHERMOT.NS": "Eicher Motors",
    "HINDALCO.NS": "Hindalco Industries", "TECHM.NS": "Tech Mahindra", "ONGC.NS": "Oil & Natural Gas Corporation",
    "BPCL.NS": "Bharat Petroleum Corporation", "BRITANNIA.NS": "Britannia Industries",
    "INDUSINDBK.NS": "IndusInd Bank", "SBILIFE.NS": "SBI Life Insurance",
    "BAJAJFINSV.NS": "Bajaj Finserv", "CIPLA.NS": "Cipla", "DIVISLAB.NS": "Divis Laboratories",
    "DRREDDY.NS": "Dr. Reddy's Laboratories", "APOLLOHOSP.NS": "Apollo Hospitals Enterprise",
    "ADANIENT.NS": "Adani Enterprises", "HDFCLIFE.NS": "HDFC Life Insurance", "BEL.NS": "Bharat Electronics",
    "TRENT.NS": "Trent",
}

NIFTY50_SECTORS = {
    "RELIANCE.NS": "Energy", "TCS.NS": "Information Technology", "HDFCBANK.NS": "Financial Services",
    "INFY.NS": "Information Technology", "ICICIBANK.NS": "Financial Services",
    "HINDUNILVR.NS": "Fast Moving Consumer Goods", "ITC.NS": "Fast Moving Consumer Goods",
    "SBIN.NS": "Financial Services", "BHARTIARTL.NS": "Telecommunication",
    "KOTAKBANK.NS": "Financial Services", "LT.NS": "Construction", "WIPRO.NS": "Information Technology",
    "AXISBANK.NS": "Financial Services", "BAJFINANCE.NS": "Financial Services",
    "MARUTI.NS": "Automobile", "SUNPHARMA.NS": "Healthcare", "TITAN.NS": "Consumer Goods",
    "ULTRACEMCO.NS": "Construction Materials", "NTPC.NS": "Power", "POWERGRID.NS": "Power",
    "M&M.NS": "Automobile", "ASIANPAINT.NS": "Consumer Goods", "HCLTECH.NS": "Information Technology",
    "NESTLEIND.NS": "Fast Moving Consumer Goods", "JSWSTEEL.NS": "Metals & Mining",
    "TATASTEEL.NS": "Metals & Mining", "ADANIPORTS.NS": "Services", "COALINDIA.NS": "Energy",
    "GRASIM.NS": "Construction Materials", "BAJAJ-AUTO.NS": "Automobile",
    "HEROMOTOCO.NS": "Automobile", "EICHERMOT.NS": "Automobile", "HINDALCO.NS": "Metals & Mining",
    "TECHM.NS": "Information Technology", "ONGC.NS": "Energy", "BPCL.NS": "Energy",
    "BRITANNIA.NS": "Fast Moving Consumer Goods", "INDUSINDBK.NS": "Financial Services",
    "SBILIFE.NS": "Financial Services", "BAJAJFINSV.NS": "Financial Services", "CIPLA.NS": "Healthcare",
    "DIVISLAB.NS": "Healthcare", "DRREDDY.NS": "Healthcare", "APOLLOHOSP.NS": "Healthcare Services",
    "ADANIENT.NS": "Metals & Mining", "HDFCLIFE.NS": "Financial Services", "BEL.NS": "Industrials",
    "TRENT.NS": "Retail",
}

sym_50 = get_nifty_50_symbols()
n50 = {
    "name": "NIFTY 50",
    "slug": "nifty50",
    "index_ticker": "^NSEI",
    "description": "NIFTY 50 is the benchmark broad-based index representing the top 50 companies by market capitalization listed on NSE.",
    "constituents": [
        {"symbol": s, "companyName": NIFTY50_NAMES.get(s, s.replace(".NS", "")), "sector": NIFTY50_SECTORS.get(s, "Unknown")}
        for s in sym_50
    ],
}

os.makedirs("universe", exist_ok=True)
with open("universe/nifty50.json", "w") as f:
    json.dump(n50, f, indent=2)
print(f"Created universe/nifty50.json ({len(n50['constituents'])} constituents)")

print("Done")
