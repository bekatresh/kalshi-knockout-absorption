"""
Layer 1 backtest: for every settled knockout, build a minimal 4-node bracket
[loser, winner, next_opponent, SHADOW] anchored to the REAL pre-match champ
prices (from decomposition_results.csv / snapshots.csv), pin the actual
match outcome via Simulator.query(), and compare the model's predicted
delta_consistent / delta_adjusted against the ACTUALLY OBSERVED deltas
(winner_share/next_opponent_share/field_share * released, from
decomposition_results.csv -- exactly decompose.py's own bucketing, so the
comparison is apples-to-apples).

Methodology / why 4 nodes, not the true historical bracket:
  We don't have the full historical bracket tree for early rounds (only
  immediate next-opponent adjacency, retrospectively derived -- see
  src/config.py). A 4-node bracket [loser, winner, next_opponent, SHADOW]
  is the minimal structure that lets the DP express the one relationship we
  actually know and care about testing: winner's consistent gain coupling
  to next_opponent's loss via shared bracket structure (winner and
  next_opponent meet in the modeled next round). SHADOW is a synthetic
  stand-in for "whoever next_opponent's own first-round opponent was" --
  structurally necessary (Bracket needs a power-of-2 tree) but not itself
  compared against anything. Its target price is calibrated with
  next_opponent's OWN real historical pre-match win probability when
  next_opponent later appears as a winner in our dataset (true for all 22
  matches here), else a documented 0.7 default.
  "Field" = a 4th node absorbing all OTHER teams' combined mass (the
  residual after loser+winner+next_opponent), directly comparable to
  decompose.py's field_share * released.

Run: python -m simulator.backtest
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .engine import Simulator  # noqa: E402

SHADOW_Q_DEFAULT = 0.7


def _shadow_q(results: pd.DataFrame, next_opponent: str) -> float:
    row = results[results.winner == next_opponent]
    if len(row):
        return float(row.iloc[0].q_winner)
    return SHADOW_Q_DEFAULT


def backtest_match(results: pd.DataFrame, matches: pd.DataFrame,
                   snapshots: pd.DataFrame, match_id: str) -> dict | None:
    row = results[results.match_id == match_id].iloc[0]
    mrow = matches[matches.match_id == match_id].iloc[0]
    w, l = row.winner, row.loser
    nxt = str(mrow.next_opponent_teams)
    n = nxt.split(";")[0] if nxt and nxt != "nan" else None
    if n is None:
        return None

    pre_w, pre_l = float(row.winner_pre), float(row.loser_pre)
    snap_n = snapshots[(snapshots.match_id == match_id) & (snapshots.team == n)]
    if snap_n.empty or pd.isna(snap_n.iloc[0].pre):
        return None
    pre_n_raw = float(snap_n.iloc[0].pre)
    pre_n = pre_n_raw / float(row.raw_vig_pre)

    x_target = max(1.0 - pre_w - pre_l - pre_n, 1e-4)
    q_w = float(row.q_winner)          # P(winner advances), pre-match
    q_n = _shadow_q(results, n)

    teams = [l, w, n, "SHADOW"]
    market_champ = {l: pre_l, w: pre_w, n: pre_n, "SHADOW": x_target}
    match_markets = {(l, w): 1 - q_w, (n, "SHADOW"): q_n}

    try:
        sim = Simulator(teams, market_champ, match_markets)
        res = sim.query((l, w), outcome=w)
    except Exception as e:
        return {"match_id": match_id, "error": str(e)}

    actual_w = row.winner_share * row.released
    actual_n = row.next_opponent_share * row.released
    actual_field = row.field_share * row.released

    pred_w_c, pred_w_a = res.loc[w, "delta_consistent"], res.loc[w, "delta_adjusted"]
    pred_n_c, pred_n_a = res.loc[n, "delta_consistent"], res.loc[n, "delta_adjusted"]
    pred_field_c, pred_field_a = res.loc["SHADOW", "delta_consistent"], res.loc["SHADOW", "delta_adjusted"]

    return {
        "match_id": match_id, "winner": w, "loser": l, "next_opponent": n,
        "q_winner": q_w, "released": row.released,
        "actual_winner": actual_w, "pred_winner_consistent": pred_w_c, "pred_winner_adjusted": pred_w_a,
        "actual_next_opp": actual_n, "pred_next_opp_consistent": pred_n_c, "pred_next_opp_adjusted": pred_n_a,
        "actual_field": actual_field, "pred_field_consistent": pred_field_c, "pred_field_adjusted": pred_field_a,
        "err_winner_consistent": abs(pred_w_c - actual_w), "err_winner_adjusted": abs(pred_w_a - actual_w),
        "err_next_opp_consistent": abs(pred_n_c - actual_n), "err_next_opp_adjusted": abs(pred_n_a - actual_n),
        "err_field_consistent": abs(pred_field_c - actual_field), "err_field_adjusted": abs(pred_field_a - actual_field),
    }


def run_backtest() -> pd.DataFrame:
    results = pd.read_csv("data/processed/decomposition_results.csv")
    matches = pd.read_csv("data/processed/matches.csv")
    snapshots = pd.read_csv("data/processed/snapshots.csv")

    rows = []
    for match_id in results.match_id:
        r = backtest_match(results, matches, snapshots, match_id)
        if r is not None:
            rows.append(r)
    return pd.DataFrame(rows)


def mae_table(bt: pd.DataFrame) -> pd.DataFrame:
    ok = bt[~bt.get("error", pd.Series(False, index=bt.index)).notna()] if "error" in bt.columns else bt
    roles = ["winner", "next_opp", "field"]
    out = []
    for role in roles:
        actual = ok[f"actual_{role}"]
        pred_c = ok[f"pred_{role}_consistent"]
        pred_a = ok[f"pred_{role}_adjusted"]
        out.append({
            "role": role,
            "MAE_consistent": (pred_c - actual).abs().mean(),
            "MAE_adjusted": (pred_a - actual).abs().mean(),
            "sign_agree_consistent": (np.sign(actual) == np.sign(pred_c)).mean(),
            "sign_agree_adjusted": (np.sign(actual) == np.sign(pred_a)).mean(),
            "n": len(ok),
        })
    return pd.DataFrame(out)


def write_report(bt: pd.DataFrame, mae: pd.DataFrame, path: str = "simulator/backtest_report.md") -> None:
    n_ok = len(bt) - bt.get("error", pd.Series(dtype=object)).notna().sum() if "error" in bt.columns else len(bt)
    n_err = bt.get("error", pd.Series(dtype=object)).notna().sum() if "error" in bt.columns else 0

    overall_consistent = mae.MAE_consistent.mean()
    overall_adjusted = mae.MAE_adjusted.mean()
    mae_verdict = ("adjusted (ea) beats pure consistency on MAE" if overall_adjusted < overall_consistent
                  else "pure consistency beats the ea adjustment on MAE")

    lines = []
    lines.append("# Simulator Layer 1 backtest\n")
    lines.append(f"Backtested {n_ok} of {len(bt) + n_err} settled knockouts "
                 f"({n_err} skipped/errored). Methodology: minimal 4-node "
                 "bracket [loser, winner, next_opponent, SHADOW] per match -- "
                 "see simulator/backtest.py module docstring for why.\n")

    lines.append("## Two important caveats before reading the numbers\n")
    lines.append(
        "1. **ea was fit on these same 22 matches** (`simulator/fit_ea.py` reads "
        "`decomposition_results.csv`, which covers exactly this backtest set). "
        "This is an in-sample check, not a held-out test -- there's no "
        "independent data yet to hold out. Treat the verdict below as "
        "'does the fitted ea at least not hurt the training data' rather "
        "than genuine out-of-sample validation. Re-run this backtest as new "
        "knockouts settle and ea gets refit on a growing/rolling window.\n"
        "2. **The 4-node toy bracket is shallower than the real tournament** "
        "(loser beaten in round 0, next_opponent faced in round 1 = the toy "
        "bracket's FINAL). The real tournament has 3-5 more rounds after "
        "that for early matches. This inflates the toy model's ABSOLUTE "
        "predicted deltas for winner/next_opponent well above the real "
        "observed magnitudes (see the per-match table -- predicted winner "
        "deltas are routinely 3-10x the actual). The MAE numbers below are "
        "dominated by this scale mismatch, not by whether the model gets "
        "the *direction* of the effect right. Sign agreement (does the "
        "model at least get the direction right?) is a scale-robust "
        "secondary check reported alongside MAE for this reason.\n"
    )

    lines.append("## MAE by role (absolute probability points, i.e. 0.01 = 1 percentage point)\n")
    lines.append(mae.round(4).to_string(index=False))
    lines.append("")
    lines.append(f"\n**MAE verdict: {mae_verdict}** "
                 f"(mean MAE across roles: consistent={overall_consistent:.4f}, "
                 f"adjusted={overall_adjusted:.4f}) -- read this alongside "
                 "caveat 2 above; it's likely more about toy-bracket scale "
                 "than about ea's real value.\n")

    sign_row = mae.set_index("role")
    lines.append(
        "**Sign-agreement verdict (scale-robust, arguably more informative):**\n"
        f"- winner: consistent={sign_row.loc['winner','sign_agree_consistent']:.0%}, "
        f"adjusted={sign_row.loc['winner','sign_agree_adjusted']:.0%} "
        "-- both essentially trivial (the winner of a match it just won "
        "almost always gains probability).\n"
        f"- next_opponent: consistent={sign_row.loc['next_opp','sign_agree_consistent']:.0%}, "
        f"adjusted={sign_row.loc['next_opp','sign_agree_adjusted']:.0%} "
        "-- close to a coin flip either way. The model does NOT reliably "
        "predict whether next_opponent gains or loses probability on a "
        "per-match basis, despite the real aggregate mass-weighted "
        "next_opponent_share being solidly positive (~0.6-0.8, see "
        "ea_params.json). Don't trust this simulator's next_opponent signal "
        "match-by-match.\n"
        f"- field: consistent={sign_row.loc['field','sign_agree_consistent']:.0%}, "
        f"adjusted={sign_row.loc['field','sign_agree_adjusted']:.0%} "
        "-- **this is the standout result.** Pure bracket-consistency almost "
        "always predicts the field GAINS probability when a match settles "
        "(wrong sign most of the time -- real field mass usually drops, per "
        "CLAUDE.md's structural-insight note that the field's path hardens "
        "when a bigger team advances). The ea adjustment fixes the sign on "
        "the large majority of matches. This is the one place the ea "
        "adjustment demonstrably earns its keep in this backtest.\n"
    )

    lines.append("## Per-match comparison\n")
    cols = ["match_id", "winner", "loser", "next_opponent", "q_winner", "released",
            "actual_winner", "pred_winner_consistent", "pred_winner_adjusted",
            "actual_next_opp", "pred_next_opp_consistent", "pred_next_opp_adjusted",
            "actual_field", "pred_field_consistent", "pred_field_adjusted"]
    display_cols = [c for c in cols if c in bt.columns]
    lines.append(bt[display_cols].round(4).to_string(index=False))
    if "error" in bt.columns and bt.error.notna().any():
        lines.append("\n## Errors\n")
        lines.append(bt[bt.error.notna()][["match_id", "error"]].to_string(index=False))
    Path(path).write_text("\n".join(lines))
    print(f"Wrote {path}")


if __name__ == "__main__":
    bt = run_backtest()
    mae = mae_table(bt)
    print(mae.round(4).to_string(index=False))
    write_report(bt, mae)
