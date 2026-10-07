#!/usr/bin/env python3
"""Carby: correct the low brightness and red-difference bits (fixes gradient banding).
Brightness bits 0-2 -> P33, P34, P35; red-difference bits 0-1 -> P50, P49. Same five pins, rearranged."""
import os, re, sys
p = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf")
s = open(p).read()
MAP = {"DAC_Green[0]": 33, "DAC_Green[1]": 34, "DAC_Green[2]": 35, "DAC_Red[0]": 50, "DAC_Red[1]": 49}
before = {n: re.search(r'NET "%s"\s+LOC = P(\d+)' % re.escape(n), s) for n in MAP}
missing = [n for n, m in before.items() if not m]
if missing: sys.exit("not found in pin file: " + ", ".join(missing) + " - nothing written")
if sorted(int(m.group(1)) for m in before.values()) != sorted(MAP.values()):
    sys.exit("pin file is not in the expected state (" + ", ".join(f"{n}=P{m.group(1)}" for n, m in before.items()) + ") - nothing written")
for net, pin in MAP.items():
    s = re.sub(r'(NET "%s"\s+LOC = )P\d+' % re.escape(net), r'\g<1>P%d' % pin, s)
locs = re.findall(r'LOC = (P\d+)', s)
dups = sorted({x for x in locs if locs.count(x) > 1})
if dups: sys.exit("pin conflict " + ", ".join(dups) + " - nothing written")
open(p + ".before-lowbits", "w").write(open(p).read())
open(p, "w").write(s)
print("brightness bits 0-2 -> P33 P34 P35, red-difference bits 0-1 -> P50 P49 (backup: constraints-dualgc.ucf.before-lowbits)")
