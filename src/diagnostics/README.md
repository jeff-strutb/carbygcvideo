# Diagnostics

These are the test firmwares used to map the Carby Component board. **They are reference tools and are not needed to flash GCVideo.** Each one builds a small FPGA design with ISE, flashes it over J1, and then reads results back or shows them on the TV. Flashing one replaces the cable's firmware until you flash GCVideo or the original backup again.

Each script takes a command as its first argument (`build`, `flash`, and a read or survey command); the usage lines at the top of each file show the exact form. They expect ISE on `PATH` for `build`, and the GCVideo tree at `~/gcvideo` (they borrow its bitgen settings).

**diag4.py** gives every candidate FPGA output pin a unique PWM signature: pin number k is high for k+1 out of every 40 clock cycles, so it settles at its own average voltage. Measuring the DC voltage on a DAC input pin with a multimeter, then running `diag4.py which <volts>`, names the FPGA pin wired to it. This is how the DAC clock (P70) and SYNC (P15) pins were found.

**diag7.py** is the photo calibration grid. It draws a 16 by 10 grid of boxes on the TV in 240p. Each box's left half shows a background color, and its right half shows the same background with one FPGA line flipped. The background is set over the FT232H between photos (`diag7.py base ...`), so every line can be seen against a useful background. The photos showed which color channel and bit each line drives.

**diag8.py** is an input activity monitor. Every FPGA pin becomes a pulled-up input, and the FPGA counts level changes on each. `diag8.py watch` asks you to press the board's button and use a remote at the cable, then names the pins that responded. This found the IR receiver (P82) and the button (P21).

**diag9.py** settles the lowest color bits. It drives P33, P34, P35, P49 and P50 at 10, 30, 50, 70 and 90 percent duty, so each settles at a widely spaced average voltage. Five meter readings on the DAC (`diag9.py read`) identify the exact wiring of the lowest bits, and the script can correct the pin file automatically.

**diag.py, diag2.py, diag3.py** are the earlier input-side tools: an internal logic analyzer that samples every candidate pin on the console clock (used for the video data, CSel, and audio pins), a check that runs GCVideo's own clock generator and video decoder on the measured pins, and blanking-flag statistics per data pin.
