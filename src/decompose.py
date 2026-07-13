"""
Core analysis: when a team is knocked out, where does its championship
probability go?

Definitions (all in NORMALIZED probability space — raw Kalshi prices carry
vig/longshot bias, so each snapshot is renormalized to sum to 1):

  R           = loser's released mass = p_loser(pre) - p_loser(post)
  share_j     = (p_j(post) - p_j(pre)) / R          for every surviving team j
  implied winner jump (consistency): if championship and match markets are
      jointly coherent, p_winner(post) should be p_winner(pre) / q, where
      q = winner's pre-match win probability. So
      implied_share_winner = p_w(pre) * (1/q - 1) / R
  excess_absorption = actual winner share / implied winner share
      > 1  -> market rewards winners MORE than consistency implies
             (your Belgium hedge idea has extra juice)
      < 1  -> released mass leaks to future opponents / the field
             (the hedge window is thinner than the naive math says)

Buckets reported per match:
  winner | next_opponent | rest_of_field | vig_change (residual)
"""

from __future__ import annotations

import pandas as pd


def normalize(s: pd.Series) -> pd.Series:
    return s / s.sum()


def decompose_match(snaps: pd.DataFrame, match: dict) -> dict:
    """
    snaps: DataFrame with columns [team, pre, post] for ONE match,
           raw probabilities (may not sum to 1).
    match: dict with winner, loser, winner_pre_match_prob, next_opponent_teams.
    """
    df = snaps.dropna(subset=["pre", "post"]).set_index("team")
    raw_pre_sum, raw_post_sum = df["pre"].sum(), df["post"].sum()
    pre, post = normalize(df["pre"]), normalize(df["post"])

    w, l = match["winner"], match["loser"]
    nxt = match["next_opponent_teams"]
    if isinstance(nxt, str):
        nxt = [t for t in nxt.split(";") if t]
    else:
        nxt = []  # NaN when read back from CSV -- bracket opponent not fixed yet
    q = float(match["winner_pre_match_prob"])

    released = pre[l] - post[l]
    delta = post - pre

    winner_share = delta[w] / released
    next_share = sum(delta[t] for t in nxt if t in delta.index) / released
    others = [t for t in delta.index if t not in {w, l, *nxt}]
    field_share = delta[others].sum() / released

    implied_winner_delta = pre[w] * (1.0 / q - 1.0)
    implied_winner_share = implied_winner_delta / released

    return {
        "match_id": match["match_id"],
        "winner": w, "loser": l, "q_winner": q,
        "loser_pre": pre[l], "released": released,
        "winner_pre": pre[w], "winner_post": post[w],
        "winner_share": winner_share,
        "next_opponent_share": next_share,
        "field_share": field_share,
        "implied_winner_share": implied_winner_share,
        "excess_absorption": winner_share / implied_winner_share
        if implied_winner_share else float("nan"),
        "raw_vig_pre": raw_pre_sum, "raw_vig_post": raw_post_sum,
    }


def run_all(snapshots: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """snapshots: [match_id, team, pre, post]; matches: one row per match."""
    out = []
    for _, m in matches.iterrows():
        s = snapshots[snapshots.match_id == m["match_id"]][["team", "pre", "post"]]
        out.append(decompose_match(s, m.to_dict()))
    res = pd.DataFrame(out)
    return res


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    cols = ["winner_share", "next_opponent_share", "field_share",
            "implied_winner_share", "excess_absorption"]
    agg = results[cols].agg(["mean", "median", "std", "min", "max"]).T
    agg["n"] = len(results)
    return agg.round(3)


def hedge_pnl(n_loser_contracts: int, loser_entry_c: float, loser_pre_c: float,
              q_winner: float, hedge_price_c: float,
              excess_absorption: float, fee_rate: float = 0.07) -> pd.DataFrame:
    """
    Scenario P&L for the 'hold loser-to-win-cup, buy winner-to-advance' hedge,
    across hedge sizes. Prices in cents. excess_absorption scales the
    repricing of the loser's championship contract if the loser WINS the
    match (symmetry assumption: same absorption dynamics apply).

    If loser wins match: loser champ contract -> loser_pre_c / (1 - q_winner)
                          * excess_absorption, sold at that level.
    If winner wins match: loser champ contract -> ~0.
    Kalshi fee ~ fee_rate * p * (1-p) per contract, charged on taker fills.
    """
    p = hedge_price_c / 100.0
    fee_per_hedge_c = fee_rate * p * (1 - p) * 100

    reprice_c = loser_pre_c / (1.0 - q_winner) * excess_absorption
    rows = []
    for n_hedge in range(0, 121, 5):
        cost_hedge = n_hedge * (hedge_price_c + fee_per_hedge_c) / 100.0
        # state A: hedge pays out (loser eliminated)
        pnl_a = n_hedge * (100 - hedge_price_c - fee_per_hedge_c) / 100.0 \
            - n_loser_contracts * loser_entry_c / 100.0
        # state B: loser advances, champ position marked to repriced level
        pnl_b = -cost_hedge + n_loser_contracts * (reprice_c - loser_entry_c) / 100.0
        rows.append({"n_hedge": n_hedge, "pnl_if_hedge_wins": round(pnl_a, 2),
                     "pnl_if_loser_advances": round(pnl_b, 2),
                     "worst_case": round(min(pnl_a, pnl_b), 2)})
    return pd.DataFrame(rows)
