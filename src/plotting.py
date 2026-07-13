"""Plots for the absorption decomposition results."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def absorption_bars(results: pd.DataFrame, path: str) -> None:
    """Stacked bars: where each eliminated team's mass went, per match."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), width_ratios=[2, 1])

    ax = axes[0]
    x = np.arange(len(results))
    labels = results.apply(lambda r: f"{r.winner} ko {r.loser}", axis=1)
    w = 0.27
    ax.bar(x - w, results.winner_share, w, label="Winner", color="#2563eb")
    ax.bar(x, results.next_opponent_share, w, label="Next opponent",
           color="#f59e0b")
    ax.bar(x + w, results.field_share, w, label="Rest of field",
           color="#9ca3af")
    ax.scatter(x - w, results.implied_winner_share, marker="_", s=500,
               color="#111827", label="Consistency-implied winner share", zorder=5)
    ax.axhline(0, lw=0.8, color="k")
    ax.axhline(1.0, ls=":", lw=1, color="k")
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Share of released probability")
    ax.set_title("Where does the loser's championship probability go?")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.axhline(1.0, ls="--", color="k", lw=1)
    ax.bar(x, results.excess_absorption, color=np.where(
        results.excess_absorption >= 1, "#16a34a", "#dc2626"))
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_title("Excess absorption ratio\n(actual / consistency-implied winner jump)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def hedge_frontier(pnl: pd.DataFrame, path: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(pnl.n_hedge, pnl.pnl_if_hedge_wins, label="P&L if hedge pays (loser out)")
    ax.plot(pnl.n_hedge, pnl.pnl_if_loser_advances, label="P&L if loser advances")
    ax.plot(pnl.n_hedge, pnl.worst_case, "k--", lw=2, label="Worst case")
    ax.axhline(0, color="gray", lw=0.8)
    ok = pnl[pnl.worst_case > 0]
    if not ok.empty:
        ax.axvspan(ok.n_hedge.min(), ok.n_hedge.max(), alpha=0.12, color="green",
                   label="Both-states-positive window")
    ax.set_xlabel("Hedge contracts (winner-advances YES)")
    ax.set_ylabel("P&L ($)")
    ax.set_title(title)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
