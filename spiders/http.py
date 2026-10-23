"""HTTP client factories.

Two flavours are used on purpose:
* httpx      - plain Python TLS stack; enough when the check is purely header/cookie/rate based.
* curl_cffi  - BoringSSL/NSS impersonation; needed where the server fingerprints TLS (JA3/JA4)
               and HTTP/2 and compares it with the User-Agent the client claims.
"""
from __future__ import annotations

import httpx
from curl_cffi.requests import AsyncSession

CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def httpx_client(proxy: str | None = None, **kw) -> httpx.AsyncClient:
    limits = httpx.Limits(max_connections=32, max_keepalive_connections=32)
    return httpx.AsyncClient(http2=True, headers=BROWSER_HEADERS, proxy=proxy, limits=limits,
                             timeout=30, follow_redirects=True, **kw)


def impersonating_session(browser: str, proxy: str | None = None) -> AsyncSession:
    """A session whose TLS ClientHello, HTTP/2 SETTINGS and default headers all match `browser`.

    We deliberately do not override the User-Agent: curl_cffi sends the one that belongs
    to the impersonated build, so TLS fingerprint and UA can never disagree.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    return AsyncSession(impersonate=browser, proxies=proxies, timeout=30, max_clients=32)
