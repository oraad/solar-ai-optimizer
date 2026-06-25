#!/usr/bin/env python3
"""Generate ar.json and fr.json from en.json via Google Translate (one-off build script)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("Install: pip install deep-translator", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1] / "src" / "locales"
CACHE: dict[tuple[str, str], str] = {}


def translate(text: str, target: str) -> str:
    if not text or text.strip() == "":
        return text
    # Preserve interpolation tokens
    if text.startswith("{") and text.endswith("}"):
        return text
    key = (target, text)
    if key in CACHE:
        return CACHE[key]
    try:
        out = GoogleTranslator(source="en", target=target).translate(text)
        CACHE[key] = out
        time.sleep(0.05)
        return out
    except Exception as e:
        print(f"warn: {e!r} for {text[:60]!r}", file=sys.stderr)
        return text


def walk(obj: Any, target: str) -> Any:
    if isinstance(obj, str):
        return translate(obj, target)
    if isinstance(obj, list):
        return [walk(v, target) for v in obj]
    if isinstance(obj, dict):
        return {k: walk(v, target) for k, v in obj.items()}
    return obj


def main() -> None:
    en = json.loads((ROOT / "en.json").read_text(encoding="utf-8"))
    for code, name in [("fr", "fr.json"), ("ar", "ar.json")]:
        print(f"Translating to {code}…")
        out = walk(en, code)
        (ROOT / name).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {name}")


if __name__ == "__main__":
    main()
