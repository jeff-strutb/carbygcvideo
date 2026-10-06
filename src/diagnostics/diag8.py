#!/usr/bin/env python3
"""
diag8.py - find the Carby's IR receiver and IR button pins (no probing).

  python3 ~/diag8.py build                              (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag8.py flash    (AD4 jumper held on pin 100)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag8.py watch    (AD4 jumper UNPLUGGED from the FT232H)

Every FPGA I/O pin becomes a pulled-up input; the FPGA counts changes on each, and 'watch' asks you
to press the board's button and fire a remote at the cable, then names the pins that responded.
"""
import os, re, sys, subprocess, hashlib, time, json
HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag8")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
SKIP = {90, 53, 51, 46, 27, 100}           # clock, FT232H lines, PROG
TEMPLATE = r"""-- Carby diagnostic 8: input activity monitor.
-- Every candidate pin is an input. For each, the FPGA counts level changes (saturating 15 bits)
-- and records the current level. The FT232H reads a snapshot over SCK (P53) / MISO (P51);
-- a pause > ~19 ms starts a new read; each snapshot is framed by A5C3 ... 5A3C; each read clears the counters.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity top is
  generic ( N : integer := @@N@@ );
  port (
    cap_clk : in  std_logic;                       -- P90 (console 54 MHz)
    sck     : in  std_logic;                       -- P53
    miso    : out std_logic;                       -- P51
    pins    : in  std_logic_vector(N-1 downto 0)
  );
end top;
architecture rtl of top is
  type cnt_t is array (0 to N-1) of unsigned(14 downto 0);
  signal cnt   : cnt_t := (others => (others => '0'));
  signal p1, p2, p3 : std_logic_vector(N-1 downto 0) := (others => '0');
  signal sh    : std_logic_vector(N*16+31 downto 0) := (others => '0');
  signal s1, s2, s3 : std_logic := '0';
  signal idle  : unsigned(19 downto 0) := (others => '1');
  signal first : std_logic := '1';
  signal q     : std_logic := '0';
begin
  process (cap_clk)
    variable snap : boolean;
  begin
    if rising_edge(cap_clk) then
      p1 <= pins; p2 <= p1; p3 <= p2;
      s1 <= sck; s2 <= s1; s3 <= s2;
      snap := false;
      if s2 = '1' and s3 = '0' then                 -- SCK rising edge (host has sampled MISO)
        idle <= (others => '0');
        if first = '1' then
          snap := true; first <= '0';
        else
          sh <= sh(N*16+30 downto 0) & '0';
          q  <= sh(N*16+31);
        end if;
      elsif idle /= (idle'range => '1') then
        idle <= idle + 1;
      else
        first <= '1';
      end if;
      if snap then sh(N*16+31 downto N*16+16) <= x"A5C3"; sh(15 downto 0) <= x"5A3C"; end if;
      for i in 0 to N-1 loop
        if snap then
          sh(16+i*16+15) <= p2(i);
          sh(16+i*16+14 downto 16+i*16) <= std_logic_vector(cnt(i));
          if p2(i) /= p3(i) then cnt(i) <= to_unsigned(1, 15); else cnt(i) <= (others => '0'); end if;
        elsif p2(i) /= p3(i) and cnt(i) /= (cnt(i)'range => '1') then
          cnt(i) <= cnt(i) + 1;
        end if;
      end loop;
      if snap then q <= '0'; end if;
    end if;
  end process;
  miso <= q;
end rtl;
"""

