import sys, hashlib
out_path = sys.argv[1] if len(sys.argv) > 1 else 'carby_backup.bin'
from pyftdi.spi import SpiController
spi = SpiController(cs_count=1)
spi.configure('ftdi://ftdi:232h/1')
gpio = spi.get_gpio()
gpio.set_direction(0x10, 0x10)
gpio.write(0x00)
port = spi.get_port(cs=0, freq=1e6, mode=0)
input("Hold the AD4 wire tip on pin 100 and keep it there. Press Enter...")
jid = port.exchange([0x9F], 3)
print("JEDEC ID:", jid.hex())
if not 0x10 <= jid[2] <= 0x19:
    sys.exit("Flash not responding correctly. Stop and open an issue with this output.")
size = 1 << jid[2]
print(f"Flash size: {size*8//1048576} Mbit")
def dump():
    out = bytearray()
    for a in range(0, size, 4096):
        out += port.exchange([0x03, (a>>16)&255, (a>>8)&255, a&255], 4096)
    return bytes(out)
d1 = dump(); d2 = dump()
spi.terminate()
if d1 != d2: sys.exit("The two reads differ. Not saved. Open an issue with this output.")
if d1.count(0xFF) == len(d1): sys.exit("Read was all blank. Not saved. Open an issue with this output.")
open(out_path, 'wb').write(d1)
print(f"Saved {out_path}  sha256:", hashlib.sha256(d1).hexdigest())
