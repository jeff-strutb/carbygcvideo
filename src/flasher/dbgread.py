#!/usr/bin/env python3
"""Read the debug port of the carby_build.py firmware through the SPI header and print a verdict.
Arms the counters once, waits for the full window, then reads (no re-arming between USB chunks)."""
import time
from pyftdi.spi import SpiController
c = SpiController(cs_count=2); c.configure('ftdi://ftdi:232h/1')
p = c.get_port(cs=1, freq=3e6, mode=0)      # CS1 = AD4 (unplugged); AD3 stays high = flash deselected
pre = bytes(p.exchange(b'\xff' * 1024, duplex=True))   # one arm, pointer reset
time.sleep(0.2)                                        # 2^20 cycles = 19.4 ms window completes
data = bytes(p.exchange(b'\x00' * 16, duplex=True))
c.terminate()
bit = lambda k: (data[k >> 3] >> (7 - (k & 7))) & 1
word = lambda w: sum(bit(w*32 + j) << j for j in range(32))
dac, hs, st = (word(i) for i in range(3))
allv = lambda b, v: b.count(v) == len(b)
if (st >> 8) & 0xff == 0xA5:
    print(f"FPGA configured, main firmware running (marker OK), window done: {(st >> 1) & 1}")
    print(f"  clock manager locked : {(st >> 2) & 1}")
    print(f"  VSync/field detect   : {'P62 is VSync (swapped)' if (st >> 3) & 1 else 'P61 is VSync (as mapped)'}")
    print(f"  DAC clock pulses     : {dac}   (expect ~262144 at 15 kHz)")
    print(f"  HSync pulses         : {hs}   (expect ~305 at 15 kHz)")
elif allv(pre, 0xff) and allv(data, 0x00):
    print("ECHO: FPGA configured, clock manager locked, internal clock not running.")
elif allv(pre, 0x00) and allv(data, 0xff):
    print("INVERTED ECHO: FPGA configured, clock manager NOT locked.")
elif allv(pre, 0xff) and allv(data, 0xff):
    print("Line floating high: recovery stage running (main firmware not started).")
else:
    print(f"No echo, no marker: FPGA not configured with this firmware. (replies {pre[:4].hex()} / {data[:4].hex()})")
