"""Export HA brand icons and upscaled logos from canonical sources.

Icons are generated from the square mark PNG under brand/. Logos are
upscaled from brand/logo_source.png (composed from the same mark).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
BRAND = REPO / "brand"
ADDON = REPO / "solar_ai_optimizer"
FRONTEND_PUBLIC = REPO / "frontend" / "public"

# Designed landscape logo (shortest side upscaled to HA limits).
LOGO_SOURCE = BRAND / "logo_source.png"
# Square mark used for icons / favicon / UI (256 px export).
ICON_SOURCE = BRAND / "icon_source.png"


def upscale_shortest(img: Image.Image, target_shortest: int) -> Image.Image:
    w, h = img.size
    scale = target_shortest / min(w, h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)


def export_icons(mark: Image.Image) -> None:
    icon256 = mark.resize((256, 256), Image.Resampling.LANCZOS)
    icon512 = mark.resize((512, 512), Image.Resampling.LANCZOS)
    fav32 = mark.resize((32, 32), Image.Resampling.LANCZOS)

    BRAND.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
    ADDON.mkdir(parents=True, exist_ok=True)

    icon256.save(BRAND / "icon.png", optimize=True)
    icon512.save(BRAND / "icon@2x.png", optimize=True)
    icon256.save(ADDON / "icon.png", optimize=True)
    icon512.save(FRONTEND_PUBLIC / "brand-mark.png", optimize=True)
    fav32.save(FRONTEND_PUBLIC / "favicon.png", optimize=True)


def export_logos(logo: Image.Image) -> None:
    # HA: shortest side 128–256 (normal), 256–512 (@2x).
    logo256 = upscale_shortest(logo, 256)
    logo512 = upscale_shortest(logo, 512)
    logo256.save(BRAND / "logo.png", optimize=True)
    logo512.save(BRAND / "logo@2x.png", optimize=True)
    logo256.save(ADDON / "logo.png", optimize=True)


def verify_assets() -> None:
    checks = [
        (BRAND / "icon.png", (256, 256)),
        (BRAND / "icon@2x.png", (512, 512)),
        (BRAND / "logo.png", None),
        (BRAND / "logo@2x.png", None),
        (ADDON / "icon.png", (256, 256)),
        (ADDON / "logo.png", None),
        (FRONTEND_PUBLIC / "brand-mark.png", (512, 512)),
        (FRONTEND_PUBLIC / "favicon.png", (32, 32)),
    ]
    for path, exact in checks:
        im = Image.open(path).convert("RGBA")
        if exact and im.size != exact:
            raise SystemExit(f"{path}: expected {exact}, got {im.size}")
        shortest = min(im.size)
        if "logo" in path.name:
            min_shortest = 128 if "@2x" not in path.name else 256
            max_shortest = 256 if "@2x" not in path.name else 512
            if shortest < min_shortest:
                raise SystemExit(
                    f"{path}: shortest side {shortest} below HA minimum {min_shortest}"
                )
            if shortest > max_shortest:
                raise SystemExit(
                    f"{path}: shortest side {shortest} above HA maximum {max_shortest}"
                )
        corners = [im.getpixel((0, 0)), im.getpixel((im.width - 1, 0))]
        print(path.relative_to(REPO), im.size, "corners", corners)


def main() -> None:
    if not LOGO_SOURCE.exists():
        raise SystemExit(f"Missing logo source: {LOGO_SOURCE}")
    if not ICON_SOURCE.exists():
        raise SystemExit(f"Missing icon source: {ICON_SOURCE}")

    logo = Image.open(LOGO_SOURCE).convert("RGBA")
    mark = Image.open(ICON_SOURCE).convert("RGBA")
    export_icons(mark)
    export_logos(logo)
    print("exported brand assets")
    verify_assets()


if __name__ == "__main__":
    main()
