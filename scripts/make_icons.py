"""Draw the app icon with Pillow (same shapes as static/logo.svg) and write
packaging/icon.ico (Windows) and packaging/icon.icns (Mac).

    python scripts/make_icons.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging"


def _rotated_ellipse(size, cx, cy, rx, ry, angle, color):
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color)
    return layer.rotate(-angle, center=(cx, cy), resample=Image.BICUBIC)


def _heart(size, s):
    """Points along the heart in logo.svg, scaled by s."""
    pts = []
    # left lobe arc + right lobe arc approximated from the SVG's two arcs
    for cx, start, end in ((24.75, 180, 360), (39.25, 180, 360)):
        for i in range(0, 61):
            a = math.radians(start + (end - start) * i / 60)
            pts.append(((cx + 7.3 * math.cos(a)) * s, (33.4 + 7.3 * math.sin(a)) * s))
    # down to the point and back along the two cubic curves from the SVG
    def cubic(p0, p1, p2, p3, n=40):
        for i in range(1, n + 1):
            t = i / n
            x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
            y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
            pts.append((x * s, y * s))
    cubic((46.5, 34.2), (46.5, 40.5), (40.5, 45.5), (32, 51.5))
    cubic((32, 51.5), (23.5, 45.5), (17.5, 40.5), (17.5, 34.2))
    return pts


def render(size: int) -> Image.Image:
    s = size / 64
    big = size * 4  # draw large, downsample for smooth edges
    S = big / 64
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # background: rounded square with a diagonal gradient
    grad = Image.new("RGBA", (big, big))
    gd = ImageDraw.Draw(grad)
    for i in range(big * 2):
        t = i / (big * 2)
        c = (int(79 + (43 - 79) * t), int(120 + (74 - 120) * t), int(216 + (155 - 216) * t), 255)
        gd.line([(i, 0), (0, i)], fill=c)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(18 * S), fill=255)
    img.paste(grad, (0, 0), mask)
    for cx, cy, rx, ry, ang in ((19.5, 25, 5, 6.3, -20), (44.5, 25, 5, 6.3, 20), (28, 17, 4.7, 5.9, -7), (36, 17, 4.7, 5.9, 7)):
        layer = _rotated_ellipse(big, cx * S, cy * S, rx * S, ry * S, ang, (255, 255, 255, 255))
        img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    d.polygon(_heart(big, S), fill=(255, 214, 179, 255))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = {n: render(n) for n in sizes}
    images[256].save(OUT / "icon.ico", sizes=[(n, n) for n in sizes])
    images[256].save(OUT / "icon.icns")
    images[256].save(OUT / "icon-256.png")
    print("wrote", OUT / "icon.ico", OUT / "icon.icns")


if __name__ == "__main__":
    main()
