# FPGA pin map

Every signal GCVideo uses, and the FPGA pin it sits on in the Carby Component (board "GCAnalog 1.9", FPGA XC3S200A-4VQG100C).

"How established" means:

- **Measured**: found with a live diagnostic capture on the board, or with a multimeter.
- **Photo**: found by TV photo calibration (a test pattern that flips one FPGA line per box, photographed on the TV).
- **Ramp**: verified with the 240p Test Suite color ramps.
- **Meter**: found with the diag9 signature test, a multimeter reading on each DAC pin (see [technical-notes.md](technical-notes.md)).

Bits are listed from bit 0 (least significant) to bit 7 (most significant). In GCVideo's source, Y is driven on the DAC's green input, Pr on red, and Pb on blue.

| Signal | FPGA pin(s) | How established |
| --- | --- | --- |
| Console 54 MHz clock (VClockN) | P90 | Measured |
| Color select (CSel) | P73 | Measured |
| Video data VData 0 to 7 | P72, P68, P71, P65, P64, P61, P62, P60 | Measured |
| Audio I2S data, LR clock, bit clock | P56, P59, P57 | Measured |
| DAC clock | P70 | Measured |
| DAC SYNC | P15 | Measured |
| DAC BLANK | not FPGA-driven; held high by the FPGA's unused-pin pull-ups | Measured |
| Y, DAC green input, bits 0 to 7 | P33, P34, P35, P32, P28, P20, P19, P16 | Bits 0 to 2 Meter; bits 3 to 7 Photo |
| Pr, DAC red input, bits 0 to 7 | P50, P49, P44, P43, P41, P40, P37, P36 | Bits 0 and 1 Meter; bits 2 to 7 Photo |
| Pb, DAC blue input, bits 0 to 7 | P13, P12, P10, P9, P99, P98, P94, P93 | Bits 0 to 3 Ramp; bits 4 to 7 Photo |
| IR receiver (U7) | P82 | Measured |
| IR button (BU1), active low | P21 | Measured |
| Controller data (PadData) | none on this cable; P7 assigned and pulled down | Tested |
| Cable detect | P48 | Upstream default |
| Spare GCVideo outputs (CSync, HSync, VSync, LED) | P3, P4, P5, P6 | Parked |
| Spare constant-high output (DAC_PSave port) | P30 | Parked |
| SPI flash MOSI, CLK, MISO, CS | P46, P53, P51, P27 | Board labels |
| PROG_B | P100 | Datasheet |

Every connection between the FPGA and the DAC has now been measured.

The final pin file is [src/carby_pins_final.ucf](../src/carby_pins_final.ucf).

Notes:

- VData 5 and 6 (P61 and P62): the firmware checks at run time which of the two carries the vertical sync field flag and swaps them if needed. See [technical-notes.md](technical-notes.md).
- "Parked" means GCVideo still drives the signal, but this board has no use for it, so it was moved to a spare pin. The sync and LED outputs were first placed on P9, P10, P12 and P13, and were moved to P3 to P6 when P9, P10, P12 and P13 turned out to be Pb bits 0 to 3.
- The pin file also assigns the digital (DVI) output pins and the analog-mode input (ForceYPbPr, P39) from upstream GCDual. This board has no DVI output, and those assignments were left as upstream had them.
