"""Offline smoke test using SYNTHETIC data. Renders a short video into a temp folder
and deletes it afterwards (no sample MP4 is kept).

Run from the project root:   python tests/smoke_test.py
Optional:                    python tests/smoke_test.py --all   (every style x aspect)
"""
import itertools
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from services.script_generator import template_script  # noqa: E402
from services.video_generator import STYLES, generate_video  # noqa: E402
from config import Config  # noqa: E402

SYNTHETIC_PROPERTY = {
    "name": "Azure Heights Residency", "location": "Lakeview Road, Sample City", "price": "$385,000",
    "property_type": "Apartment", "bedrooms": 3, "bathrooms": 2, "area": "1,850",
    "features": ["Covered parking", "Rooftop garden", "24/7 security", "Fitness studio"],
    "contact": "Sample Realty Team\n+00 000 000 0000\nhello@example.com", "cta": "Book a private viewing",
}


def synthetic_images(folder: Path, n: int = 5) -> list[Path]:
    """Gradient images with simple shapes - purely synthetic placeholders."""
    paths = []
    sizes = [(1600, 1067), (1200, 1600), (1600, 900), (1400, 1400), (1800, 1200)]
    for i in range(n):
        w, h = sizes[i % len(sizes)]
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):
            for x in range(0, w):
                px[x, y] = (40 + 30 * i + y * 60 // h, 90 + x * 80 // w, 150 - 10 * i + y * 40 // h)
        d = ImageDraw.Draw(img)
        d.rectangle((w * .2, h * .35, w * .8, h * .85), fill=(235, 228, 214))
        d.polygon([(w * .15, h * .35), (w * .5, h * .12), (w * .85, h * .35)], fill=(120, 60, 50))
        d.rectangle((w * .45, h * .6, w * .55, h * .85), fill=(70, 50, 40))
        p = folder / f"synthetic_{i}.jpg"
        img.save(p, quality=90)
        paths.append(p)
    return paths


def main() -> None:
    combos = list(itertools.product(STYLES, Config.ASPECT_RATIOS)) if "--all" in sys.argv else [("modern_luxury", "16:9")]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        imgs = synthetic_images(tmp)
        script = template_script(SYNTHETIC_PROPERTY, len(imgs))
        for style, aspect in combos:
            out = tmp / f"test_{style}_{aspect.replace(':', 'x')}.mp4"
            generate_video(imgs, SYNTHETIC_PROPERTY, script, style, aspect, out, fps=8)
            print(f"OK  {style:22s} {aspect:5s} -> {out.stat().st_size / 1024:.0f} KB")
    print("Smoke test passed (temporary files deleted).")


if __name__ == "__main__":
    main()
