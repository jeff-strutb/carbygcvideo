#!/usr/bin/env python3
"""
carby_build.py - prepare and build GCVideo 3.1 for the Carby Component (GCAnalog 1.9) in one go.

Run from a shell where ISE and the ZPU compiler are on PATH:
    source /opt/Xilinx/14.7/ISE_DS/settings64.sh ; export PATH=~/zpu/bin:$PATH
    python3 carby_build.py [GCVIDEO_TREE]

GCVIDEO_TREE is the GCVideo 3.1 source tree (default: ~/gcvideo). In this
repository that is src/gcvideo, which already contains every change below.

What it builds (on top of the GCVideo 3.1 source tree):
  * Carby pin map (measured on the board)            - checked in the .ucf files
  * DAC_PSave: spare constant-high output, parked on P30 (P70 is the DAC clock)
  * line doubling off by default (240p/288p/480i/576i) - for a 15 kHz CRT
  * recovery stage: IR-button check disabled
  * main firmware: automatic VSync/field flag detection on P61/P62
  * composite sync driven on the spare sync and LED outputs (P3 to P6)
  * main firmware: debug read-out on the SPI header (read with dbgread.py)
"""
import os, sys, subprocess, shutil, hashlib
H   = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/gcvideo"))
G   = os.path.join(H, "HDL/gcvideo_dvi/src")
FW  = os.path.join(H, "Firmware")
OUT = os.path.join(H, "HDL/gcvideo_dvi/build/gcvideo-dvi-dual-gc-3.1-crt-spirom-complete.bin")

for tool in ("xst", "zpu-elf-gcc"):
    if not shutil.which(tool):
        sys.exit(f"{tool} not on PATH - run:  source /opt/Xilinx/14.7/ISE_DS/settings64.sh ; export PATH=~/zpu/bin:$PATH")

def must(cond, msg):
    if not cond: sys.exit("STOP: " + msg)

# ---- 1. pin map must already be in the .ucf (from carby_pins.py) -------------------
up = os.path.join(G, "constraints-dualgc.ucf"); u = open(up).read()
must('NET "CSel"         LOC = P73;' in u and 'NET "VData[0]"     LOC = P72;' in u,
     "Carby pin map not found in constraints-dualgc.ucf (run carby_pins.py first)")
if 'NET "DAC_PSave"' not in u:
    u += '\n# Carby: spare constant-high output (DAC_PSave port), parked on P30. P70 is the DAC clock.\nNET "DAC_PSave" LOC = P30 | IOSTANDARD = LVCMOS33;\n'
    open(up, "w").write(u)
print("ok  pin map present, DAC_PSave parked on P30")

# ---- 2. firmware C changes (idempotent) ---------------------------------------------
p = os.path.join(FW, "settings-main.c"); s = open(p).read()
s2 = s.replace("= VIDEOIF_SET_LD_ENABLE | VIDEOIF_SET_SL_ALTERNATE;", "= VIDEOIF_SET_SL_ALTERNATE;")
s2 = s2.replace("video_settings[VIDMODE_240p] = VIDEOIF_SET_LD_ENABLE;", "video_settings[VIDMODE_240p] = 0;")
s2 = s2.replace("video_settings[VIDMODE_288p] = VIDEOIF_SET_LD_ENABLE;", "video_settings[VIDMODE_288p] = 0;")
must("video_settings[VIDMODE_240p] = 0;" in s2, "could not set line-doubling defaults in settings-main.c")
open(p, "w").write(s2); print("ok  line doubling off by default")
p = os.path.join(FW, "flasher.c"); s = open(p).read()
s2 = s.replace("if (!(IRRX->pulsedata & IRRX_BUTTON)) {", "if (0) { // Carby: IR button check disabled", 1)
must("Carby: IR button check disabled" in s2, "could not disable IR button check in flasher.c")
open(p, "w").write(s2); print("ok  recovery-stage IR check disabled")

# ---- 3. VHDL: reset to clean 3.1, then patch -----------------------------------------
# A tree that already has the Carby VHDL changes (such as src/gcvideo in this
# repository) is built as it is. Otherwise the three files are reset with git
# and patched.
VHDL_DONE = ("-- Carby" in open(os.path.join(G, "toplevel_gcdual.vhd")).read() and
             "DbgLocked" in open(os.path.join(G, "datapipe.vhd")).read() and
             "DbgLocked" in open(os.path.join(G, "component_defs.vhd")).read())
if not VHDL_DONE:
  for f in ("toplevel_gcdual.vhd", "datapipe.vhd", "component_defs.vhd"):
    subprocess.check_call(["git", "checkout", "--", f], cwd=G)

def patch(name, pairs):
    if VHDL_DONE: return
    p = os.path.join(G, name); s = open(p).read()
    for a, b in pairs:
        must(s.count(a) == 1, f"{name}: anchor not found: {a[:70]!r}")
        s = s.replace(a, b)
    open(p, "w").write(s)

