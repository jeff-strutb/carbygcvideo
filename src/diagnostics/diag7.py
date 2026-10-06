#!/usr/bin/env python3
"""
diag7.py - Carby colour-wiring calibration by photo (no probing).

  python3 ~/diag7.py build [pins]                       (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
                                                        e.g. build 16 36 93 -> those lines on at power-up
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag7.py flash    (AD4 jumper held on pin 100)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag7.py base all          (photo 1 background: every line on)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag7.py base 44 20 6      (photo 2 background: these FPGA pins on)

The screen shows a 16 x 10 grid of boxes inside a checkered frame. Each box's LEFT half is the
background; its RIGHT half is the background with one FPGA line flipped. Each of the 37 candidate
lines appears in 4 boxes. Sync is on P15, the DAC clock on P70.
"""
import os, sys, subprocess, hashlib, time
HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag7")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
C    = [44, 43, 41, 40, 37, 36, 35, 34, 20, 19, 16, 13, 12, 10, 9, 6, 5, 4, 3, 99, 98, 94, 93, 49, 33, 32, 28, 52, 48, 77, 78, 83, 84, 85, 86, 88, 50]
VHDL = r"""-- Carby diagnostic 7: photo calibration grid.
-- 240p (858 x 262 @ 13.5 MHz). Sync on P15, DAC clock on P70.
-- Active area 720 x 240. Frame: 6-pixel ring of 2x2 checker (all lines on / all off) around a
-- 576 x 180 grid of 16 x 10 boxes (36 x 18). Box n (raster order) tests line (n mod 40) if < 37:
-- its LEFT half shows the base pattern, its RIGHT half shows base XOR that line. Boxes with
-- (n mod 40) >= 37 show base in both halves (references). 1-pixel base gaps between boxes.
-- The 37-bit base is loaded from the FT232H: 40-bit frames MSB-first on MOSI (P46) clocked
-- by SCK (P53); a pause > 150 us starts a new frame.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity top is
  port (
    cap_clk : in  std_logic;                        -- P90
    sck     : in  std_logic;                        -- P53
    mosi    : in  std_logic;                        -- P46
    lines   : out std_logic_vector(36 downto 0);
    syncp   : out std_logic;                        -- P15
    dacclk  : out std_logic                         -- P70
  );
end top;
architecture rtl of top is
  signal div   : unsigned(1 downto 0) := (others => '0');
  signal hc    : unsigned(9 downto 0) := (others => '0');
  signal vc    : unsigned(8 downto 0) := (others => '0');
  signal t     : std_logic := '0';
  signal q     : std_logic_vector(36 downto 0) := (others => '0');
  signal s     : std_logic := '1';
  signal base  : std_logic_vector(36 downto 0) := @@BASEINIT@@;
  -- grid walking
  signal bx    : unsigned(5 downto 0) := (others => '0');   -- pixel within box (0..35)
  signal by    : unsigned(4 downto 0) := (others => '0');   -- line within box row (0..17)
  signal kline : unsigned(5 downto 0) := (others => '0');   -- current box's test line (n mod 40)
  signal krow  : unsigned(5 downto 0) := (others => '0');   -- first box of this row (mod 40)
  -- FT232H receiver
  signal s1, s2, s3, m1, m2 : std_logic := '0';
  signal idle  : unsigned(13 downto 0) := (others => '0');
  signal nbit  : unsigned(5 downto 0) := (others => '0');
  signal sh    : std_logic_vector(39 downto 0) := (others => '0');
begin
  process (cap_clk)
    variable ax, ay : integer range -1024 to 1023;
    variable inact, ingrid, inring, ck : boolean;
    variable pat : std_logic_vector(36 downto 0);
  begin
    if rising_edge(cap_clk) then
      t <= not t;
      -- receiver
      s1 <= sck; s2 <= s1; s3 <= s2; m1 <= mosi; m2 <= m1;
      if s2 = '1' and s3 = '0' then
        idle <= (others => '0');
        sh <= sh(38 downto 0) & m2;
        if nbit = 39 then base <= sh(35 downto 0) & m2; nbit <= (others => '0');
        else nbit <= nbit + 1; end if;
      elsif idle /= (idle'range => '1') then idle <= idle + 1;
      else nbit <= (others => '0'); end if;
      -- video
      div <= div + 1;
      if div = 3 then
        if hc = 857 then
          hc <= (others => '0');
          if vc = 261 then vc <= (others => '0'); else vc <= vc + 1; end if;
        else
          hc <= hc + 1;
        end if;
        ax := to_integer(hc) - 122; ay := to_integer(vc) - 30;
        inact  := hc >= 122 and hc < 842 and vc >= 30 and vc < 252;
        ingrid := inact and ax >= 72 and ax < 648 and ay >= 21 and ay < 201;
        inring := inact and ax >= 66 and ax < 654 and ay >= 15 and ay < 207 and not ingrid;
        -- grid walk: start of grid on each line
        if inact and ax = 71 then
          bx <= (others => '0');
          if ay = 21 then by <= (others => '0'); krow <= (others => '0'); kline <= (others => '0');
          elsif ay > 21 and ay < 201 then
            if by = 17 then
              by <= (others => '0');
              if krow + 16 >= 40 then krow <= krow + 16 - 40; kline <= krow + 16 - 40;
              else krow <= krow + 16; kline <= krow + 16; end if;
            else
              by <= by + 1; kline <= krow;
            end if;
          end if;
        elsif ingrid then
          if bx = 35 then
            bx <= (others => '0');
            if kline = 39 then kline <= (others => '0'); else kline <= kline + 1; end if;
          else
            bx <= bx + 1;
          end if;
        end if;
        -- pattern
        pat := base;
        if ingrid and bx >= 18 and bx < 35 and by < 17 and kline < 37 then
          pat(to_integer(kline)) := not base(to_integer(kline));
        end if;
        if ingrid and (bx = 35 or by = 17) then pat := base; end if;
        ck := ((ax / 2) mod 2) /= ((ay / 2) mod 2);
        if inring then
          if ck then pat := (others => '1'); else pat := (others => '0'); end if;
        elsif not ingrid then
          pat := (others => '0');
        end if;
        if inact then q <= pat; else q <= (others => '0'); end if;
        if vc < 3 then
          if hc < 794 then s <= '0'; else s <= '1'; end if;
        else
          if hc < 64 then s <= '0'; else s <= '1'; end if;
        end if;
      end if;
    end if;
  end process;
  lines  <= q;
  syncp  <= s;
  dacclk <= t;
end rtl;
"""
UCF  = r"""NET "cap_clk" LOC = P90 | IOSTANDARD = LVCMOS33;
NET "sck" LOC = P53 | IOSTANDARD = LVCMOS33;
NET "mosi" LOC = P46 | IOSTANDARD = LVCMOS33;
NET "syncp" LOC = P15 | IOSTANDARD = LVCMOS33;
NET "dacclk" LOC = P70 | IOSTANDARD = LVCMOS33;
NET "lines<0>" LOC = P44 | IOSTANDARD = LVCMOS33;
NET "lines<1>" LOC = P43 | IOSTANDARD = LVCMOS33;
NET "lines<2>" LOC = P41 | IOSTANDARD = LVCMOS33;
NET "lines<3>" LOC = P40 | IOSTANDARD = LVCMOS33;
NET "lines<4>" LOC = P37 | IOSTANDARD = LVCMOS33;
NET "lines<5>" LOC = P36 | IOSTANDARD = LVCMOS33;
NET "lines<6>" LOC = P35 | IOSTANDARD = LVCMOS33;
NET "lines<7>" LOC = P34 | IOSTANDARD = LVCMOS33;
NET "lines<8>" LOC = P20 | IOSTANDARD = LVCMOS33;
NET "lines<9>" LOC = P19 | IOSTANDARD = LVCMOS33;
NET "lines<10>" LOC = P16 | IOSTANDARD = LVCMOS33;
NET "lines<11>" LOC = P13 | IOSTANDARD = LVCMOS33;
NET "lines<12>" LOC = P12 | IOSTANDARD = LVCMOS33;
NET "lines<13>" LOC = P10 | IOSTANDARD = LVCMOS33;
NET "lines<14>" LOC = P9 | IOSTANDARD = LVCMOS33;
NET "lines<15>" LOC = P6 | IOSTANDARD = LVCMOS33;
NET "lines<16>" LOC = P5 | IOSTANDARD = LVCMOS33;
NET "lines<17>" LOC = P4 | IOSTANDARD = LVCMOS33;
NET "lines<18>" LOC = P3 | IOSTANDARD = LVCMOS33;
NET "lines<19>" LOC = P99 | IOSTANDARD = LVCMOS33;
NET "lines<20>" LOC = P98 | IOSTANDARD = LVCMOS33;
NET "lines<21>" LOC = P94 | IOSTANDARD = LVCMOS33;
NET "lines<22>" LOC = P93 | IOSTANDARD = LVCMOS33;
NET "lines<23>" LOC = P49 | IOSTANDARD = LVCMOS33;
NET "lines<24>" LOC = P33 | IOSTANDARD = LVCMOS33;
NET "lines<25>" LOC = P32 | IOSTANDARD = LVCMOS33;
NET "lines<26>" LOC = P28 | IOSTANDARD = LVCMOS33;
NET "lines<27>" LOC = P52 | IOSTANDARD = LVCMOS33;
NET "lines<28>" LOC = P48 | IOSTANDARD = LVCMOS33;
NET "lines<29>" LOC = P77 | IOSTANDARD = LVCMOS33;
NET "lines<30>" LOC = P78 | IOSTANDARD = LVCMOS33;
NET "lines<31>" LOC = P83 | IOSTANDARD = LVCMOS33;
NET "lines<32>" LOC = P84 | IOSTANDARD = LVCMOS33;
NET "lines<33>" LOC = P85 | IOSTANDARD = LVCMOS33;
NET "lines<34>" LOC = P86 | IOSTANDARD = LVCMOS33;
NET "lines<35>" LOC = P88 | IOSTANDARD = LVCMOS33;
NET "lines<36>" LOC = P50 | IOSTANDARD = LVCMOS33;
"""

