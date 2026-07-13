"""
Layer 2 — Bracket engine.

Single-elimination bracket with EXACT championship probabilities via dynamic
programming (no Monte Carlo noise), and strength inversion: per-team ratings
are fitted so the unconditional champ probabilities reproduce the market's
championship prices. The simulator is therefore market-anchored by
construction; conditional queries (pin an outcome, set an in-play advance
probability) re-run the DP with an overridden pairwise matrix.

Bracket format: list of team codes in seed order. Round 1 pairs (0,1),
(2,3), ...; winners pair up in order. len must be a power of 2.

DP: reach[i, 0] = 1
    reach[i, r+1] = reach[i, r] * sum_{j in opposite half of i's block}
                     reach[j, r] * P_adv[i, j]
Champ prob = reach[i, n_rounds].
"""

from __future__ import annotations

import numpy as np

from .match_model import Match


def _blocks(n_teams: int, rnd: int):
    """Yield (block_start, half_size) for round rnd (0-indexed)."""
    size = 2 ** (rnd + 1)
    for start in range(0, n_teams, size):
        yield start, size // 2


class Bracket:
    def __init__(self, teams: list[str], mu: float = 2.6):
        n = len(teams)
        assert n & (n - 1) == 0, "bracket size must be a power of 2"
        self.teams = list(teams)
        self.idx = {t: i for i, t in enumerate(teams)}
        self.n = n
        self.rounds = int(np.log2(n))
        self.mu = mu
        self.r = np.zeros(n)              # log-strength ratings
        self._pairwise_cache: np.ndarray | None = None

    # ---- pairwise advance matrix from ratings ----
    def pairwise(self) -> np.ndarray:
        if self._pairwise_cache is not None:
            return self._pairwise_cache
        P = np.full((self.n, self.n), 0.5)
        for i in range(self.n):
            for j in range(i + 1, self.n):
                m = Match(self.teams[i], self.teams[j], q_a=0.5, mu=self.mu)
                m.d = (self.r[i] - self.r[j]) / 2
                la, lb = m.rates()
                from .match_model import advance_prob
                p = advance_prob(la, lb)
                P[i, j], P[j, i] = p, 1 - p
        self._pairwise_cache = P
        return P

    # ---- exact champ probabilities ----
    def champ_probs(self, overrides: dict[tuple[str, str], float] | None = None
                    ) -> np.ndarray:
        """
        overrides: {(team_a, team_b): P(team_a advances)} — applied
        symmetrically. Use to pin outcomes (1.0/0.0) or inject live
        in-play advance probabilities from Layer 1.
        """
        P = self.pairwise().copy()
        for (a, b), p in (overrides or {}).items():
            ia, ib = self.idx[a], self.idx[b]
            P[ia, ib], P[ib, ia] = p, 1 - p

        reach = np.ones(self.n)
        for rnd in range(self.rounds):
            new = np.zeros(self.n)
            for start, half in _blocks(self.n, rnd):
                left = slice(start, start + half)
                right = slice(start + half, start + 2 * half)
                for i in range(start, start + half):
                    new[i] = reach[i] * (reach[right] * P[i, right]).sum()
                for i in range(start + half, start + 2 * half):
                    new[i] = reach[i] * (reach[left] * P[i, left]).sum()
            reach = new
        return reach

    # ---- strength inversion ----
    def calibrate_to_market(self, market_champ: dict[str, float],
                            overrides: dict[tuple[str, str], float] | None = None,
                            iters: int = 400, lr: float = 0.6,
                            tol: float = 1e-6, verbose: bool = False) -> dict:
        """
        Fit ratings so champ_probs() matches market championship prices
        (renormalized over bracket teams). Pass the live round-1 match
        markets as `overrides` — round-1 probabilities then come from the
        market directly and ratings only need to explain later rounds.
        This also absorbs any non-transitivity between a team's match odds
        and its championship price.
        """
        target = np.array([market_champ[t] for t in self.teams], dtype=float)
        target = target / target.sum()
        hist = []
        for k in range(iters):
            self._pairwise_cache = None
            sim = self.champ_probs(overrides)
            sim = sim / sim.sum()
            err = float(np.abs(sim - target).max())
            hist.append(err)
            if err < tol:
                break
            self.r += lr * np.log(np.maximum(target, 1e-9) /
                                  np.maximum(sim, 1e-9))
            self.r -= self.r.mean()
        self._pairwise_cache = None
        if verbose:
            print(f"calibration: {k+1} iters, max abs err {err:.2e}")
        return {"iters": k + 1, "max_abs_err": err, "history": hist}
