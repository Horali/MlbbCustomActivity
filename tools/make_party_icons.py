"""Draw the party badge icons party_1..party_5 (1024 px PNG) and a preview sheet.

Flat dark people on a transparent background, like Discord's own party icon.
Usage: python tools/make_party_icons.py [out_dir]   (default: assets/)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
SS = 4  # supersampling for smooth edges
FG = (30, 31, 34, 255)  # near black, like Discord's party icon

# (x, y, scale) per person, back row first. x, y = centre of the head, 0..1.
LAYOUTS = {
    1: [(0.50, 0.37, 1.00)],
    2: [(0.36, 0.41, 0.76), (0.64, 0.41, 0.76)],
    3: [(0.27, 0.41, 0.62), (0.73, 0.41, 0.62), (0.50, 0.45, 0.78)],
    4: [(0.20, 0.42, 0.52), (0.80, 0.42, 0.52), (0.38, 0.45, 0.64), (0.62, 0.45, 0.64)],
    5: [(0.17, 0.42, 0.46), (0.83, 0.42, 0.46), (0.32, 0.44, 0.56), (0.68, 0.44, 0.56),
        (0.50, 0.47, 0.68)],
}


def person(d: ImageDraw.ImageDraw, cx: float, cy: float, k: float, fill, grow: float = 0) -> None:
    """Head plus a half-ellipse for the shoulders."""
    s = SIZE * SS
    head_r = 0.11 * s * k + grow
    x, y = cx * s, cy * s
    d.ellipse([x - head_r, y - head_r, x + head_r, y + head_r], fill=fill)
    w = 0.21 * s * k + grow
    top = y + 0.15 * s * k - grow
    h = 0.24 * s * k + 2 * grow
    d.pieslice([x - w, top, x + w, top + 2 * h], 180, 360, fill=fill)  # flat-bottomed shoulders


def icon(n: int) -> Image.Image:
    """Dark people on a transparent background, with a soft light glow so they
    stay readable on dark art."""
    s = SIZE * SS
    people = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    pd = ImageDraw.Draw(people)
    gap = 0.022 * s
    for cx, cy, k in LAYOUTS[n]:
        person(pd, cx, cy, k, (0, 0, 0, 0), grow=gap)  # cut a clear gap around each person
        person(pd, cx, cy, k, FG)
    alpha = people.split()[3]
    shadow = Image.new("RGBA", (s, s), (255, 255, 255, 0))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.02 * s)).point(lambda a: int(a * 0.55)))
    img = Image.alpha_composite(shadow, people)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "assets"
    out.mkdir(parents=True, exist_ok=True)
    icons = {n: icon(n) for n in LAYOUTS}
    for n, im in icons.items():
        im.save(out / f"party_{n}.png")
    # preview: big row, and each badge on the large image at card size
    sheet = Image.new("RGBA", (5 * 220 + 20, 400), (243, 228, 245, 255))
    large = None
    lp = out / "mlbb_icon.png"
    if lp.exists():
        large = Image.open(lp).convert("RGBA").resize((100, 100), Image.LANCZOS)
    for i, n in enumerate(sorted(icons)):
        sheet.alpha_composite(icons[n].resize((200, 200), Image.LANCZOS), (20 + i * 220, 10))
        x, y = 60 + i * 220, 250
        if large is not None:
            sheet.alpha_composite(large, (x, y))
        sheet.alpha_composite(icons[n].resize((40, 40), Image.LANCZOS), (x + 70, y + 70))
    sheet.save(out / "party_preview.png")
    print("wrote", out)


if __name__ == "__main__":
    main()
