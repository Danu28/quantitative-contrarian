from __future__ import annotations
import subprocess, sys
from datetime import datetime, timedelta

year_offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # years back from 2026

end = datetime(2026 - year_offset, 7, 10)
all_fridays = []
d = end
while len(all_fridays) < 52:
    if d.weekday() == 4:
        all_fridays.append(d.strftime("%Y-%m-%d"))
    d -= timedelta(days=1)
dates = all_fridays[::3]

results = []
for d in dates:
    r = subprocess.run([sys.executable, "forward_check.py", "--date", d, "--strategy", "factor", "--top", "5"],
                       capture_output=True, text=True, timeout=120)
    lines = r.stdout.splitlines()
    summary = "N/A"
    caps = False
    for line in lines:
        if "10 TRADING DAYS" in line: caps = True
        if caps and "Summary:" in line and "wins" in line:
            summary = line.strip(); break
    results.append((d, summary))
    print(f"{d}: {summary}")

print("\n\nAGGREGATE:")
tw, tt, tr = 0, 0, []
for d, s in results:
    if s == "N/A": continue
    parts = s.split()
    for p in parts:
        if "/" in p and "wins" not in p:
            w, t = p.split("/"); tw += int(w); tt += int(t); break
    for p in parts:
        if p.startswith("+") or p.startswith("-"):
            tr.append(float(p.replace("%",""))); break
print(f"  Total: {tw}/{tt} wins ({tw/tt*100:.0f}%)")
if tr: print(f"  Avg 10d return: {sum(tr)/len(tr):+.2f}%")
