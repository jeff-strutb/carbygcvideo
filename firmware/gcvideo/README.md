# GCVideo 3.1 for the Carby Component

`carby_gcvideo31_final.bin` is GCVideo-DVI 3.1 built for the Carby Component cable (board "GCAnalog 1.9") from the source in [src/](../../src/). Its version string is `3.1-crt`: the line doubler is off by default, for standard-definition CRTs.

| File | Size | SHA-256 |
| --- | --- | --- |
| carby_gcvideo31_final.bin | 346,144 bytes | `3a5d8b1573c84af365d97d76d226bfda484467a9a1db87d3a9d4e0f0fe4ec474` |

Check it:

```bash
sha256sum -c SHA256SUMS
```

## What is in the file

This is the full GCVideo flash image for the dual-gc target (`gcvideo-dvi-dual-gc-3.1-crt-spirom-complete.bin`): a recovery stage at the start, and the main firmware stored at offset `0x30000` behind a `GCDU` tag. On this board only the main firmware is used. `flashbin.py` in `main` mode takes it out of the image and writes it at offset 0, where the FPGA loads it directly at power-on. See [docs/technical-notes.md](../../docs/technical-notes.md), note 4.

## Flashing it

Follow the [flashing guide](../../docs/carby-component-gcvideo-3.1-flashing-guide.pdf). Back up your firmware first. In short, from the repository root:

```bash
python3 src/flasher/flashbin.py firmware/gcvideo/carby_gcvideo31_final.bin main
```

Hold the AD4 wire on FPGA pin 100 when asked, press Enter, and keep holding until the script prints `DONE - verified OK`.

## Caution

This build keeps GCDual's hardware ID (`GCDU`). Do not run GCVideo's official console updater on a Carby Component with this firmware: it could install the stock GCDual image, which has the wrong pin map and gives a black screen. Recovery from that is a reflash over J1.
