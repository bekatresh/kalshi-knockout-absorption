"""
Script form of notebooks/analysis.ipynb, run against the real 2026-07-06
data pull. Produces:
    data/processed/decomposition_results.csv          single pre/post snapshot
    data/processed/decomposition_results_vwap3.csv     VWAP-of-3-candles variant
    results/absorption_decomposition.png
    results/hedge_frontier.png
Prints sanity checks, both summaries (unweighted + mass-weighted), and the
underdog-vs-favorite cut to stdout for RUN_NOTES.md.
"""
import pandas as pd

from src.decompose import run_all, summarize, hedge_pnl
from src.plotting import absorption_bars, hedge_frontier

snapshots = pd.read_csv("data/processed/snapshots.csv")
matches = pd.read_csv("data/processed/matches.csv")

print("=" * 70)
print("BASELINE (single pre/post snapshot)")
print("=" * 70)
results = run_all(snapshots, matches)
print(results.round(3).to_string())
results.to_csv("data/processed/decomposition_results.csv", index=False)

print("\nUnweighted summary:")
print(summarize(results))

print("\nMass-weighted summary (weight = released):")
w = results["released"]
weighted = {}
for col in ["winner_share", "next_opponent_share", "field_share",
            "implied_winner_share", "excess_absorption"]:
    weighted[col] = (results[col] * w).sum() / w.sum()
print(pd.Series(weighted).round(3))

print("\nUnderdog-won vs favorite-won cut:")
results["underdog_won"] = results.q_winner < 0.5
print(results.groupby("underdog_won")["excess_absorption"].describe())

print("\n" + "=" * 70)
print("ROBUSTNESS VARIANT (VWAP of 3 pre-window / 3 post-window candles)")
print("=" * 70)
snaps_v = snapshots.drop(columns=["pre", "post"]).rename(
    columns={"pre_vwap3": "pre", "post_vwap3": "post"})
matches_v = matches.drop(columns=["winner_pre_match_prob"]).rename(
    columns={"winner_pre_match_prob_vwap3": "winner_pre_match_prob"})
results_v = run_all(snaps_v, matches_v)
print(results_v.round(3).to_string())
results_v.to_csv("data/processed/decomposition_results_vwap3.csv", index=False)

print("\nUnweighted summary (VWAP3):")
print(summarize(results_v))

print("\nMass-weighted summary (VWAP3, weight = released):")
w_v = results_v["released"]
weighted_v = {}
for col in ["winner_share", "next_opponent_share", "field_share",
            "implied_winner_share", "excess_absorption"]:
    weighted_v[col] = (results_v[col] * w_v).sum() / w_v.sum()
print(pd.Series(weighted_v).round(3))

print("\nBaseline vs VWAP3 median excess_absorption:",
      results.excess_absorption.median(), "vs", results_v.excess_absorption.median())

absorption_bars(results, "results/absorption_decomposition.png")

ea_baseline_median = results.excess_absorption.median()
ea_vwap3_median = results_v.excess_absorption.median()
ea_mass_weighted = weighted["excess_absorption"]

print("\nHedge P&L sensitivity to excess_absorption estimate "
      "(BEL champ 1000 YES @ 1.28c, BEL last 1.4c, USA-advances 54c, q(USA)=0.53):")
for label, ea in [("baseline median", ea_baseline_median),
                  ("VWAP3 median", ea_vwap3_median),
                  ("mass-weighted mean", ea_mass_weighted)]:
    pnl = hedge_pnl(n_loser_contracts=1000, loser_entry_c=1.28, loser_pre_c=1.4,
                    q_winner=0.53, hedge_price_c=54.0, excess_absorption=ea)
    n_positive = len(pnl[pnl.worst_case > 0])
    print(f"\n  ea={ea:.3f} ({label}): "
          f"{n_positive}/{len(pnl)} hedge sizes have worst_case > 0")
    print(pnl.iloc[::4].to_string(index=False))

# plot using the mass-weighted estimate -- least sensitive to any single
# noisy tiny-loser_pre match (see RUN_NOTES)
ea = ea_mass_weighted
pnl = hedge_pnl(n_loser_contracts=1000, loser_entry_c=1.28, loser_pre_c=1.4,
                q_winner=0.53, hedge_price_c=54.0, excess_absorption=ea)
hedge_frontier(pnl, "results/hedge_frontier.png",
               f"BEL champ + USA-advances hedge (excess absorption={ea:.2f}, mass-weighted)")

print("\nWrote decomposition_results.csv, decomposition_results_vwap3.csv, "
      "results/absorption_decomposition.png, results/hedge_frontier.png")
