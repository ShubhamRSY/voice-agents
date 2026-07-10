#!/usr/bin/env python3
"""Build a 4-slide LinkedIn deck from Chat / Copilot / Voice / Integrations screenshots.

Run capture first:
  python scripts/capture_mode_screenshots.py

Then:
  python scripts/build_linkedin_ppt.py

Output: exports/Nexus_LinkedIn_Launch.pptx
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "exports" / "screenshots"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "Nexus_LinkedIn_Launch.pptx"

SLIDES = [
    ("01-chat.png", "Chat"),
    ("02-copilot.png", "Copilot"),
    ("03-voice.png", "Voice"),
    ("04-integrations.png", "62 Integrations"),
]


def main() -> None:
    from pptx import Presentation
    from pptx.util import Inches

    missing = [name for name, _ in SLIDES if not (SHOTS / name).exists()]
    if missing:
        raise SystemExit(
            f"Missing screenshots: {missing}\n"
            "Run: python scripts/capture_mode_screenshots.py"
        )

    prs = Presentation()
    # 16:9 widescreen
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "Nexus — Chat · Copilot · Voice · Integrations"

    slide_w = prs.slide_width
    slide_h = prs.slide_height

    for filename, label in SLIDES:
        img_path = SHOTS / filename
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        from PIL import Image as PILImage

        with PILImage.open(img_path) as img:
            img_w, img_h = img.size

        aspect = img_w / img_h
        slide_aspect = slide_w / slide_h

        if aspect > slide_aspect:
            pic_w = slide_w
            pic_h = int(slide_w / aspect)
        else:
            pic_h = slide_h
            pic_w = int(slide_h * aspect)

        left = int((slide_w - pic_w) / 2)
        top = int((slide_h - pic_h) / 2)
        slide.shapes.add_picture(str(img_path), left, top, width=pic_w, height=pic_h)

    EXPORTS.mkdir(exist_ok=True)
    prs.save(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