patch("datapipe.vhd", [
 ("    ForceYPbPr : in  std_logic;\n", "    ForceYPbPr : in  std_logic;\n    DbgLocked  : out std_logic;\n"),
 ("  Inst_ClockGen: ClockGen", "  DbgLocked <= clock_locked;\n\n  Inst_ClockGen: ClockGen"),
])
if not VHDL_DONE:
  cd = open(os.path.join(G, "component_defs.vhd")).read()
  anchor = "      ForceYPbPr : in  std_logic := '1'; -- default: Not forced\n"
  i = cd.lower().find("component datapipe"); j = cd.find(anchor, i)
  must(i >= 0 and j >= 0, "component_defs.vhd: Datapipe port anchor not found")
  cd = cd[:j] + anchor + "      DbgLocked  : out std_logic;\n" + cd[j + len(anchor):]
  open(os.path.join(G, "component_defs.vhd"), "w").write(cd)

DECL = """  -- Carby
  signal f_copi, f_cipo, f_sck, f_sel, dac_clk_i, dbg_locked : std_logic;
  signal dp_vdata : std_logic_vector(7 downto 0);
  signal dp_csel  : std_logic;
  signal csync_i  : std_logic;
  signal sck_in, mosi_in : std_logic;
  -- input stage + VSync/field auto-detect
  signal in_vd, in_vd2 : std_logic_vector(7 downto 0) := (others => '0');
  signal in_cs, in_cs2, in_cs3 : std_logic := '0';
  signal det_ph   : unsigned(1 downto 0) := (others => '0');
  signal det_blank, det_sel : std_logic := '0';
  signal det_ra, det_rb : unsigned(14 downto 0) := (others => '0');
  -- debug read-out
  type dbg_cnt_t is array (0 to 1) of unsigned(19 downto 0);
  signal dbg_cnt   : dbg_cnt_t := (others => (others => '0'));
  signal dbg_win   : unsigned(19 downto 0) := (others => '0');
  signal dbg_done, dbg_arm, dbg_a1, dbg_a2, dbg_a3, dbg_ph : std_logic := '0';
  signal dbg_s1, dbg_s2, dbg_s3, dbg_m1, dbg_m2, dbg_m3, dbg_miso : std_logic := '0';
  signal dbg_alive : unsigned(3 downto 0) := (others => '0');
  signal dbg_ptr   : unsigned(17 downto 0) := (others => '0');
  signal dbg_word  : std_logic_vector(31 downto 0) := (others => '0');
  signal dbg_bsel  : unsigned(4 downto 0) := (others => '0');
begin
"""
BODY = """
  Flash_SEL <= f_sel;
  DAC_Clock <= dac_clk_i;

  main_only: if Module = "main" generate
    -- input stage: register the console bus, auto-detect which of bits 5/6 is VSync
    process (pipe_clock)
    begin
      if rising_edge(pipe_clock) then
        in_vd <= VData; in_cs <= CSel;
        in_vd2 <= in_vd; in_cs2 <= in_cs; in_cs3 <= in_cs2;
        if in_cs2 /= in_cs3 then
          det_ph <= "00";
          if in_vd2 = x"00" then det_blank <= '1'; else det_blank <= '0'; end if;
        else
          det_ph <= det_ph + 1;
          if det_ph = "01" and det_blank = '1' then
            if in_vd2(5) = '0' then
              if det_ra /= (det_ra'range => '1') then det_ra <= det_ra + 1; end if;
            else
              if det_ra /= 0 and det_ra(14) = '0' then det_sel <= '0'; end if;
              det_ra <= (others => '0');
            end if;
            if in_vd2(6) = '0' then
              if det_rb /= (det_rb'range => '1') then det_rb <= det_rb + 1; end if;
            else
              if det_rb /= 0 and det_rb(14) = '0' then det_sel <= '1'; end if;
              det_rb <= (others => '0');
            end if;
          end if;
        end if;
      end if;
    end process;
    dp_vdata <= in_vd(7) & in_vd(5) & in_vd(6) & in_vd(4 downto 0) when det_sel = '1' else in_vd;
    dp_csel  <= in_cs;

    -- debug read-out (active only while the flash is deselected)
    Flash_SCK  <= f_sck  when f_sel = '0' else 'Z';
    Flash_COPI <= f_copi when f_sel = '0' else 'Z';
    Flash_CIPO <= (mosi_in xor (not dbg_locked)) when f_sel = '1' and dbg_alive = 0 else
                  dbg_miso                       when f_sel = '1' else 'Z';
    f_cipo  <= Flash_CIPO;
    sck_in  <= Flash_SCK;
    mosi_in <= Flash_COPI;

    process (pipe_clock)
    begin
      if rising_edge(pipe_clock) then
        if dbg_alive /= 15 then dbg_alive <= dbg_alive + 1; end if;
        dbg_a1 <= dbg_arm; dbg_a2 <= dbg_a1; dbg_a3 <= dbg_a2;
        dbg_ph <= video_hsync;
        if dbg_a3 /= dbg_a2 then
          dbg_cnt <= (others => (others => '0')); dbg_win <= (others => '0'); dbg_done <= '0';
        elsif dbg_done = '0' then
          dbg_win <= dbg_win + 1;
          if dbg_win = x"FFFFF" then dbg_done <= '1'; end if;
          if dac_clk_i = '0' then dbg_cnt(0) <= dbg_cnt(0) + 1; end if;
          if video_hsync = '0' and dbg_ph = '1' then dbg_cnt(1) <= dbg_cnt(1) + 1; end if;
        end if;
        dbg_s1 <= sck_in;  dbg_s2 <= dbg_s1; dbg_s3 <= dbg_s2;
        dbg_m1 <= mosi_in; dbg_m2 <= dbg_m1; dbg_m3 <= dbg_m2;
        if dbg_m2 = '1' and dbg_m3 = '0' then dbg_arm <= not dbg_arm; end if;
        if dbg_s2 = '1' and dbg_s3 = '0' then
          if dbg_m2 = '1' then dbg_ptr <= (others => '0'); else dbg_ptr <= dbg_ptr + 1; end if;
        end if;
        if dbg_s2 = '0' and dbg_s3 = '1' then
          case to_integer(dbg_ptr(7 downto 5)) is
            when 0      => dbg_word <= std_logic_vector(resize(dbg_cnt(0), 32));
            when 1      => dbg_word <= std_logic_vector(resize(dbg_cnt(1), 32));
            when 2      => dbg_word <= x"0000A5" & "0000" & det_sel & dbg_locked & dbg_done & '1';
            when others => dbg_word <= (others => '0');
          end case;
          dbg_bsel <= dbg_ptr(4 downto 0);
        end if;
        dbg_miso <= dbg_word(to_integer(dbg_bsel));
      end if;
    end process;
  end generate;

  not_main: if Module /= "main" generate
    dp_vdata   <= VData;
    dp_csel    <= CSel;
    Flash_SCK  <= f_sck;
    Flash_COPI <= f_copi;
    Flash_CIPO <= 'Z';
    f_cipo     <= Flash_CIPO;
  end generate;

end Behavioral;"""
patch("toplevel_gcdual.vhd", [
 ("    Flash_COPI : out std_logic;\n    Flash_CIPO : in  std_logic;\n    Flash_SCK  : out std_logic;\n",
  "    Flash_COPI : inout std_logic;\n    Flash_CIPO : inout std_logic;\n    Flash_SCK  : inout std_logic;\n"),
 ("    -- audio out\n    SPDIF_Out  : out std_logic;\n\n", ""),
 ("    ForceYPbPr : in    std_logic\n  );",
  "    ForceYPbPr : in    std_logic;\n\n    -- Carby: DAC power-save control (high = DAC on)\n    DAC_PSave  : out   std_logic\n  );"),
 ("begin\n\n  swap_red", DECL + "\n  swap_red"),
 ("    VData       => VData,\n    CSel        => CSel,\n", "    VData       => dp_vdata,\n    CSel        => dp_csel,\n"),
 ("    Flash_COPI  => Flash_COPI,\n    Flash_CIPO  => Flash_CIPO,\n    Flash_SCK   => Flash_SCK,\n    Flash_SEL   => Flash_SEL,\n",
  "    Flash_COPI  => f_copi,\n    Flash_CIPO  => f_cipo,\n    Flash_SCK   => f_sck,\n    Flash_SEL   => f_sel,\n"),
 ("    SPDIF_Out   => SPDIF_Out,", "    SPDIF_Out   => open,"),
 ("    DAC_Clock   => DAC_Clock,\n", "    DAC_Clock   => dac_clk_i,\n"),
 ("    ForceYPbPr  => ForceYPbPr,\n", "    ForceYPbPr  => ForceYPbPr,\n    DbgLocked   => dbg_locked,\n"),
 ("  CableDetect <= '1';", "  CableDetect <= '1';\n  DAC_PSave   <= '1';"),
 # composite sync on every candidate sync pin (the DAC SYNC input is wired to one of them)
 ("    CSync_out   => CSync_out,", "    CSync_out   => csync_i,"),
 ("  VSync_out <= video_vsync;\n  HSync_out <= video_hsync;", "  CSync_out <= csync_i;\n  VSync_out <= csync_i;\n  HSync_out <= csync_i;"),
 ("  LED <= heartbeat_vsync;", "  LED <= csync_i;"),
 ("\nend Behavioral;", BODY),
])
print("ok  VHDL " + ("already has the Carby changes" if VHDL_DONE else "prepared") +
      " (DAC_PSave, VSync/field auto-detect, composite sync on spare outputs, debug read-out)")

# ---- 4. build -----------------------------------------------------------------------
hd = os.path.join(H, "HDL/gcvideo_dvi")
shutil.rmtree(os.path.join(hd, "build"), ignore_errors=True)
print("building (10-30 minutes)... log: ~/build.log")
with open(os.path.expanduser("~/build.log"), "w") as log:
    rc = subprocess.call(["make", "TARGET=dual-gc", "VERSION=3.1-crt"], cwd=hd, stdout=log, stderr=subprocess.STDOUT)
if not os.path.exists(OUT):
    sys.exit("BUILD FAILED - run:  grep -B2 -A8 ERROR ~/build.log | head -40")
b = open(OUT, "rb").read()
print("BUILD OK:", OUT)
print("SHA-256:", hashlib.sha256(b).hexdigest())
