"""Mysterious Passages / The Clockwork Door

Clue: "a slow, steady tapping echoes from within - each knock must match its hidden pulse".

Findings (timestamped probes, see README):
  * The door is open to any client, but it is rate limited **per source IP** (changing UA, TLS
    stack or cookies does not reset it) and answers 429 "The Door Trembles" when exceeded.
  * Budget: 5 requests per ~60 s sliding window. 12 s spacing runs indefinitely; 8 s spacing
    fails on the 6th knock; a burst gets exactly 5 through.
  * Rejected knocks count too: hammering a 429 keeps the door shut (a 1 req/s poll stayed blocked
    for 7+ minutes). The only way back is a full quiet window.

Approach - knock to the pulse:
  * Every exit IP gets its own pacer that spaces requests >= PULSE_INTERVAL apart, so a single
    IP never exceeds the budget no matter how high `--rps` is set.
  * On an unexpected 429 the exit goes completely silent for COOLDOWN before retrying (polling
    would only extend the block).
  * Throughput scales horizontally: pass several proxies (`CLOCKWORK_PROXIES`, comma separated)
    and the effective rate becomes len(exits) / PULSE_INTERVAL. Without proxies it is 1/12 req/s.
"""
from __future__ import annotations

import asyncio
import os
import time

from ..core import BASE_URL, Outcome, load_run
from ..http import httpx_client

SLUG, CATEGORY, NAME = "the_clockwork_door", "Mysterious Passages", "The Clockwork Door"
PATH = f"{BASE_URL}/{SLUG}"

BUDGET, WINDOW = 5, 60.0                    # 5 knocks per 60 s per IP
PULSE_INTERVAL = WINDOW / BUDGET + 0.5      # 12.5 s - a little margin for clock/latency jitter
PULSE_RPS = round(1 / PULSE_INTERVAL, 3)
COOLDOWN = WINDOW + 5
MAX_RETRIES = 2
DEFAULT_REQUESTS = 8


class Exit:
    """One egress IP (direct connection or a proxy) with its own pulse."""

    def __init__(self, proxy: str | None):
        self.label = "direct" if proxy is None else proxy.split("@")[-1]
        self.client = httpx_client(proxy)
        self.next_free = 0.0


class ExitPool:
    def __init__(self, proxies: list[str | None]):
        self.exits = [Exit(p) for p in proxies]
        self._lock = asyncio.Lock()

    async def acquire(self) -> Exit:
        """Reserve the exit that is free soonest and wait for its next beat."""
        async with self._lock:
            ex = min(self.exits, key=lambda e: e.next_free)
            now = time.monotonic()
            start = max(now, ex.next_free)
            ex.next_free = start + PULSE_INTERVAL
        if start > now:
            await asyncio.sleep(start - now)
        return ex

    def penalise(self, ex: Exit) -> None:
        ex.next_free = max(ex.next_free, time.monotonic() + COOLDOWN)

    async def aclose(self) -> None:
        await asyncio.gather(*(e.client.aclose() for e in self.exits))


def configured_proxies() -> list[str | None]:
    raw = os.environ.get("CLOCKWORK_PROXIES", "")
    proxies = [p.strip() for p in raw.split(",") if p.strip()]
    return proxies or [None]


async def solve(requests: int, rps: float, **_):
    pool = ExitPool(configured_proxies())
    retries = 0

    async def attempt() -> Outcome:
        nonlocal retries
        for i in range(MAX_RETRIES + 1):
            ex = await pool.acquire()
            r = await ex.client.get(PATH)
            if r.status_code != 429:
                return Outcome(r.status_code, r.text)
            pool.penalise(ex)  # go quiet for a whole window instead of hammering
            retries += 1
        return Outcome(r.status_code, r.text, "still 429 after cooldown retries")

    # The user's --rps is an upper bound; the pulse of each exit is the real governor.
    ceiling = len(pool.exits) / PULSE_INTERVAL
    effective = min(rps, ceiling)
    try:
        report, outcomes = await load_run(NAME, CATEGORY, attempt, requests=requests,
                                          rps=effective, concurrency=len(pool.exits))
    finally:
        await pool.aclose()
    extra = {"exits": [e.label for e in pool.exits], "pulse_interval_s": PULSE_INTERVAL,
             "budget": f"{BUDGET} req / {WINDOW:.0f}s per IP", "requested_rps": rps,
             "rate_ceiling_rps": round(ceiling, 3), "retries_after_429": retries}
    return report, outcomes, extra
