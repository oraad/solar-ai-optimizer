#!/usr/bin/env python3
"""Translate backend locale JSON files from en.json (optional maintainer tool)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "i18n" / "locales"


def _walk_strings(obj, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            out.extend(_walk_strings(v, p))
    elif isinstance(obj, str):
        out.append((path, obj))
    return out


def _set_path(obj: dict, key: str, value: str) -> None:
    parts = key.split(".")
    cur = obj
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate backend locales from en.json")
    parser.add_argument("target", choices=["ar", "fr"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Install deep-translator to run this script") from exc

    with (LOCALES_DIR / "en.json").open(encoding="utf-8") as f:
        en = json.load(f)
    target_path = LOCALES_DIR / f"{args.target}.json"
    with target_path.open(encoding="utf-8") as f:
        target = json.load(f)

    translator = GoogleTranslator(source="en", target=args.target)
    token_re = re.compile(r"\{(\w+)\}")

    for key, text in _walk_strings(en):
        if not text.strip():
            continue
        placeholders = token_re.findall(text)
        masked = text
        for i, name in enumerate(placeholders):
            masked = masked.replace(f"{{{name}}}", f"__PH{i}__")
        translated = translator.translate(masked)
        for i, name in enumerate(placeholders):
            translated = translated.replace(f"__PH{i}__", f"{{{name}}}")
        _set_path(target, key, translated)

    if args.dry_run:
        print(json.dumps(target, ensure_ascii=False, indent=2)[:2000])
        return
    with target_path.open("w", encoding="utf-8") as f:
        json.dump(target, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {target_path}")


if __name__ == "__main__":
    main()
