#!/usr/bin/env python3
"""Build docs/carby-component-gcvideo-3.1-flashing-guide.pdf.

    pip install -r requirements.txt
    python3 annotate.py        # only needed if the photos or callouts change
    python3 build_guide.py

The PDF is rendered from guide.html and guide.css with WeasyPrint. The author
field is taken from `git config user.name`; the creator and producer fields
are left neutral.
"""
import io
import os
import subprocess

from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "carby-component-gcvideo-3.1-flashing-guide.pdf"))
TITLE = "Carby Component: GCVideo 3.1 Flashing Guide"


def git_user_name():
    try:
        return subprocess.check_output(["git", "config", "user.name"], cwd=HERE, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main():
    pdf = HTML(filename=os.path.join(HERE, "guide.html")).write_pdf()

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter(clone_from=reader)
    writer.metadata = None
    meta = {"/Title": TITLE, "/Subject": "Backing up and flashing the Carby Component cable",
            "/Creator": "", "/Producer": ""}
    author = git_user_name()
    if author:
        meta["/Author"] = author
    writer.add_metadata(meta)
    with open(OUT, "wb") as f:
        writer.write(f)
    print(f"wrote {os.path.relpath(OUT)} ({len(reader.pages)} pages)")


if __name__ == "__main__":
    main()
