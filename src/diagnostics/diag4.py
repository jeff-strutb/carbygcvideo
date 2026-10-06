#!/usr/bin/env python3
"""
diag4.py - Carby diagnostic 4: identify which FPGA pin drives a given DAC input.
Every candidate FPGA output pin gets its own PWM duty cycle; the DC voltage you
measure on a DAC input names the FPGA pin wired to it.

  python3 ~/diag4.py build                                  (after: source .../settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag4.py flash        (AD4 jumper held on pin 100)
  python3 ~/diag4.py survey                                 (guided walk, no pin counting: measure, map, write pin file)
  python3 ~/diag4.py which 1.65                             (single lookup)
"""
import os, sys, subprocess, hashlib, time, re, itertools
HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag4")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
C    = [44, 43, 41, 40, 37, 36, 35, 34, 20, 19, 16, 15, 13, 12, 10, 9, 6, 5, 4, 3, 99, 98, 94, 93, 49, 33, 32, 28, 52, 48, 77, 78, 83, 84, 85, 86, 88, 50]
VHDL = r"""-- Carby diagnostic 4: every candidate output pin gets a unique PWM duty cycle.
-- Pin index k (0..37) is high for k+1 out of every 40 clocks -> DC = 3.3 V * (k+1)/40.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity top is
  port (
    cap_clk : in  std_logic;                        -- P90, console 54 MHz clock
    pwm     : out std_logic_vector(37 downto 0);
    psave   : out std_logic;                        -- P70, keep the DAC powered
    dacclk  : out std_logic                         -- P50, DAC clock keeps running
  );
end top;
architecture rtl of top is
  signal cnt : unsigned(5 downto 0) := (others => '0');
  signal q   : std_logic_vector(37 downto 0) := (others => '0');
  signal t   : std_logic := '0';
begin
  process (cap_clk)
  begin
    if rising_edge(cap_clk) then
      if cnt = 39 then cnt <= (others => '0'); else cnt <= cnt + 1; end if;
      for k in 0 to 37 loop
        if cnt < k + 1 then q(k) <= '1'; else q(k) <= '0'; end if;
      end loop;
      t <= not t;
    end if;
  end process;
  pwm    <= q;
  psave  <= '1';
  dacclk <= t;
end rtl;
"""
UCF  = r"""NET "cap_clk" LOC = P90 | IOSTANDARD = LVCMOS33;
NET "psave" LOC = P30 | IOSTANDARD = LVCMOS33;
NET "dacclk" LOC = P70 | IOSTANDARD = LVCMOS33;
NET "pwm<0>" LOC = P44 | IOSTANDARD = LVCMOS33;
NET "pwm<1>" LOC = P43 | IOSTANDARD = LVCMOS33;
NET "pwm<2>" LOC = P41 | IOSTANDARD = LVCMOS33;
NET "pwm<3>" LOC = P40 | IOSTANDARD = LVCMOS33;
NET "pwm<4>" LOC = P37 | IOSTANDARD = LVCMOS33;
NET "pwm<5>" LOC = P36 | IOSTANDARD = LVCMOS33;
NET "pwm<6>" LOC = P35 | IOSTANDARD = LVCMOS33;
NET "pwm<7>" LOC = P34 | IOSTANDARD = LVCMOS33;
NET "pwm<8>" LOC = P20 | IOSTANDARD = LVCMOS33;
NET "pwm<9>" LOC = P19 | IOSTANDARD = LVCMOS33;
NET "pwm<10>" LOC = P16 | IOSTANDARD = LVCMOS33;
NET "pwm<11>" LOC = P15 | IOSTANDARD = LVCMOS33;
NET "pwm<12>" LOC = P13 | IOSTANDARD = LVCMOS33;
NET "pwm<13>" LOC = P12 | IOSTANDARD = LVCMOS33;
NET "pwm<14>" LOC = P10 | IOSTANDARD = LVCMOS33;
NET "pwm<15>" LOC = P9 | IOSTANDARD = LVCMOS33;
NET "pwm<16>" LOC = P6 | IOSTANDARD = LVCMOS33;
NET "pwm<17>" LOC = P5 | IOSTANDARD = LVCMOS33;
NET "pwm<18>" LOC = P4 | IOSTANDARD = LVCMOS33;
NET "pwm<19>" LOC = P3 | IOSTANDARD = LVCMOS33;
NET "pwm<20>" LOC = P99 | IOSTANDARD = LVCMOS33;
NET "pwm<21>" LOC = P98 | IOSTANDARD = LVCMOS33;
NET "pwm<22>" LOC = P94 | IOSTANDARD = LVCMOS33;
NET "pwm<23>" LOC = P93 | IOSTANDARD = LVCMOS33;
NET "pwm<24>" LOC = P49 | IOSTANDARD = LVCMOS33;
NET "pwm<25>" LOC = P33 | IOSTANDARD = LVCMOS33;
NET "pwm<26>" LOC = P32 | IOSTANDARD = LVCMOS33;
NET "pwm<27>" LOC = P28 | IOSTANDARD = LVCMOS33;
NET "pwm<28>" LOC = P52 | IOSTANDARD = LVCMOS33;
NET "pwm<29>" LOC = P48 | IOSTANDARD = LVCMOS33;
NET "pwm<30>" LOC = P77 | IOSTANDARD = LVCMOS33;
NET "pwm<31>" LOC = P78 | IOSTANDARD = LVCMOS33;
NET "pwm<32>" LOC = P83 | IOSTANDARD = LVCMOS33;
NET "pwm<33>" LOC = P84 | IOSTANDARD = LVCMOS33;
NET "pwm<34>" LOC = P85 | IOSTANDARD = LVCMOS33;
NET "pwm<35>" LOC = P86 | IOSTANDARD = LVCMOS33;
NET "pwm<36>" LOC = P88 | IOSTANDARD = LVCMOS33;
NET "pwm<37>" LOC = P50 | IOSTANDARD = LVCMOS33;
"""

