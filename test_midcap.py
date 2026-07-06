"""Validate midcap 150 config."""
import sys
sys.path.insert(0, "reverse_engineer")
from universe_loader import load_universe

m150 = load_universe("niftymidcap150")
m150_syms = set(m150["symbols"])
print(f"Midcap 150: {len(m150_syms)} symbols")

n500 = load_universe("nifty500")
n500_syms = set(n500["symbols"])
print(f"NIFTY 500: {len(n500_syms)} symbols")

overlap = m150_syms & n500_syms
not_in_n500 = m150_syms - n500_syms
print(f"Midcap 150 in NIFTY 500: {len(overlap)}/{len(m150_syms)}")
if not_in_n500:
    print(f"Midcap 150 NOT in NIFTY 500 ({len(not_in_n500)}): {sorted(not_in_n500)[:10]}")

n50 = load_universe("nifty50")
n50_syms = set(n50["symbols"])
overlap_n50 = m150_syms & n50_syms
if overlap_n50:
    print(f"ERROR: Midcap 150 contains NIFTY 50 stocks: {overlap_n50}")
else:
    print("OK: No overlap with NIFTY 50")

check = ["360ONE.NS", "ZFCVINDIA.NS", "3MINDIA.NS", "BEL.NS", "HAL.NS", "LICI.NS"]
for s in check:
    print(f"  Has {s}: {s in m150_syms}")
