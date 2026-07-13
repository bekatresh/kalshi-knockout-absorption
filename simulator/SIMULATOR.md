# Simulator — bracket repricing engine

Answers: "if fixture X goes to score S at minute M (or settles with outcome
O), how should every remaining team's championship probability move — and
what will the market *likely* do given measured absorption behavior?"

Drop this `simulator/` folder into the kalshi-knockout-absorption repo root,
next to `src/`. Run everything from repo root.

## Layers

1. **Match model** (`match_model.py`) — double-Poisson goals, calibrated by
   bisection so pre-match advance prob == Kalshi match market. In-play
   states → conditional advance prob. ET (1.05x intensity) + penalties
   (coin flip) for knockout draws.
2. **Bracket DP** (`bracket.py`) — EXACT championship probabilities (no MC
   noise). Strength inversion fits per-team ratings so unconditional champ
   probs reproduce market championship prices, with round-1 fixtures pinned
   to their live match markets (ratings only explain rounds 2+; absorbs
   match-vs-champ price non-transitivity).
3. **Absorption adjustment** (`engine.py`, params via `fit_ea.py`) — scales
   the (probable) winner's consistent delta by the measured excess
   absorption (underdog 1.18 / favorite 1.01 as of Jul 6), faded by
   `decisiveness` for in-play states, others renormalized.

## Usage

```python
from simulator.engine import Simulator
sim = Simulator(TEAMS, MARKET_CHAMP, MATCH_MARKETS)   # see demo_sim.py
sim.query(("FRA","MAR"), score=(0,1), minute=15)      # in-play
sim.query(("FRA","MAR"), outcome="MAR")               # settled
sim.screen_fixtures()                                  # hedge screen table
```

`python simulator/demo_sim.py` runs with placeholder prices/bracket.

## What Claude Code must wire up (in order)

1. **Live inputs**: replace demo placeholders with pulls — champ prices
   (KXMENWORLDCUP, remember the TEAM_CODE_MAP crosswalk from src/config.py)
   and match markets (KXWCADVANCE) for the real remaining fixtures. Reuse
   src/kalshi_client.py + the dollars() convention from the understat work.
2. **Real bracket structure**: the demo's 8-team seed order is a GUESS.
   Verify the actual draw (web search) — DP pairing depends on seed order
   being right. If remaining teams ≠ power of 2 (mid-round), pin already-
   settled fixtures via overrides rather than shrinking the bracket.
3. **Refit ea**: `python -m simulator.fit_ea`; make Simulator load
   ea_params.json when present.
4. **Backtest Layer 1** (validation gift): for settled matches, feed the
   known final states into query() and compare predicted champ deltas vs
   the actual deltas in data/processed/snapshots.csv. Report MAE by team
   bucket (winner / next opponent / field). This is the single best check
   that the whole stack is trustworthy.
5. Optional: per-fixture `mu` from Kalshi totals markets if they exist.

## Interpretation warnings

- Champ probs are normalized WITHIN the bracket teams; raw Kalshi prices
  include vig and long-tail residue. Map model probs back to price space by
  multiplying by (sum of raw remaining-team prices) before comparing to
  quotes for trade signals.
- `decisiveness` fading of ea for in-play states is a v0 heuristic (an
  early goal is not an elimination). The Layer-1 backtest will show whether
  it's roughly right.
- Poisson independence understates late one-goal-game drama; treat minute
  75+ numbers as approximate.
- ea params rest on 7 filtered matches (4 underdog). Refit every round.