def build(args=()):
    """build                -> power-on background: every line on
       build 16 36 93       -> power-on background: just these FPGA pins on"""
    mask = (1 << len(C)) - 1
    if args:
        mask = 0
        for a in args:
            pnum = int(a.lstrip("Pp"))
            if pnum not in C: sys.exit(f"P{pnum} is not one of the candidate lines")
            mask |= 1 << C.index(pnum)
    init = '"' + "".join("1" if mask >> k & 1 else "0" for k in range(len(C) - 1, -1, -1)) + '"'
    os.makedirs(os.path.join(WORK, "xst/tmp"), exist_ok=True)
    open(os.path.join(WORK, "top.vhd"), "w").write(VHDL.replace("@@BASEINIT@@", init))
    on = [f"P{p}" for k, p in enumerate(C) if mask >> k & 1]
    print("power-on background:", "all lines on" if len(on) == len(C) else " ".join(on))
    open(os.path.join(WORK, "top.ucf"), "w").write(UCF)
    open(os.path.join(WORK, "top.prj"), "w").write('vhdl work "top.vhd"\n')
    open(os.path.join(WORK, "top.xst"), "w").write(
        'set -tmpdir "xst/tmp"\nset -xsthdpdir "xst"\nrun\n-ifn top.prj\n-ifmt mixed\n'
        f'-ofn top\n-ofmt NGC\n-p {PART}\n-top top\n-iobuf YES\n')
    ut = open(UT).read()
    ut = ut.replace("UnusedPin:PullDown", "UnusedPin:PullUp").replace("ICAP_Enable:Yes", "ICAP_Enable:No")
    open(os.path.join(WORK, "bitgen.ut"), "w").write(ut)     # pull-ups keep the DAC's BLANK high
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
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag7/build.log")
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


