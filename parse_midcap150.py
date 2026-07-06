"""Parse NIFTY Midcap 150 from tickjournal HTML."""
import json, re
from pathlib import Path

HTML_PATH = Path.home() / ".local" / "share" / "opencode" / "tool-output" / "tool_f372e1fd8001J3hWgZ7oTkn3TI"
text = HTML_PATH.read_text(encoding="utf-8", errors="replace")

clean = re.sub(r'<[^>]+>', '\n', text)
lines = [l.strip() for l in clean.split('\n')]

KNOWN_SECTORS = {
    "Automobiles", "Financial Services", "Healthcare", "Capital Goods", "Banks",
    "Information Technology", "Industrial Products", "Consumer Goods", "Chemicals",
    "Metals & Mining", "Capital Markets", "Construction", "Oil & Gas", "Power",
    "Telecom", "Insurance", "Realty", "Retail", "FMCG", "Aerospace & Defense",
    "Healthcare Services", "Diversified", "Transport", "Petroleum Products",
    "Leisure Services", "Textiles", "Logistics & Cargo", "Media",
    "Consumer Durables", "Construction Materials", "Beverages", "Services",
    "Renewable Energy", "Fast Moving Consumer Goods", "Consumer Services",
    "Oil Gas & Consumable Fuels",
}

def is_symbol(s):
    return bool(re.match(r'^[A-Z][A-Z0-9&.\-]+$', s)) and len(s) >= 2 and len(s) <= 15

constituents = []
i = 0
while i < len(lines):
    line = lines[i]
    if line in KNOWN_SECTORS:
        sector = line
        # Look backwards: symbol is somewhere before the sector
        # Pattern: symbol (N lines up), possibly company, then sector
        # Possible positions for symbol: i-3, i-4, i-5 (need to skip company name and empties)
        symbol = None
        company = None
        for lookback in range(1, 8):
            if i - lookback < 0:
                break
            candidate = lines[i - lookback]
            if candidate.startswith("\u20b9") or candidate.startswith("Rs") or candidate.startswith("INR"):
                continue
            if is_symbol(candidate) and candidate not in ("NSE", "BSE", "EQ", "INDICES", "STOCKS", "STOCK", "TOTAL", "GAINERS", "LOSERS"):
                symbol = candidate
                # Look for company name between symbol and sector
                for j in range(lookback - 1, 0, -1):
                    between = lines[i - j]
                    if between and not between.startswith("\u20b9") and not is_symbol(between) and between not in ("", "NSE", "BSE"):
                        company = between
                        break
                break
        if symbol and symbol not in ("NSE", "BSE", "EQ", "INDICES", "STOCKS"):
            constituents.append({
                "symbol": f"{symbol}.NS" if not symbol.endswith(".NS") else symbol,
                "name": company or symbol,
                "sector": sector,
            })
    i += 1

print(f"Raw parsed: {len(constituents)}")
seen = {}
for c in constituents:
    seen[c["symbol"]] = c
unique = list(seen.values())
print(f"Unique: {len(unique)}")

config = {
    "name": "NIFTY Midcap 150",
    "slug": "niftymidcap150",
    "index_ticker": "^NSEI",
    "description": "NIFTY Midcap 150 represents companies ranked 101-250 by full market capitalisation from NIFTY 500.",
    "constituents": unique,
}

out_path = Path(__file__).resolve().parent / "universe" / "niftymidcap150.json"
with open(out_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print(f"Saved to {out_path}")
for c in unique[:20]:
    print(f"  {c['symbol']:25s} {c['name']:35s} {c['sector']}")
if len(unique) > 20:
    print(f"  ... and {len(unique)-20} more")
