"""
Absorption replication: does an optimized BASKET of surviving teams
replicate where a loser's released championship mass goes, better than
the naive "all mass to the match winner" view — and does any such rule
generalize out-of-sample?

This is a standalone research module, separate from decompose.py's own
per-match bucketing (winner/next_opponent/field shares). It asks a
sharper question: is there a STABLE, LEARNABLE weighting rule (fit on
other matches) that predicts a held-out match's full per-team delta
vector better than (a) the naive single-winner view or (b) a fixed
winner+next-opponent split? A null result here is exactly as informative
as a positive one -- see absorption_basket_report.md for the verdict.

Pipeline (run as `python -m src.absorption_basket`):
  1. build_dataset()      -- per-match normalized delta vectors + R
  2. fit_match_weights()  -- descriptive per-match simplex-constrained fit
  3. loo_cv()             -- the real test: rules a/b/c, in- vs out-of-sample
  4. tradability_check()  -- realized (not hypothetical) post-fee P&L using
                             LOO-predicted weights on the ACTUAL settled outcome

Definitions match decompose.py exactly: all prices renormalized to sum to
1 per snapshot before differencing (raw Kalshi books carry ~5-10% vig).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROC = Path("data/processed")
FEE_RATE = 0.07
MIN_RELEASED = 0.005  # matches simulator/fit_ea.py's noise filter


def normalize(s: pd.Series) -> pd.Series:
    return s / s.sum()


def build_dataset(snapshots: pd.DataFrame, matches: pd.DataFrame,
                  variant: str = "single") -> list[dict]:
    """One dict per match: normalized pre/post/delta Series (all surviving
    teams + loser), R (loser's released mass), winner/loser/next_opponent
    codes, q_winner. variant is 'single' or 'vwap3'."""
    pre_col = "pre" if variant == "single" else "pre_vwap3"
    post_col = "post" if variant == "single" else "post_vwap3"
    q_col = "winner_pre_match_prob" if variant == "single" else "winner_pre_match_prob_vwap3"

    out = []
    for _, mrow in matches.iterrows():
        mid = mrow.match_id
        s = snapshots[snapshots.match_id == mid][["team", pre_col, post_col]].dropna()
        if s.empty:
            continue
        pre = normalize(s.set_index("team")[pre_col])
        post = normalize(s.set_index("team")[post_col])
        # only keep teams present in both (dropna above already aligns this
        # since pre_col/post_col are dropped together per row)
        common = pre.index.intersection(post.index)
        pre, post = pre[common], post[common]
        delta = post - pre

        w, l = mrow.winner, mrow.loser
        nxt_raw = str(mrow.next_opponent_teams)
        nxt = nxt_raw.split(";")[0] if nxt_raw and nxt_raw != "nan" else None
        if l not in pre.index or w not in pre.index:
            continue
        R = float(pre[l] - post[l])
        q = mrow[q_col]
        if pd.isna(q):
            continue
        out.append({
            "match_id": mid, "variant": variant,
            "pre": pre, "post": post, "delta": delta,
            "winner": w, "loser": l, "next_opponent": nxt if nxt in pre.index else None,
            "R": R, "q_winner": float(q),
        })
    return out


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection of v onto {w : w >= 0, sum(w) = 1} (Duchi et al.
    2008 / Wang & Carreira-Perpinan). Used to find the closest non-negative,
    mass-conserving weight vector to v = delta/R."""
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u) - 1
    ind = np.arange(1, n + 1)
    cond = u - css / ind > 0
    if not cond.any():
        return np.full(n, 1.0 / n)
    rho = ind[cond][-1]
    theta = css[cond][-1] / rho
    return np.maximum(v - theta, 0)