def build():
    os.makedirs(os.path.join(WORK, "xst/tmp"), exist_ok=True)
    open(os.path.join(WORK, "top.vhd"), "w").write(VHDL)
    open(os.path.join(WORK, "top.ucf"), "w").write(UCF)
    open(os.path.join(WORK, "top.prj"), "w").write('vhdl work "top.vhd"\n')
    open(os.path.join(WORK, "top.xst"), "w").write(
        'set -tmpdir "xst/tmp"\nset -xsthdpdir "xst"\nrun\n-ifn top.prj\n-ifmt mixed\n'
        f'-ofn top\n-ofmt NGC\n-p {PART}\n-top top\n-iobuf YES\n')
    ut = open(UT).read().replace("UnusedPin:PullUp", "UnusedPin:PullDown").replace("ICAP_Enable:Yes", "ICAP_Enable:No")
    open(os.path.join(WORK, "bitgen.ut"), "w").write(ut)
    for f in ("top.bin", "top.ncd", "top_map.ncd", "top.ngd", "top.ngc"):
        try: os.remove(os.path.join(WORK, f))
        except FileNotFoundError: pass
    steps = [["xst", "-ifn", "top.xst", "-ofn", "top.syr"],
             ["ngdbuild", "-uc", "top.ucf", "-p", PART, "top.ngc", "top.ngd"],
             ["map", "-p", PART, "-o", "top_map.ncd", "top.ngd", "top.pcf"],
             ["par", "-w", "top_map.ncd", "top.ncd", "top.pcf"],
             ["bitgen", "-f", "bitgen.ut", "top.ncd"]]
    log = open(os.path.join(WORK, "build.log"), "w")
    for s in steps:
        print("----", s[0]); log.flush()
        if subprocess.call(s, cwd=WORK, stdout=log, stderr=subprocess.STDOUT) != 0:
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag4/build.log")
    b = open(os.path.join(WORK, "top.bin"), "rb").read()
    print("BUILD OK:", len(b), "bytes, SHA-256", hashlib.sha256(b).hexdigest())

