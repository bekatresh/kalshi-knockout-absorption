"""
Discovery helper: verify series tickers, build the champ<->match team-code
crosswalk, and auto-draft KNOCKOUT_MATCHES.

Usage:
    python -m src.discover --find-series worldcup     # search series
    python -m src.discover --champion                 # list champ markets
    python -m src.discover --crosswalk                 # print TEAM_CODE_MAP
    python -m src.discover --draft-matches            # draft settled knockouts

The draft prints a Python literal you can paste into src/config.py, with
winner/loser inferred from settlement and next_opponent_teams inferred from
each team's next chronological event in MATCH_SERIES (works because Kalshi
only creates an event once both participants are fixed -- so if a team's
winning match has no later event yet, its next opponent isn't determined
yet and next_opponent_teams comes back empty; fill it by hand from the
bracket in that case).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from typing import Optional

from .config import CHAMPION_SERIES, MATCH_SERIES
from .kalshi_client import KalshiPublic, dollars

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def find_series(client: KalshiPublic, keyword: str) -> None:
    # /series endpoint lists series; filter client-side
    data = client._get("/series", limit=1000)
    hits = [s for s in data.get("series", [])
            if keyword.lower() in json.dumps(s).lower()]
    for s in hits:
        print(f"{s.get('ticker'):<24} {s.get('title')}")
    if not hits:
        print("No series matched; try a different keyword or browse kalshi.com URLs.")


def list_champion_markets(client: KalshiPublic) -> None:
    for m in client.iter_markets(series_ticker=CHAMPION_SERIES):
        last = dollars(m, "last_price")
        print(f"{m['ticker']:<30} {m.get('yes_sub_title', ''):<20} "
              f"last={'n/a' if last is None else f'{last*100:.1f}c':<8} status={m.get('status')}")


def _team_name(m: dict) -> str:
    return (m.get("yes_sub_title") or "").replace(" advances", "").strip()


def build_team_crosswalk(client: KalshiPublic) -> dict[str, str]:
    """Map MATCH_SERIES ticker-suffix codes (e.g. "USA","BEL","ENG") to
    CHAMPION_SERIES ticker-suffix codes (e.g. "US","BE","GB") by joining on
    team name -- the two series use different country-code conventions."""
    champ_by_name = {}
    for m in client.iter_markets(series_ticker=CHAMPION_SERIES):
        champ_by_name[_team_name(m).lower()] = m["ticker"].rsplit("-", 1)[-1]

    crosswalk = {}
    for ev in client.iter_events(MATCH_SERIES):
        for m in client.iter_markets(event_ticker=ev["event_ticker"]):
            code = m["ticker"].rsplit("-", 1)[-1]
            champ_code = champ_by_name.get(_team_name(m).lower())
            if champ_code:
                crosswalk[code] = champ_code
    return crosswalk


def print_crosswalk(client: KalshiPublic) -> None:
    cw = build_team_crosswalk(client)
    print("TEAM_CODE_MAP = {  # match-code -> champ-code")
    for k, v in sorted(cw.items()):
        print(f'    "{k}": "{v}",')
    print("}")


def _date_key(event_ticker: str) -> tuple[int, int, int]:
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", event_ticker)
    yy, mon, dd = m.groups()
    return (int(yy), MONTHS[mon], int(dd))


def draft_matches(client: KalshiPublic) -> None:
    """Pair up every settled MATCH_SERIES event into a winner/loser match,
    and infer next_opponent_teams from each winner's next chronological
    appearance across all events."""
    events = list(client.iter_events(MATCH_SERIES))
    events.sort(key=lambda e: _date_key(e["event_ticker"]))

    event_markets: dict[str, list[dict]] = {}
    for ev in events:
        event_markets[ev["event_ticker"]] = list(
            client.iter_markets(event_ticker=ev["event_ticker"]))

    # per-team chronological timeline of (event_ticker, other_team_code)
    timeline: dict[str, list[str]] = {}
    for ev in events:
        et = ev["event_ticker"]
        ms = event_markets[et]
        if len(ms) != 2:
            continue
        codes = [m["ticker"].rsplit("-", 1)[-1] for m in ms]
        for code in codes:
            timeline.setdefault(code, []).append(et)

    drafted = []
    for ev in events:
        et = ev["event_ticker"]
        ms = event_markets[et]
        if len(ms) != 2:
            continue
        if any(m.get("status") != "finalized" or m.get("result") not in ("yes", "no")
               for m in ms):
            continue  # not settled yet -- skip (that's the live trade, not backtest data)

        winner_m = next(m for m in ms if m.get("result") == "yes")
        loser_m = next(m for m in ms if m.get("result") == "no")
        w = winner_m["ticker"].rsplit("-", 1)[-1]
        l = loser_m["ticker"].rsplit("-", 1)[-1]

        settle_iso = winner_m.get("settlement_ts") or winner_m.get("close_time")
        # Kalshi doesn't expose actual kickoff time; approximate as
        # settlement - 2.5h (regulation + stoppage + halftime, roughly).
        # Fine given PRE_WINDOW_S=6h -- refine by hand from the real match
        # schedule if you need tighter pre-kickoff snapshots.
        # strip fractional seconds -- Kalshi's precision varies and py3.9's
        # fromisoformat only accepts 0, 3, or 6 fractional digits
        settle_clean = re.sub(r"\.\d+", "", settle_iso)
        settle_dt = dt.datetime.fromisoformat(settle_clean.replace("Z", "+00:00"))
        kickoff_iso = (settle_dt - dt.timedelta(hours=2.5)).isoformat().replace("+00:00", "Z")

        team_timeline = timeline.get(w, [])
        idx = team_timeline.index(et)
        next_opponent_teams: list[str] = []
        if idx + 1 < len(team_timeline):
            next_et = team_timeline[idx + 1]
            next_ms = event_markets[next_et]
            next_opponent_teams = [m["ticker"].rsplit("-", 1)[-1] for m in next_ms
                                    if m["ticker"].rsplit("-", 1)[-1] != w]

        drafted.append({
            "match_id": et,
            "match_market_ticker": winner_m["ticker"],
            "kickoff_iso": kickoff_iso,
            "settle_iso": settle_iso,
            "winner": w,
            "loser": l,
            "winner_pre_match_prob": None,
            "next_opponent_teams": next_opponent_teams,
        })

    print(f"# {len(drafted)} settled knockout matches found (out of "
          f"{len(events)} {MATCH_SERIES} events)\n"
          f"# next_opponent_teams == [] means the adjacent bracket tie "
          f"hadn't settled yet as of this run -- fill by hand.\n"
          "KNOCKOUT_MATCHES = [")
    for d in drafted:
        print("    " + json.dumps(d) + ",")
    print("]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--find-series", metavar="KEYWORD")
    ap.add_argument("--champion", action="store_true")
    ap.add_argument("--crosswalk", action="store_true")
    ap.add_argument("--draft-matches", action="store_true")
    args = ap.parse_args()

    c = KalshiPublic()
    if args.find_series:
        find_series(c, args.find_series)
    if args.champion:
        list_champion_markets(c)
    if args.crosswalk:
        print_crosswalk(c)
    if args.draft_matches:
        draft_matches(c)
