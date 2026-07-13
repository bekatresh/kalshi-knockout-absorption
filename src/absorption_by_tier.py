"""
Does knockout absorption structure differ by the STRENGTH TIER of the
eliminated team? The pooled analysis (src/absorption_basket.py) found no
generalizable basket rule on average across all 22 matches -- but averaging
a handful of rare, large-released-mass "contender falls" together with many
frequent, negligible-mass "longshot falls" can hide a conditional pattern
that only shows up when a genuine contender is eliminated.

This is descriptive / hypothesis-generating, NOT a trading test and NOT a
significance test -- there are only ~6 contender-elimination matches in the
current dataset. See absorption_by_tier_report.md for the explicit "how
much data would confirm this" framing.

Pipeline (run as `python -m src.absorption_by_tier`):
  1. classify_tiers()       -- natural-break split on loser_pre (data-driven,
                               not hardcoded), both single and vwap3 variants
  2. per_match_table()      -- full per-match share metrics + tier label
  3. field_price_correlation() -- within contender matches only: does the
                               field's absorption correlate with a
                               surviving team's own pre-match price?
  4. coherence_deviation()  -- actual vs. implied absorption, by tier

Definitions match decompose.py / METRICS_REFERENCE.md §2 exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.absorption_basket import build_dataset  # noqa: E402

PROC = Path("data/processed")
OUT = Path("results")


# ---------------------------------------------------------------------
# Step 1: data-driven tier split
# ---------------------------------------------------------------------

def find_natural_break(loser_pre: pd.Series) -> float:
    """Sort loser_pre descending; find the single largest multiplicative
    gap between consecutive values; return the threshold (midpoint,
    geometric) that splits there. Data-driven, not hardcoded to 0.03."""
    vals = np.sort(loser_pre.to_numpy())[::-1]
    ratios = vals[:-1] / vals[1:]
    split_idx = int(np.argmax(ratios))  # gap AFTER this index (0-indexed, descending)
    lo, hi = vals[split_idx + 1], vals[split_idx]
    return float(np.sqrt(lo * hi))  # geometric midpoint of the gap


def classify_tiers(results: pd.DataFrame) -> pd.DataFrame:
    threshold = find_natural_break(results["loser_pre"])
    out = results.copy()
    out["tier"] = np.where(out["loser_pre"] >= threshold, "contender", "longshot")
    out.attrs["threshold"] = threshold
    return out


# ---------------------------------------------------------------------
# Step 2: per-match table (already essentially decomposition_results.csv
# plus the tier label -- kept as a thin wrapper for a single entry point)
# ---------------------------------------------------------------------

def per_match_table(results: pd.DataFrame) -> pd.DataFrame:
    tiered = classify_tiers(results)
    cols = ["match_id", "winner", "loser", "tier", "q_winner", "loser_pre",
            "released", "winner_share", "next_opponent_share", "field_share",
            "implied_winner_share", "excess_absorption"]
    return tiered[cols].sort_values("loser_pre", ascending=False)


# ---------------------------------------------------------------------
# Step 3: within contender matches, does the field's absorption correlate
# with a surviving team's own pre-match price? (tests "strong teams
# absorb more")
# ---------------------------------------------------------------------

def field_price_correlation(datasets: list[dict], contender_match_ids: list[str]) -> pd.DataFrame:
    rows = []
    for m in datasets:
        if m["match_id"] not in contender_match_ids:
            continue
        field = [t for t in m["delta"].index
                if t not in {m["winner"], m["loser"], m["next_opponent"]}]
        if len(field) < 3:
            rows.append({"match_id": m["match_id"], "n_field_teams": len(field),
                        "pearson_r": np.nan, "note": "too few field teams for a correlation"})
            continue
        pre_prices = m["pre"][field].to_numpy()
        deltas = m["delta"][field].to_numpy()
        r = float(np.corrcoef(pre_prices, deltas)[0, 1])
        rows.append({
            "match_id": m["match_id"], "n_field_teams": len(field),
            "pearson_r": round(r, 4),
            "field_share_total": round(float(m["delta"][field].sum() / m["R"]), 4) if m["R"] else np.nan,
            "note": "",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Step 4: coherence deviation by tier
# ---------------------------------------------------------------------

def coherence_deviation(results: pd.DataFrame) -> pd.DataFrame:
    tiered = classify_tiers(results)
    tiered["deviation"] = tiered["winner_share"] - tiered["implied_winner_share"]
    tiered["abs_deviation"] = tiered["deviation"].abs()
    tiered["ea_deviation_from_1"] = (tiered["excess_absorption"] - 1.0).abs()
    return tiered[["match_id", "tier", "loser_pre", "winner_share",
                  "implied_winner_share", "deviation", "abs_deviation",
                  "excess_absorption", "ea_deviation_from_1"]].sort_values(
        "loser_pre", ascending=False)


def tier_summary(deviation_df: pd.DataFrame) -> pd.DataFrame:
    return deviation_df.groupby("tier").agg(
        n=("match_id", "count"),
        mean_ea=("excess_absorption", "mean"), median_ea=("excess_absorption", "median"),
        std_ea=("excess_absorption", "std"),
        mean_abs_deviation=("abs_deviation", "mean"),
        mean_ea_deviation_from_1=("ea_deviation_from_1", "mean"),
        median_ea_deviation_from_1=("ea_deviation_from_1", "median"),
    ).round(4).reset_index()


# ---------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------

_YLIM = {"winner_share": (-3, 3), "next_opponent_share": (-3, 3),
        "field_share": (-3, 3), "excess_absorption": (-1.5, 2.5)}


def plot_shares_vs_loser_pre(results: pd.DataFrame, threshold: float, path: str) -> None:
    """Note: y-axis is clipped to a sensible band per metric. Several
    longshot matches (R < 0.005, the same instability threshold
    METRICS_REFERENCE.md §2.1 already flags) have raw share values in the
    hundreds because dividing by a near-zero released mass blows up the
    ratio -- plotting those on a linear axis makes every other point
    invisible. excess_absorption is structurally more robust to tiny R
    (both numerator and denominator blow up together, so the ratio stays
    bounded) and isn't materially clipped."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tiered = classify_tiers(results)
    metrics = ["winner_share", "next_opponent_share", "field_share", "excess_absorption"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    colors = {"contender": "#dc2626", "longshot": "#6b7280"}
    for ax, metric in zip(axes.flat, metrics):
        ylo, yhi = _YLIM[metric]
        n_clipped = 0
        for tier, sub in tiered.groupby("tier"):
            in_range = sub[(sub[metric] >= ylo) & (sub[metric] <= yhi)]
            n_clipped += len(sub) - len(in_range)
            ax.scatter(in_range["loser_pre"], in_range[metric], label=tier,
                      color=colors[tier], alpha=0.8, s=50)
        ax.axvline(threshold, ls="--", color="k", lw=0.8, alpha=0.6)
        ax.axhline(1.0 if metric in ("winner_share", "excess_absorption") else 0.0,
                  ls=":", color="k", lw=0.8, alpha=0.5)
        ax.set_xscale("log")
        ax.set_ylim(ylo, yhi)
        ax.set_xlabel("loser_pre (log scale)")
        ax.set_ylabel(metric)
        title = metric
        if n_clipped:
            title += f"  ({n_clipped} tiny-R longshot points off-axis, see CSV)"
        ax.set_title(title, fontsize=10)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("Absorption shares vs. loser's pre-match championship price\n"
                "(dashed vertical = data-driven contender/longshot break; "
                "y-axis clipped -- see per-panel titles and caption in report)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_field_price_correlation(datasets: list[dict], contender_match_ids: list[str], path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ds_by_id = {m["match_id"]: m for m in datasets}
    n = len(contender_match_ids)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3.5 * nrows))
    axes = axes.flat
    for ax, mid in zip(axes, contender_match_ids):
        m = ds_by_id[mid]
        field = [t for t in m["delta"].index
                if t not in {m["winner"], m["loser"], m["next_opponent"]}]
        x = m["pre"][field].to_numpy()
        y = m["delta"][field].to_numpy()
        r = np.corrcoef(x, y)[0, 1] if len(field) >= 3 else float("nan")
        ax.scatter(x, y, alpha=0.6, s=25, color="#2563eb")
        ax.axhline(0, color="k", lw=0.6, alpha=0.5)
        ax.set_title(f"{mid.split('-')[-1]}  (r={r:.2f}, n={len(field)})", fontsize=10)
        ax.set_xlabel("field team's pre-match price (norm.)")
        ax.set_ylabel("Δp (absorption)")
    for ax in list(axes)[n:]:
        ax.axis("off")
    fig.suptitle("Within contender-elimination matches: does a field team's own\n"
                "pre-match price predict how much of the released mass it absorbs?")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def main() -> None:
    OUT.mkdir(exist_ok=True)
    snapshots = pd.read_csv(PROC / "snapshots.csv")
    matches = pd.read_csv(PROC / "matches.csv")

    for variant, results_csv in [("single", "decomposition_results.csv"),
                                 ("vwap3", "decomposition_results_vwap3.csv")]:
        print(f"\n{'='*70}\n{variant}\n{'='*70}")
        results = pd.read_csv(PROC / results_csv)
        threshold = find_natural_break(results["loser_pre"])
        print(f"natural-break threshold: {threshold:.5f}")

        pm = per_match_table(results)
        pm.insert(0, "variant", variant)
        pm.to_csv(PROC / f"absorption_by_tier_matches_{variant}.csv", index=False)
        print(pm["tier"].value_counts().to_string())

        dev = coherence_deviation(results)
        summ = tier_summary(dev)
        summ.insert(0, "variant", variant)
        summ.to_csv(PROC / f"absorption_by_tier_summary_{variant}.csv", index=False)
        print(summ.to_string(index=False))

        if variant == "single":
            ds = build_dataset(snapshots, matches, variant)
            contender_ids = pm[pm.tier == "contender"].match_id.tolist()
            corr = field_price_correlation(ds, contender_ids)
            corr.to_csv(PROC / "absorption_by_tier_field_correlation.csv", index=False)
            print("\nfield-price correlation (contender matches only):")
            print(corr.to_string(index=False))

            plot_shares_vs_loser_pre(results, threshold, str(OUT / "shares_vs_loser_pre.png"))
            plot_field_price_correlation(ds, contender_ids, str(OUT / "field_price_correlation.png"))
            print(f"\nWrote {OUT/'shares_vs_loser_pre.png'} and {OUT/'field_price_correlation.png'}")

    print("\nWrote per-match and summary CSVs to data/processed/")


if __name__ == "__main__":
    main()
