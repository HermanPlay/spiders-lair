"""Mysterious Passages / The Exiled Door

Clue: "hums in a language not your own - the walls welcome only those who come from beyond".

Finding: every response carries the debug header `request-country-is-mx: False`. The door
geolocates the *source IP* and only opens for Mexico. Spoofing headers (X-Forwarded-For,
X-Real-IP, CF-IPCountry, Accept-Language: es-MX) changes nothing, so the request has to really
egress from a Mexican IP.

Approach: route the traffic through a Mexican proxy (e.g. Oxylabs residential/datacenter with
country targeting `cc-MX`). The proxy URL comes from `--mx-proxy` or the `MX_PROXY` env var.
We verify the server agrees (`request-country-is-mx: True`) before running the load test.
"""
import os

from ..core import BASE_URL, Outcome, load_run
from ..http import httpx_client

SLUG, CATEGORY, NAME = "the_exiled_door", "Mysterious Passages", "The Exiled Door"
PATH = f"{BASE_URL}/{SLUG}"
GEO_HEADER = "request-country-is-mx"


async def solve(requests: int, rps: float, mx_proxy: str | None = None, **_):
    mx_proxy = mx_proxy or os.environ.get("MX_PROXY")

    async with httpx_client() as direct:
        r = await direct.get(PATH)
        extra = {"direct_status": r.status_code, "direct_geo_header": r.headers.get(GEO_HEADER)}

    if not mx_proxy:
        # No Mexican exit available: record the direct (blocked) attempt as evidence and stop.
        extra["skipped"] = "no MX proxy configured: pass --mx-proxy or set MX_PROXY"
        report, outcomes = await load_run(NAME, CATEGORY, lambda: _get(PATH), requests=1, rps=1)
        return report, outcomes, extra

    async with httpx_client(mx_proxy) as client:
        probe = await client.get(PATH)
        extra["proxy_geo_header"] = probe.headers.get(GEO_HEADER)

        async def attempt() -> Outcome:
            r = await client.get(PATH)
            return Outcome(r.status_code, r.text, "" if r.headers.get(GEO_HEADER) == "True" else "non-MX exit")

        report, outcomes = await load_run(NAME, CATEGORY, attempt, requests=requests, rps=rps)
    return report, outcomes, extra


async def _get(url: str) -> Outcome:
    async with httpx_client() as c:
        r = await c.get(url)
        return Outcome(r.status_code, r.text, f"{GEO_HEADER}: {r.headers.get(GEO_HEADER)}")
