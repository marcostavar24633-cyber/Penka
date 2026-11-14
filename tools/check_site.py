#!/usr/bin/env python3
"""Dependency-free quality checks for the static PENKA site.

Run from the repository root:
    python tools/check_site.py
The command exits with status 1 when an error is found.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "index.html"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.images: list[tuple[str, str | None]] = []
        self.references: list[tuple[str, str]] = []
        self.h1_count = 0
        self.title = False
        self.description = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if "id" in data and data["id"]:
            self.ids.append(data["id"])
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and data.get("name", "").lower() == "description":
            self.description = bool(data.get("content", "").strip())
        if tag == "img":
            # The lightbox image receives its src only when a gallery item is opened.
            if "lightbox-image" not in data.get("class", "").split():
                self.images.append((data.get("src", ""), data.get("alt")))
        for attr in ("src", "href", "poster"):
            value = data.get(attr)
            if value:
                self.references.append((tag, value))
        srcset = data.get("srcset", "")
        for item in srcset.split(","):
            candidate = item.strip().split(" ")[0] if item.strip() else ""
            if candidate:
                self.references.append((tag, candidate))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self.title = True


def local_target(value: str) -> str | None:
    value = value.strip()
    if not value or value.startswith(("data:", "blob:", "javascript:", "mailto:", "tel:")):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    return path


def main() -> int:
    if not HTML_FILE.is_file():
        print("ERROR: index.html not found in repository root")
        return 1

    parser = SiteParser()
    parser.feed(HTML_FILE.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    if not parser.title:
        errors.append("Document title is missing or empty")
    if not parser.description:
        errors.append("Meta description is missing or empty")
    if parser.h1_count != 1:
        errors.append(f"Expected exactly one H1, found {parser.h1_count}")

    duplicates = [item for item, count in Counter(parser.ids).items() if count > 1]
    if duplicates:
        errors.append("Duplicate IDs: " + ", ".join(sorted(duplicates)))

    for src, alt in parser.images:
        if not src:
            errors.append("Image without src attribute")
        if alt is None:
            errors.append(f"Image without alt attribute: {src or '(unknown)'}")
        elif not alt.strip():
            warnings.append(f"Decorative image has empty alt: {src}")

    checked: set[str] = set()
    for tag, value in parser.references:
        # Verify same-page fragments before resolving the local path.
        if value.startswith("#"):
            fragment = value[1:]
            # HTMLParser also sees JavaScript template literals in inline scripts.
            # Dynamic fragments are resolved at runtime and cannot be checked statically.
            if "${" in fragment:
                continue
            if fragment and fragment not in parser.ids:
                errors.append(f"Broken in-page anchor: {value}")
            continue
        path = local_target(value)
        if path is None:
            continue
        if path in checked:
            continue
        checked.add(path)
        target = (ROOT / path.lstrip("/")).resolve()
        if not target.exists():
            errors.append(f"Missing local {tag} resource: {value}")

    print("PENKA static-site quality check")
    print(f"Images: {len(parser.images)} | unique local references checked: {len(checked)}")
    for warning in warnings:
        print("WARN: " + warning)
    for error in errors:
        print("ERROR: " + error)
    if errors:
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\nPASSED: no errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
