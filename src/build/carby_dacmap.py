#!/usr/bin/env python3
"""Apply the Carby Component DAC wiring (measured from the TV photos) to ~/gcvideo's pin file."""
import os, re, sys
p = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf")
s = open(p).read()
MAP = {}
for b, pin in enumerate([50, 49, 33, 32, 28, 20, 19, 16]): MAP[f"DAC_Green[{b}]"] = pin   # Y   (bits 4-7 measured)
for b, pin in enumerate([34, 35, 44, 43, 41, 40, 37, 36]): MAP[f"DAC_Red[{b}]"]   = pin   # Pr  (bits 2-7 measured)
for b, pin in enumerate([6, 5, 4, 3, 99, 98, 94, 93]):     MAP[f"DAC_Blue[{b}]"]  = pin   # Pb  (bits 4-7 measured)
MAP.update({"DAC_SyncN": 15, "DAC_Clock": 70, "CSync_out": 9, "HSync_out": 10, "VSync_out": 12, "LED": 13})
for net, pin in MAP.items():
    s, n = re.subn(r'(NET "%s"\s+LOC = )P\d+' % re.escape(net), r'\g<1>P%d' % pin, s)
    if n != 1: sys.exit(f"could not update {net} - nothing written")
locs = re.findall(r'LOC = (P\d+)', s)
dups = sorted({x for x in locs if locs.count(x) > 1})
if dups: sys.exit("pin conflict " + ", ".join(dups) + " - nothing written")
open(p + ".before-dacmap", "w").write(open(p).read())
open(p, "w").write(s)
print("DAC map applied (backup: constraints-dualgc.ucf.before-dacmap)")
