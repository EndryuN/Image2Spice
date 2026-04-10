"""Use Playwright to visually verify pin highlight positions in wire mode.

Run with: npx playwright test test_pin_positions.py
Or:       python test_pin_positions.py  (uses playwright sync API)

Requires: frontend running on localhost:5173, backend on localhost:8000
"""
import asyncio
import json
import sys
from pathlib import Path

# Add backend to path for dictionary loading
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from playwright.async_api import async_playwright

    dictionary = json.loads(
        (Path(__file__).parent.parent.parent / "dictionary" / "components.json").read_text()
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto("http://localhost:5173", wait_until="networkidle")
        await page.wait_for_timeout(1000)

        # Add one of each component type via the palette
        test_types = ["voltage", "res", "cap", "ind", "diode"]
        for comp_type in test_types:
            # Click the component button in the palette
            btn = page.locator(f'button:has-text("{comp_type}")')
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(300)

        # Switch to wire mode
        wire_btn = page.locator('button:has-text("Wire")')
        if await wire_btn.count() > 0:
            await wire_btn.first.click()
            await page.wait_for_timeout(500)

        # Take screenshot of wire mode with pin highlights
        await page.screenshot(path="pin_check_wire_mode.png", full_page=False)
        print("Screenshot saved: pin_check_wire_mode.png")

        # Now let's inspect the SVG to check pin circle positions vs component positions
        pin_circles = await page.evaluate("""() => {
            const svg = document.querySelector('svg');
            if (!svg) return { error: 'No SVG found' };

            // Get all pin highlight circles (the ones with accent color stroke)
            const circles = svg.querySelectorAll('circle[stroke*="accent"], circle[stroke*="1976d2"]');
            const pinPositions = [];
            circles.forEach(c => {
                const cx = parseFloat(c.getAttribute('cx'));
                const cy = parseFloat(c.getAttribute('cy'));
                if (!isNaN(cx) && !isNaN(cy) && parseFloat(c.getAttribute('r')) < 10) {
                    pinPositions.push({ x: cx, y: cy });
                }
            });

            // Get component group transforms
            const compGroups = [];
            svg.querySelectorAll('g[transform^="translate"]').forEach(g => {
                const transform = g.getAttribute('transform');
                const match = transform.match(/translate\\((\\d+\\.?\\d*),\\s*(\\d+\\.?\\d*)\\)/);
                if (match) {
                    // Check if this group has a path (component symbol)
                    const path = g.querySelector('path');
                    if (path) {
                        compGroups.push({
                            x: parseFloat(match[1]),
                            y: parseFloat(match[2]),
                            pathD: path.getAttribute('d')?.substring(0, 30) + '...',
                        });
                    }
                }
            });

            return { pins: pinPositions, components: compGroups };
        }""")

        print(f"\nFound {len(pin_circles.get('pins', []))} pin highlights:")
        for pin in pin_circles.get('pins', []):
            print(f"  Pin at ({pin['x']}, {pin['y']})")

        print(f"\nFound {len(pin_circles.get('components', []))} components:")
        for comp in pin_circles.get('components', []):
            print(f"  Component at ({comp['x']}, {comp['y']}) path={comp['pathD']}")

        # Now hover the mouse over the SVG to see pin highlighting
        svg_box = await page.locator('svg').bounding_box()
        if svg_box:
            # Move mouse across the SVG to trigger pin highlights
            for x_pct in [0.2, 0.4, 0.6, 0.8]:
                mx = svg_box['x'] + svg_box['width'] * x_pct
                my = svg_box['y'] + svg_box['height'] * 0.5
                await page.mouse.move(mx, my)
                await page.wait_for_timeout(200)

            await page.screenshot(path="pin_check_hover.png", full_page=False)
            print("\nHover screenshot saved: pin_check_hover.png")

        # Keep browser open for manual inspection
        print("\nBrowser open for inspection. Close manually or press Ctrl+C.")
        try:
            await asyncio.sleep(30)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
