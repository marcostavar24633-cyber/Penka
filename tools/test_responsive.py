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
WIDTHS = (320, 360, 375, 390, 420, 768, 1024, 1440, 1920)


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

            # Keyboard skip link must become visible when focused.
            skip_link = page.locator('a.sr-only[href="#main"]')
            if skip_link.count() != 1:
                failures.append("A single skip-to-content link is missing")
            else:
                skip_link.focus()
                skip_box = skip_link.bounding_box()
                if not skip_box or skip_box["width"] <= 1 or skip_box["height"] <= 1:
                    failures.append("Skip-to-content link is not visibly revealed on keyboard focus")
                page.locator("body").click(position={"x": 2, "y": 2})

            # Respect the operating system's reduced-motion preference.
            page.emulate_media(reduced_motion="reduce")
            reduced_motion = page.evaluate("""() => {
              const animation = getComputedStyle(document.querySelector('.penka-marquee-track'));
              const transition = getComputedStyle(document.querySelector('.btn-primary'));
              return {
                enabled: matchMedia('(prefers-reduced-motion: reduce)').matches,
                animationDuration: parseFloat(animation.animationDuration),
                animationIterations: animation.animationIterationCount,
                transitionDuration: parseFloat(transition.transitionDuration)
              };
            }""")
            if not reduced_motion["enabled"] or reduced_motion["animationDuration"] > 0.001:
                failures.append(f"Reduced-motion preference did not suppress continuous animation: {reduced_motion}")
            if reduced_motion["animationIterations"] != "1" or reduced_motion["transitionDuration"] > 0.001:
                failures.append(f"Reduced-motion preference did not minimize motion effects: {reduced_motion}")
            page.emulate_media(reduced_motion="no-preference")
            print("PASS accessibility preferences: visible skip link and reduced-motion support")

            # Automated WCAG 2.2 AA audit with axe-core in both color themes.
            axe_path = ROOT / "node_modules" / "axe-core" / "axe.min.js"
            if not axe_path.exists():
                failures.append("axe-core is missing; accessibility audit could not run")
            else:
                page.add_script_tag(path=str(axe_path))
                for theme_name in ("light", "dark"):
                    current_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
                    if (theme_name == "dark" and current_theme != "dark") or (theme_name == "light" and current_theme == "dark"):
                        page.locator(".theme-toggle").click()
                    page.wait_for_function(
                        "() => document.documentElement.getAttribute('data-theme') === "
                        + ("'dark'" if theme_name == "dark" else "null")
                    )
                    page.wait_for_timeout(300)
                    audit = page.evaluate("""async () => {
                      const result = await axe.run(document, {
                        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }
                      });
                      return result.violations.map(v => ({
                        id: v.id, impact: v.impact, description: v.description,
                        help: v.help, nodes: v.nodes.map(n => ({
                          target: n.target, summary: n.failureSummary
                        }))
                      }));
                    }""")
                    for violation in audit:
                        targets = ", ".join(str(node["target"]) for node in violation["nodes"])
                        details = " | ".join(
                            f"{node['target']}: {node['summary']}" for node in violation["nodes"]
                        )
                        failures.append(
                            f"axe {theme_name} [{violation['impact']}] {violation['id']}: "
                            f"{violation['help']} — {targets} — {details}"
                        )
                    print(f"AXE {theme_name}: {len(audit)} WCAG violations")
                if page.evaluate("document.documentElement.getAttribute('data-theme') === 'dark'"):
                    page.locator(".theme-toggle").click()
                    page.wait_for_function("document.documentElement.getAttribute('data-theme') !== 'dark'")

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

            # Mobile navigation: open, Escape, outside click, and link activation.
            page.set_viewport_size({"width": 390, "height": 850})
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            page.evaluate("window.scrollTo(0, 0)")
            toggle = page.locator(".menu-toggle")
            sheet = page.locator("#sheet")
            page.locator(".menu-toggle").evaluate("(el) => el.click()")
            try:
                page.wait_for_function("""() => {
                    const button = document.querySelector('.menu-toggle');
                    return button?.getAttribute('aria-expanded') === 'true' &&
                        document.querySelector('#sheet')?.classList.contains('open');
                }""", timeout=3000)
            except Exception:
                failures.append("Mobile menu did not open or update aria-expanded")
            page.keyboard.press("Escape")
            if toggle.get_attribute("aria-expanded") != "false" or sheet.evaluate("(el) => el.classList.contains('open')"):
                failures.append("Mobile menu did not close on Escape")
            if page.evaluate("document.activeElement === document.querySelector('.menu-toggle')") is False:
                failures.append("Mobile menu did not return focus to its toggle after Escape")
            page.locator(".menu-toggle").evaluate("(el) => el.click()")
            page.locator("#sheet a[href='#about']").evaluate("(el) => el.click()")
            try:
                page.wait_for_function("""() => {
                    const button = document.querySelector('.menu-toggle');
                    return button?.getAttribute('aria-expanded') === 'false';
                }""", timeout=3000)
            except Exception:
                failures.append("Mobile menu did not close after navigation link activation")

            # Mobile navigation: outside click and desktop breakpoint cleanup.
            page.locator(".menu-toggle").evaluate("(el) => el.click()")
            page.locator("h1").click(position={"x": 5, "y": 5})
            if toggle.get_attribute("aria-expanded") != "false" or sheet.evaluate("(el) => el.classList.contains('open')"):
                failures.append("Mobile menu did not close after an outside click")
            page.locator(".menu-toggle").evaluate("(el) => el.click()")
            page.set_viewport_size({"width": 1024, "height": 850})
            page.wait_for_timeout(150)
            if toggle.get_attribute("aria-expanded") != "false" or sheet.evaluate("(el) => el.classList.contains('open')"):
                failures.append("Mobile menu remained open after switching to desktop width")
            page.set_viewport_size({"width": 390, "height": 850})
            page.wait_for_timeout(100)

            # Menu tabs: pointer selection and arrow/Home/End keyboard behavior.
            coffee = page.locator("#t-coffee")
            tea = page.locator("#t-tea")
            bake = page.locator("#t-bake")
            dessert = page.locator("#t-dessert")
            tea.click()
            if tea.get_attribute("aria-selected") != "true" or not page.locator("#p-tea").is_visible():
                failures.append("Menu tab click did not activate the tea panel")
            tea.focus()
            page.keyboard.press("ArrowRight")
            if bake.get_attribute("aria-selected") != "true" or page.evaluate("document.activeElement.id") != "t-bake":
                failures.append("ArrowRight did not move focus and selection to the next menu tab")
            page.keyboard.press("End")
            if dessert.get_attribute("aria-selected") != "true":
                failures.append("End did not select the last menu tab")
            page.keyboard.press("Home")
            if coffee.get_attribute("aria-selected") != "true":
                failures.append("Home did not select the first menu tab")

            # Theme toggle: visual state, accessible label, and persisted preference.
            theme = page.locator(".theme-toggle")
            theme.click()
            try:
                page.wait_for_function("""() => {
                    const button = document.querySelector('.theme-toggle');
                    return document.documentElement.getAttribute('data-theme') === 'dark' &&
                        button?.getAttribute('aria-label') === 'Включить светлую тему';
                }""", timeout=3000)
            except Exception:
                failures.append("Theme toggle did not apply dark theme or update its accessible label")
            if page.evaluate("localStorage.getItem('penka-theme')") != "dark":
                failures.append("Dark theme preference was not persisted")
            theme.click()
            try:
                page.wait_for_function("document.documentElement.getAttribute('data-theme') !== 'dark'", timeout=3000)
            except Exception:
                failures.append("Theme toggle did not return to light theme")

            # Gallery: visible captions must match the controls' accessible names.
            gallery_labels = page.locator(".gallery .g").evaluate_all(
                "els => els.map(el => ({label: el.getAttribute('aria-label'), caption: el.querySelector('figcaption')?.textContent?.trim()}))"
            )
            for item in gallery_labels:
                if not item["label"] or item["label"] != item["caption"]:
                    failures.append(
                        f"Gallery accessible name does not match visible caption: {item}"
                    )

            # Gallery: open by keyboard, navigate, close, and restore focus.
            first_gallery_item = page.locator(".gallery .g").first
            first_gallery_item.focus()
            page.keyboard.press("Enter")
            lightbox = page.locator(".lightbox")
            if not lightbox.evaluate("(el) => el.open"):
                failures.append("Gallery did not open from keyboard activation")
            first_caption = page.locator(".lightbox-caption").inner_text()
            page.keyboard.press("ArrowRight")
            second_caption = page.locator(".lightbox-caption").inner_text()
            if first_caption == second_caption:
                failures.append("Gallery ArrowRight did not advance to a different image")
            page.keyboard.press("ArrowLeft")
            if page.locator(".lightbox-caption").inner_text() != first_caption:
                failures.append("Gallery ArrowLeft did not return to the previous image")
            page.locator(".lightbox-next").click()
            if page.locator(".lightbox-caption").inner_text() == first_caption:
                failures.append("Gallery next button did not advance to another image")
            page.locator(".lightbox-prev").click()
            if page.locator(".lightbox-caption").inner_text() != first_caption:
                failures.append("Gallery previous button did not return to the first image")
            page.locator(".lightbox-close").click()
            if lightbox.evaluate("(el) => el.open"):
                failures.append("Gallery close button did not dismiss the lightbox")
            if page.evaluate("document.activeElement === document.querySelector('.gallery .g')") is False:
                failures.append("Gallery did not restore focus to the activating item")

            print("PASS interactions: mobile navigation, menu tabs, theme toggle, gallery keyboard and button controls")
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