def flash():
    from pyftdi.spi import SpiController
    img = open(os.path.join(WORK, "top.bin"), "rb").read()
    c = SpiController(cs_count=1); c.configure('ftdi://ftdi:232h/1')
    g = c.get_gpio(); g.set_direction(0x10, 0x10); g.write(0)
    p = c.get_port(cs=0, freq=1e6, mode=0)
    input("Hold the AD4 wire on pin 100 until DONE. Press Enter...")
    jid = bytes(p.exchange([0x9F], 3))
    if jid != b'\xc2\x20\x13': c.terminate(); sys.exit("Flash not responding (ID " + jid.hex() + "). Nothing written.")
    def wait():
        while p.exchange([0x05], 1)[0] & 1: time.sleep(0.01)
    p.exchange([0x06]); p.exchange([0x01, 0x00]); wait()
    sr = p.exchange([0x05], 1)[0]
    if sr & 0x9c: c.terminate(); sys.exit(f"Flash write-protected (status 0x{sr:02x}). Nothing written.")
    print("Erasing..."); p.exchange([0x06]); p.exchange([0xC7]); wait()
    print("Writing...")
    for o in range(0, len(img), 256):
        p.exchange([0x06]); p.exchange(bytes([0x02, o>>16&255, o>>8&255, o&255]) + img[o:o+256]); wait()
    rd = bytearray()
    for o in range(0, len(img), 4096):
        rd += p.exchange([0x03, o>>16&255, o>>8&255, o&255], min(4096, len(img)-o))
    c.terminate()
    sys.exit("DONE - verified OK" if bytes(rd) == img else "VERIFY FAILED - rerun")

# candidate FPGA output pins, in diag4 signature order (index k -> duty (k+1)/40)
DVI = {77,78,83,84,85,86,88,89}
# DAC pins to visit: label, ADV7125 pin number, where to find it (photo orientation)
_o = lambda n: f"{n}{'st' if n % 10 == 1 and n != 11 else 'nd' if n % 10 == 2 and n != 12 else 'rd' if n % 10 == 3 and n != 13 else 'th'}"
STEPS = ([("S", 12, "top row, leftmost pin"), ("BL", 11, "top row, 2nd pin from the LEFT")] +
         [(f"G{b}", 3 + b, f"top row, {_o(3+b)} pin from the RIGHT end") for b in range(8)] +
         [(f"B{b}", 16 + b, f"left side, {_o(4+b)} pin from the TOP") for b in range(8)] +
         [(f"R{b}", 41 + b, f"right side, {_o(5+b)} pin from the BOTTOM") for b in range(8)])

def classify(v, rail):
    """voltage -> ('pin', P) | ('high',None) | ('low',None) | ('bad',None)"""
    x = v / rail * 40 - 1
    k = round(x)
    if v >= rail * 0.975: return ("high", None)
    if v <= 0.04: return ("low", None)
    if 0 <= k < len(C) and abs(x - k) <= 0.45: return ("pin", C[k])
    return ("bad", None)

def plug_assignment(m, plugv):
    """m: label->pin. plugv: {'red','green','blue'} -> volts. Returns {plug: 'R'|'G'|'B'} best match."""
    duty = {p: (i + 1) / 40 for i, p in enumerate(C)}
    def ch(prefix, sync=False):
        v = sum((1 << b) * duty.get(m.get(f"{prefix}{b}"), 0) for b in range(8))
        if sync: v += 102 * duty.get(m.get("S"), 0)          # ~40 IRE sync pedestal on IOG, in DAC steps
        return v
    pred = {"R": ch("R"), "G": ch("G", True), "B": ch("B")}
    best = None
    for perm in itertools.permutations("RGB"):
        a = dict(zip(("red", "green", "blue"), perm))
        # one unknown scale: fit, then relative error
        num = sum(plugv[p] * pred[a[p]] for p in a); den = sum(pred[a[p]] ** 2 for p in a)
        k = num / den if den else 0
        err = sum((plugv[p] - k * pred[a[p]]) ** 2 for p in a) / max(sum(v * v for v in plugv.values()), 1e-9)
        if best is None or err < best[0]: best = (err, a)
    return best[1], best[0], pred

