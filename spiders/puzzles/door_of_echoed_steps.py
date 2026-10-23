"""Mysterious Passages / The Door of Echoed Steps

Clue: "it listens for the trace of a traveler's past" / "only those who carry the ancient tokens".

Finding: the home page sets `wormhole_token=galactic-cookie-42`. The door returns 403 unless that
cookie is presented, i.e. the visitor must have "walked through" the lobby first. A Referer alone
does not help.

Approach: plain HTTP client, visit `/` once so the cookie jar picks the token up, then reuse the
session for every request. Nothing is hardcoded - if the token value rotates we still get it.
"""
from ..core import BASE_URL, Outcome, load_run
from ..http import httpx_client

SLUG, CATEGORY, NAME = "the_door_of_echoed_steps", "Mysterious Passages", "The Door of Echoed Steps"
PATH = f"{BASE_URL}/{SLUG}"


async def solve(requests: int, rps: float, **_):
    async with httpx_client() as naive:
        naive_status = (await naive.get(PATH)).status_code

    async with httpx_client() as client:
        await client.get(f"{BASE_URL}/")  # picks up the wormhole_token cookie
        cookies = dict(client.cookies)

        async def attempt() -> Outcome:
            r = await client.get(PATH, headers={"Referer": f"{BASE_URL}/"})
            return Outcome(r.status_code, r.text)

        report, outcomes = await load_run(NAME, CATEGORY, attempt, requests=requests, rps=rps)
    return report, outcomes, {"naive_status_without_cookie": naive_status, "cookies_from_lobby": cookies}
