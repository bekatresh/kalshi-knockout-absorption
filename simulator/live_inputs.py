"""
Live Kalshi pull -> (TEAMS, MARKET_CHAMP, MATCH_MARKETS) for Simulator,
covering the real remaining bracket (simulator/bracket_2026.py).

Usage:
    from simulator.live_inputs import build_live_inputs
    teams, market_champ, match_markets, raw_champ_sum = build_live_inputs()
    sim = Simulator(teams, market_champ, match_markets)

MATCH_MARKETS deliberately spans TWO rounds at once: the 6 already-settled
Round-of-16 results (pinned 0.0/1.0, from bracket_2026.SETTLED_R16_OVERRIDES),
the 2 still-live Round-of-16 fixtures (Argentina-Egypt, Switzerland-Colombia),
and the 3 live Quarterfinal fixtures (France-Morocco, Spain-Belgium,
Norway-England) that already exist because their Round-of-16 feeders settled.
Bracket.champ_probs' pairwise-override mechanism works on team-index pairs
directly, not just round-0 slots, so mixing rounds like this is valid -- see
bracket_2026.py's DP trace in the module docstring.

Raw-price-sum bookkeeping (interpretation warning from SIMULATOR.md): champ
probs inside Simulator are renormalized to sum to 1 over just the 16 bracket
teams. `raw_champ_sum` is the sum of the RAW (un-renormalized) Kalshi mid
prices across those 16 teams -- multiply model probabilities by this to map
back to Kalshi price-space cents for a trade signal.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import CHAMPION_SERIES, MATCH_SERIES, TEAM_CODE_MAP  # noqa: E402
from src.kalshi_client import KalshiPublic, dollars  # noqa: E402

from .bracket_2026 import LIVE_R16_FIXTURES, SETTLED_R16_OVERRIDES, TEAMS_16  # noqa: E402

# Live Quarterfinal fixtures created once their Round-of-16 feeders settled.
# Stored in the tuple order the deliverable queries by (see run_live.py).
LIVE_QF_FIXTURES: list[tuple[str, str]] = [("FRA", "MAR"), ("ESP", "BEL"), ("ENG", "NOR")]

# event_ticker for each live fixture, keyed by the (a, b) tuple used above.
# team_a in the tuple is whichever side we want q_a = P(a advances) for.
FIXTURE_EVENTS: dict[tuple[str, str], str] = {
    ("ARG", "EGY"): "KXWCADVANCE-26JUL07ARGEGY",
    ("SUI", "COL"): "KXWCADVANCE-26JUL07SUICOL",
    ("FRA", "MAR"): "KXWCADVANCE-26JUL09FRAMAR",
    ("ESP", "BEL"): "KXWCADVANCE-26JUL10ESPBEL",
    ("ENG", "NOR"): "KXWCADVANCE-26JUL11NORENG",
}


def _mid(client: KalshiPublic, ticker: str) -> float | None:
    """Last trade price if available, else bid/ask mid.

    Same fix as pull_data.candle_price(): an eliminated/thin market's top of
    book snaps to Kalshi's no-liquidity default (yes_bid=$0, yes_ask=$1),
    which mid-of-bid-ask misreads as a fake $0.50 -- confirmed here too
    (CAN/PAR/POR/USA/BRA/MEX, all eliminated, all showed exactly 50.00c
    before this fix). last_price_dollars correctly reflects the true
    near-zero settled value.
    """
    m = client.get_market(ticker)
    px = dollars(m, "last_price")
    if px is not None:
        return px
    bid, ask = dollars(m, "yes_bid"), dollars(m, "yes_ask")
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return None


def _fixture_prob(client: KalshiPublic, fixture: tuple[str, str]) -> float:
    """P(fixture[0] advances) from the live match market."""
    a, b = fixture
    event = FIXTURE_EVENTS[fixture]
    a_ticker = f"{event}-{a}"
    p = _mid(client, a_ticker)
    if p is not None:
        return p
    # fall back to the other side's price if this team's market is thin
    b_ticker = f"{event}-{b}"
    p_b = _mid(client, b_ticker)
    if p_b is None:
        raise RuntimeError(f"No usable price for either side of {fixture} ({event})")
    return 1 - p_b


def build_live_inputs(client: KalshiPublic | None = None):
    """Returns (teams, market_champ, match_markets, raw_champ_sum)."""
    client = client or KalshiPublic()

    teams = list(TEAMS_16)

    champ_by_champcode = {
        m["ticker"].rsplit("-", 1)[-1]: m
        for m in client.iter_markets(series_ticker=CHAMPION_SERIES)
    }
    market_champ = {}
    for team in teams:
        champ_code = TEAM_CODE_MAP.get(team, team)
        m = champ_by_champcode.get(champ_code)
        if m is None:
            raise RuntimeError(f"No {CHAMPION_SERIES} market found for {team} "
                              f"(champ code {champ_code})")
        p = _mid(client, m["ticker"])
        market_champ[team] = p if p is not None else 0.0005  # eliminated/no-quote floor

    raw_champ_sum = sum(market_champ.values())

    # Teams pinned as definitively eliminated must have EXACTLY zero champ
    # target, not their small illiquid-residual live price (~0.1c): with the
    # override forcing their DP reach to exactly 0.0, calibrate_to_market's
    # rating update does log(target/sim) -- target=tiny-but-nonzero vs
    # sim=exactly-0 blows up (confirmed: overflow in exp, calibration -> NaN).
    # target=0.0 exactly makes both sides of the ratio hit the same 1e-9
    # floor, so no rating update happens for them (correctly -- their rating
    # can't matter once reach is pinned to 0 regardless of it).
    for (loser, _winner) in SETTLED_R16_OVERRIDES:
        market_champ[loser] = 0.0

    match_markets: dict[tuple[str, str], float] = dict(SETTLED_R16_OVERRIDES)
    for fixture in LIVE_R16_FIXTURES + LIVE_QF_FIXTURES:
        match_markets[fixture] = _fixture_prob(client, fixture)

    return teams, market_champ, match_markets, raw_champ_sum


if __name__ == "__main__":
    teams, market_champ, match_markets, raw_sum = build_live_inputs()
    print(f"{len(teams)} bracket teams: {teams}")
    print("\nchamp prices (raw Kalshi mid, probability units):")
    for t in teams:
        print(f"  {t:<4} {market_champ[t]*100:6.2f}c")
    print(f"\nraw champ price sum across bracket teams: {raw_sum:.4f} "
          f"(map model probs back to price space by multiplying by this)")
    print("\nmatch markets (P(team_a advances)):")
    for (a, b), q in match_markets.items():
        print(f"  {a}-{b}: {q:.4f}")
