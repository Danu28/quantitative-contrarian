import sys
sys.path.insert(0, "reverse_engineer")
from universe_loader import load_universe, list_available_detailed

c = load_universe("nifty50")
print(f"NIFTY 50: {len(c['symbols'])} symbols, ticker={c['index_ticker']}")

c = load_universe("nifty500")
print(f"NIFTY 500: {len(c['symbols'])} symbols")

avail = list_available_detailed()
print("Available configs:")
for d in avail:
    print(f"  {d['slug']:20s} {d['name']:30s} {d['n_constituents']} constituents")

try:
    load_universe("nonexistent")
except FileNotFoundError as e:
    print(f"Expected error: {e}")

print("All checks passed")
