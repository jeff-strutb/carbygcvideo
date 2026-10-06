#!/usr/bin/env python3
"""Carby: move Pb (blue-difference) bits 3-0 to P9/P10/P12/P13 and park the spare sync/LED outputs on P3-P6."""
import os, re, sys
p = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf")
s = open(p).read()
MAP = {"DAC_Blue[3]": 9, "DAC_Blue[2]": 10, "DAC_Blue[1]": 12, "DAC_Blue[0]": 13,
       "CSync_out": 3, "HSync_out": 4, "VSync_out": 5, "LED": 6}
for net, pin in MAP.items():
    s, n = re.subn(r'(NET "%s"\s+LOC = )P\d+' % re.escape(net), r'\g<1>P%d' % pin, s)
    if n != 1: sys.exit(f"could not update {net} - nothing written")
locs = re.findall(r'LOC = (P\d+)', s)
dups = sorted({x for x in locs if locs.count(x) > 1})
if dups: sys.exit("pin conflict " + ", ".join(dups) + " - nothing written")
open(p + ".before-pbfix", "w").write(open(p).read())
open(p, "w").write(s)
print("Pb bits 3-0 -> P9 P10 P12 P13; sync/LED outputs -> P3-P6 (backup: constraints-dualgc.ucf.before-pbfix)")
