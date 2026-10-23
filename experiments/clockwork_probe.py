"""Measures The Clockwork Door's per-IP budget: knocks at a fixed gap and logs each status.

    uv run python -m experiments.clockwork_probe 12 8     # gap seconds, number of knocks
Wait >60 s of silence before running, otherwise leftover knocks from earlier skew the result.
Results observed (see README): burst -> 5 x 200 then 429; 8 s and 11 s gaps -> 5 x 200 then 429;
12 s gaps -> unlimited 200s. => 5 requests / 60 s sliding window, 429s counted.
"""
import datetime
import json
import sys
import time

import httpx

from spiders.core import BASE_URL, RESULTS_DIR

gap, n = float(sys.argv[1]), int(sys.argv[2])
log = []
with httpx.Client(headers={"User-Agent": "Mozilla/5.0"}) as c:
    t0 = time.monotonic()
    for _ in range(n):
        status = c.get(f"{BASE_URL}/the_clockwork_door").status_code
        log.append({"t": round(time.monotonic() - t0, 2), "at": datetime.datetime.now().isoformat(timespec="milliseconds"),
                    "status": status})
        print(log[-1], flush=True)
        time.sleep(gap)
out = RESULTS_DIR / "experiments"
out.mkdir(parents=True, exist_ok=True)
(out / f"clockwork_gap_{gap:g}s.json").write_text(json.dumps(log, indent=2))
