# Spider's Lair — bo7.online scraping puzzles

Scrapers for the eight puzzles on [bo7.online](https://bo7.online), with the evidence that each
door opened / mirror aligned, and the experiments used to work out each blocking mechanism.

| Category | Puzzle | Blocking mechanism | Tool | Result |
|---|---|---|---|---|
| Mysterious Passages | The Door of Echoed Steps | Session cookie set by the lobby page | httpx | ✅ 1000/1000 @ 100 req/s |
| Mysterious Passages | The Clockwork Door | Per-IP rate limit: 5 req / 60 s sliding window, 429s count | httpx + per-IP pacer | ✅ 8/8 (+6/6 when asked for 50 req/s) |
| Mysterious Passages | The Exiled Door | IP geolocation: Mexico only | httpx + MX proxy | ✅ 30/30 @ 5 req/s, 200/200 @ ~17.6 req/s |
| Curious Reflections | The Fractured Mirror | TLS fingerprint + browser-specific headers must match the UA | curl_cffi (Chrome) | ✅ 1000/1000 @ 100 req/s |
| Curious Reflections | The Silver Veil | TLS fingerprint must strictly match the UA's browser | curl_cffi (Chrome) | ✅ 1000/1000 @ 100 req/s |
| Curious Reflections | The Mirrored Gaze | Firefox User-Agent only | curl_cffi (Firefox) | ✅ 1000/1000 @ 100 req/s |
| Shattered Thresholds | The Sleeping Vault | Content is loaded by JavaScript | Camoufox | ✅ 60/60 @ ~8.8 pages/s |
| Shattered Thresholds | The Verity Gate | JS checks `navigator.webdriver`, headless UA and engine-vs-UA consistency | Camoufox | ✅ 60/60 @ ~8.4 pages/s |

## Running it

```bash
uv sync                                   # installs deps from pyproject.toml / uv.lock into .venv
uv run python -m camoufox fetch          # downloads the Camoufox browser

uv run run_all.py                         # all puzzles, default load
uv run run_all.py -p the_silver_veil -n 1000 --rps 100 --tag stress
MX_PROXY=https://149.88.22.33:9443 uv run run_all.py -p the_exiled_door
CLOCKWORK_PROXIES=http://p1,http://p2 uv run run_all.py -p the_clockwork_door --rps 1
```

`--rps` is enforced by a shared scheduler (`spiders/core.py::RateLimiter`) that spaces request
*starts* evenly, so it is the rate the server actually sees; concurrency grows with the target
so latency does not cap it. Every run writes, per puzzle, `results/<puzzle>/report.json`
(status counts, headlines, achieved req/s, puzzle-specific evidence) plus `opened.html`
(a solved page) and/or `blocked.html`.

## Layout

```
run_all.py                      CLI: runs puzzles, saves evidence
spiders/core.py                 rate limiter, load runner, "is it open?" detection, result saving
spiders/http.py                 httpx (plain TLS) and curl_cffi (browser-impersonating TLS) factories
spiders/puzzles/*.py            one module per puzzle / puzzle group; docstrings explain each mechanism
experiments/mirror_matrix.py    TLS x User-Agent x header matrix behind the mirror findings
experiments/clockwork_probe.py  fixed-gap knocking used to measure the Clockwork budget
results/                        reports + HTML from the runs (main run, stress/, experiments/, recon/)
```

## Approach, puzzle by puzzle

I began by fetching every page with a plain client and reading the response *and headers*
(`results/recon/`). The hints in the copy, together with a few debug headers the server leaves in,
pointed at each mechanism. I then confirmed each one with controlled experiments before writing
the scraper. I used a browser only where JavaScript has to run.

### Mysterious Passages

**The Door of Echoed Steps** ("the trace of a traveler's past", "ancient tokens"). The home page
sets `wormhole_token=galactic-cookie-42`. Without it the door is a 403; a Referer alone does not
help. The scraper visits `/` first and reuses the cookie jar, so it would still work if the token
rotated. The report records `naive_status_without_cookie: 403`.

**The Clockwork Door** ("each knock must match its hidden pulse"). The door opens for anyone but
answers 429 "The Door Trembles" when knocked too often. I measured the limit with timestamped
probes (`results/experiments/clockwork_observations.json`):

| Spacing | Outcome |
|---|---|
| back-to-back burst | exactly 5 × 200, then 429 |
| 8 s | 5 × 200, 6th (+42 s) → 429 |
| 11 s | 5 × 200, 6th (+55.7 s) → 429 |
| 12 s | every knock 200 (6th at +60.6 s) |

So the budget is **5 requests per 60 s sliding window, per source IP**. Changing the UA, TLS
stack or cookies does not reset it. Rejected knocks count too: polling once a second kept the
door shut for more than 7 minutes. The solver gives every exit IP its own pacer at one knock per
12.5 s, so no `--rps` value can push one IP over the budget. On an unexpected 429 the exit goes
silent for a full window before retrying. Throughput scales across IPs: with *N* proxies in
`CLOCKWORK_PROXIES` the ceiling is *N*/12.5 req/s. The stress run asked for 50 req/s; the pacer
held it at 0.08 req/s and all 6 knocks opened.

**The Exiled Door** ("a language not your own", "those who come from beyond"). Each response
carries the header `request-country-is-mx: False`, so the door geolocates the client IP and
only opens for Mexico. Spoofed `X-Forwarded-For`, `X-Real-IP`, `CF-IPCountry` and
`Accept-Language` headers made no difference. The solver sends traffic through a proxy given in
`--mx-proxy`/`MX_PROXY` (for example Oxylabs with country `MX`), reads the header to confirm the
exit is Mexican, then runs the load test.

The solved run used a free public HTTPS proxy in Querétaro (`https://149.88.22.33:9443`).
Through it the header flips to `True` and the door answers "The Exiled Door Resonates"
(`doors_open.jpg`, "¡bienvenido a mi telaraña!"). The run opened 30/30 at 5 req/s, and the
stress run 200/200 at about 17.6 req/s; the proxy's ~0.5 s latency is the ceiling there. Its
TLS certificate does not match its IP, so `spiders/http.py` skips verification for the hop to
the proxy only. The tunnelled TLS session to bo7.online is still fully verified. The report
keeps the direct attempt (`direct_status: 403`, `direct_geo_header: False`) for contrast; the
blocked page is in `results/recon/the_exiled_door.html`.

### Curious Reflections

All three mirrors return 403 to Python's TLS stack with a Chrome UA. `/tls_info` shows the server
computes a JA3 hash for each connection. `experiments/mirror_matrix.py` crosses TLS stack
(Python, or curl_cffi impersonating Chrome, Firefox or Safari) with User-Agent, then strips real
browser headers one at a time on a fresh connection each time
(`results/experiments/mirror_matrix.json`):

| TLS + UA | Fractured | Silver | Gaze |
|---|---|---|---|
| Python + Chrome UA | 403 | 403 | 403 |
| Python + Firefox UA | 403 | 403 | **200** |
| Python + Safari UA | **200** | 403 | 403 |
| Chrome TLS + Chrome UA (full headers) | **200** | **200** | 403 |
| Chrome TLS + Firefox UA | 403 | 403 | **200** |
| Firefox TLS + Firefox UA (full headers) | **200** | **200** | **200** |
| Safari TLS (curl_cffi) + any UA | 403 | 403 | 403 unless Firefox UA |

* **The Fractured Mirror** ("breaks when the voice is unnatural"): the TLS family and the
  header set must both fit the UA. Removing `Accept-Encoding` or `Priority` from real Chrome
  headers, or `Accept-Encoding`, `Priority` or `TE` from real Firefox headers, gives a 403. The
  `sec-ch-ua*`, `sec-fetch-*`, `Accept` and `Accept-Language` headers are optional. Its TLS check
  is loose: Python TLS with a Safari UA passes, since Safari sends no `Priority` header.
* **The Silver Veil** ("a perfect balance of trust"): TLS and UA must match exactly. Any
  cross-pairing fails, and so does Python TLS with any UA. Other headers and HTTP version are
  ignored.
* **The Mirrored Gaze** ("the right eyes"): only a Firefox UA is accepted.

The scrapers use curl_cffi impersonation without touching the UA, so TLS ClientHello, HTTP/2
SETTINGS, header order and UA all come from one real browser build. The two Chrome-checking
mirrors use Chrome. The Gaze uses Firefox: it would pass on a Firefox UA alone, but a fully
consistent Firefox fingerprint would also pass the stricter checks if the mirror tightened. The
curl_cffi Safari profile is not accepted by these mirrors, so I did not use it.

### Shattered Thresholds (the only puzzles that need a browser)

**The Sleeping Vault** ("shows nothing… until you truly look"). The server always returns the
sealed door. An inline script then fetches `/resources/open.html` and swaps it in, so an HTTP
client never sees the door open. Camoufox renders the page and waits for the "slides open"
headline. `opened.html` holds the rendered DOM.

**The Verity Gate** ("breaks only for what is authentic"). The server parses the UA into
`<script id="what-is-my-browser">{"family": …, "major": …}</script>`, and
`/resources/the_verity_gate.js` (saved in `results/recon/verity.js`) fails the page if any of
these hold:
* `navigator.webdriver === true`;
* the UA family is `headlesschrome`;
* the claimed engine does not match the real one, judged by `userAgentData` brands,
  `window.chrome` and `-moz-` CSS support.

During exploration, stock headless Playwright Chromium failed the first two checks
(`webdriver: true`, server claim `headlesschrome`). The scrapers use
[Camoufox](https://camoufox.com), a Firefox build patched in C++ rather than with JS shims, so
`navigator.webdriver` is false. Its generated fingerprint keeps the UA and the Gecko engine
features in agreement. The server claims `{"family": "firefox"}`, the gate's JS detects `gecko`,
and the door opens. Each report records the UA and `webdriver` value the page saw. Eight
browser contexts are shared by the workers so page loads run in parallel. On this laptop the
stress run reached about 8.5 of the 10 requested pages/s, limited by local rendering.

## Notes

* The `/advanced/basic`, `/advanced/machine` and `/tls_info` pages are informational fingerprint
  collectors. They showed what the server can see (webdriver flag, canvas/audio/GPU/voice lies,
  JA3) and helped choose what to keep consistent.
* `robots.txt` disallows everything. I scraped anyway because the site exists for this exercise.
  I kept the load modest apart from the deliberate stress runs, and the Clockwork scraper
  respects the server's budget rather than fighting it.
