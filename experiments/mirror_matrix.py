"""Reproduces the Curious Reflections experiments: TLS stack x User-Agent x headers.

    python -m experiments.mirror_matrix
Writes results/experiments/mirror_matrix.json.
"""
import asyncio
import json

import httpx
from curl_cffi.requests import AsyncSession

from spiders.core import BASE_URL, RESULTS_DIR

MIRRORS = ["the_fractured_mirror", "the_silver_veil", "the_mirrored_gaze"]
UAS = {
    "chrome_ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "firefox_ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "safari_ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "python_ua": "python-httpx/0.28",
}


async def statuses(get, mirrors=MIRRORS) -> dict:
    out = {}
    for m in mirrors:
        out[m] = (await get(f"{BASE_URL}/{m}")).status_code
        await asyncio.sleep(0.2)
    return out


async def main():
    rows = []
    # 1. Python TLS (httpx) with every UA -> expected all 403
    for ua_name, ua in UAS.items():
        async with httpx.AsyncClient(http2=True, headers={"User-Agent": ua}) as c:
            rows.append({"tls": "python/httpx", "ua": ua_name, **await statuses(c.get)})
    # 2. Browser TLS (curl_cffi) with own UA and with foreign UAs
    for browser in ["chrome", "firefox", "safari"]:
        async with AsyncSession(impersonate=browser) as s:
            rows.append({"tls": browser, "ua": "own (impersonated)", **await statuses(s.get)})
            for ua_name, ua in UAS.items():
                rows.append({"tls": browser, "ua": ua_name,
                             **await statuses(lambda u: s.get(u, headers={"User-Agent": ua}))})
    # 3. Header ablation (real browser headers minus one). A fresh session per request, since a
    #    session's own defaults would otherwise be merged back in.
    ablation = {}
    for browser in ["chrome", "firefox"]:
        async with AsyncSession(impersonate=browser) as s:
            sent = (await s.get("https://tls.peet.ws/api/all")).json()
        frame = next(f for f in sent["http2"]["sent_frames"] if f.get("frame_type") == "HEADERS")
        full = dict(h.split(": ", 1) for h in frame["headers"] if not h.startswith(":"))
        for drop in [None, *full]:
            hdrs = {k: v for k, v in full.items() if k != drop}
            async with AsyncSession(impersonate=browser, default_headers=False) as s:
                ablation[f"{browser}: {'drop ' + drop if drop else 'all headers'}"] = await statuses(
                    lambda u: s.get(u, headers=hdrs), MIRRORS[:2])

    out = RESULTS_DIR / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mirror_matrix.json").write_text(json.dumps({"matrix": rows, "fractured_header_ablation": ablation}, indent=2))
    w = max(len(r["tls"]) + len(r["ua"]) for r in rows) + 3
    for r in rows:
        print(f"{r['tls'] + ' + ' + r['ua']:<{w}}", *(r[m] for m in MIRRORS))
    for k, v in ablation.items():
        print(f"{k:<40}", *v.values())


if __name__ == "__main__":
    asyncio.run(main())
