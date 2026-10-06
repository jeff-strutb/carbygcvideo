#!/usr/bin/env python3
"""
diag.py - Carby pin diagnostic: an internal logic analyzer for the FPGA.

  python3 ~/diag.py build                    (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag.py flash     (usual flash hookup, AD4 wire held on pin 100)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag.py read      (AD4 jumper REMOVED from the FT232H)

The diagnostic configures the FPGA with every candidate pin as an input (nothing is
driven toward the console), records 4096 samples of all of them on the falling edge
of pin 90, counts transitions on each pin (clocked by pin 90, and by the FT232H clock),
and streams the results out over the SPI header lines (P53 clock in, P46 in, P51 data out).
The flash chip stays deselected during readout because the FT232H holds its CS high.
"""
import os, sys, subprocess, hashlib, time

HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
PINS = [23,24,25,29,30,31,56,57,59,60,61,62,64,65,68,71,72,73,77,78,
        83,84,85,86,88,89,7,21,39,82,97]          # bit index 0..30
PREFIX = 32768                                    # bytes of 0xFF: counting phase

VHDL = r"""-- Carby pin diagnostic: internal logic analyzer, read out over the SPI header.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity top is
  port (
    pins    : in  std_logic_vector(30 downto 0);  -- candidate inputs
    cap_clk : in  std_logic;                      -- P90, suspected console video clock
    sck     : in  std_logic;                      -- P53, clock from FT232H
    mosi    : in  std_logic;                      -- P46, '1' = count/reset phase
    miso    : out std_logic                       -- P51, data to FT232H
  );
  attribute BUFFER_TYPE : string;
  attribute BUFFER_TYPE of sck : signal is "IBUF";
end top;

architecture rtl of top is
  type cnt_t is array (0 to 31) of unsigned(24 downto 0);
  type scnt_t is array (0 to 31) of unsigned(15 downto 0);

  -- capture-clock domain
  signal c1, c2 : std_logic_vector(31 downto 0) := (others => '0');
  signal cnt    : cnt_t := (others => (others => '0'));
  signal win    : unsigned(19 downto 0) := (others => '0');
  signal wdone  : std_logic := '0';
  type ram_t is array (0 to 4095) of std_logic_vector(31 downto 0);
  signal ram    : ram_t;
  signal din    : std_logic_vector(31 downto 0) := (others => '0');
  signal waddr  : unsigned(11 downto 0) := (others => '0');
  signal cdone  : std_logic := '0';

  -- sck domain
  signal q1, q2 : std_logic_vector(31 downto 0) := (others => '0');
  signal scnt   : scnt_t := (others => (others => '0'));
  signal ptr    : unsigned(17 downto 0) := (others => '0');
  signal dout   : std_logic_vector(31 downto 0) := (others => '0');
  signal cw     : std_logic_vector(31 downto 0) := (others => '0');
  signal sw     : std_logic_vector(31 downto 0) := (others => '0');
  signal st     : std_logic_vector(31 downto 0);
  signal bsel   : unsigned(4 downto 0) := (others => '0');
  signal rsel   : std_logic_vector(2 downto 0) := (others => '0');
  signal pv     : std_logic_vector(31 downto 0);
  signal arm_t  : std_logic := '0';
  signal pmosi  : std_logic := '0';
  signal a1, a2, a3 : std_logic := '0';
begin
  pv <= cap_clk & pins;

  process (cap_clk)
  begin
    if falling_edge(cap_clk) then
      din <= pv;
      c1 <= pv; c2 <= c1;
      a1 <= arm_t; a2 <= a1; a3 <= a2;
      if a3 /= a2 then
        -- re-arm: restart capture and counters at the start of each readout
        waddr <= (others => '0'); cdone <= '0';
        win <= (others => '0'); wdone <= '0';
        cnt <= (others => (others => '0'));
      elsif cdone = '0' then
        ram(to_integer(waddr)) <= din;
        if waddr = 4095 then cdone <= '1'; end if;
        waddr <= waddr + 1;
      end if;
      if a3 = a2 and wdone = '0' then
        win <= win + 1;
        if win = (win'range => '1') then wdone <= '1'; end if;
        for i in 0 to 31 loop
          if c1(i) /= c2(i) then cnt(i) <= cnt(i) + 1; end if;
        end loop;
      end if;
    end if;
  end process;

  process (sck)
  begin
    if rising_edge(sck) then
      q1 <= pv; q2 <= q1;
      pmosi <= mosi;
      if mosi = '1' and pmosi = '0' then arm_t <= not arm_t; end if;
      if mosi = '1' then
        ptr <= (others => '0');
        for i in 0 to 31 loop
          if q1(i) /= q2(i) and scnt(i) /= x"FFFF" then scnt(i) <= scnt(i) + 1; end if;
        end loop;
      else
        ptr <= ptr + 1;
      end if;
    end if;
  end process;

  process (sck)
  begin
    if falling_edge(sck) then
      dout <= ram(to_integer(ptr(16 downto 5)));
      cw   <= std_logic_vector(resize(cnt(to_integer(ptr(9 downto 5))), 32));
      sw   <= std_logic_vector(resize(scnt(to_integer(ptr(9 downto 5))), 32));
      bsel <= ptr(4 downto 0);
      rsel(2) <= ptr(17); rsel(1) <= ptr(11); rsel(0) <= ptr(10);
    end if;
  end process;

  st <= (31 downto 2 => '0') & wdone & cdone;

  miso <= dout(to_integer(bsel)) when rsel(2) = '0' else
          cw(to_integer(bsel))   when rsel(1 downto 0) = "00" else
          sw(to_integer(bsel))   when rsel(1 downto 0) = "01" else
          st(to_integer(bsel));
end rtl;
"""

