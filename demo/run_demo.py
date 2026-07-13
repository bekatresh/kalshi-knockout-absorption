"""
Synthetic end-to-end demo.

Simulates a 12-team championship market through 4 knockout matches with a
KNOWN ground-truth absorption profile, then runs the exact same
decomposition the real pipeline uses, so you can see the output shapes and
sanity-check that the estimator recovers the truth.

Ground truth used here (edit and re-run to explore):
  - winner absorbs ALPHA x the consistency-implied jump
  - winner's next opponent soaks NEXT_FRAC of what's left
  - remainder spreads across the field proportional to pre-match prob
  - multiplicative noise + vig drift to mimic real snapshots
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.decompose import hedge_pnl, run_all, summarize  # noqa: E402
from src.plotting import absorption_bars, hedge_frontier  # noqa: E402

rng = np.random.default_rng(7)

ALPHA = 1.15      # winners absorb 15% MORE than consistency implies
NEXT_BETA = 0.5   # sensitivity of next opponent to who they now face
NOISE = 0.04

TEAMS = ["ESP", "FRA", "ENG", "BRA", "ARG", "GER", "POR", "NED",
         "USA", "BEL", "MAR", "COL"]
STRENGTH = np.array([18, 15, 12, 12, 10, 8, 7, 6, 3.8, 1.4, 2.9, 3.6])

MATCHES = [
    dict(match_id="KO1_GER_NED", winner="GER", loser="NED", q=0.55, nxt=["FRA"]),
    dict(match_id="KO2_ARG_POR", winner="ARG", loser="POR", q=0.58, nxt=["BRA"]),
    dict(match_id="KO3_ENG_MAR", winner="ENG", loser="MAR", q=0.78, nxt=["ARG"]),
    dict(match_id="KO4_USA_BEL", winner="USA", loser="BEL", q=0.53, nxt=["ESP"]),
]


def main() -> None:
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    p = pd.Series(STRENGTH / STRENGTH.sum(), index=TEAMS)
    snap_rows, match_rows = [], []

    for m in MATCHES:
        w, l, q = m["winner"], m["loser"], m["q"]
        pre = p.copy()

        post = pre.copy()
        post[l] = 0.0
        post[w] = min(ALPHA * pre[w] / q, 0.95)   # consistency jump x alpha
        # next opponent's path gets harder if the favorite advanced (q>0.5),
        # easier if the underdog did — signed effect, scaled by NEXT_BETA
        nxt = [t for t in m["nxt"] if t not in (w, l)]
        for t in nxt:
            post[t] = pre[t] * (1 + NEXT_BETA * ((1 - q) - q))
        post = post / post.sum()                   # field absorbs the residual

        # observation noise + vig drift, as if read from candle mids
        obs_pre = pre * (1 + rng.normal(0, NOISE, len(pre))) * 1.06
        obs_post = post * (1 + rng.normal(0, NOISE, len(post))) * 1.05
        obs_post[l] = max(obs_post[l], 0.001)

        for t in TEAMS:
            snap_rows.append(dict(match_id=m["match_id"], team=t,
                                  pre=obs_pre[t], post=obs_post[t]))
        match_rows.append(dict(match_id=m["match_id"], winner=w, loser=l,
                               winner_pre_match_prob=q,
                               next_opponent_teams=";".join(m["nxt"])))
        p = post / post.sum()  # market rolls forward

    snapshots, matches = pd.DataFrame(snap_rows), pd.DataFrame(match_rows)
    results = run_all(snapshots, matches)

    pd.set_option("display.width", 160)
    print("=== Per-match decomposition ===")
    print(results[["match_id", "q_winner", "loser_pre", "winner_share",
                   "implied_winner_share", "next_opponent_share",
                   "field_share", "excess_absorption"]].round(3).to_string(index=False))
    print(f"\n(ground truth ALPHA = {ALPHA}, NEXT_BETA = {NEXT_BETA})")
    print("\n=== Summary across matches ===")
    print(summarize(results).to_string())

    results.to_csv(out / "decomposition_results.csv", index=False)
    absorption_bars(results, str(out / "absorption_decomposition.png"))

    # Hedge P&L for the live USA/BEL setup using the estimated excess absorption
    ea = results.excess_absorption.median()
    pnl = hedge_pnl(n_loser_contracts=1000, loser_entry_c=1.28, loser_pre_c=1.4,
                    q_winner=0.53, hedge_price_c=54.0, excess_absorption=ea)
    pnl.to_csv(out / "hedge_pnl.csv", index=False)
    hedge_frontier(pnl, str(out / "hedge_frontier.png"),
                   f"BEL champ (1000 @ 1.28c) + USA-advances hedge @ 54c\n"
                   f"excess absorption = {ea:.2f} (demo estimate)")
    w = pnl[pnl.worst_case > 0]
    print("\n=== Hedge window (both states positive) ===")
    print(w.to_string(index=False) if not w.empty else "No positive window.")


if __name__ == "__main__":
    main()
