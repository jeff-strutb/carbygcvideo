#!/usr/bin/env python3
"""
diag2.py - Carby diagnostic 2: runs GCVideo's own clock generator and video decoder
           on the measured pin map and reports whether each stage works.

  python3 ~/diag2.py build                    (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag2.py flash     (usual flash hookup, AD4 wire held on pin 100)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag2.py read      (AD4 jumper REMOVED from the FT232H)

The diagnostic configures the FPGA with every candidate pin as an input (nothing is
driven toward the console), records 4096 samples of all of them on the falling edge
of pin 90, counts transitions on each pin (clocked by pin 90, and by the FT232H clock),
and streams the results out over the SPI header lines (P53 clock in, P46 in, P51 data out).
The flash chip stays deselected during readout because the FT232H holds its CS high.
"""
import os, sys, subprocess, hashlib, time

HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag2")
SRC  = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/src")
GCV  = ["video_defs.vhd", "Deglitcher.vhd", "component_defs.vhd", "ClockGen.vhd", "gcdv_decoder.vhd"]
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
PART = "xc3s200a-vq100-4"
PINS = [23,24,25,29,30,31,56,57,59,60,61,62,64,65,68,71,72,73,77,78,
        83,84,85,86,88,89,7,21,39,82,97]          # bit index 0..30
PREFIX = 32768                                    # bytes of 0xFF: counting phase

