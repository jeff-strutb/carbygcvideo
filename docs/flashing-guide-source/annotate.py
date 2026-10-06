#!/usr/bin/env python3
"""Draw callouts on the board photos.

Reads the original photos from docs/images/ and writes annotated copies next
to them (*-annotated.jpg). Coordinates are given on a reference size for each
photo and scaled to the real image, so the photos can be replaced with larger
or smaller copies of the same shot.

    python3 annotate.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.normpath(os.path.join(HERE, "..", "images"))

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

YELLOW = (255, 214, 0)
CYAN = (0, 220, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


class Canvas:
    """An image plus a scale factor from reference coordinates to real pixels."""

    def __init__(self, name, ref_width, out_width, crop=None, offset=(0, 0)):
        """crop is (left, top, right, bottom) in reference coordinates.

        offset is where the photo's top-left corner sits in reference
        coordinates, for photos that were already cropped from a larger shot.
        ref_width is then the photo's own width in reference units.
        """
        im = ImageOps.exif_transpose(Image.open(os.path.join(IMAGES, name))).convert("RGB")
        k = im.width / ref_width
        self.origin = offset
        if crop:
            im = im.crop(tuple(round((v - o) * k) for v, o in zip(crop, offset * 2)))
            self.origin = (crop[0], crop[1])
        if im.width > out_width:
            k *= out_width / im.width
            im = im.resize((out_width, round(im.height * out_width / im.width)), Image.LANCZOS)
        self.im = im
        self.k = k
        self.d = ImageDraw.Draw(im)
        self.unit = max(2, round(im.width / 400))   # line and text scale

    def p(self, xy):
        return ((xy[0] - self.origin[0]) * self.k, (xy[1] - self.origin[1]) * self.k)

    def arrow(self, start, end, color=YELLOW):
        (x0, y0), (x1, y1) = self.p(start), self.p(end)
        w = self.unit * 2
        ang = math.atan2(y1 - y0, x1 - x0)
        head = w * 4.5
        bx, by = x1 - head * math.cos(ang), y1 - head * math.sin(ang)
        pts = [(x1, y1),
               (bx + head * 0.55 * math.sin(ang), by - head * 0.55 * math.cos(ang)),
               (bx - head * 0.55 * math.sin(ang), by + head * 0.55 * math.cos(ang))]
        self.d.line([(x0, y0), (bx, by)], fill=BLACK, width=w + self.unit * 2)
        self.d.polygon(pts, fill=BLACK)
        self.d.line([(x0, y0), (bx, by)], fill=color, width=w)
        shrink = [(px + (sum(q[0] for q in pts) / 3 - px) * 0.25,
                   py + (sum(q[1] for q in pts) / 3 - py) * 0.25) for px, py in pts]
        self.d.polygon(shrink, fill=color)

    def label(self, at, text, number=None, color=YELLOW, size=1.0, anchor="mm"):
        """Draw a label box centred on `at` (reference coords). Returns the box."""
        f = font(round(self.unit * 9 * size))
        x, y = self.p(at)
        pad = self.unit * 3
        circle = 0
        if number is not None:
            circle = round(self.unit * 13 * size)
        tw = self.d.textlength(text, font=f)
        asc, desc = f.getmetrics()
        th = asc + desc
        w = tw + pad * 2 + (circle + pad if circle else 0)
        h = max(th, circle) + pad * 2
        if anchor == "mm":
            left, top = x - w / 2, y - h / 2
        elif anchor == "lm":
            left, top = x, y - h / 2
        else:  # "rm"
            left, top = x - w, y - h / 2
        self.d.rounded_rectangle([left - self.unit, top - self.unit, left + w + self.unit, top + h + self.unit],
                                 radius=pad * 2, fill=BLACK)
        self.d.rounded_rectangle([left, top, left + w, top + h], radius=pad * 2, fill=color)
        tx = left + pad
        if circle:
            cy = top + h / 2
            self.d.ellipse([tx, cy - circle / 2, tx + circle, cy + circle / 2], fill=BLACK)
            nf = font(round(circle * 0.62))
            self.d.text((tx + circle / 2, cy), str(number), font=nf, fill=color, anchor="mm")
            tx += circle + pad
        self.d.text((tx, top + h / 2), text, font=f, fill=BLACK, anchor="lm")
        return (left, top, left + w, top + h)

    def ring(self, at, r, color=YELLOW):
        x, y = self.p(at)
        r = r * self.k
        for width, col in ((self.unit * 3, BLACK), (self.unit * 2, color)):
            self.d.ellipse([x - r, y - r, x + r, y + r], outline=col, width=width)

    def callout(self, label_at, target, text, number=None, color=YELLOW, anchor="mm", size=1.0):
        self.arrow(label_at, target, color)
        self.label(label_at, text, number, color, size, anchor)

    def save(self, name):
        out = os.path.join(IMAGES, name)
        self.im.save(out, quality=88, optimize=True)
        print("wrote", os.path.relpath(out, os.path.join(HERE, "..", "..")))


def fpga_side():
    # Reference size 1290 x 900 (the photo's own size).
    c = Canvas("board-fpga-side.jpg", 1290, 1600)
    pads = {"+3.3V": 432, "GND": 480, "MOSI": 527, "CLK": 572, "MISO": 619, "CS": 665}
    y_pad = 662
    xs = [180, 330, 480, 630, 780, 930]
    for i, (name, x) in enumerate(pads.items()):
        c.ring((x, y_pad), 13)
        c.callout((xs[i], 810), (x, y_pad + 14), name, size=1.4)
    c.callout((250, 130), (460, 298), "Pin 1", 2, CYAN, size=1.4)
    c.ring((460, 298), 10, CYAN)
    c.callout((640, 60), (493, 262), "Pin 100 (PROG_B)", 3, YELLOW, size=1.4)
    c.ring((493, 266), 11)
    c.callout((1100, 150), (700, 300), "FPGA U1", 1, WHITE, size=1.4)
    c.save("board-fpga-side-annotated.jpg")


def dac_side():
    # Reference size 1400 x 1050 (the photo scaled down from 4032 x 3024).
    c = Canvas("board-dac-side.jpg", 1400, 2000)
    pads = {"+3.3V": 572, "GND": 625, "MOSI": 678, "CLK": 732, "MISO": 786, "CS": 842}
    xs = [430, 575, 720, 865, 1010, 1155]
    for i, (name, x) in enumerate(pads.items()):
        c.ring((x, 190), 14)
        c.callout((xs[i], 60), (x, 174), name, size=1.2)
    c.callout((1160, 470), (800, 470), "DAC U2", 1, WHITE, size=1.4)
    c.callout((1190, 330), (960, 280), "Flash U5", 2, WHITE, size=1.4)
    c.callout((1110, 920), (910, 700), "IR receiver U7", 3, WHITE, size=1.4)
    c.callout((180, 80), (345, 200), "Button BU1", 4, WHITE, size=1.4)
    c.save("board-dac-side-annotated.jpg")


def pin100_closeup():
    # Reference size 1200 x 1280 (the image's own size). The owner's marks are kept.
    c = Canvas("fpga-pin100-marked.png", 1200, 1200)
    c.callout((90, 640), (175, 512), "Pin 1", None, CYAN, size=1.0)
    c.save("fpga-pin100-annotated.jpg")


def wiring_carby():
    # Reference units: the uncropped shot scaled to 1050 x 1400. The photo in the
    # repository is the part from (235, 520) to (1050, 1180).
    c = Canvas("wiring-carby-j1-pins.jpg", 815, 1400, offset=(235, 520))
    names = ["+3.3V (unused)", "GND", "MOSI", "CLK", "MISO", "CS"]
    ys = [688, 750, 815, 882, 950, 1020]
    for name, y in zip(names, ys):
        c.callout((485, y), (530, y), name, anchor="rm", size=1.15)
    c.save("wiring-carby-j1-annotated.jpg")


def wiring_ft232h():
    # Reference units: the uncropped shot scaled to 1050 x 1400. The photo in the
    # repository is the part from (360, 330) to (1050, 1000).
    c = Canvas("wiring-ft232h-headers.jpg", 690, 1400, offset=(360, 330))
    pins = [("AD0 = CLK", (557, 518)), ("AD1 = MOSI", (568, 558)), ("AD2 = MISO", (580, 598)),
            ("AD3 = CS", (592, 640)), ("AD4 = pin 100", (605, 680))]
    for i, (text, (x, y)) in enumerate(pins):
        c.callout((720, 390 + i * 85), (x + 12, y - 4), text, anchor="lm", size=1.5)
    c.callout((740, 935), (665, 858), "GND", anchor="lm", size=1.5)
    c.save("wiring-ft232h-annotated.jpg")


if __name__ == "__main__":
    fpga_side()
    dac_side()
    pin100_closeup()
    wiring_carby()
    wiring_ft232h()
