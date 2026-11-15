from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://marcostavar24633-cyber.github.io/Penka/"
OUT = Path("artifacts/portfolio")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    ("desktop", 1440, 1000),
    ("tablet", 768, 1024),
    ("mobile", 390, 844),
]

def prepare_page(page):
    response = page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    if response is None or not response.ok:
        raise RuntimeError(f"Published site did not respond successfully: {response.status if response else 'no response'}")
    page.locator("body").wait_for(state="visible", timeout=15000)
    try:
        page.evaluate("""() => Promise.race([
          document.fonts.ready.then(() => true),
          new Promise(resolve => setTimeout(() => resolve(false), 15000))
        ])""")
    except PlaywrightTimeoutError:
        print("Font readiness timed out; continuing with available fonts.", flush=True)

    # Scroll through the page to trigger native lazy loading.
    page.evaluate("""async () => {
      const step = Math.max(350, window.innerHeight * 0.7);
      const maxY = document.documentElement.scrollHeight;
      for (let y = 0; y < maxY; y += step) {
        window.scrollTo(0, y);
        await new Promise(resolve => setTimeout(resolve, 120));
      }
      window.scrollTo(0, 0);
    }""")

    # Never wait indefinitely for a failed or deferred image.
    page.evaluate("""async () => {
      const images = Array.from(document.images);
      for (const image of images) image.loading = "eager";
      await Promise.all(images.map(image => {
        if (image.complete) return Promise.resolve();
        return new Promise(resolve => {
          const finish = () => resolve();
          image.addEventListener("load", finish, { once: true });
          image.addEventListener("error", finish, { once: true });
          setTimeout(finish, 10000);
        });
      }));
    }""")
    # The site defers off-screen sections with content-visibility and scroll-reveal.
    # For a complete portfolio capture, reveal the existing content without changing
    # the published page or its normal visitor behavior.
    page.evaluate("""() => {
      document.querySelectorAll("main > section").forEach(section => {
        section.style.contentVisibility = "visible";
      });
      document.querySelectorAll("[data-fade]").forEach(element => {
        element.classList.add("in");
      });
    }""")
    page.wait_for_timeout(900)

def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, width, height in VIEWPORTS:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
            print(f"Opening {name} viewport ({width}x{height})", flush=True)
            prepare_page(page)
            page.screenshot(path=str(OUT / f"penka-{name}-full.png"), full_page=True, animations="disabled")
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / f"penka-{name}-hero.png"), full_page=False, animations="disabled")
            print(f"Captured {name}: {width}x{height}", flush=True)
            page.close()
        browser.close()

if __name__ == "__main__":
    main()
