# Original firmware backup

`carby_backup.bin` is the firmware the Carby Component cable shipped with: a full dump of the 512 KB SPI flash (MX25L4005), read twice over J1 and checked to match.

A modified GCVideo-DVI 2.4d build by Insurrection Industries, distributed under GCVideo's license (the BSD-style license in [LICENSE](../../LICENSE)). The vendor did not publish the modified source.

GC-Forever's Game Boy Interface wiki lists this firmware as "Insurrection Industries CARBY v2.4d-2".

| File | Size | SHA-256 |
| --- | --- | --- |
| carby_backup.bin | 524,288 bytes | `d7e25e1af843aa424e5c740e0e00690f0429120f4630d0e75bdc3935e503f607` |

Check it:

```bash
sha256sum -c SHA256SUMS
```

## Your own backup

Back up your own cable before flashing anything (step 1 of the [flashing guide](../../docs/carby-component-gcvideo-3.1-flashing-guide.pdf)). If your dump's SHA-256 matches the one above, your cable has the same firmware as the one documented here. Keep your own dump either way.

## Restoring it

Wire the FT232H as described in the flashing guide, then run from the repository root:

```bash
python3 src/flasher/restore.py firmware/original/carby_backup.bin
```

When asked, hold the AD4 wire on FPGA pin 100 and press Enter. Keep holding until the script prints `DONE - verified OK. You can let go.` Then disconnect the FT232H and power-cycle the console.

`restore.py` only writes an image whose SHA-256 matches the value above. It refuses any other file with `Image file hash mismatch. Nothing written.`
