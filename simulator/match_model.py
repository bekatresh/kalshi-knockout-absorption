"""
Layer 1 — In-play match model.

Double-Poisson goal model per fixture, calibrated so the PRE-MATCH advance
probability exactly matches the Kalshi match market. Any in-play state
(score, minute) then maps to a conditional advance probability.

Model:
  goals_A ~ Poisson(lam_A * t_remaining_frac)
  goals_B ~ Poisson(lam_B * t_remaining_frac)
  lam_A = (mu/2) * exp(+d),  lam_B = (mu/2) * exp(-d)
    mu = expected total goals in 90' (default 2.6; override per match from
         a totals market if you have one)
    d  = strength split, solved by bisection so P(A advances) == q_market
  Draws after 90' -> extra time (30' at ET_INTENSITY x per-minute rate);
  still level -> penalties at PENS_PROB_A (default 0.5).

Known limitations (documented, not hidden):
  - Independent Poissons; no Dixon-Coles low-score correlation adjustment.
  - No red cards / momentum; late-game desperation only via LATE_BOOST.
  - Penalties treated as skill-free coin flip by default.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson

MAX_GOALS = 12          # truncation for score distributions
ET_INTENSITY = 1.05     # ET per-minute scoring vs regulation
PENS_PROB_A = 0.5
LATE_BOOST = 1.0        # >1 inflates rates in final minutes (v0: off)


def _score_dist(lam: float, n: int = MAX_GOALS) -> np.ndarray:
    p = poisson.pmf(np.arange(n + 1), lam)
    p[-1] += 1 - p.sum()  # dump tail into last bucket
    return p


def outcome_probs(lam_a: float, lam_b: float) -> tuple[float, float, float]:
    """(P(A more goals), P(level), P(B more goals)) over a segment."""
    pa, pb = _score_dist(lam_a), _score_dist(lam_b)
    m = np.outer(pa, pb)
    win_a = np.tril(m, -1).sum()   # rows = A goals
    draw = np.trace(m)
    return win_a, draw, m.T[np.tril_indices_from(m, -1)].sum() if False else 1 - win_a - draw


def advance_prob(lam_a: float, lam_b: float, pens_a: float = PENS_PROB_A,
                 goal_diff: int = 0) -> float:
    """
    P(A advances) given remaining-segment rates and current goal_diff
    (A minus B). Draw on aggregate -> ET -> pens.
    """
    pa, pb = _score_dist(lam_a), _score_dist(lam_b)
    m = np.outer(pa, pb)
    i, j = np.indices(m.shape)
    final_diff = goal_diff + (i - j)
    p_win90 = m[final_diff > 0].sum()
    p_draw90 = m[final_diff == 0].sum()

    # extra time (30 minutes at ET intensity, rates are per-90 units)
    et_a = lam_a * (30 / 90) * ET_INTENSITY if lam_a > 0 else 0.26 * ET_INTENSITY
    et_b = lam_b * (30 / 90) * ET_INTENSITY if lam_b > 0 else 0.26 * ET_INTENSITY
    ea_, eb_ = _score_dist(et_a), _score_dist(et_b)
    met = np.outer(ea_, eb_)
    ii, jj = np.indices(met.shape)
    p_et_win_a = met[ii > jj].sum()
    p_et_draw = met[ii == jj].sum()

    return p_win90 + p_draw90 * (p_et_win_a + p_et_draw * pens_a)


@dataclass
class Match:
    team_a: str
    team_b: str
    q_a: float               # market pre-match advance prob for team_a
    mu: float = 2.6          # expected total goals in 90'
    d: float = 0.0           # solved strength split

    def calibrate(self) -> "Match":
        lo, hi = -3.0, 3.0
        for _ in range(60):
            mid = (lo + hi) / 2
            la, lb = (self.mu / 2) * np.exp(mid), (self.mu / 2) * np.exp(-mid)
            if advance_prob(la, lb) < self.q_a:
                lo = mid
            else:
                hi = mid
        self.d = (lo + hi) / 2
        return self

    def rates(self) -> tuple[float, float]:
        return (self.mu / 2) * np.exp(self.d), (self.mu / 2) * np.exp(-self.d)

    def live_advance_prob(self, score: tuple[int, int], minute: float) -> float:
        """P(team_a advances | score at minute). minute in [0, 90]."""
        la, lb = self.rates()
        frac = max(0.0, (90 - minute) / 90) * (LATE_BOOST if minute >= 75 else 1.0)
        return advance_prob(la * frac, lb * frac,
                            goal_diff=score[0] - score[1])

    def sanity(self) -> dict:
        la, lb = self.rates()
        return {"lam_a": round(la, 3), "lam_b": round(lb, 3),
                "check_q": round(advance_prob(la, lb), 4), "target_q": self.q_a}
