#!/usr/bin/env python3
"""
flashfull.py - write a complete two-stage GCVideo image (flasher + main) to the Carby's SPI flash.

  sudo ~/ftdi/bin/python ~/flashfull.py <image.bin>        (AD4 jumper held on pin 100, GameCube on)

Checks that the file is a complete image (flasher tag at 0x2FFE8, main firmware at 0x30000) and shows
its hardware ID and version before writing. Erases the whole chip, writes, and verifies every byte.
"""
import os, sys, time

def check(img):
    if len(img) < 0x30040 or len(img) > 0x80000: sys.exit(f"{len(img)} bytes: not a complete Carby image. Nothing written.")
    tag = img[0x2FFE8:0x30000]
    if tag[8:20] != b"GCVUpdater10": sys.exit("No flasher tag at 0x2FFE8: this is not a complete two-stage image. Nothing written.")
    ver = tag[:8].rstrip(b"\0").decode(errors="replace"); hw = tag[20:24].decode(errors="replace")
    main_hw = img[0x30000:0x30004].decode(errors="replace")
    if main_hw != hw: sys.exit(f"Flasher ID {hw} and main firmware ID {main_hw} differ. Nothing written.")
    print(f"Complete image: version {ver}, hardware ID {hw}, {len(img)} bytes")
    if hw != "CBCG" and "--any-id" not in sys.argv:
        sys.exit(f"Hardware ID is {hw}, not CBCG: this was not built with the current carby_build.py. Nothing written.")

def flash(img):
    from pyftdi.spi import SpiController
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


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1: sys.exit(__doc__)
    img = open(args[0], "rb").read()
    check(img)
    flash(img)
