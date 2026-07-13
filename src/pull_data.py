"""
Pull championship-market candlesticks around every knockout settlement and
build the pre/post snapshot table the decomposition needs.

Run locally (this needs Kalshi network access):

    python -m src.pull_data

Outputs:
    data/raw/candles_<team>.csv          full candle history per team
                                         (team = CHAMPION_SERIES ticker suffix)
    data/processed/snapshots.csv         one row per (match, team) with
                                         pre/post prices
    data/processed/matches.csv           match metadata incl. winner pre-
                                         match probability

Price convention: mid of yes_bid/yes_ask close if both exist, else last
trade close. Kalshi's candlestick fields are `*_dollars` strings already in
probability units (e.g. "0.0140" = 1.4%) -- no /100 conversion needed.

KNOCKOUT_MATCHES stores winner/loser/next_opponent_teams in MATCH_SERIES
code convention (human-readable off the match market page, e.g. "USA",
"BEL"). Championship-market snapshots are keyed by CHAMPION_SERIES code
convention (e.g. "US", "BE") -- see config.TEAM_CODE_MAP. This module
translates match-codes to champ-codes before writing matches.csv so
decompose.py's team lookups line up with snapshots.csv.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .config import (CANDLE_INTERVAL_MIN, CHAMPION_SERIES, KNOCKOUT_MATCHES,
                     MATCH_SERIES, POST_WINDOW_S, PRE_WINDOW_S, TEAM_CODE_MAP)
from .kalshi_client import KalshiPublic, dollars

RAW = Path("data/raw")
PROC = Path("data/processed")


def _ts(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def candle_price(c: dict) -> float | None:
    """Last trade/mark price if available, else mid of bid/ask close.

    Prefer trade price over bid/ask mid (not the reverse -- verified on real
    data): once a market goes quiet (thin trading, or just after
    settlement), Kalshi's book snaps to the no-liquidity default (yes_bid=0,
    yes_ask=1), and mid-of-bid-ask reads that as a fake 0.5 even though the
    last actual trade/settlement price correctly sat near 0. Confirmed on
    KXMENWORLDCUP-26-RSA's settlement candle: price.close=$0.001 (correct)
    vs bid/ask mid=$0.50 (artifact).
    """
    px = dollars(c.get("price") or {}, "close")
    if px is not None:
        return px
    bid = dollars(c.get("yes_bid") or {}, "close")
    ask = dollars(c.get("yes_ask") or {}, "close")
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return None


def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """Empty `candles` is expected for teams eliminated before this run's
    time window (their market stopped trading earlier) -- returns an empty
    frame with the right columns rather than raising.

    Zero-volume candles are dropped: with no trades that hour, `price.close`
    just echoes Kalshi's no-liquidity default quote (yes_bid=$0/yes_ask=$1 ->
    a fake $0.50), not a real mark. Confirmed on
    KXMENWORLDCUP-26-UZB (long-eliminated, illiquid): its only post-
    elimination candle has volume_fp=0 and price.close=$0.50 even though the
    team is worthless. Dropping it lets snapshot() correctly fall through to
    "no data" instead of latching onto that stale $0.50.
    """
    if not candles:
        return pd.DataFrame(columns=["ts", "price", "volume", "dt"])
    rows = [{"ts": c.get("end_period_ts"), "price": candle_price(c),
             "volume": float(c.get("volume_fp") or 0)}
            for c in candles]
    df = pd.DataFrame(rows).dropna(subset=["price"])
    df = df[df["volume"] > 0]
    if not df.empty:
        df["dt"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    return df


def snapshot(df: pd.DataFrame, at_ts: int, direction: str, n: int = 1,
            upper_bound: int | None = None) -> float | None:
    """Probability at/around at_ts: mean of the last n candles at/before
    at_ts ('pre') or the first n candles at/after ('post'), the latter
    optionally capped at `upper_bound` so a thin post-settlement market
    can't reach past a subsequent match's own settlement. n=1 reproduces
    the single-snapshot estimate; n>1 is the VWAP-style robustness variant."""
    if df.empty:
        return None
    if direction == "pre":
        sub = df[df.ts <= at_ts].tail(n)
    else:
        sub = df[df.ts >= at_ts]
        if upper_bound is not None:
            sub = sub[sub.ts <= upper_bound]
        sub = sub.head(n)
    return None if sub.empty else float(sub.price.mean())


BOUNDARY_BUFFER_S = 30 * 60  # keep snapshots this far clear of a neighboring match's settlement


def clipped_window(match: dict, all_settles: list[int]) -> dict:
    """Clip [pre_ts, post_ts, post_upper] so this match's snapshot window
    never crosses another match's settlement -- otherwise a team's
    "post" price can silently include ITS OWN unrelated result that
    happened to settle inside this match's pre->post span. Confirmed on
    KXWCADVANCE-26JUL06USABEL: Spain's "next-opponent" delta was almost
    entirely Spain's own PORESP win (settled inside USABEL's naive
    pre-window), not a reaction to Belgium beating the USA.

    pre_ts  = max(kickoff - PRE_WINDOW_S,  latest earlier settlement + buffer)
    post_ts = settlement (unchanged -- already the tightest possible start)
    post_upper = min(settlement + POST_WINDOW_S, next settlement - buffer)
    """
    k, s = _ts(match["kickoff_iso"]), _ts(match["settle_iso"])
    earlier = [t for t in all_settles if t < k and t != s]
    later = [t for t in all_settles if t > s]
    latest_earlier = max(earlier) if earlier else None
    next_settle = min(later) if later else None

    pre_ts = k - PRE_WINDOW_S
    if latest_earlier is not None:
        pre_ts = max(pre_ts, latest_earlier + BOUNDARY_BUFFER_S)
    post_upper = s + POST_WINDOW_S
    if next_settle is not None:
        post_upper = min(post_upper, next_settle - BOUNDARY_BUFFER_S)

    return {
        "pre_ts": pre_ts, "post_ts": s, "post_upper": post_upper,
        "pre_clipped_s": pre_ts - (k - PRE_WINDOW_S),
        "post_clipped_s": (s + POST_WINDOW_S) - post_upper,
        "pre_invalid": pre_ts >= k,
        "post_invalid": post_upper <= s,
    }


def main() -> None:
    if not KNOCKOUT_MATCHES:
        raise SystemExit("config.KNOCKOUT_MATCHES is empty — run "
                         "`python -m src.discover --draft-matches` first.")

    client = KalshiPublic()

    champ = {m["ticker"].rsplit("-", 1)[-1]: m
             for m in client.iter_markets(series_ticker=CHAMPION_SERIES)}
    teams = sorted(champ)
    print(f"{len(teams)} championship markets: {teams}")
    settled_no = {t for t, m in champ.items()
                  if m.get("status") == "finalized" and m.get("result") == "no"}

    # extra fetch-only buffer so the earliest match's pre-snapshot has room
    # to find a preceding candle (its pre_ts sits exactly at the naive t_min,
    # which left zero margin and produced an unusable all-NaN pre snapshot)
    fetch_buffer_s = 6 * 3600
    t_min = min(_ts(m["kickoff_iso"]) for m in KNOCKOUT_MATCHES) - PRE_WINDOW_S - fetch_buffer_s
    t_max = max(_ts(m["settle_iso"]) for m in KNOCKOUT_MATCHES) + POST_WINDOW_S

    candles: dict[str, pd.DataFrame] = {}
    for team, mkt in champ.items():
        cs = client.candlesticks(CHAMPION_SERIES, mkt["ticker"],
                                 t_min, t_max, CANDLE_INTERVAL_MIN)
        df = candles_to_df(cs)
        candles[team] = df
        df.to_csv(RAW / f"candles_{team}.csv", index=False)
        print(f"  {team}: {len(df)} candles")

    all_settles = [_ts(m["settle_iso"]) for m in KNOCKOUT_MATCHES]

    snap_rows, match_rows = [], []
    clip_report = []
    for match in KNOCKOUT_MATCHES:
        k, s = _ts(match["kickoff_iso"]), _ts(match["settle_iso"])
        win = clipped_window(match, all_settles)
        pre_ts, post_ts, post_upper = win["pre_ts"], win["post_ts"], win["post_upper"]
        if win["pre_clipped_s"] > 0 or win["post_clipped_s"] > 0 or win["pre_invalid"] or win["post_invalid"]:
            clip_report.append({
                "match_id": match["match_id"],
                "pre_clipped_min": round(win["pre_clipped_s"] / 60, 1),
                "post_clipped_min": round(win["post_clipped_s"] / 60, 1),
                "pre_invalid": win["pre_invalid"], "post_invalid": win["post_invalid"],
            })

        q = match.get("winner_pre_match_prob")
        if q is None:  # read from the match market's last pre-kickoff candle
            mc = candles_to_df(client.candlesticks(
                MATCH_SERIES, match["match_market_ticker"],
                k - PRE_WINDOW_S, k, CANDLE_INTERVAL_MIN))
            q = snapshot(mc, k, "pre")
            q_vwap3 = snapshot(mc, k, "pre", n=3)
            # ticker suffix is one team; flip if it's the loser's market
            if match["match_market_ticker"].rsplit("-", 1)[-1] == match["loser"]:
                q = None if q is None else 1 - q
                q_vwap3 = None if q_vwap3 is None else 1 - q_vwap3
        else:
            q_vwap3 = q

        winner_champ = TEAM_CODE_MAP.get(match["winner"], match["winner"])
        loser_champ = TEAM_CODE_MAP.get(match["loser"], match["loser"])
        next_champ = [TEAM_CODE_MAP.get(t, t) for t in match["next_opponent_teams"]]

        match_rows.append({
            "match_id": match["match_id"],
            "match_market_ticker": match["match_market_ticker"],
            "kickoff_iso": match["kickoff_iso"], "settle_iso": match["settle_iso"],
            "winner": winner_champ, "loser": loser_champ,
            "next_opponent_teams": ";".join(next_champ),
            "winner_pre_match_prob": q,
            "winner_pre_match_prob_vwap3": q_vwap3,
        })

        for team in teams:
            pre = snapshot(candles[team], pre_ts, "pre")
            pre_vwap3 = snapshot(candles[team], pre_ts, "pre", n=3)
            post = snapshot(candles[team], post_ts, "post", upper_bound=post_upper)
            post_vwap3 = snapshot(candles[team], post_ts, "post", n=3, upper_bound=post_upper)
            # A just-eliminated team's champ market goes fully illiquid
            # (zero volume) almost immediately -- no post-window candle
            # survives the volume>0 filter. But a "no"-settled market is
            # *definitionally* worth $0, so impute rather than drop (dropping
            # would silently exclude the match's own loser from the
            # decomposition, or crash it -- confirmed on KXWCADVANCE-26JUN30CIVNOR,
            # where Ivory Coast has zero post-window volume anywhere).
            # Only ever applied to "post" (never "pre" -- a team not yet
            # eliminated as of a match's pre-snapshot must keep its real price).
            imputed = team in settled_no
            if imputed:
                post = 0.0 if post is None else post
                post_vwap3 = 0.0 if post_vwap3 is None else post_vwap3
            # Flag rather than silently widen: a clipped window that leaves
            # no candle (and isn't covered by the settled-no impute above)
            # means this team's snapshot for this match is genuinely missing,
            # not a signal to fall back to the wide (contamination-prone)
            # window.
            snap_rows.append({
                "match_id": match["match_id"], "team": team,
                "pre": pre, "post": post,
                "pre_vwap3": pre_vwap3, "post_vwap3": post_vwap3,
                "pre_missing_clipped": pre is None,
                "post_missing_clipped": (post is None) and not imputed,
            })

    pd.DataFrame(snap_rows).to_csv(PROC / "snapshots.csv", index=False)
    pd.DataFrame(match_rows).to_csv(PROC / "matches.csv", index=False)
    if clip_report:
        clip_df = pd.DataFrame(clip_report)
        clip_df.to_csv(PROC / "window_clip_report.csv", index=False)
        print(f"\n{len(clip_report)} of {len(KNOCKOUT_MATCHES)} matches had "
             f"their snapshot window clipped to avoid crossing a neighboring "
             f"match's settlement -- see {PROC/'window_clip_report.csv'}")
        n_invalid = clip_df.pre_invalid.sum() + clip_df.post_invalid.sum()
        if n_invalid:
            print(f"  WARNING: {n_invalid} match(es) have an invalid clipped "
                 "window (matches settled too close together for any clean "
                 "snapshot) -- check window_clip_report.csv")
    n_flagged = pd.DataFrame(snap_rows)[["pre_missing_clipped", "post_missing_clipped"]].any(axis=1).sum()
    if n_flagged:
        print(f"{n_flagged} (match, team) snapshot(s) had no candle inside "
             "the clipped window -- flagged in snapshots.csv, left as NaN "
             "rather than falling back to the wide window")
    print(f"\nWrote {PROC/'snapshots.csv'} and {PROC/'matches.csv'}")


if __name__ == "__main__":
    main()
