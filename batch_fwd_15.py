from __future__ import annotations
import subprocess, sys

DATES = ["2026-07-09","2026-07-02","2026-06-18","2026-06-11","2026-06-04",
         "2026-05-28","2026-05-21","2026-05-14","2026-05-07","2026-04-30",
         "2026-04-23","2026-04-16","2026-04-09","2026-04-02","2026-03-26"]

results = []
for d in DATES:
    r = subprocess.run([sys.executable, "forward_check.py", "--date", d, "--strategy", "factor", "--top", "5"],
                       capture_output=True, text=True, timeout=120)
    lines = r.stdout.splitlines()
    capture = False
    summary = "N/A"
    for i, line in enumerate(lines):
        if "10 TRADING DAYS" in line: capture = True
        if capture and "Summary:" in line and "wins" in line:
            summary = line.strip(); break
    results.append((d, summary))
    print(f"{d}: {summary}")

print("\n\nAGGREGATE:")
tw, tt, tr = 0, 0, []
for d, s in results:
    parts = s.split()
    for p in parts:
        if "/" in p and "wins" not in p:
            w, t = p.split("/"); tw += int(w); tt += int(t); break
    for p in parts:
        if p.startswith("+") or p.startswith("-"):
            tr.append(float(p.replace("%",""))); break
print(f"  Total: {tw}/{tt} wins ({tw/tt*100:.0f}%)")
if tr: print(f"  Avg 10d return: {sum(tr)/len(tr):+.2f}%")
