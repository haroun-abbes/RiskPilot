"""End-to-end smoke test of the main user journeys through the real UI.

Prerequisites: backend on :8000 and frontend on :3000 (see README), then
    pip install playwright && python -m playwright install chromium
    python e2e/smoke.py [--shots DIR]

Journey: invalid import is blocked -> valid import -> risk -> scenario
creation and stress run -> bond analysis -> method drawer -> brief + PDF ->
every page at desktop and mobile widths without console errors.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright, expect

BASE = "http://localhost:3000"
FIX = Path(__file__).parent / "fixtures"
PAGES = ["/overview", "/portfolio", "/risk", "/stress", "/fixed-income", "/market", "/attribution", "/reports", "/data", "/settings"]


async def main(shots: Path | None):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        async def shot(name):
            if shots:
                await page.screenshot(path=str(shots / f"{name}.png"), full_page=True)

        # 1. invalid import is blocked with row-level messages
        await page.goto(f"{BASE}/portfolio")
        await page.get_by_role("tab", name="Import a portfolio").click()
        await page.set_input_files("input[type=file]", str(FIX / "invalid_portfolio.csv"))
        await page.get_by_role("button", name="Validate").click()
        await expect(page.get_by_text("Duplicate id 'A'")).to_be_visible()
        await expect(page.get_by_text("Floating-rate notes")).to_be_visible()
        await expect(page.get_by_role("button", name="Confirm import")).to_be_disabled()
        await shot("01_import_invalid")
        print("ok  invalid import blocked")

        # 2. valid import -> becomes the active portfolio
        await page.get_by_role("button", name="Back to mapping").click()
        await page.get_by_role("button", name="Choose another file").click()
        await page.set_input_files("input[type=file]", str(FIX / "demo_portfolio_SYNTHETIC.csv"))
        name = f"E2E import {int(time.time())}"
        await page.get_by_label("Portfolio name").fill(name)
        await page.get_by_role("button", name="Validate").click()
        await expect(page.get_by_text("All rows passed validation.")).to_be_visible()
        await page.get_by_role("button", name="Confirm import").click()
        await expect(page.get_by_role("heading", name="Positions")).to_be_visible()
        await expect(page.locator("select").first).to_contain_text(name)
        await shot("02_portfolio_imported")
        print("ok  valid import committed and selected")

        # 3. risk analytics computed on the imported portfolio
        await page.get_by_role("link", name="Risk Analytics").click()
        await expect(page.get_by_text("Risk measures")).to_be_visible(timeout=20000)
        await expect(page.get_by_text(re.compile(r"Basel (green|yellow|red)"))).to_be_visible()
        # method drawer
        await page.get_by_role("button", name="Method: Historical VaR").first.click()
        await expect(page.get_by_role("dialog", name="Historical VaR")).to_be_visible()
        await page.keyboard.press("Escape")
        await expect(page.get_by_role("dialog")).to_have_count(0)
        print("ok  risk page and method drawer")

        # 4. create a scenario and run it
        await page.get_by_role("link", name="Stress Lab").click()
        await page.get_by_role("button", name="New scenario").click()
        sc = f"E2E rates +50 {int(time.time())}"
        await page.get_by_label("Name").first.fill(sc)
        await page.get_by_label("EUR parallel (bp)").fill("50")
        await page.get_by_role("button", name="Save scenario").click()
        row = page.locator("table.dense tr", has_text=sc)
        await expect(row).to_be_visible(timeout=20000)
        await expect(row.locator("td").nth(1)).to_contain_text("-")
        await shot("03_stress")
        print("ok  scenario saved, revalued (loss on long bonds)")

        # 5. bond analysis from the book
        await page.get_by_role("link", name="Fixed Income").click()
        await page.get_by_role("tab", name="Bonds in portfolio").click()
        await page.get_by_role("button", name="Analyse").first.click()
        await expect(page.get_by_text("Yield to maturity")).to_be_visible(timeout=20000)
        await expect(page.get_by_text("Sum = dirty price")).to_be_visible()
        await shot("04_bond")
        print("ok  bond analytics")

        # 6. decision brief + PDF download
        await page.get_by_role("link", name="Reports").click()
        await page.get_by_role("button", name="Generate brief").click()
        await expect(page.get_by_role("link", name="Download PDF")).to_be_visible(timeout=30000)
        href = await page.get_by_role("link", name="Download PDF").get_attribute("href")
        resp = await page.request.get(f"{BASE}{href}")
        assert resp.ok and (await resp.body())[:4] == b"%PDF", "PDF export failed"
        await shot("05_brief")
        print("ok  brief generated, PDF downloadable")

        # 7. every page, desktop and mobile
        for width in (1440, 390):
            await page.set_viewport_size({"width": width, "height": 900})
            for path in PAGES:
                await page.goto(f"{BASE}{path}")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(600)
                overflow = await page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                assert overflow <= 1, f"{path} overflows horizontally by {overflow}px at {width}px"
                if width == 390:
                    await shot(f"mobile_{path.strip('/')}")
            print(f"ok  all pages render at {width}px without horizontal overflow")

        # restore demo context so the next run starts clean
        await page.evaluate("localStorage.removeItem('riskpilot-context')")
        await browser.close()
        real = [e for e in errors if "favicon" not in e]
        assert not real, "Browser errors:\n" + "\n".join(real)
        print("ok  no browser errors")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=Path, default=None)
    a = ap.parse_args()
    if a.shots:
        a.shots.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(a.shots))
