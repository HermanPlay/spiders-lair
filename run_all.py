"""Run the bo7.online puzzle scrapers and store evidence under results/.

    uv run run_all.py                          # every puzzle, default load
    uv run run_all.py -p the_silver_veil -n 200 --rps 20
    uv run run_all.py --tag stress -n 1000 --rps 100 -p the_silver_veil   # scale test
    uv run run_all.py --mx-proxy http://user:pass@pr.oxylabs.io:7777   # enables The Exiled Door
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from spiders.core import RESULTS_DIR, save
from spiders.puzzles import clockwork_door, door_of_echoed_steps, exiled_door, mirrors, shattered_thresholds

# slug -> (solver, default requests, default req/s)
PUZZLES = {
    door_of_echoed_steps.SLUG: (door_of_echoed_steps.solve, 100, 20),
    clockwork_door.SLUG: (clockwork_door.solve, clockwork_door.DEFAULT_REQUESTS, clockwork_door.PULSE_RPS),
    exiled_door.SLUG: (exiled_door.solve, 30, 5),
    **{slug: (mirrors.make_solver(slug)[1], 100, 20) for slug in mirrors.MIRRORS},
    **{slug: (shattered_thresholds.make_solver(slug)[1], 20, 4) for slug in shattered_thresholds.DOORS},
}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--puzzle", action="append", choices=PUZZLES, help="run only these (repeatable)")
    ap.add_argument("-n", "--requests", type=int, help="requests per puzzle (overrides defaults)")
    ap.add_argument("--rps", type=float, help="target requests/second (overrides defaults)")
    ap.add_argument("--mx-proxy", help="Mexican proxy URL for The Exiled Door (or env MX_PROXY)")
    ap.add_argument("--tag", help="store results under results/<tag>/ (e.g. stress runs)")
    ap.add_argument("--headed", action="store_true", help="show the browser for Shattered Thresholds")
    args = ap.parse_args()

    summary = []
    for slug in args.puzzle or PUZZLES:
        solve, n, rps = PUZZLES[slug]
        try:
            report, outcomes, extra = await solve(args.requests or n, args.rps or rps,
                                                  mx_proxy=args.mx_proxy, headed=args.headed)
        except Exception as exc:
            print(f"[SKIPPED] {slug}: {exc}")
            summary.append({"puzzle": slug, "solved": False, "error": str(exc)})
            continue
        out = save(report, outcomes, slug, extra, args.tag)
        print(report.summary(), f"-> {out.relative_to(RESULTS_DIR.parent)}")
        summary.append({"puzzle": slug, "solved": report.solved, "opened": report.opened,
                        "requests": report.requests, "achieved_rps": report.achieved_rps})

    summary_dir = RESULTS_DIR / args.tag if args.tag else RESULTS_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "summary.json").write_text(json.dumps(
        {"run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": summary}, indent=2))
    return 0 if all(s["solved"] for s in summary) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