def build_ucf(text, m, plugs):
    """Rewrite DAC/sync LOCs in constraints-dualgc.ucf text. m: label->pin (or None for tied)."""
    loc = {}
    # Y must go to the DAC's G inputs (only IOG carries sync); Cb/Cr follow the jacks
    blue_src = plugs["blue"]; red_src = plugs["red"]          # which DAC channel feeds each jack
    for b in range(8):
        loc[f"DAC_Green[{b}]"] = m[f"G{b}"]
        loc[f"DAC_Blue[{b}]"]  = m[f"{blue_src}{b}"]
        loc[f"DAC_Red[{b}]"]   = m[f"{red_src}{b}"]
    loc["DAC_SyncN"] = m["S"]
    loc["DAC_Clock"] = 70                 # measured: the DAC clock is on P70
    used = set(loc.values())
    if m.get("BL") is not None:            # BLANK driven by the FPGA: hold it high via CableDetect ('1')
        loc["CableDetect"] = m["BL"]; used.add(m["BL"])
    pool = [p for p in C if p not in DVI and p not in used]
    for net in (["CableDetect"] if "CableDetect" not in loc else []) + ["CSync_out", "HSync_out", "VSync_out", "LED"]:
        if net == "CableDetect" and 48 in pool: loc[net] = 48; pool.remove(48); continue
        loc[net] = pool.pop(0)
    for net, pin in loc.items():
        pat = r'(NET "%s"\s+LOC = )P\d+' % re.escape(net)
        text, n = re.subn(pat, r'\g<1>P%d' % pin, text)
        if n != 1: raise SystemExit(f"could not update {net} in the pin file")
    return text, loc

def num(prompt):
    while True:
        s = input(prompt).strip().lower().replace("v", "")
        try:
            if s.endswith("m"): return float(s[:-1]) / 1000
            v = float(s)
            return v / 1000 if v > 10 else v
        except ValueError:
            print("   please type a number, e.g. 1.24")

# ADV7125 LQFP-48 (datasheet Rev. D, Table 7). Board held so the DAC's printing reads normally:
# pin 1 is the top-left corner (dot on the package). Sides as the user walks them:
LEFT   = ["GND", "GND"] + [f"G{b}" for b in range(8)] + ["BL", "S"]               # pins 1..12, top -> bottom
BOTTOM = ["VAA", "GND", "GND"] + [f"B{b}" for b in range(8)] + ["CLK"]            # pins 13..24, left -> right
TOP    = [f"R{b}" for b in range(7, -1, -1)] + ["GND", "GND", "PSAVE", "RSET"]    # pins 48..37, left -> right
SIDES = [("LEFT side, starting at the TOP-LEFT corner pin (next to the dot) and going DOWN", LEFT),
         ("BOTTOM side, starting at the LEFT end and going RIGHT", BOTTOM),
         ("TOP side, starting at the LEFT end (top-left corner) and going RIGHT", TOP)]

def check_side(names, vals, rail):
    """Landmark check: GND ~0 V, VAA/PSAVE ~rail, RSET ~1.24 V. Returns list of problems."""
    probs = []
    if len(vals) != len(names): return [f"expected {len(names)} readings, got {len(vals)}"]
    for n, v in zip(names, vals):
        if n == "GND" and v > 0.05: probs.append(f"{n} position read {v:.2f} V (should be 0)")
        if n == "VAA" and abs(v - rail) > 0.15: probs.append(f"{n} position read {v:.2f} V (should be ~{rail:.2f})")
        if n == "PSAVE" and not (0.2 < v < 0.7 or abs(v - rail) <= 0.15): probs.append(f"PSAVE position read {v:.2f} V (should be ~0.4 or ~{rail:.2f})")
        if n == "RSET" and not 1.0 < v < 1.5: probs.append(f"RSET position read {v:.2f} V (should be ~1.24)")
    return probs

def side_ok(names, vals, rail):
    probs = check_side(names, vals, rail)
    for n, v in zip(names, vals):
        if n[0] in "GBRS" and n not in ("GND",) and len(n) <= 2 and n != "BL":
            if classify(v, rail)[0] != "pin": probs.append(f"{n} position read {v:.2f} V, not a signature")
        if n == "CLK" and not 0.3 * rail < v < 0.7 * rail: probs.append(f"CLOCK position read {v:.2f} V (should be ~{rail/2:.2f})")
    return probs