def build():
    os.makedirs(os.path.join(WORK, "xst/tmp"), exist_ok=True)
    open(os.path.join(WORK, "top.vhd"), "w").write(VHDL)
    ucf = ""
    for i, p in enumerate(PINS):
        ucf += f'NET "pins<{i}>" LOC = P{p} | IOSTANDARD = LVCMOS33 | PULLDOWN;\n'
    ucf += 'NET "cap_clk" LOC = P90 | IOSTANDARD = LVCMOS33 | PULLDOWN;\n'
    ucf += 'NET "sck"  LOC = P53 | IOSTANDARD = LVCMOS33;\n'
    ucf += 'NET "mosi" LOC = P46 | IOSTANDARD = LVCMOS33;\n'
    ucf += 'NET "miso" LOC = P51 | IOSTANDARD = LVCMOS33;\n'
    open(os.path.join(WORK, "top.ucf"), "w").write(ucf)
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
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag/build.log")
    b = open(os.path.join(WORK, "top.bin"), "rb").read()
    print("BUILD OK:", len(b), "bytes, SHA-256", hashlib.sha256(b).hexdigest())

def spi(cs):
    from pyftdi.spi import SpiController
    c = SpiController(cs_count=cs + 1); c.configure('ftdi://ftdi:232h/1')
    return c, c.get_port(cs=cs, freq=6e6 if cs else 1e6, mode=0)

def flash():
    img = open(os.path.join(WORK, "top.bin"), "rb").read()
    c, p = spi(0)
    g = c.get_gpio(); g.set_direction(0x10, 0x10); g.write(0)
    input("Hold the AD4 wire on pin 100 until DONE. Press Enter...")
    jid = bytes(p.exchange([0x9F], 3))
    if jid != b'\xc2\x20\x13': c.terminate(); sys.exit("Flash not responding (ID " + jid.hex() + "). Nothing written.")
    def wait():
        while p.exchange([0x05], 1)[0] & 1: time.sleep(0.01)
    print("Erasing..."); p.exchange([0x06]); p.exchange([0xC7]); wait()
    print("Writing...")
    for o in range(0, len(img), 256):
        p.exchange([0x06]); p.exchange(bytes([0x02, o>>16&255, o>>8&255, o&255]) + img[o:o+256]); wait()
    rd = bytearray()
    for o in range(0, len(img), 4096):
        rd += p.exchange([0x03, o>>16&255, o>>8&255, o&255], min(4096, len(img)-o))
    c.terminate()
    sys.exit("DONE - verified OK" if bytes(rd) == img else "VERIFY FAILED - rerun")

def decode(data):
    bit = lambda k: (data[k >> 3] >> (7 - (k & 7))) & 1
    word = lambda base, w: sum(bit(base + w*32 + j) << j for j in range(32))
    st = word(131072 + 2048, 0)
    print(f"status: capture_done={st & 1}  pin90_count_done={(st >> 1) & 1}")
    if data.count(0xff) == len(data) or data.count(0) == len(data):
        print("WARNING: readout is all-ones or all-zeros: the FPGA is not answering (diagnostic not running?)")
    cap = [word(0, w) for w in range(4096)]
    print("pin   changes@pin90clk   changes@FTclk   capture: ones%  changes")
    for i, pn in enumerate(PINS + [90]):
        ones = sum((x >> i) & 1 for x in cap)
        chg = sum(((cap[w] ^ cap[w+1]) >> i) & 1 for w in range(4095))
        print(f"P{pn:<4} {word(131072, i):14}   {word(131072 + 1024, i):12}      {100*ones/4096:6.1f}   {chg:6}")

def read():
    c, p = spi(1)        # CS1 = AD4 (must be disconnected); CS0/AD3 stays high -> flash deselected
    nbits = 131072 + 2048 + 32
    for _ in range(PREFIX // 1024):
        p.exchange(b'\xff' * 1024, duplex=True)
    n = (nbits + 7)//8 + 16; buf = bytearray()
    for o in range(0, n, 1024):
        buf += p.exchange(b'\x00' * min(1024, n - o), duplex=True)
    c.terminate()
    data = bytes(buf)
    open(os.path.join(WORK, "capture.bin"), "wb").write(data)
    decode(data)
    print("Saved ~/diag/capture.bin - upload it.")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build": build, "flash": flash, "read": read}.get(cmd, lambda: sys.exit(__doc__))()