def io_pins():
    os.makedirs(WORK, exist_ok=True)
    subprocess.call(["partgen", "-v", "xc3s200avq100"], cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pk = [f for f in os.listdir(WORK) if f.endswith(".pkg")]
    if not pk: sys.exit("partgen produced no package file - is ISE sourced?")
    pins = set()
    for line in open(os.path.join(WORK, pk[0])):
        toks = line.split()
        pn = [t for t in toks if re.fullmatch(r"P\d{1,3}", t)]
        fn = [t for t in toks if t.startswith(("IO", "IP"))]
        if pn and fn and not any(x in line for x in ("VCC", "GND", "TMS", "TCK", "TDI", "TDO", "PROG", "DONE", "SUSPEND")):
            pins.add(int(pn[0][1:]))
    pins = sorted(pins - SKIP)
    if len(pins) < 50: sys.exit(f"only found {len(pins)} I/O pins in {pk[0]} - open an issue with its first 30 lines")
    return pins

def build():
    pins = io_pins()
    json.dump(pins, open(os.path.join(WORK, "pins.json"), "w"))
    os.makedirs(os.path.join(WORK, "xst/tmp"), exist_ok=True)
    open(os.path.join(WORK, "top.vhd"), "w").write(TEMPLATE.replace("@@N@@", str(len(pins))))
    ucf = ('NET "cap_clk" LOC = P90 | IOSTANDARD = LVCMOS33;\nNET "sck" LOC = P53 | IOSTANDARD = LVCMOS33;\n'
           'NET "miso" LOC = P51 | IOSTANDARD = LVCMOS33;\n')
    for i, p in enumerate(pins): ucf += f'NET "pins<{i}>" LOC = P{p} | IOSTANDARD = LVCMOS33 | PULLUP;\n'
    open(os.path.join(WORK, "top.ucf"), "w").write(ucf)
    open(os.path.join(WORK, "top.prj"), "w").write('vhdl work "top.vhd"\n')
    open(os.path.join(WORK, "top.xst"), "w").write(
        'set -tmpdir "xst/tmp"\nset -xsthdpdir "xst"\nrun\n-ifn top.prj\n-ifmt mixed\n'
        f'-ofn top\n-ofmt NGC\n-p {PART}\n-top top\n-iobuf YES\n')
    ut = open(UT).read().replace("UnusedPin:PullDown", "UnusedPin:PullUp").replace("ICAP_Enable:Yes", "ICAP_Enable:No")
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
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag8/build.log")
    b = open(os.path.join(WORK, "top.bin"), "rb").read()
    print(f"BUILD OK: monitoring {len(pins)} pins;", len(b), "bytes, SHA-256", hashlib.sha256(b).hexdigest())

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


SYNC = format(0xA5C3, "016b"); TRAIL = format(0x5A3C, "016b")
BAD = {"n": 0}
def snapshot(port, n):
    """One read. Returns {pin_index: (level, changes)} or None if the sync word is not intact."""
    for _ in range(3):
        nbits = 2 + 16 + n * 16 + 16
        raw = port.exchange(bytes((nbits + 7) // 8 + 1), duplex=True)
        bits = "".join(f"{b:08b}" for b in raw)
        if bits[2:18] == SYNC and bits[18 + n * 16:34 + n * 16] == TRAIL:
            data = bits[18:18 + n * 16]; out = {}
            for j in range(n):                                   # first 16 bits = highest pin index
                i = n - 1 - j; w = data[j * 16:(j + 1) * 16]
                out[i] = (int(w[0]), int(w[1:], 2))
            return out
        BAD["n"] += 1
        time.sleep(0.05)                                         # > 19 ms: next read starts a fresh frame
    return None

def collect(port, n, seconds):
    lvl = {}; edges = {i: 0 for i in range(n)}; good = 0
    t = time.time()
    while time.time() - t < seconds:
        time.sleep(0.2)
        snap = snapshot(port, n)
        if snap is None: continue
        good += 1
        for i, (l, c) in snap.items():
            edges[i] += c; lvl[i] = l
    if not good: sys.exit("no clean reads at all - check the FT232H wiring (CLK, MISO) and that the GameCube is on")
    return lvl, edges, None

def watch():
    from pyftdi.spi import SpiController
    pins = json.load(open(os.path.join(WORK, "pins.json"))); n = len(pins)
    c = SpiController(cs_count=2); c.configure('ftdi://ftdi:232h/1')
    port = c.get_port(cs=1, freq=1e6, mode=0)          # CS1 = AD4: jumper must be UNPLUGGED
    snapshot(port, n); time.sleep(0.3); BAD['n'] = 0      # first read carries power-up counts
    print("\n1) Baseline: don't touch anything for 4 seconds...")
    b_lvl, b_edges, _ = collect(port, n, 4)
    quiet = [i for i in range(n) if b_edges[i] == 0]
    print(f"   {n - len(quiet)} pins are busy on their own (video, audio, clocks); {len(quiet)} are quiet.")
    input("\n2) Press and HOLD the small button BU1 on the board, keep holding, then press Enter here...")
    h_lvl, h_edges, _ = collect(port, n, 1.5)
    btn = [i for i in quiet if h_lvl[i] != b_lvl[i]]
    input("   Now RELEASE the button, then press Enter...")
    r_lvl, _, _ = collect(port, n, 1.0)
    btn = [i for i in btn if r_lvl[i] == b_lvl[i]]
    input("\n3) Point any TV remote at the cable (the side with the round receiver) and get ready.\n"
          "   Press Enter, then press remote buttons repeatedly for 4 seconds...")
    _, ir_edges, _ = collect(port, n, 4)
    ir = sorted([i for i in quiet if ir_edges[i] >= 20 and i not in btn], key=lambda i: -ir_edges[i])
    c.terminate()
    print(f"\n(reads rejected by the sync check: {BAD['n']})")
    print("\nRESULTS")
    print("  IR button (BU1):", ", ".join(f"P{pins[i]} (idle {'high' if b_lvl[i] else 'low'}, pressed {'high' if h_lvl[i] else 'low'})" for i in btn) or "no pin responded")
    print("  IR receiver    :", ", ".join(f"P{pins[i]} ({ir_edges[i]} pulses)" for i in ir) or "no pin responded")
    if len(btn) == 1 and len(ir) == 1:
        print(f"\nClear result. Apply with:\n  python3 ~/carby_irpins.py {pins[ir[0]]} {pins[btn[0]]}")
    else:
        print("\nNot a single clear answer for each - open an issue with this output")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build": build()
    elif cmd == "flash": flash()
    elif cmd == "watch": watch()
    else: sys.exit(__doc__)
