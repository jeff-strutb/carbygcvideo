# Building from source

This folder has everything needed to rebuild `firmware/gcvideo/carby_gcvideo31_final.bin` on Linux.

| Path | What it is |
| --- | --- |
| `gcvideo/` | GCVideo-DVI 3.1 (tag `GCVideo-DVI_release_3.1`) with the Carby changes already applied |
| `carby_pins_final.ucf` | The final FPGA pin file. The same file is `gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf`. |
| `build/` | `carby_build.py` and the pin-patch helpers |
| `flasher/` | FT232H flashing and readback tools (see the flashing guide) |
| `diagnostics/` | The board-mapping test firmwares, kept for reference |

## Toolchain

- Xilinx ISE 14.7 for Linux. The free WebPACK license is enough for the XC3S200A.
- A ZPU GCC toolchain (`zpu-elf-gcc`), for the soft processor firmware that runs inside the FPGA. Upstream's [Firmware/README.md](gcvideo/Firmware/README.md) explains where it comes from.
- GNU make, Perl, and Python 3.

Before building, in the same shell:

```bash
source /opt/Xilinx/14.7/ISE_DS/settings64.sh
export PATH=~/zpu/bin:$PATH
```

(Use the path where your ZPU toolchain's `bin` folder actually is.)

## Build

From the repository root:

```bash
python3 src/build/carby_build.py src/gcvideo
```

The argument is the GCVideo tree to build. It defaults to `~/gcvideo`.

What the script does, in order:

1. Checks that `xst` (ISE) and `zpu-elf-gcc` are on `PATH`, and stops if not.
2. Checks that the Carby pin map is in `constraints-dualgc.ucf` (it looks for the CSel and VData[0] lines). If the file has no `DAC_PSave` line, it adds one on P30.
3. Sets the firmware defaults in `Firmware/settings-main.c` (line doubler off), disables the IR button check in `Firmware/flasher.c`, and changes the About screen name in `Firmware/screen_about.c`. These edits are skipped silently if already made.
4. Applies the VHDL changes to `toplevel_gcdual.vhd`, `datapipe.vhd`, and `component_defs.vhd`. If the tree already has them (as `src/gcvideo` does), this step leaves the files alone. Otherwise it resets those three files with `git checkout` and patches them, so it needs a git checkout of upstream GCVideo in that case.
5. Deletes `HDL/gcvideo_dvi/build/` and runs `make TARGET=dual-gc VERSION=3.1-crt` in `HDL/gcvideo_dvi`, logging to `~/build.log`. This takes 10 to 30 minutes.
6. Prints the path and SHA-256 of `HDL/gcvideo_dvi/build/gcvideo-dvi-dual-gc-3.1-crt-spirom-complete.bin`, or `BUILD FAILED` with a hint to search the log.

The output is a full GCVideo flash image. Flash it with `flasher/flashbin.py <image> main`, which writes only the main firmware at offset 0. Whether a rebuild is byte-identical to the released image has not been checked.

### Starting from a fresh upstream checkout

To apply the same changes to a clean copy of GCVideo 3.1 (or as a starting point for a later release):

```bash
git clone https://github.com/ikorb/gcvideo.git ~/gcvideo
git -C ~/gcvideo checkout GCVideo-DVI_release_3.1
cp src/carby_pins_final.ucf ~/gcvideo/HDL/gcvideo_dvi/src/constraints-dualgc.ucf
cp src/gcvideo/HDL/gcvideo_dvi/src/constraints-common.ucf ~/gcvideo/HDL/gcvideo_dvi/src/
cp src/gcvideo/HDL/gcvideo_dvi/src/constraints-audio.ucf ~/gcvideo/HDL/gcvideo_dvi/src/
cp src/gcvideo/HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut ~/gcvideo/HDL/gcvideo_dvi/scripts/
python3 src/build/carby_build.py ~/gcvideo
```

Done this way, the resulting tree matches `src/gcvideo` file for file (checked with `diff -r`, ignoring the updater binaries noted below).

## Changes from stock GCVideo-DVI 3.1 (dual-gc target)

- `HDL/gcvideo_dvi/src/constraints-dualgc.ucf` is replaced with the Carby pin map ([carby_pins_final.ucf](carby_pins_final.ucf)). Every assignment is listed in [docs/pinout.md](../docs/pinout.md).
- `HDL/gcvideo_dvi/scripts/bitgenconfig-GC.ut`: unused pins are pulled up instead of down. This holds the DAC's BLANK input high, since the FPGA does not drive it.
- Top-level VHDL (`HDL/gcvideo_dvi/src/toplevel_gcdual.vhd`):
  - an extra constant-high output port, `DAC_PSave`, parked on spare pin P30;
  - automatic detection of which of P61 or P62 carries the vertical sync field signal, with the two swapped to match;
  - composite sync routed to the spare sync and LED outputs (`CSync_out`, `HSync_out`, `VSync_out`, `LED`);
  - a small debug counter block (DAC clock pulses, HSync pulses, clock-manager lock, which pin was picked for VSync), readable over the J1 header with [flasher/dbgread.py](flasher/dbgread.py) while the flash is deselected. For this, the three flash SPI pins became bidirectional ports;
  - the S/PDIF audio output port removed (see the next item).
- Not in the original change list, but present in the tree: the S/PDIF output is removed from `constraints-dualgc.ucf`, `constraints-common.ucf`, and `constraints-audio.ucf`. GCDual puts S/PDIF on P73, which is the console's CSel input on the Carby, and the cable has no digital audio output. These edits were made by `build/carby_pins.py`.
- `datapipe.vhd` and `component_defs.vhd`: one extra output port, `DbgLocked`, that passes the clock manager's lock signal to the debug block.
- Firmware defaults (`Firmware/settings-main.c`): line doubler off for 240p, 288p, 480i and 576i, for 15 kHz CRTs.
- Flasher stage (`Firmware/flasher.c`): the IR button check is disabled.
- About screen: the board name reads GCVideo 3.1 instead of GCVideo Dual v3.1 (`Firmware/screen_about.c`).
- Flash layout: the main firmware image is written at offset 0 (the `main` mode of `flasher/flashbin.py`), bypassing the recovery stage. This is a flashing choice, not a source change.
- Not included: upstream's prebuilt console updater files (`Updater/obj-gc/gcvupdater.dol` and `Updater/obj-wii/gcvupdater.dol`) are not in this tree. See the caution below.

## Important caution

This build keeps GCVideo's GCDual hardware ID (`GCDU`). **Do not run GCVideo's official console updater on a Carby Component with this firmware.** It could install the stock GCDual image, which has the wrong pin map and gives a black screen. Recovery from that is a reflash over J1.

A future build should set its own hardware ID, as upstream GCVideo recommends for new boards (see "Note about modifications" in [gcvideo/HDL/gcvideo_dvi/README.md](gcvideo/HDL/gcvideo_dvi/README.md)).

## Pin-patch helpers

These are the steps that produced the final pin file, run in this order against `~/gcvideo`. [carby_pins_final.ucf](carby_pins_final.ucf) supersedes them; they are kept to show how the map was reached.

- `build/carby_pins.py`: sets the console input pins (video data, CSel, clock, audio) found by live capture, and removes the S/PDIF output.
- `build/carby_dacmap.py`: sets the DAC color, clock, and sync pins found from the TV photos.
- `build/carby_pbfix.py`: moves Pb bits 0 to 3 to P13, P12, P10, P9 and parks the spare sync and LED outputs on P3 to P6.
- `build/carby_irpins.py`: puts the IR receiver and IR button on the pins found by `diag8.py` (run as `carby_irpins.py 82 21`), and holds PadData low.
- `build/carby_lowbits.py`: rearranges the five low-bit pins into the final order (brightness bits 0 to 2 on P33, P34, P35; red-difference bits 0 and 1 on P50, P49).

The final pin file supersedes all of these helpers.

## Flasher tools

All use [pyftdi](https://github.com/eblot/pyftdi) and an FT232H wired as in the flashing guide.

- `flasher/dump.py [OUTPUT]`: reads the whole flash twice, checks both reads match, and saves it (default `carby_backup.bin`).
- `flasher/flashbin.py IMAGE [main|full]`: writes a GCVideo dual-gc image. `main` (the default) writes only the main firmware at offset 0.
- `flasher/restore.py [IMAGE]`: writes the original firmware back (default `carby_backup.bin`). It only accepts the original image documented in `firmware/original`.
- `flasher/dbgread.py`: reads the debug counters of a running build over J1, with the AD4 wire unplugged.

## License

GCVideo is by Ingo Korb and is distributed under the license in [LICENSE](../LICENSE). All original source headers in `gcvideo/` are unchanged. Some files carry their own notices (for example the Exomizer decruncher and Mike Field's DVI encoder); those are kept as they are.
