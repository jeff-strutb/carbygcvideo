#!/usr/bin/env python3
"""
diag3.py - Carby diagnostic 3: console blanking-flag statistics per data pin (~5 fields).

  python3 ~/diag3.py build                    (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag3.py flash     (usual flash hookup, AD4 wire held on pin 100)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag3.py read      (AD4 jumper REMOVED from the FT232H)

The diagnostic configures the FPGA with every candidate pin as an input (nothing is
driven toward the console), records 4096 samples of all of them on the falling edge
of pin 90, counts transitions on each pin (clocked by pin 90, and by the FT232H clock),
and streams the results out over the SPI header lines (P53 clock in, P46 in, P51 data out).
The flash chip stays deselected during readout because the FT232H holds its CS high.
"""
import os, sys, subprocess, hashlib, time

HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag3")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
PINS = [23,24,25,29,30,31,56,57,59,60,61,62,64,65,68,71,72,73,77,78,
        83,84,85,86,88,89,7,21,39,82,97]          # bit index 0..30
PREFIX = 98304                                    # bytes of 0xFF: counting phase

VHDL = r"""-- Carby diagnostic 3: blanking-flag statistics per data pin, over ~5 video fields.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity top is
  port (
    pins    : in  std_logic_vector(30 downto 0);
    cap_clk : in  std_logic;                      -- P90, console video clock
    sck     : in  std_logic;                      -- P53, clock from FT232H
    mosi    : in  std_logic;                      -- P46
    miso    : out std_logic                       -- P51
  );
  attribute BUFFER_TYPE : string;
  attribute BUFFER_TYPE of sck : signal is "IBUF";
end top;

architecture rtl of top is
  -- bus as measured: index = pin list position (P60=9 P61=10 P62=11 P64=12 P65=13 P68=14 P71=15 P72=16, CSel P73=17)
  signal vd, vd1, vd2, flags_prev : std_logic_vector(7 downto 0) := (others => '0');
  signal cs1, cs2, cs3 : std_logic := '0';
  signal phase : unsigned(1 downto 0) := (others => '0');
  signal blank : std_logic := '0';
  type cnt_t is array (0 to 15) of unsigned(27 downto 0);
  signal cnt   : cnt_t := (others => (others => '0'));   -- 0..7 zeros per bit, 8..15 changes per bit
  signal total : unsigned(27 downto 0) := (others => '0');
  signal win   : unsigned(21 downto 0) := (others => '0');
  signal wdone : std_logic := '0';
  signal a1, a2, a3, arm_t, pmosi : std_logic := '0';
  signal ptr   : unsigned(17 downto 0) := (others => '0');
  signal word_r: std_logic_vector(31 downto 0) := (others => '0');
  signal bsel  : unsigned(4 downto 0) := (others => '0');
begin
  -- vd(7..0) = P60 P62 P61 P64 P65 P71 P68 P72 (the current map's bits 7..0)
  vd <= pins(9) & pins(11) & pins(10) & pins(12) & pins(13) & pins(15) & pins(14) & pins(16);

  process (cap_clk)
  begin
    if falling_edge(cap_clk) then
      vd1 <= vd; vd2 <= vd1;
      cs1 <= pins(17); cs2 <= cs1; cs3 <= cs2;
      a1 <= arm_t; a2 <= a1; a3 <= a2;
      if a3 /= a2 then
        cnt <= (others => (others => '0')); total <= (others => '0');
        win <= (others => '0'); wdone <= '0';
      else
        if cs2 /= cs3 then                       -- Y sample (same alignment as gcdv_decoder)
          phase <= "00";
          if vd2 = x"00" then blank <= '1'; else blank <= '0'; end if;
        else
          phase <= phase + 1;
          if phase = "01" and blank = '1' and wdone = '0' then   -- flags sample
            total <= total + 1;
            flags_prev <= vd2;
            for i in 0 to 7 loop
              if vd2(i) = '0' then cnt(i) <= cnt(i) + 1; end if;
              if vd2(i) /= flags_prev(i) then cnt(8+i) <= cnt(8+i) + 1; end if;
            end loop;
          end if;
        end if;
        if wdone = '0' then
          win <= win + 1;
          if win = (win'range => '1') then wdone <= '1'; end if;
        end if;
      end if;
    end if;
  end process;

  process (sck)
  begin
    if rising_edge(sck) then
      pmosi <= mosi;
      if mosi = '1' and pmosi = '0' then arm_t <= not arm_t; end if;
      if mosi = '1' then ptr <= (others => '0'); else ptr <= ptr + 1; end if;
    end if;
  end process;

  process (sck)
  begin
    if falling_edge(sck) then
      case to_integer(ptr(9 downto 5)) is
        when 0 to 15 => word_r <= std_logic_vector(resize(cnt(to_integer(ptr(8 downto 5))), 32));
        when 16      => word_r <= std_logic_vector(resize(total, 32));
        when 17      => word_r <= x"0000A5" & "0000000" & wdone;
        when others  => word_r <= (others => '0');
      end case;
      bsel <= ptr(4 downto 0);
    end if;
  end process;

  miso <= word_r(to_integer(bsel));
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
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag3/build.log")
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
    word = lambda w: sum(bit(w*32 + j) << j for j in range(32))
    w = [word(i) for i in range(18)]
    if (w[17] >> 8) & 0xff != 0xA5:
        print("No valid response (marker missing) - diagnostic not running?"); return
    tot = w[16]
    print(f"window done: {w[17] & 1}   blanking flag samples: {tot}")
    names = ["P72", "P68", "P71", "P65", "P64", "P61", "P62", "P60"]   # current map, bits 0..7
    for b in range(8):
        print(f"bit{b} ({names[b]}): zero {100*w[b]/max(tot,1):6.2f}%   changes {w[8+b]}")

def read():
    c, p = spi(1)        # CS1 = AD4 (must be disconnected); CS0/AD3 stays high -> flash deselected
    nbits = 18 * 32
    for _ in range(PREFIX // 1024):
        p.exchange(b'\xff' * 1024, duplex=True)
    n = (nbits + 7)//8 + 16; buf = bytearray()
    for o in range(0, n, 1024):
        buf += p.exchange(b'\x00' * min(1024, n - o), duplex=True)
    c.terminate()
    data = bytes(buf)
    decode(data)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build": build, "flash": flash, "read": read}.get(cmd, lambda: sys.exit(__doc__))()