def base(args):
    """Send the background pattern by driving only AD0 (clock -> P53) and AD1 (data -> P46),
    with AD3 (flash CS) held high. AD4 (wired to the FPGA reset) is left as an input."""
    from pyftdi.gpio import GpioMpsseController
    if args == ["all"]: mask = (1 << len(C)) - 1
    elif args == ["none"]: mask = 0
    else:
        mask = 0
        for a in args:
            p = int(a.lstrip("Pp"))
            if p not in C: sys.exit(f"P{p} is not one of the candidate lines")
            mask |= 1 << C.index(p)
    SCK, MOSI, CS = 0x01, 0x02, 0x08
    g = GpioMpsseController()
    g.configure('ftdi://ftdi:232h/1', direction=SCK | MOSI | CS, frequency=200000)
    seq = [CS] * 4
    for i in range(39, -1, -1):                      # 40 bits, MSB first, clock idle low
        d = MOSI if (mask >> i) & 1 else 0
        seq += [CS | d, CS | d | SCK, CS | d]
    seq += [CS] * 4
    for _ in range(3):                               # three frames; >150 us pause between them
        g.write(seq); time.sleep(0.01)
    g.set_direction(SCK | MOSI | CS, CS)             # release clock/data, keep flash deselected
    g.close()
    on = [f"P{p}" for k, p in enumerate(C) if mask >> k & 1]
    print("background set:", "all lines on" if len(on) == len(C) else ("all off" if not on else " ".join(on)))
    print("Now photograph the TV: straight on, whole screen in frame, no flash, room lights dimmed if possible.")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build": build(sys.argv[2:])
    elif cmd == "flash": flash()
    elif cmd == "base": base(sys.argv[2:])
    else: sys.exit(__doc__)