def fit_match_weights(m: dict) -> dict | None:
    """Descriptive per-match fit: find non-negative weights w over
    surviving teams (sum=1) minimizing ||delta_j - w_j*R||. Equivalent to
    projecting delta/R onto the probability simplex (R is a positive
    scalar per match, so this is just a rescaled Euclidean projection)."""
    if m["R"] is None or not np.isfinite(m["R"]) or abs(m["R"]) < 1e-9:
        return None
    teams = [t for t in m["delta"].index if t != m["loser"]]
    delta = m["delta"][teams].to_numpy()
    R = m["R"]
    target = delta / R
    w = project_to_simplex(target)
    residual = delta - w * R
    return {
        "match_id": m["match_id"], "teams": teams, "weights": w,
        "residual_norm": float(np.linalg.norm(residual)),
        "residual_l1": float(np.abs(residual).sum()),
    }


def weights_table(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for m in datasets:
        fit = fit_match_weights(m)
        if fit is None:
            rows.append({"match_id": m["match_id"], "variant": m["variant"],
                        "team": None, "weight": None, "role": "SKIPPED (R~0)",
                        "residual_norm": None})
            continue
        top_idx = int(np.argmax(fit["weights"]))
        top_team = fit["teams"][top_idx]
        for team, w in zip(fit["teams"], fit["weights"]):
            if w < 1e-6:
                continue
            role = ("winner" if team == m["winner"]
                    else "next_opponent" if team == m["next_opponent"]
                    else "field")
            rows.append({
                "match_id": m["match_id"], "variant": m["variant"], "team": team,
                "weight": round(float(w), 4), "role": role,
                "is_top_weighted": team == top_team,
                "residual_norm": round(fit["residual_norm"], 5),
                "residual_l1": round(fit["residual_l1"], 5),
                "R": round(m["R"], 5),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Step 3: does a common rule generalize out-of-sample? (the real test)
# ---------------------------------------------------------------------

def _actual_share(m: dict, team: str | None) -> float:
    if team is None or team not in m["delta"].index or m["R"] == 0:
        return np.nan
    return float(m["delta"][team] / m["R"])


def _other_teams(m: dict) -> list[str]:
    excl = {m["winner"], m["loser"], m["next_opponent"]}
    return [t for t in m["delta"].index if t not in excl]


def rule_a_predict(m: dict, _train: list[dict]) -> dict[str, float]:
    """Naive: all released mass to the match winner."""
    return {m["winner"]: m["R"]}


def rule_b_fit(train: list[dict]) -> dict:
    """Winner + next-opponent split at the training folds' mass-weighted
    mean empirical shares (unconditional, no features)."""
    w_shares = np.array([_actual_share(m, m["winner"]) for m in train])
    n_shares = np.array([_actual_share(m, m["next_opponent"]) for m in train])
    weights = np.array([abs(m["R"]) for m in train])
    n_mask = ~np.isnan(n_shares)
    return {
        "winner_share": float(np.average(w_shares, weights=weights)),
        "next_opponent_share": (float(np.average(n_shares[n_mask], weights=weights[n_mask]))
                               if n_mask.any() else 0.0),
    }


def rule_b_predict(m: dict, params: dict) -> dict[str, float]:
    out = {m["winner"]: params["winner_share"] * m["R"]}
    if m["next_opponent"] is not None:
        out[m["next_opponent"]] = params["next_opponent_share"] * m["R"]
    return out


def _weighted_ols(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    """Weighted least squares y ~ a + b*x. Returns (a, b). Falls back to
    the weighted mean (b=0) if x has ~no variance (avoids a wild slope
    estimate off a handful of points)."""
    if np.std(x) < 1e-6 or len(x) < 4:
        return float(np.average(y, weights=w)), 0.0
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(w)
    try:
        beta = np.linalg.solve(X.T @ W @ X, X.T @ W @ y)
        return float(beta[0]), float(beta[1])
    except np.linalg.LinAlgError:
        return float(np.average(y, weights=w)), 0.0


def rule_c_fit(train: list[dict]) -> dict:
    """Learned rule: winner_share, next_opponent_share, field_share ~
    a + b*q_winner, weighted least squares (weight = released mass),
    fit on the training folds only. Single feature (q_winner) deliberately
    -- q directly determines the *coherent* implied share
    (p_w*(1/q-1)/R in decompose.py), so it's the most theoretically
    motivated predictor, and 2 params/target keeps this defensible against
    overfitting relative to n-1 training matches per fold."""
    q = np.array([m["q_winner"] for m in train])
    R = np.array([abs(m["R"]) for m in train])
    w_shares = np.array([_actual_share(m, m["winner"]) for m in train])
    n_shares = np.array([_actual_share(m, m["next_opponent"]) for m in train])
    f_shares = np.array([
        sum(_actual_share(m, t) for t in _other_teams(m)) for m in train
    ])
    n_mask = ~np.isnan(n_shares)
    return {
        "winner": _weighted_ols(q, w_shares, R),
        "next_opponent": (_weighted_ols(q[n_mask], n_shares[n_mask], R[n_mask])
                          if n_mask.sum() >= 4 else (float(np.average(n_shares[n_mask], weights=R[n_mask])), 0.0)
                          if n_mask.any() else (0.0, 0.0)),
        "field": _weighted_ols(q, f_shares, R),
    }


def rule_c_predict(m: dict, params: dict) -> dict[str, float]:
    q = m["q_winner"]
    a_w, b_w = params["winner"]
    winner_share = a_w + b_w * q
    out = {m["winner"]: winner_share * m["R"]}
    if m["next_opponent"] is not None:
        a_n, b_n = params["next_opponent"]
        out[m["next_opponent"]] = (a_n + b_n * q) * m["R"]
    a_f, b_f = params["field"]
    field_share_total = (a_f + b_f * q) * m["R"]
    others = _other_teams(m)
    if others:
        pre_weights = np.array([m["pre"][t] for t in others])
        if pre_weights.sum() > 0:
            pre_weights = pre_weights / pre_weights.sum()
        else:
            pre_weights = np.full(len(others), 1.0 / len(others))
        for t, pw in zip(others, pre_weights):
            out[t] = field_share_total * pw
    return out


def match_error(m: dict, predicted: dict[str, float]) -> dict:
    """Squared/absolute error between predicted and actual delta, over
    every surviving team in this match (excluding the loser)."""
    teams = [t for t in m["delta"].index if t != m["loser"]]
    actual = m["delta"][teams]
    pred = pd.Series({t: predicted.get(t, 0.0) for t in teams})
    err = actual - pred
    out = {
        "match_id": m["match_id"], "sse": float((err ** 2).sum()),
        "mae_all": float(err.abs().mean()),
        "winner_abs_err": float(abs(err[m["winner"]])),
    }
    if m["next_opponent"] is not None:
        out["next_opp_abs_err"] = float(abs(err[m["next_opponent"]]))
    else:
        out["next_opp_abs_err"] = np.nan
    field_teams = _other_teams(m)
    out["field_sse"] = float((err[field_teams] ** 2).sum()) if field_teams else np.nan
    return out


RULES = {
    "a_naive": (lambda train: None, rule_a_predict),
    "b_winner_nextopp": (rule_b_fit, rule_b_predict),
    "c_learned_q": (rule_c_fit, rule_c_predict),
}


def loo_cv(datasets: list[dict]) -> pd.DataFrame:
    """Leave-one-match-out CV for every rule, plus the in-sample
    (fit-and-evaluate-on-everything) comparison for contrast."""
    rows = []
    n = len(datasets)
    for rule_name, (fit_fn, predict_fn) in RULES.items():
        # out-of-sample (proper LOO)
        for i in range(n):
            held_out = datasets[i]
            train = datasets[:i] + datasets[i + 1:]
            params = fit_fn(train)
            pred = predict_fn(held_out, params) if params is not None else predict_fn(held_out, train)
            err = match_error(held_out, pred)
            err.update({"rule": rule_name, "mode": "out_of_sample"})
            rows.append(err)
        # in-sample (fit on everything, evaluate on everything -- the
        # overfit-prone comparison, kept explicitly labeled)
        params_full = fit_fn(datasets) if fit_fn(datasets) is not None else None
        for m in datasets:
            pred = predict_fn(m, params_full) if params_full is not None else predict_fn(m, datasets)
            err = match_error(m, pred)
            err.update({"rule": rule_name, "mode": "in_sample"})
            rows.append(err)
    return pd.DataFrame(rows)


def cv_summary(cv: pd.DataFrame) -> pd.DataFrame:
    agg = cv.groupby(["rule", "mode"]).agg(
        n=("match_id", "count"),
        mean_sse=("sse", "mean"), median_sse=("sse", "median"),
        mean_mae_all=("mae_all", "mean"),
        mean_winner_abs_err=("winner_abs_err", "mean"),
        mean_next_opp_abs_err=("next_opp_abs_err", "mean"),
        mean_field_sse=("field_sse", "mean"),
    ).reset_index()
    return agg.round(5)


def win_rate_table(cv: pd.DataFrame) -> pd.DataFrame:
    """Per-fold win rate (rule beats naive rule a) out-of-sample, with a
    two-sided binomial test against 50/50 -- robust to the aggregate mean
    being dragged around by a few outlier folds (which mean_sse is not).
    This is the more honest headline number given n is small."""
    from scipy.stats import binomtest

    oos = cv[cv["mode"] == "out_of_sample"]
    rows = []
    for metric in ["sse", "mae_all", "winner_abs_err"]:
        piv = oos.pivot(index="match_id", columns="rule", values=metric)
        n = len(piv)
        for rule in ["b_winner_nextopp", "c_learned_q"]:
            wins = int((piv[rule] < piv["a_naive"]).sum())
            p = float(binomtest(wins, n, 0.5).pvalue)
            rows.append({"metric": metric, "rule": rule, "beats_naive": wins,
                        "n_folds": n, "win_rate": round(wins / n, 3),
                        "binomial_p_value": round(p, 4)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Step 4: tradability -- realized (not hypothetical) post-fee P&L using
# LOO-predicted weights on the outcome that ACTUALLY happened
# ---------------------------------------------------------------------

def tradability_check(datasets: list[dict], rule_name: str,
                      n_contracts: int = 1000, fee_rate: float = FEE_RATE) -> pd.DataFrame:
    """For each match, held out of training (LOO), predict weights from the
    other matches, then compute the REALIZED P&L of holding the loser's
    champ position (entry = pre-match price) plus a basket sized
    proportionally to the rule's predicted share (contracts_j =
    predicted_share_j * n_contracts, so a perfect naive prediction is
    exactly a 1:1 offset), using the ACTUAL realized post-match prices --
    no hypothetical symmetric-outcome assumption, unlike decompose.hedge_pnl.
    """
    fit_fn, predict_fn = RULES[rule_name]
    rows = []
    n = len(datasets)
    for i in range(n):
        held_out = datasets[i]
        train = datasets[:i] + datasets[i + 1:]
        params = fit_fn(train)
        pred = predict_fn(held_out, params) if params is not None else predict_fn(held_out, train)

        R = held_out["R"]
        loser = held_out["loser"]
        loser_pre_c = held_out["pre"][loser] * 100
        loser_post_c = held_out["post"][loser] * 100
        loser_pnl = n_contracts * (loser_post_c - loser_pre_c) / 100

        basket_pnl = 0.0
        basket_cost_c = 0.0
        for team, pred_delta in pred.items():
            share = pred_delta / R if R else 0.0
            contracts = share * n_contracts
            pre_c = held_out["pre"][team] * 100
            post_c = held_out["post"][team] * 100
            p = pre_c / 100
            fee_c = fee_rate * p * (1 - p) * 100 * abs(contracts)
            leg_pnl = contracts * (post_c - pre_c) / 100 - fee_c / 100
            basket_pnl += leg_pnl
            basket_cost_c += abs(contracts) * pre_c

        rows.append({
            "match_id": held_out["match_id"], "rule": rule_name,
            "loser_pnl": round(loser_pnl, 2), "basket_pnl": round(basket_pnl, 2),
            "net_pnl": round(loser_pnl + basket_pnl, 2),
            "basket_notional_c": round(basket_cost_c, 2),
        })
    return pd.DataFrame(rows)


def tradability_summary(datasets: list[dict], sample_label: str, variant: str) -> pd.DataFrame:
    rows = []
    for rule in RULES:
        t = tradability_check(datasets, rule)
        rows.append({
            "sample": sample_label, "variant": variant, "rule": rule,
            "n": len(t), "mean_net_pnl": round(float(t.net_pnl.mean()), 2),
            "median_net_pnl": round(float(t.net_pnl.median()), 2),
            "n_positive": int((t.net_pnl > 0).sum()),
            "pct_positive": round(float((t.net_pnl > 0).mean()), 3),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def main() -> None:
    snapshots = pd.read_csv(PROC / "snapshots.csv")
    matches = pd.read_csv(PROC / "matches.csv")

    all_weights, all_cv, all_winrate, all_trade = [], [], [], []

    for variant in ["single", "vwap3"]:
        ds = build_dataset(snapshots, matches, variant)
        ds_filtered = [m for m in ds if abs(m["R"]) >= MIN_RELEASED]
        print(f"[{variant}] n={len(ds)} matches built, {len(ds_filtered)} pass "
             f"R>={MIN_RELEASED} filter")

        wt = weights_table(ds)
        all_weights.append(wt)

        for sample_label, subset in [("full", ds), ("filtered_R", ds_filtered)]:
            if len(subset) < 4:
                print(f"  skipping {sample_label} ({variant}): too few matches ({len(subset)})")
                continue
            cv = loo_cv(subset)
            summ = cv_summary(cv)
            summ.insert(0, "sample", sample_label)
            summ.insert(0, "variant", variant)
            all_cv.append(summ)

            wr = win_rate_table(cv)
            wr.insert(0, "sample", sample_label)
            wr.insert(0, "variant", variant)
            all_winrate.append(wr)

            trade = tradability_summary(subset, sample_label, variant)
            all_trade.append(trade)

    weights_df = pd.concat(all_weights, ignore_index=True)
    cv_df = pd.concat(all_cv, ignore_index=True)
    winrate_df = pd.concat(all_winrate, ignore_index=True)
    trade_df = pd.concat(all_trade, ignore_index=True)

    weights_df.to_csv(PROC / "absorption_basket_weights.csv", index=False)
    cv_df.to_csv(PROC / "absorption_basket_cv.csv", index=False)
    winrate_df.to_csv(PROC / "absorption_basket_winrate.csv", index=False)
    trade_df.to_csv(PROC / "absorption_basket_tradability.csv", index=False)

    print("\n=== CV summary (out_of_sample rows only) ===")
    print(cv_df[cv_df["mode"] == "out_of_sample"].to_string(index=False))
    print("\n=== Win-rate vs naive (out-of-sample) ===")
    print(winrate_df.to_string(index=False))
    print("\n=== Tradability (LOO, post-fee, realized) ===")
    print(trade_df.to_string(index=False))
    print(f"\nWrote {PROC/'absorption_basket_weights.csv'}, "
         f"{PROC/'absorption_basket_cv.csv'}, "
         f"{PROC/'absorption_basket_winrate.csv'}, "
         f"{PROC/'absorption_basket_tradability.csv'}")


if __name__ == "__main__":
    main()
