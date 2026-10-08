# GCVideo 3.1 for the Carby Component

`carby_gcvideo31_full.bin` is GCVideo-DVI 3.1 built for the Carby Component cable (board "GCAnalog 1.9") from the source in [src/](../../src/). Its version string is `3.1-crt`: the line doubler is off by default, for standard-definition CRTs.

| File | Size | SHA-256 |
| --- | --- | --- |
| carby_gcvideo31_full.bin | 346,144 bytes | `427238cb5e05a72854eb1091bcff001c50b1ae15868636f57319a88949d5c296` |

Check it:

```bash
sha256sum -c SHA256SUMS
```

## What is in the file

The file is a full image (update tool at offset 0, main firmware at 0x30000) flashed with `flashfull.py`. It is GCVideo's standard two-stage layout for the dual-gc target (`gcvideo-dvi-dual-gc-3.1-crt-spirom-complete.bin`), with the hardware ID `CBCG` (Carby Component). See [docs/technical-notes.md](../../docs/technical-notes.md), note 4.

## Flashing it

Follow the [flashing guide](../../docs/carby-component-gcvideo-3.1-flashing-guide.pdf). Back up your firmware first. In short, from the repository root:

```bash
python3 src/flasher/flashfull.py firmware/gcvideo/carby_gcvideo31_full.bin
```

Settings reset to defaults the first time this image starts.

`flashfull.py` checks the file before writing (size, update-tool tag, hardware ID CBCG), then erases, writes, and verifies. Hold the AD4 wire on FPGA pin 100 when asked, press Enter, and keep holding until the script prints `DONE - verified OK`.
