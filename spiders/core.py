"""Shared plumbing for every puzzle: rate limiting, load runs, result capture."""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

BASE_URL = "https://bo7.online"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# Markers the site uses on a solved page ("the door opened or the mirror aligned").
OPEN_MARKERS = ("The door slides open", "The Mirror Aligns")


def is_open(html: str) -> bool:
    return any(m in html for m in OPEN_MARKERS)


def headline(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


class RateLimiter:
    """Spaces request *starts* evenly at `rps` per second, shared by all workers.

    Using a schedule (rather than sleep-after-response) keeps the rate stable
    regardless of latency, so `rps` is what the server actually sees.
    """

    def __init__(self, rps: float):
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            await asyncio.sleep(start - now)


@dataclass
class Outcome:
    status: int
    html: str
    note: str = ""


@dataclass
class RunReport:
    puzzle: str
    category: str
    requests: int
    target_rps: float
    achieved_rps: float = 0.0
    opened: int = 0
    statuses: dict = field(default_factory=dict)
    headlines: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def solved(self) -> bool:
        return self.requests > 0 and self.opened == self.requests

    def summary(self) -> str:
        mark = "SOLVED" if self.solved else ("PARTIAL" if self.opened else "FAILED")
        return (f"[{mark:7}] {self.category} / {self.puzzle}: {self.opened}/{self.requests} opened "
                f"@ {self.achieved_rps:.2f} req/s (target {self.target_rps}) statuses={self.statuses}")


async def load_run(
    puzzle: str,
    category: str,
    attempt: Callable[[], Awaitable[Outcome]],
    *,
    requests: int,
    rps: float,
    concurrency: int | None = None,
) -> tuple[RunReport, list[Outcome]]:
    """Fire `requests` attempts at `rps`, `concurrency` in flight at most.

    Default concurrency is ~0.5 s worth of requests, so latency never caps the target rate.
    """
    concurrency = concurrency or max(8, int(rps / 2))
    limiter = RateLimiter(rps)
    sem = asyncio.Semaphore(concurrency)
    starts: list[float] = []

    async def one() -> Outcome:
        async with sem:
            await limiter.wait()
            starts.append(time.monotonic())
            try:
                return await attempt()
            except Exception as exc:  # network errors count as failures, not crashes
                return Outcome(0, "", f"{type(exc).__name__}: {exc}")

    t0 = time.monotonic()
    outcomes = await asyncio.gather(*(one() for _ in range(requests)))
    elapsed = time.monotonic() - t0

    report = RunReport(puzzle, category, requests, rps, elapsed_s=round(elapsed, 2))
    # Rate the server saw: request starts per second (n-1 intervals between n starts).
    span = max(starts) - min(starts) if len(starts) > 1 else 0.0
    report.achieved_rps = round((len(starts) - 1) / span, 2) if span else 0.0
    report.opened = sum(is_open(o.html) for o in outcomes)
    report.statuses = dict(Counter(str(o.status) for o in outcomes))
    report.headlines = dict(Counter(headline(o.html) or "(none)" for o in outcomes))
    report.notes = sorted({o.note for o in outcomes if o.note})[:5]
    return report, outcomes


def save(report: RunReport, outcomes: list[Outcome], slug: str, extra: dict | None = None,
         tag: str | None = None) -> Path:
    """Store the report plus one opened and (if any) one blocked HTML sample."""
    out = RESULTS_DIR / tag / slug if tag else RESULTS_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    opened = next((o for o in outcomes if is_open(o.html)), None)
    blocked = next((o for o in outcomes if o.html and not is_open(o.html)), None)
    if opened:
        (out / "opened.html").write_text(opened.html, encoding="utf-8")
    if blocked:
        (out / "blocked.html").write_text(blocked.html, encoding="utf-8")
    data = asdict(report) | {"solved": report.solved, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if extra:
        data |= extra
    (out / "report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
