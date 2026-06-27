#!/usr/bin/env python3
"""Verify every English doc page has translations for configured locales."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MANIFEST = DOCS / "i18n" / "locales.yaml"


def load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def english_pages(manifest: dict[str, Any]) -> list[Path]:
    default = manifest["default"]
    locale_ids = {loc["id"] for loc in manifest["locales"] if loc["id"] != default}
    pages: list[Path] = []
    for path in sorted(DOCS.glob("*.md")):
        stem = path.stem
        if any(stem.endswith(f".{loc}") for loc in locale_ids):
            continue
        pages.append(path)
    return pages


def main() -> int:
    manifest = load_manifest()
    targets = [loc["id"] for loc in manifest["locales"] if loc.get("translate")]
    missing: list[str] = []

    for source in english_pages(manifest):
        for locale in targets:
            dest = source.with_name(f"{source.stem}.{locale}.md")
            if not dest.is_file():
                missing.append(str(dest.relative_to(ROOT)))

    if missing:
        print("Missing translated docs:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        print("\nRun: python scripts/translate_docs.py", file=sys.stderr)
        return 1

    print(f"Docs i18n parity OK ({len(english_pages(manifest))} pages × {len(targets)} locales)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
