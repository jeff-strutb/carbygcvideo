import sys, time, hashlib, struct
from pyftdi.spi import SpiController
path, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "main")
full = open(path,'rb').read()
if full[0x30000:0x30004] != b'GCDU': sys.exit("Not a GCDual image. Nothing written.")
print("Image SHA-256:", hashlib.sha256(full).hexdigest())
if mode == "main":
    n = struct.unpack('>I', full[0x30004:0x30008])[0]; img = full[0x30014:0x30014+n]
else:
    img = full
spi = SpiController(cs_count=1); spi.configure('ftdi://ftdi:232h/1')
g = spi.get_gpio(); g.set_direction(0x10,0x10); g.write(0)
p = spi.get_port(cs=0, freq=1e6, mode=0)
input(f"[{mode} layout] Hold the AD4 wire on pin 100 until DONE. Press Enter...")
jid = bytes(p.exchange([0x9F],3))
if jid != b'\xc2\x20\x13': spi.terminate(); sys.exit("Flash not responding (ID " + jid.hex() + "). Nothing written.")
def wait():
    while p.exchange([0x05],1)[0] & 1: time.sleep(0.01)
p.exchange([0x06]); p.exchange([0x01,0x00]); wait()
sr = p.exchange([0x05],1)[0]
if sr & 0x9c: spi.terminate(); sys.exit(f"Flash still write-protected (status 0x{sr:02x}). Nothing written.")
print("Erasing..."); p.exchange([0x06]); p.exchange([0xC7]); wait()
print("Writing...")
for o in range(0, len(img), 256):
    p.exchange([0x06]); p.exchange(bytes([0x02,o>>16&255,o>>8&255,o&255]) + img[o:o+256]); wait()
print("Verifying...")
rd = bytearray()
for o in range(0, len(img), 4096):
    rd += p.exchange([0x03,o>>16&255,o>>8&255,o&255], min(4096, len(img)-o))
spi.terminate()
sys.exit("DONE - verified OK" if bytes(rd) == img else "VERIFY FAILED - rerun")
