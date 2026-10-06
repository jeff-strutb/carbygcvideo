# Flashing guide source

The PDF in `docs/` is built from these files:

- `guide.html` and `guide.css`: the guide's text and layout.
- `annotate.py`: draws the arrows and labels on the board photos. It reads the originals in `docs/images/` and writes the `*-annotated.jpg` copies next to them.
- `build_guide.py`: renders the PDF with WeasyPrint and sets its metadata (author from `git config user.name`).

To rebuild:

```bash
python3 -m venv ~/guide-venv
~/guide-venv/bin/pip install -r requirements.txt
~/guide-venv/bin/python annotate.py
~/guide-venv/bin/python build_guide.py
```

WeasyPrint needs the Pango library installed (for example `apt install libpango-1.0-0` on Debian or Ubuntu, `brew install pango` on macOS).
