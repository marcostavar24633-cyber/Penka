from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://marcostavar24633-cyber.github.io/Penka/"
OUT = Path("artifacts/portfolio")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    ("desktop", 1440, 1000),
    ("tablet", 768, 1024),
    ("mobile", 390, 844),
]

def prepare_page(page):
    page.goto(URL, wait_until="networkidle", timeout=90000)
    page.evaluate("document.fonts.ready")
    # Visit the full document so native lazy-loaded images are requested.
    page.evaluate("""async () => {
      const step = Math.max(400, window.innerHeight * 0.8);
      for (let y = 0; y < document.body.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      window.scrollTo(0, 0);
    }""")
    page.wait_for_timeout(1200)
    page.evaluate("""async () => {
      await Promise.all(Array.from(document.images, image => {
        if (image.complete) return Promise.resolve();
        return new Promise(resolve => {
          image.addEventListener("load", resolve, { once: true });
          image.addEventListener("error", resolve, { once: true });
        });
      }));
    }""")

def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, width, height in VIEWPORTS:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
            prepare_page(page)
            page.screenshot(path=str(OUT / f"penka-{name}-full.png"), full_page=True)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT / f"penka-{name}-hero.png"), full_page=False)
            print(f"Captured {name}: {width}x{height}")
            page.close()
        browser.close()

if __name__ == "__main__":
    main()
