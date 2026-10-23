"""Shattered Thresholds - the two JavaScript-gated doors. These are the only puzzles that need a browser.

The Sleeping Vault - "it shows nothing... until you truly look"
    The server always returns the *sealed* markup (HTTP 200). An inline script swaps in
    `/resources/open.html` client-side. An HTTP client only ever sees the sealed door; the
    vault opens only when the page's JavaScript is actually executed.

The Verity Gate - "its seal breaks only for what is authentic"
    The server parses the User-Agent and embeds its verdict in
    `<script id="what-is-my-browser">{"family": "chrome", "major": 130}</script>`.
    `/resources/the_verity_gate.js` then checks, in the browser:
      * `navigator.webdriver` must not be true          (automation flag)
      * the UA family must not be `headlesschrome`      (default headless UA)
      * the claimed family/engine must match what the JS engine really is
        (userAgentData brands, window.chrome, CSS -moz-* support, ...).
    Stock headless Playwright Chromium fails the first two.

Approach: Camoufox, a Firefox build patched at the C++ level for stealth. It reports
`navigator.webdriver = false` without JS shims, and its generated fingerprint keeps the UA,
the Gecko engine features the gate probes (`-moz-appearance`, no `window.chrome`) and the
rest of navigator consistent - so the server's claim ("firefox") and the JS-detected engine
("gecko") agree. Camoufox drives the browser through the Playwright API, so pages/contexts
work as usual.
"""
from __future__ import annotations

import asyncio

from camoufox.async_api import AsyncCamoufox

from ..core import BASE_URL, Outcome, is_open, load_run
from ..http import httpx_client

CATEGORY = "Shattered Thresholds"
DOORS = {"the_sleeping_vault": "The Sleeping Vault", "the_verity_gate": "The Verity Gate"}


async def render(context, url: str, timeout_ms: int = 10_000) -> Outcome:
    page = await context.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded")
        try:  # the door opens asynchronously (fetch of open.html); wait for it, else keep sealed DOM
            await page.wait_for_function(
                "() => /slides open/i.test(document.querySelector('h1')?.textContent || '')",
                timeout=timeout_ms)
        except Exception:
            pass
        html = await page.content()
        return Outcome(resp.status if resp else 0, html)
    finally:
        await page.close()


def make_solver(slug: str):
    name, url = DOORS[slug], f"{BASE_URL}/{slug}"

    async def solve(requests: int, rps: float, headed: bool = False, **_):
        async with httpx_client() as naive:  # what a plain HTTP client sees
            naive_open = is_open((await naive.get(url)).text)

        async with AsyncCamoufox(headless=not headed, os="macos", locale="en-US") as browser:
            # A small pool of contexts (separate cookie jars/tabs) shared by the workers.
            contexts = [await browser.new_context() for _ in range(8)]
            probe = await contexts[0].new_page()
            await probe.goto(url)
            fingerprint = await probe.evaluate("""() => ({
                userAgent: navigator.userAgent, webdriver: navigator.webdriver,
                claim: document.getElementById('what-is-my-browser')?.textContent ?? null})""")
            await probe.close()
            counter = iter(range(10**9))

            async def attempt() -> Outcome:
                return await render(contexts[next(counter) % len(contexts)], url)

            report, outcomes = await load_run(name, CATEGORY, attempt, requests=requests, rps=rps,
                                              concurrency=len(contexts) * 2)

        extra = {"browser": "camoufox", **fingerprint, "plain_http_client_opened": naive_open}
        return report, outcomes, extra

    return name, solve


if __name__ == "__main__":  # quick manual check
    async def _main():
        for slug in DOORS:
            report, _, extra = await make_solver(slug)[1](3, 1)
            print(report.summary(), extra)
    asyncio.run(_main())