VHDL = r"""-- Carby diagnostic 2: GCVideo's own ClockGen + gcdv_decoder on the measured pins.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.video_defs.all;

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
  signal clk54, locked : std_logic;
  signal vdata  : std_logic_vector(7 downto 0);
  signal csel   : std_logic;
  signal pce, pce2 : boolean;
  signal video  : VideoY422;

  type cnt_t is array (0 to 3) of unsigned(23 downto 0);
  signal cnt    : cnt_t := (others => (others => '0'));
  signal win    : unsigned(19 downto 0) := (others => '0');
  signal wdone  : std_logic := '0';
  signal pcs, phs : std_logic := '0';
  signal a1, a2, a3 : std_logic := '0';

  signal arm_t, pmosi : std_logic := '0';
  signal ptr    : unsigned(17 downto 0) := (others => '0');
  signal word_r : std_logic_vector(31 downto 0) := (others => '0');
  signal bsel   : unsigned(4 downto 0) := (others => '0');
  signal lk1, lk2 : std_logic := '0';
begin
  -- measured Carby map (pins index: P60=9 P61=10 P62=11 P64=12 P65=13 P68=14 P71=15 P72=16 P73=17 P57=7)
  vdata <= pins(9) & pins(11) & pins(10) & pins(12) & pins(13) & pins(15) & pins(14) & pins(16);
  csel  <= pins(17);

  Inst_ClockGen : entity work.ClockGen
    generic map (TargetConsole => "GC")
    port map (ClockIn => cap_clk, BClock => pins(7), Clock54M => clk54, ClockAudio => open,
              DVIClockP => open, DVIClockN => open, Locked => locked);

  Inst_Decoder : entity work.gcdv_decoder
    port map (VClockI => clk54, VData => vdata, CSel => csel,
              PixelClockEnable => pce, PixelClockEnable2x => pce2, Video => video);

  -- counters in the internal 54 MHz domain: 0 = clock cycles, 1 = CSel toggles,
  -- 2 = pixel clock enables from the decoder, 3 = HSync pulses from the decoder
  process (clk54)
  begin
    if rising_edge(clk54) then
      a1 <= arm_t; a2 <= a1; a3 <= a2;
      pcs <= csel;
      if video.HSync then phs <= '1'; else phs <= '0'; end if;
      if a3 /= a2 then
        cnt <= (others => (others => '0')); win <= (others => '0'); wdone <= '0';
      elsif wdone = '0' then
        win <= win + 1;
        if win = (win'range => '1') then wdone <= '1'; end if;
        cnt(0) <= cnt(0) + 1;
        if pcs /= csel then cnt(1) <= cnt(1) + 1; end if;
        if pce then cnt(2) <= cnt(2) + 1; end if;
        if video.HSync and phs = '0' then cnt(3) <= cnt(3) + 1; end if;
      end if;
    end if;
  end process;

  -- readout: word 0..3 = counters, word 4 = status (bit0 DCM locked, bit1 window done)
  process (sck)
  begin
    if rising_edge(sck) then
      pmosi <= mosi; lk1 <= locked; lk2 <= lk1;
      if mosi = '1' and pmosi = '0' then arm_t <= not arm_t; end if;
      if mosi = '1' then ptr <= (others => '0'); else ptr <= ptr + 1; end if;
    end if;
  end process;

  process (sck)
  begin
    if falling_edge(sck) then
      case to_integer(ptr(7 downto 5)) is
        when 0 to 3 => word_r <= std_logic_vector(resize(cnt(to_integer(ptr(6 downto 5))), 32));
        when 4      => word_r <= (31 downto 2 => '0') & wdone & lk2;
        when others => word_r <= (others => '0');
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
    import shutil
    for f in GCV: shutil.copy(os.path.join(SRC, f), WORK)
    open(os.path.join(WORK, "top.prj"), "w").write("".join(f'vhdl work "{f}"\n' for f in GCV + ["top.vhd"]))
    open(os.path.join(WORK, "top.xst"), "w").write(
        'set -tmpdir "xst/tmp"\nset -xsthdpdir "xst"\nrun\n-ifn top.prj\n-ifmt mixed\n'
        f'-ofn top\n-ofmt NGC\n-p {PART}\n-top top\n-iobuf YES\n')
    ut = open(UT).read().replace("UnusedPin:PullUp", "UnusedPin:PullDown").replace("ICAP_Enable:Yes", "ICAP_Enable:No")
    open(os.path.join(WORK, "bitgen.ut"), "w").write(ut)
    for f in ("top.bin", "top.ncd", "top_map.ncd", "top.ngd", "top.ngc"):
        try: os.remove(os.path.join(WORK, f))
        except FileNotFoundError: pass
    steps = [["xst", "-ifn", "top.xst", "-ofn", "top.syr"],
             ["ngdbuild", "-aul", "-uc", "top.ucf", "-p", PART, "top.ngc", "top.ngd"],
             ["map", "-p", PART, "-o", "top_map.ncd", "top.ngd", "top.pcf"],
             ["par", "-w", "top_map.ncd", "top.ncd", "top.pcf"],
             ["bitgen", "-f", "bitgen.ut", "top.ncd"]]
    log = open(os.path.join(WORK, "build.log"), "w")
    for s in steps:
        print("----", s[0]); log.flush()
        if subprocess.call(s, cwd=WORK, stdout=log, stderr=subprocess.STDOUT) != 0:
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag2/build.log")
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
    clk, cs, pce, hs, st = (word(i) for i in range(5))
    print(f"DCM locked: {st & 1}   window done: {(st >> 1) & 1}")
    print(f"internal 54MHz clock cycles : {clk:9}   (expect 1048576)")
    print(f"CSel toggles                : {cs:9}   (expect ~262144, i.e. 1 per 4 clocks)")
    print(f"decoder pixel enables       : {pce:9}   (expect ~262144)")
    print(f"decoder HSync pulses        : {hs:9}   (expect ~305, one per video line)")

def read():
    c, p = spi(1)        # CS1 = AD4 (must be disconnected); CS0/AD3 stays high -> flash deselected
    nbits = 160
    for _ in range(PREFIX // 1024):
        p.exchange(b'\xff' * 1024, duplex=True)
    n = (nbits + 7)//8 + 16; buf = bytearray()
    for o in range(0, n, 1024):
        buf += p.exchange(b'\x00' * min(1024, n - o), duplex=True)
    c.terminate()
    data = bytes(buf)
    open(os.path.join(WORK, "capture.bin"), "wb").write(data)
    decode(data)
    print("Done.")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build": build, "flash": flash, "read": read}.get(cmd, lambda: sys.exit(__doc__))()
