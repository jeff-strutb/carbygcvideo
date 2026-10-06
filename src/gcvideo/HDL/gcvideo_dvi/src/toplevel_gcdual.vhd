----------------------------------------------------------------------------------
-- GCVideo DVI HDL
-- Copyright (C) 2014-2021, Ingo Korb <ingo@akana.de>
-- All rights reserved.
--
-- Redistribution and use in source and binary forms, with or without
-- modification, are permitted provided that the following conditions are met:
--
-- 1. Redistributions of source code must retain the above copyright notice,
--    this list of conditions and the following disclaimer.
-- 2. Redistributions in binary form must reproduce the above copyright notice,
--    this list of conditions and the following disclaimer in the documentation
--    and/or other materials provided with the distribution.
--
-- THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
-- AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
-- IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
-- ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
-- LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
-- CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
-- SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
-- INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
-- CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
-- ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
-- THE POSSIBILITY OF SUCH DAMAGE.
--
-- toplevel_gcdual.vhd: top level module for the GCDual board
--
----------------------------------------------------------------------------------

library IEEE;

use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;
library UNISIM;
use UNISIM.VComponents.all;

use work.Component_Defs.all;
use work.video_defs.all;

entity toplevel_gcdual is
  generic (
    TargetConsole: string; -- "GC"
    SwapRed      : string := "NO";
    SwapGreen    : string := "NO";
    SwapBlue     : string := "NO";
    Firmware     : string;
    Module       : string
  );
  port (
    -- clocks
    VClockN    : in  std_logic;

    -- gamecube video signals
    VData      : in  std_logic_vector(7 downto 0);
    CSel       : in  std_logic; -- usually named ClkSel, but it's really a color select
    CableDetect: out std_logic;

    -- console audio signals
    I2S_BClock : in  std_logic;
    I2S_LRClock: in  std_logic;
    I2S_Data   : in  std_logic;

    -- gamecube controller
    PadData    : in  std_logic;

    -- IR receiver
    IRReceiver : in  std_logic;
    IRButton   : in  std_logic;

    -- flash chip
    Flash_COPI : inout std_logic;
    Flash_CIPO : inout std_logic;
    Flash_SCK  : inout std_logic;
    Flash_SEL  : out std_logic;

    -- board-internal
    LED        : out std_logic;

    -- digital video out
    DVI_Clock  : out   std_logic_vector(1 downto 0);
    DVI_Red    : out   std_logic_vector(1 downto 0);
    DVI_Green  : out   std_logic_vector(1 downto 0);
    DVI_Blue   : out   std_logic_vector(1 downto 0);

    -- analog video out
    DAC_Red    : out   std_logic_vector(7 downto 0);
    DAC_Green  : out   std_logic_vector(7 downto 0);
    DAC_Blue   : out   std_logic_vector(7 downto 0);
    DAC_SyncN  : out   std_logic;
    DAC_Clock  : out   std_logic;
    CSync_out  : out   std_logic;
    VSync_out  : out   std_logic;
    HSync_out  : out   std_logic;

    -- analog mode fallback select
    ForceYPbPr : in    std_logic;

    -- Carby: DAC power-save control (high = DAC on)
    DAC_PSave  : out   std_logic
  );
end toplevel_gcdual;

architecture Behavioral of toplevel_gcdual is
  signal pipe_clock     : std_logic;
  signal video_hsync    : std_logic;
  signal video_vsync    : std_logic;
  signal heartbeat_vsync: std_logic;
  signal cable_detect   : std_logic;
  signal swap_red       : Pair_Swap_t;
  signal swap_green     : Pair_Swap_t;
  signal swap_blue      : Pair_Swap_t;
  signal dac_rgbmode    : boolean;
  signal out_red        : std_logic_vector(7 downto 0);
  signal out_green      : std_logic_vector(7 downto 0);
  signal out_blue       : std_logic_vector(7 downto 0);

  -- Carby
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

  swap_red   <= Pair_Regular when SwapRed   = "NO" else Pair_Swapped;
  swap_green <= Pair_Regular when SwapGreen = "NO" else Pair_Swapped;
  swap_blue  <= Pair_Regular when SwapBlue  = "NO" else Pair_Swapped;

  -- data pipe
  Inst_Datapipe: Datapipe generic map (
    TargetConsole => TargetConsole,
    Firmware      => Firmware,
    Module        => Module
  ) port map (
    VClockN     => VClockN,
    VData       => dp_vdata,
    CSel        => dp_csel,
    CableDetect => cable_detect,
    I2S_BClock  => I2S_BClock,
    I2S_LRClock => I2S_LRClock,
    I2S_Data    => I2S_Data,
    PadData     => PadData,
    IRReceiver  => IRReceiver,
    IRButton    => IRButton,
    Flash_COPI  => f_copi,
    Flash_CIPO  => f_cipo,
    Flash_SCK   => f_sck,
    Flash_SEL   => f_sel,
    PipeClock   => pipe_clock,
    DAC_RGBMode => dac_rgbmode,
    SPDIF_Out   => open,
    DAC_Red     => DAC_Red,
    DAC_Green   => DAC_Green,
    DAC_Blue    => DAC_Blue,
    DAC_SyncN   => DAC_SyncN,
    DAC_Clock   => dac_clk_i,
    CSync_out   => csync_i,
    VSync_out   => video_vsync,
    HSync_out   => video_hsync,
    ForceYPbPr  => ForceYPbPr,
    DbgLocked   => dbg_locked,
    Pair_Red    => swap_red,
    Pair_Green  => swap_green,
    Pair_Blue   => swap_blue,
    DVI_Clock   => DVI_Clock,
    DVI_Red     => DVI_Red,
    DVI_Green   => DVI_Green,
    DVI_Blue    => DVI_Blue
  );
  CSync_out <= csync_i;
  VSync_out <= csync_i;
  HSync_out <= csync_i;

  -- GCDual cable detect is actually INIT_B, keep high
  CableDetect <= '1';
  DAC_PSave   <= '1';

  -- heartbeat on LED
  Inst_Heartbeat: LED_Heartbeat port map (
    Clock           => pipe_clock,
    VSync           => video_vsync,
    HeartbeatVSync2 => heartbeat_vsync
  );

  LED <= csync_i;

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

end Behavioral;
