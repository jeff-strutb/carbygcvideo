#!/usr/bin/env python3
"""
diag9.py - settle the Carby's lowest DAC bits with five meter readings.

  python3 ~/diag9.py build                              (after: source /opt/Xilinx/14.7/ISE_DS/settings64.sh)
  sudo HOME=$HOME ~/ftdi/bin/python ~/diag9.py flash    (AD4 jumper held on pin 100)
  python3 ~/diag9.py read                               (GameCube on, FT232H unplugged, meter on DC volts)

Five FPGA pins (P33, P34, P35, P49, P50) each output a different steady voltage: 10, 30, 50, 70
and 90 percent of the supply. Measuring five DAC pins names the FPGA pin wired to each one.
"""
import os, re, sys, subprocess, hashlib, time
HOME = os.path.expanduser("~")
WORK = os.path.join(HOME, "diag9")
UT   = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut")
UCFP = os.path.join(HOME, "gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf")
PART = "xc3s200a-vq100-4"
PINS = [33, 34, 35, 49, 50]                    # signature 10, 30, 50, 70, 90 percent
VHDL = r"""-- Carby diagnostic 9: five widely spaced PWM signatures on the five low-bit candidate pins.
-- 54 MHz console clock, 40-step PWM (1.35 MHz). Duty: P33 4/40, P34 12/40, P35 20/40, P49 28/40, P50 36/40.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity top is
  port (
    cap_clk : in  std_logic;                     -- P90
    sig     : out std_logic_vector(4 downto 0)   -- 0:P33 1:P34 2:P35 3:P49 4:P50
  );
end top;
architecture rtl of top is
  signal cnt : unsigned(5 downto 0) := (others => '0');
  signal q   : std_logic_vector(4 downto 0) := (others => '0');
  type duty_t is array (0 to 4) of integer range 0 to 40;
  constant DUTY : duty_t := (4, 12, 20, 28, 36);
begin
  process (cap_clk)
  begin
    if rising_edge(cap_clk) then
      if cnt = 39 then cnt <= (others => '0'); else cnt <= cnt + 1; end if;
      for i in 0 to 4 loop
        if to_integer(cnt) < DUTY(i) then q(i) <= '1'; else q(i) <= '0'; end if;
      end loop;
    end if;
  end process;
  sig <= q;
end rtl;
"""
UCF  = ('NET "cap_clk" LOC = P90 | IOSTANDARD = LVCMOS33;\n' +
        "".join(f'NET "sig<{i}>" LOC = P{p} | IOSTANDARD = LVCMOS33;\n' for i, p in enumerate(PINS)))
# DAC pins to read (board held with the DAC printing upright, pin 1 at the top-left by the dot)
READ = [("G0", 3, "LEFT side, 3rd pin from the top",            "DAC_Green[0]"),
        ("G1", 4, "LEFT side, 4th pin from the top",            "DAC_Green[1]"),
        ("G2", 5, "LEFT side, 5th pin from the top",            "DAC_Green[2]"),
        ("R1", 42, "TOP row, 6th pin from the RIGHT end",       "DAC_Red[1]"),
        ("R0", 41, "TOP row, 5th pin from the RIGHT end",       "DAC_Red[0]")]

def build():
    os.makedirs(os.path.join(WORK, "xst/tmp"), exist_ok=True)
    open(os.path.join(WORK, "top.vhd"), "w").write(VHDL)
    open(os.path.join(WORK, "top.ucf"), "w").write(UCF)
    open(os.path.join(WORK, "top.prj"), "w").write('vhdl work "top.vhd"\n')
    open(os.path.join(WORK, "top.xst"), "w").write(
        'set -tmpdir "xst/tmp"\nset -xsthdpdir "xst"\nrun\n-ifn top.prj\n-ifmt mixed\n'
        f'-ofn top\n-ofmt NGC\n-p {PART}\n-top top\n-iobuf YES\n')
    ut = open(UT).read().replace("UnusedPin:PullUp", "UnusedPin:PullDown").replace("ICAP_Enable:Yes", "ICAP_Enable:No")
    open(os.path.join(WORK, "bitgen.ut"), "w").write(ut)     # unused pins low: an unexpected DAC pin reads ~0 V
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
            sys.exit(f"{s[0]} FAILED - run:  tail -40 ~/diag9/build.log")
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


def num(prompt):
    while True:
        s = input(prompt).strip().lower().replace("v", "")
        try: return float(s)
        except ValueError: print("   type the number the meter shows, e.g. 1.71")

def identify(v, rail):
    f = v / rail
    if f < 0.03: return None, "about 0 V: not one of the five pins (or the probe missed)"
    if f > 0.97: return None, "full supply: not one of the five pins (or touching a supply pin)"
    k = round((f - 0.10) / 0.20)
    if 0 <= k <= 4 and abs(f - (0.10 + 0.20 * k)) <= 0.06: return PINS[k], None
    return None, "between two signatures: the probe may be touching two pins"

def read():
    print(__doc__.split("\n\n")[2])
    print("\nBlack probe on the white ground wire stub the whole time.\n")
    rail = num("Red probe on the 3.3 V stub (black wire). Reading: ")
    found = {}
    for lab, pin, where, net in READ:
        while True:
            v = num(f"DAC {lab} (pin {pin}, {where}): ")
            p, why = identify(v, rail)
            if p is not None: found[net] = p; print(f"   -> FPGA P{p}"); break
            print("   " + why + ". Measure again.")
    if len(set(found.values())) != 5:
        sys.exit("Two DAC pins matched the same FPGA pin - one reading slipped. Run 'read' again.")
    print("\nRESULT")
    for net, p in found.items(): print(f"  {net:<13} = P{p}")
    s = open(UCFP).read()
    cur = {n: int(re.search(r'NET "%s"\s+LOC = P(\d+)' % re.escape(n), s).group(1)) for n in found}
    if cur == found:
        print("\nThe pin file already matches every reading. Nothing to change: the wiring is exact.")
        return
    if sorted(cur.values()) != sorted(found.values()):
        sys.exit("The readings use pins outside the current group - send this output for help. Nothing written.")
    for n, p in found.items(): s = re.sub(r'(NET "%s"\s+LOC = )P\d+' % re.escape(n), r'\g<1>P%d' % p, s)
    open(UCFP + ".before-diag9", "w").write(open(UCFP).read()); open(UCFP, "w").write(s)
    print("\nPin file corrected (backup: constraints-dualgc.ucf.before-diag9). Rebuild with carby_build.py and flash.")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build": build()
    elif cmd == "flash": flash()
    elif cmd == "read": read()
    else: sys.exit(__doc__)
