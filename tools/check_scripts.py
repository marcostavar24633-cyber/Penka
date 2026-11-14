#!/usr/bin/env python3
"""Validate inline JavaScript syntax and JSON-LD in index.html using Node.js."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "index.html"


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[tuple[dict[str, str | None], str]] = []
        self.current_attrs: dict[str, str | None] | None = None
        self.current_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.current_attrs = dict(attrs)
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if self.current_attrs is not None:
            self.current_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.current_attrs is not None:
            self.blocks.append((self.current_attrs, "".join(self.current_parts)))
            self.current_attrs = None
            self.current_parts = []


def main() -> int:
    if not HTML_FILE.is_file():
        print("ERROR: index.html not found")
        return 1
    node = shutil.which("node")
    if not node:
        print("ERROR: Node.js is required for JavaScript syntax validation")
        return 1

    parser = ScriptParser()
    parser.feed(HTML_FILE.read_text(encoding="utf-8"))
    errors: list[str] = []
    js_count = 0
    json_count = 0

    with tempfile.TemporaryDirectory(prefix="penka-js-check-") as temp_dir:
        for index, (attrs, source) in enumerate(parser.blocks, start=1):
            source = source.strip()
            if not source or attrs.get("src"):
                continue
            mime = (attrs.get("type") or "").strip().lower()
            if mime in {"application/ld+json", "application/json"}:
                json_count += 1
                try:
                    json.loads(source)
                except json.JSONDecodeError as exc:
                    errors.append(f"Script #{index}: invalid {mime}: {exc}")
                continue
            if mime and mime not in {"text/javascript", "application/javascript", "module"}:
                continue

            js_count += 1
            path = Path(temp_dir) / f"inline-{index}.js"
            path.write_text(source + "\n", encoding="utf-8")
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                errors.append(f"Script #{index}: JavaScript syntax error:\n{detail}")

    print("PENKA script quality check")
    print(f"Inline JavaScript blocks checked: {js_count}")
    print(f"Structured JSON blocks checked: {json_count}")
    for error in errors:
        print("ERROR: " + error)
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        return 1
    print("\nPASSED: inline scripts and JSON blocks are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
