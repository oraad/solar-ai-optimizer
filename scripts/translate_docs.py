#!/usr/bin/env python3
"""Generate localized docs from English sources via Google Translate.

Maintainer script — not run in CI. Install deps:

    pip install deep-translator pyyaml
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
    from deep_translator import GoogleTranslator
except ImportError:
    print("Install: pip install deep-translator pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MANIFEST = DOCS / "i18n" / "locales.yaml"
CACHE: dict[tuple[str, str], str] = {}


def load_manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def english_pages() -> list[Path]:
    manifest = load_manifest()
    locale_ids = {loc["id"] for loc in manifest["locales"] if loc["id"] != manifest["default"]}
    pages: list[Path] = []
    for path in sorted(DOCS.glob("*.md")):
        stem = path.stem
        if any(stem.endswith(f".{loc}") for loc in locale_ids):
            continue
        pages.append(path)
    return pages


def split_newline(text: str) -> tuple[str, str]:
    if text.endswith("\n"):
        return text[:-1], "\n"
    return text, ""


def translate_text(text: str, target: str) -> str:
    if not text or not text.strip():
        return text
    key = (target, text)
    if key in CACHE:
        return CACHE[key]
    try:
        out = GoogleTranslator(source="en", target=target).translate(text)
        if not out:
            out = text
        CACHE[key] = out
        time.sleep(0.03)
        return out
    except Exception as exc:
        print(f"warn: {exc!r} for {text[:80]!r}", file=sys.stderr)
        return text


def translate_plain(text: str, target: str) -> str:
    if not text or not text.strip():
        return text
    anchor_parts = re.split(r"(\{#[\w-]+\})", text)
    if len(anchor_parts) > 1:
        return "".join(
            piece if re.fullmatch(r"\{#[\w-]+\}", piece) else translate_text(piece, target)
            if piece.strip()
            else piece
            for piece in anchor_parts
        )
    return translate_text(text, target)


def translate_inline(text: str, target: str) -> str:
    if not text:
        return text

    parts = re.split(r"(!\[[^\]]*\]\([^)]+\))", text)
    if len(parts) > 1:
        return "".join(p if p.startswith("![") else translate_inline(p, target) for p in parts)

    parts = re.split(r"(`[^`\n]+`)", text)
    if len(parts) > 1:
        return "".join(p if p.startswith("`") else translate_inline(p, target) for p in parts)

    parts = re.split(r"(\[[^\]]+\]\([^)]+\))", text)
    if len(parts) > 1:
        out: list[str] = []
        for part in parts:
            match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if match:
                out.append(f"[{translate_text(match.group(1), target)}]({match.group(2)})")
            else:
                out.append(translate_plain(part, target))
        return "".join(out)

    return translate_plain(text, target)


def translate_prose(text: str, target: str) -> str:
    body, suffix = split_newline(text)
    return translate_inline(body, target) + suffix


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped.startswith("|") and re.fullmatch(r"\|[\s\-:|]+\|", stripped)


def translate_admonition(line: str, target: str) -> str:
    body, suffix = split_newline(line)
    match = re.match(r'^(\s*(?:!!!|\?\?\?)\s+\w+(?:\s+"([^"]*)")?\s*)(.*)$', body)
    if not match:
        return translate_prose(line, target)
    prefix, title, rest = match.groups()
    if title:
        translated_title = translate_text(title, target)
        prefix = prefix.replace(f'"{title}"', f'"{translated_title}"')
    if rest.strip():
        return prefix + translate_prose(rest + suffix, target)
    return prefix + suffix


def translate_line(line: str, target: str) -> str:
    body, suffix = split_newline(line)
    heading = re.match(r"^(#{1,6}\s+)(.*?)(\s+\{#[\w-]+\})?\s*$", body)
    if heading:
        prefix, text, anchor = heading.groups()
        return prefix + translate_inline(text, target) + (anchor or "") + suffix
    if is_table_separator(line):
        return line
    if re.match(r"^\s*(?:!!!|\?\?\?)\s+", body):
        return translate_admonition(line, target)
    return translate_prose(line, target)


def translate_markdown(content: str, target: str) -> str:
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            front_matter = content[: end + 5]
            body = content[end + 5 :]
            return front_matter + translate_markdown(body, target)

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    in_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if not stripped.strip():
            out.append(line)
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", stripped.strip()):
            out.append(line)
            continue
        out.append(translate_line(line, target))

    return "".join(out)


def output_path(source: Path, locale: str) -> Path:
    return source.with_name(f"{source.stem}.{locale}.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate English docs to configured locales.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing translations")
    parser.add_argument(
        "pages",
        nargs="*",
        help="Optional page stems (e.g. index installation); default: all English pages",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    targets = [loc for loc in manifest["locales"] if loc.get("translate")]
    pages = english_pages()
    if args.pages:
        wanted = set(args.pages)
        pages = [p for p in pages if p.stem in wanted]

    for source in pages:
        english = source.read_text(encoding="utf-8")
        for loc in targets:
            locale_id = loc["id"]
            dest = output_path(source, locale_id)
            if dest.exists() and not args.force:
                print(f"skip {dest.name} (exists; use --force)")
                continue
            print(f"Translating {source.name} → {dest.name} ({locale_id})…")
            translated = translate_markdown(english, locale_id)
            translated = re.sub(r"(\]\()images/", r"\1../images/", translated)
            dest.write_text(translated, encoding="utf-8")
            print(f"Wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
