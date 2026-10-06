import sys, time, hashlib
from pyftdi.spi import SpiController
img = open(sys.argv[1] if len(sys.argv) > 1 else 'carby_backup.bin','rb').read()
if hashlib.sha256(img).hexdigest() != 'd7e25e1af843aa424e5c740e0e00690f0429120f4630d0e75bdc3935e503f607':
    sys.exit("Image file hash mismatch. Nothing written.")
spi = SpiController(cs_count=1); spi.configure('ftdi://ftdi:232h/1')
g = spi.get_gpio(); g.set_direction(0x10, 0x10); g.write(0)
p = spi.get_port(cs=0, freq=1e6, mode=0)
input("Hold the AD4 wire on pin 100 and keep holding until DONE. Press Enter...")
if bytes(p.exchange([0x9F], 3)) != b'\xc2\x20\x13':
    sys.exit("Flash ID wrong or missing. Nothing written.")
def wait():
    while p.exchange([0x05], 1)[0] & 1: time.sleep(0.01)
p.exchange([0x06]); p.exchange([0x01, 0x00]); wait()
print("Erasing..."); p.exchange([0x06]); p.exchange([0xC7]); wait()
print("Writing...")
for a in range(0, len(img), 256):
    p.exchange([0x06])
    p.exchange(bytes([0x02, a>>16 & 255, a>>8 & 255, a & 255]) + img[a:a+256]); wait()
    if a % 0x10000 == 0: print(f"  {a*100//len(img)}%")
print("Verifying...")
rd = bytearray()
for a in range(0, len(img), 4096):
    rd += p.exchange([0x03, a>>16 & 255, a>>8 & 255, a & 255], min(4096, len(img)-a))
spi.terminate()
if bytes(rd) != img: sys.exit("VERIFY FAILED. Don't power-cycle; rerun the script.")
print("DONE - verified OK. You can let go.")
