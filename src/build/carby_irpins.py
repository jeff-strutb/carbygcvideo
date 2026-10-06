#!/usr/bin/env python3
"""Carby: put GCVideo's IR receiver and IR button on the pins diag8 found, with pull-ups.
Usage: carby_irpins.py <ir_pin> <button_pin>"""
import os, re, sys
ir, btn = int(sys.argv[1]), int(sys.argv[2])
p = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf")
s = open(p).read()
taken = {int(x): net for net, x in re.findall(r'NET "([^"]+)"\s+LOC = P(\d+)', s) if net not in ("IRReceiver", "IRButton")}
for pin in (ir, btn):
    if pin in taken: sys.exit(f"P{pin} is already used by {taken[pin]} in the pin file - nothing written")
for net, pin in (("IRReceiver", ir), ("IRButton", btn)):
    s, n = re.subn(r'NET "%s"[^\n]*' % net, f'NET "{net}"{" " * (13 - len(net))}LOC = P{pin} | PULLUP;', s)
    if n != 1: sys.exit(f"could not update {net} - nothing written")
s, n = re.subn(r'NET "PadData"[^\n]*', 'NET "PadData"      LOC = P7 | PULLDOWN;', s)   # no controller wire on this cable: hold it at ground
if n != 1: sys.exit("could not update PadData - nothing written")
locs = re.findall(r'LOC = (P\d+)', s)
dups = sorted({x for x in locs if locs.count(x) > 1})
if dups: sys.exit("pin conflict " + ", ".join(dups) + " - nothing written")
open(p + ".before-irpins", "w").write(open(p).read())
open(p, "w").write(s)
print(f"IRReceiver -> P{ir}, IRButton -> P{btn}, both with pull-ups; PadData held low (backup: constraints-dualgc.ucf.before-irpins)")
