"""
Refit the Layer-3 absorption parameters from the knockout decomposition.

Usage (from repo root, after each new round of knockouts):
    python -m src.pull_data          # refresh decompositions first
    python -m simulator.fit_ea

Reads decomposition_results.csv (and _vwap3 if present), filters to
matches with meaningful released mass, and writes simulator/ea_params.json
which engine.Simulator can load instead of the hardcoded defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

MIN_RELEASED = 0.005


def fit(results_csv: str = "data/processed/decomposition_results.csv",
        out_json: str = "simulator/ea_params.json") -> dict:
    res = pd.read_csv(results_csv)
    f = res[res.released >= MIN_RELEASED].copy()
    f["underdog_won"] = f.q_winner < 0.5

    def wmean(d):
        return float(np.average(d.excess_absorption, weights=d.released))

    ud, fav = f[f.underdog_won], f[~f.underdog_won]
    params = {
        "ea_underdog": round(wmean(ud), 3) if len(ud) else 1.0,
        "ea_favorite": round(wmean(fav), 3) if len(fav) else 1.0,
        "n_underdog": int(len(ud)), "n_favorite": int(len(fav)),
        "min_released": MIN_RELEASED,
        "next_opp_share_underdog":
            round(float(np.average(ud.next_opponent_share, weights=ud.released)), 3)
            if len(ud) else None,
        "source": results_csv,
    }
    Path(out_json).write_text(json.dumps(params, indent=2))
    print(json.dumps(params, indent=2))
    return params


if __name__ == "__main__":
    fit()
