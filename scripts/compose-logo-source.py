"""Compose brand/logo_source.png from icon_source mark + wordmark text."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
BRAND = REPO / "brand"
ICON_SOURCE = BRAND / "icon_source.png"
LOGO_SOURCE = BRAND / "logo_source.png"


def sample_cyan(mark: Image.Image) -> tuple[int, int, int, int]:
    cyan = (36, 168, 224, 255)
    for y in range(80, 180):
        for x in range(80, 180):
            r, g, b, a = mark.getpixel((x, y))
            if a > 200 and b > 180 and g > 100 and r < 80:
                return (r, g, b, 255)
    return cyan


def main() -> None:
    mark = Image.open(ICON_SOURCE).convert("RGBA")
    cyan = sample_cyan(mark)

    height = 256
    width = 640
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))

    mark_size = 200
    mark_resized = mark.resize((mark_size, mark_size), Image.Resampling.LANCZOS)
    mx = 28
    my = (height - mark_size) // 2
    canvas.alpha_composite(mark_resized, (mx, my))

    draw = ImageDraw.Draw(canvas)
    font_file = next(
        p
        for p in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        if Path(p).exists()
    )
    font_top = ImageFont.truetype(font_file, 42)
    font_bot = ImageFont.truetype(font_file, 48)

    text_x = mx + mark_size + 28
    line1 = "Solar AI"
    line2 = "Optimizer"
    bbox1 = draw.textbbox((0, 0), line1, font=font_top)
    bbox2 = draw.textbbox((0, 0), line2, font=font_bot)
    h1 = bbox1[3] - bbox1[1]
    h2 = bbox2[3] - bbox2[1]
    gap = 8
    total_h = h1 + gap + h2
    ty = (height - total_h) // 2 - bbox1[1]
    draw.text((text_x, ty), line1, font=font_top, fill=(255, 255, 255, 255))
    draw.text((text_x, ty + h1 + gap), line2, font=font_bot, fill=cyan)

    pixels = canvas.load()
    right = 0
    for x in range(width - 1, -1, -1):
        for y in range(height):
            r, g, b, a = pixels[x, y]
            if a > 0 and (r > 8 or g > 8 or b > 8):
                right = x
                break
        if right:
            break
    out = canvas.crop((0, 0, min(width, right + 28), height))
    out.save(LOGO_SOURCE, optimize=True)
    print(f"wrote {LOGO_SOURCE.relative_to(REPO)} {out.size} cyan={cyan}")


if __name__ == "__main__":
    main()