def survey():
    import shutil
    print("\nGuided DAC survey (no pin counting).")
    print("Setup: diag4 flashed, FT232H USB unplugged, GameCube ON, meter on DC volts,")
    print("black probe on the white ground wire stub.")
    print("Turn the board so the DAC's printing (ADV7125) reads normally. Pin 1 is the TOP-LEFT")
    print("corner pin, next to the small dot on the chip.\n")
    rail = num("Red probe on the 3.3 V stub (black wire). Reading: ")
    m = {}
    for desc, names in SIDES:
        while True:
            print(f"\n{desc}: touch each pin in turn, sliding ONE pin each time, {len(names)} pins.")
            vals = [num(f"  pin {i+1:2}/{len(names)}: ") for i in range(len(names))]
            probs = side_ok(names, vals, rail)
            sig = [classify(v, rail)[1] for n, v in zip(names, vals) if classify(v, rail)[0] == "pin" and n not in ("BL", "GND", "VAA", "PSAVE", "RSET", "CLK")]
            dups = {p for p in sig if sig.count(p) > 1}
            if dups: probs.append("the same signature appeared twice (" + ", ".join(f"P{p}" for p in dups) + ") - probably the same pin read twice")
            if not probs:
                for n, v in zip(names, vals):
                    if n in ("GND", "VAA", "PSAVE", "RSET", "CLK"): continue
                    kind, p = classify(v, rail)
                    m[n] = p if kind == "pin" else None
                    if n == "BL":
                        print("   BLANK: " + {"pin": f"driven by FPGA P{p}", "high": "tied high on the board",
                                              "low": "held LOW (unused FPGA pin) - the build will pull it up",
                                              "bad": "unclear reading - the build will pull unused pins up"}[kind])
                print("   side OK: landmarks line up.")
                break
            print("   This side doesn't line up:")
            for pr in probs: print("    - " + pr)
            print("   Most likely a pin was skipped or read twice. Let's redo this side from its first pin.")
    allp = [p for k, p in m.items() if p is not None]
    dups = {p for p in allp if allp.count(p) > 1}
    if dups: raise SystemExit("Two DAC pins matched the same FPGA pin (" + ", ".join(f"P{p}" for p in dups) + "). Rerun the survey.")
    print("\nNow the three video jacks. Unplug the cable from the TV.")
    print("For each plug: black probe on the plug's OUTER metal sleeve, red probe on its CENTER pin.")
    plugv = {c: num(f"{c.upper()} plug: ") for c in ("red", "green", "blue")}
    a, err, _ = plug_assignment(m, plugv)
    print(f"   jacks: red <- DAC {a['red']}, green <- DAC {a['green']}, blue <- DAC {a['blue']}   (fit error {err:.4f})")
    if a["green"] != "G":
        print("   NOTE: Y (with sync) will come out of the " + [k for k, v in a.items() if v == 'G'][0] + " jack - plug that one into the TV's Y input.")
    base = os.path.expanduser("~/gcvideo/HDL/gcvideo_dvi")
    ucfp = os.path.join(base, "src/constraints-dualgc.ucf")
    shutil.copy(ucfp, ucfp + ".before-survey")
    text, loc = build_ucf(open(ucfp).read(), m, a)
    open(ucfp, "w").write(text)
    utp = os.path.join(base, "scripts/bitgenconfig-GC.ut")
    ut = open(utp).read().replace("UnusedPin:PullDown", "UnusedPin:PullUp"); open(utp, "w").write(ut)
    with open(os.path.expanduser("~/carby_dac_map.txt"), "w") as f:
        f.write(f"supply {rail} V\n")
        for n in ["S", "BL"] + [f"{c}{b}" for c in "GBR" for b in range(8)]:
            f.write(f"DAC {n:<3} <- {('FPGA P%d' % m[n]) if m.get(n) else 'not FPGA-driven'}\n")
        f.write("jacks: " + ", ".join(f"{k} <- DAC {v}" for k, v in a.items()) + "\n\n")
        for net, pin in loc.items(): f.write(f"{net:<14} LOC = P{pin}\n")
    print("\nDone. Map saved to ~/carby_dac_map.txt; pin file updated (backup: constraints-dualgc.ucf.before-survey);")
    print("unused FPGA pins set to pull up (holds BLANK high).")
    print("Next: build the final firmware with  python3 ~/carby_build.py")

def which(v, rail=3.3):
    k = v / rail * 40 - 1
    best = sorted(range(len(C)), key=lambda i: abs(i - k))[:3]
    print(f"{v:.2f} V  ->  duty {100*v/rail:.1f}%")
    for i in best:
        print(f"   P{C[i]:<3}  (expected {rail*(i+1)/40:.2f} V)")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build": build()
    elif cmd == "flash": flash()
    elif cmd == "survey": survey()
    elif cmd == "which": which(float(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 3.3)
    else: sys.exit(__doc__)
