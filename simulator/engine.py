"""
Layer 3 + query interface.

Simulator.query() answers: "if fixture X reaches state S (score/minute) or
outcome O, how do all championship probabilities move?"

Outputs THREE columns per team:
  champ_pre        current market-anchored probability
  champ_consistent what coherent markets would reprice to (bracket DP)
  champ_adjusted   what the market will *likely* do, applying the measured
                   absorption regularities (excess absorption by winner,
                   next-opponent flow) from decomposition_results.csv

The adjustment is a v0 heuristic, clearly parameterized:
  - the winner's consistent delta is scaled by ea (underdog/favorite branch)
  - scaling is faded by `decisiveness` for in-play states (a 15th-minute
    goal is not an elimination; ea applies fully only at settlement)
  - everyone else's deltas are rescaled so probabilities still sum to 1
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .bracket import Bracket
from .match_model import Match

_EA_PARAMS_PATH = Path(__file__).parent / "ea_params.json"


def _load_ea_defaults() -> tuple[float, float]:
    """Load refit ea params (simulator/fit_ea.py) if present, else fall back
    to the original hardcoded 7-match (n=4 underdog) estimate."""
    if _EA_PARAMS_PATH.exists():
        try:
            params = json.loads(_EA_PARAMS_PATH.read_text())
            return float(params["ea_underdog"]), float(params["ea_favorite"])
        except Exception:
            pass
    return 1.18, 1.01


# Defaults: refit from simulator/fit_ea.py when ea_params.json exists,
# otherwise the original hardcoded 7-match (n=4 underdog) estimate.
EA_UNDERDOG, EA_FAVORITE = _load_ea_defaults()


@dataclass
class Simulator:
    teams: list[str]
    market_champ: dict[str, float]          # current champ prices (prob units)
    match_markets: dict[tuple[str, str], float]  # {(A,B): P(A advances)} live
    mu_totals: dict[tuple[str, str], float] = field(default_factory=dict)
    ea_underdog: float = EA_UNDERDOG
    ea_favorite: float = EA_FAVORITE
    calib_lr: float = 0.6
    calib_iters: int = 400

    def __post_init__(self):
        self.bracket = Bracket(self.teams)
        # Round-1 matches use the LIVE match market, not the rating-implied
        # probability — market info dominates for priced fixtures.
        self.base_overrides = {pair: q for pair, q in self.match_markets.items()}
        self.calib = self.bracket.calibrate_to_market(
            self.market_champ, overrides=self.base_overrides,
            lr=self.calib_lr, iters=self.calib_iters)
        self._pre = self._probs(self.base_overrides)

    def _probs(self, overrides) -> pd.Series:
        p = self.bracket.champ_probs(overrides)
        return pd.Series(p / p.sum(), index=self.teams)

    def _match(self, fixture: tuple[str, str]) -> Match:
        q = self.match_markets.get(fixture)
        if q is None:
            a, b = fixture
            q = 1 - self.match_markets[(b, a)]
            fixture = (a, b)
        mu = self.mu_totals.get(fixture, 2.6)
        return Match(fixture[0], fixture[1], q_a=q, mu=mu).calibrate()

    def query(self, fixture: tuple[str, str],
              score: tuple[int, int] | None = None,
              minute: float | None = None,
              outcome: str | None = None) -> pd.DataFrame:
        """
        fixture: (team_a, team_b) as listed in match_markets.
        Either give an in-play state (score, minute) or outcome=team_code.
        """
        a, b = fixture
        if fixture in self.match_markets:
            q_pre = self.match_markets[fixture]
        else:
            # tolerate reversed order, same as _match() -- callers shouldn't
            # need to know which order a fixture was stored in
            q_pre = 1 - self.match_markets[(b, a)]

        if outcome is not None:
            q_live = 1.0 if outcome == a else 0.0
            decisiveness = 1.0
            state = f"{outcome} advances (settled)"
        else:
            m = self._match(fixture)
            q_live = m.live_advance_prob(score, minute)
            # how much of the eventual elimination has "happened"
            decisiveness = abs(q_live - q_pre) / max(q_pre, 1 - q_pre)
            state = f"{a} {score[0]}-{score[1]} {b} @ {minute:.0f}'"

        over = dict(self.base_overrides)
        over[fixture] = q_live
        post = self._probs(over)

        # ---- Layer 3: absorption adjustment on the (probable) winner ----
        winner = a if q_live >= q_pre else b        # whoever the state favors
        was_underdog = (q_pre < 0.5) if winner == a else (q_pre > 0.5)
        ea = self.ea_underdog if was_underdog else self.ea_favorite
        ea_eff = 1 + (ea - 1) * decisiveness

        adj = post.copy()
        delta_w = post[winner] - self._pre[winner]
        adj[winner] = self._pre[winner] + ea_eff * delta_w
        others = adj.index != winner
        resid = 1 - adj[winner]
        adj[others] = adj[others] * resid / adj[others].sum()

        out = pd.DataFrame({
            "champ_pre": self._pre, "champ_consistent": post,
            "champ_adjusted": adj,
            "delta_consistent": post - self._pre,
            "delta_adjusted": adj - self._pre,
        }).sort_values("champ_pre", ascending=False)
        out.attrs.update(state=state, q_pre=q_pre, q_live=q_live,
                         decisiveness=decisiveness, winner=winner,
                         ea_applied=ea_eff)
        return out

    def screen_fixtures(self) -> pd.DataFrame:
        """Both-outcome repricing summary for every round-1 fixture —
        the hedge-screening table."""
        rows = []
        for (a, b), q in self.match_markets.items():
            for team, other in ((a, b), (b, a)):
                res = self.query((a, b), outcome=team)
                rows.append({
                    "fixture": f"{a}-{b}", "if_advances": team,
                    "prob": q if team == a else 1 - q,
                    f"champ_move_{'winner'}":
                        f"{team}: {res.champ_pre[team]*100:.2f} -> "
                        f"{res.champ_adjusted[team]*100:.2f}c",
                    "loser_released_pts": round(res.champ_pre[other] * 100, 2),
                    "biggest_third_party_move":
                        res.drop([a, b]).delta_adjusted.abs().idxmax(),
                })
        return pd.DataFrame(rows)
