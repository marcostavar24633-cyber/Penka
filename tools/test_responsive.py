#!/usr/bin/env python3
"""Browser-based responsive smoke tests for the PENKA landing page."""
from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 8765
WIDTHS = (320, 360, 375, 390, 420, 768, 1024)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass


def main() -> int:
    os.chdir(ROOT)
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(ROOT), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    failures: list[str] = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: failures.append(f"Browser JavaScript error: {error}"))
            response = page.goto(f"http://127.0.0.1:{PORT}/", wait_until="domcontentloaded")
            if response is None or not response.ok:
                failures.append(f"Page did not load successfully: {response.status if response else 'no response'}")
            page.wait_for_timeout(300)

            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 850})
                page.wait_for_timeout(100)
                metrics = page.evaluate("""() => ({
                    viewport: document.documentElement.clientWidth,
                    document: document.documentElement.scrollWidth,
                    body: document.body.scrollWidth,
                    title: document.querySelector('h1')?.getBoundingClientRect().toJSON(),
                    header: document.querySelector('.header')?.getBoundingClientRect().toJSON(),
                    tabs: document.querySelector('.tabs')?.getBoundingClientRect().toJSON(),
                    gallery: document.querySelector('.gallery')?.getBoundingClientRect().toJSON()
                })""")
                if metrics["document"] > metrics["viewport"] + 1 or metrics["body"] > metrics["viewport"] + 1:
                    failures.append(
                        f"{width}px: horizontal overflow "
                        f"(viewport={metrics['viewport']}, document={metrics['document']}, body={metrics['body']})"
                    )
                for name in ("title", "header", "tabs", "gallery"):
                    rect = metrics.get(name)
                    if rect and (rect["right"] > width + 1 or rect["left"] < -1):
                        failures.append(f"{width}px: {name} extends beyond viewport ({rect['left']}..{rect['right']})")

                if width <= 760:
                    page.evaluate("window.scrollTo(0, 700)")
                    page.wait_for_timeout(150)
                    cta = page.locator(".mcta")
                    if cta.count() and cta.is_visible():
                        box = cta.bounding_box()
                        if box and (box["x"] < 0 or box["x"] + box["width"] > width + 1):
                            failures.append(f"{width}px: mobile CTA extends beyond viewport")
                    page.evaluate("window.scrollTo(0, 0)")

                print(f"PASS {width}px: viewport={metrics['viewport']} document={metrics['document']} body={metrics['body']}")

            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    if failures:
        print("\nRESPONSIVE TEST FAILURES:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("\nRESPONSIVE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
