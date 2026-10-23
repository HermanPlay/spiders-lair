"""Curious Reflections - the three mirrors.

All three answer 403 "The Mirror Cracks" to an ordinary Python client sending a Chrome
User-Agent, because the server fingerprints the connection itself (`/tls_info` exposes the JA3
it computes). Experiments (`python -m experiments.mirror_matrix`, results/experiments/) showed:

The Fractured Mirror - "its reflection breaks when the voice is unnatural"
    The "voice" is the TLS ClientHello *and* the header set, both judged against the UA:
      * Chrome/Firefox TLS must come with a Chrome/Firefox UA respectively;
      * the browser-specific headers must be there: `Accept-Encoding` and `Priority` for
        Chrome, plus `TE: trailers` for Firefox. Dropping any one of them -> 403, while
        sec-ch-ua*, sec-fetch-*, Accept, Accept-Language are optional.
    Its TLS check is a loose family heuristic: Python's OpenSSL hello paired with a *Safari* UA
    (Safari sends no Priority header) slips through - a weakness, not something we rely on.

The Silver Veil - "a perfect balance of trust will make it clear"
    Balance = the TLS fingerprint and the claimed User-Agent must agree, strictly: Chrome TLS +
    Chrome UA and Firefox TLS + Firefox UA pass; any cross-pairing, and Python TLS with any UA
    (Safari included), fails. It ignores the other headers (UA alone is enough) and HTTP version.

The Mirrored Gaze - "it opens only when met by the right eyes"
    Only a Firefox User-Agent is accepted ("the right eyes"). Chrome/Safari/Edge are refused
    even with perfect TLS. We send a genuinely consistent Firefox fingerprint rather than just
    the UA string, so the request would also survive the stricter checks of the other mirrors.

Approach: curl_cffi impersonation, which keeps TLS, HTTP/2 SETTINGS, header order and UA in
lock-step with one real browser build.
"""
from ..core import BASE_URL, Outcome, load_run
from ..http import CHROME_UA, httpx_client, impersonating_session

CATEGORY = "Curious Reflections"
MIRRORS = {
    # slug: (display name, browser to impersonate)
    "the_fractured_mirror": ("The Fractured Mirror", "chrome"),
    "the_silver_veil": ("The Silver Veil", "chrome"),
    "the_mirrored_gaze": ("The Mirrored Gaze", "firefox"),
}


def make_solver(slug: str):
    name, browser = MIRRORS[slug]
    url = f"{BASE_URL}/{slug}"

    async def solve(requests: int, rps: float, proxy: str | None = None, **_):
        async with httpx_client(proxy) as naive:  # Python TLS + Chrome UA -> expected 403
            naive_status = (await naive.get(url, headers={"User-Agent": CHROME_UA})).status_code

        async with impersonating_session(browser, proxy) as s:
            tls = (await s.get(f"{BASE_URL}/tls_info")).json()

            async def attempt() -> Outcome:
                r = await s.get(url)
                return Outcome(r.status_code, r.text)

            report, outcomes = await load_run(name, CATEGORY, attempt, requests=requests, rps=rps)
        extra = {"impersonated_browser": browser, "server_seen_ja3": tls.get("ja3"),
                 "naive_status_python_tls": naive_status}
        return report, outcomes, extra

    return name, solve
