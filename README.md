# Kalshi Knockout Absorption Analysis

When a World Cup team is eliminated, where does its championship probability
*go*? This project measures that redistribution empirically on real Kalshi
markets, builds a repricing simulator on top of the answer, and — this is
the part most writeups skip — documents the methodology mistakes that
would have produced a false positive if left uncaught.

**Bottom line up front:** the trade thesis that motivated this project does
**not** hold up under clean measurement. That's a real result, not a
non-result — see [§3](#3-the-headline-finding-and-why-it-changed).

---

## 1. Motivation

I held 1,000 Belgium championship-YES contracts at 1.28¢ and was considering
buying USA-advances (54¢, implied ~53% for USA) as a hedge for the
USA-vs-Belgium knockout match. The logic: if Belgium loses, my champ
position goes to ~0, but the hedge pays out. If Belgium wins instead, my
champ position should *reprice upward* — Belgium just proved it can beat a
credible opponent — potentially by more than simple coherence implies, since
markets are known to sometimes over-reward winners relative to what the math
says they should. If that over-reward ("excess absorption") is real and
priced in cheaply enough, the hedge has edge beyond a simple insurance
trade.

That "does the market over-reward winners" question is answerable with
data Kalshi publishes for free: every knockout match has a live
match-winner market (`KXWCADVANCE`, "does team X advance?") and a
championship market (`KXMENWORLDCUP`, "does team X win the whole
tournament?"). Coherence between the two pins down exactly what a winner's
championship price *should* do when they advance. Whatever it actually does
beyond that is the edge (or the leak).

## 2. The methodology, as it actually happened

This section is the part a polished results page usually hides. It's here
on purpose — the mistakes and how they were caught are as much the point of
this project as the final number.

**Phase 0 — build on synthetic data first.** Before touching real markets,
the whole pipeline (`demo/run_demo.py`) was validated against a synthetic
bracket with known ground truth, specifically to see how noisy the
estimator gets when a knockout's released probability mass is tiny (a
heavy favorite eliminating a no-hoper). It's very noisy — ±0.3 swings in
`excess_absorption` from 4% price noise alone. That caveat shaped
everything downstream (VWAP smoothing, mass-weighting, filtering tiny
`released` matches).

**Phase 1 — real data has its own bugs.** The initial `src/config.py` series
tickers were guesses (`KXWCUP`, `KXWCUPGAME`) and both were wrong — the real
tickers are `KXMENWORLDCUP` and `KXWCADVANCE`, found via
`src/discover.py`. Kalshi's price fields turned out to be `*_dollars`
strings, not the cents-integers the client code assumed — a silent `None`,
not a 404, so it wouldn't have failed loudly. A subtler one: once a market
goes quiet (thin trading, or right after it settles), the order book snaps
to a no-liquidity default (`yes_bid=$0`, `yes_ask=$1`), and naively taking
the bid/ask midpoint reads that as a fake 50¢ — confirmed on a just-eliminated
team whose real settlement price was $0.001. Fixed by preferring last-trade
price over bid/ask mid, and dropping zero-volume candles outright. There's
also a full write-up of the champion-market vs. advance-market team-code
crosswalk (`US` vs `USA`, `GB` vs `ENG`, etc. — the two market families use
different code conventions for the same team) in `src/config.py`.

**Phase 2 — first measurement looked like a real edge.** Once the pipeline
ran clean on real settled knockouts, `excess_absorption` averaged **~1.18**
for underdog wins — i.e. winners appeared to gain ~18% more championship
probability than coherence implies. That's the original hedge thesis,
looking confirmed.

**Phase 3 — built a simulator on top of the (still unvalidated) finding.**
To go from "one number averaged across matches" to "what should happen if
*this specific* match resolves *this specific* way," `simulator/` adds a
double-Poisson in-play match model, an exact bracket dynamic program with
market-anchored strength ratings, and an absorption-adjustment layer using
the measured `excess_absorption`. It's wired to live Kalshi data and the
actual confirmed 2026 knockout bracket (verified via web research against
three independent sources, since Kalshi doesn't publish the bracket tree
directly), with a Streamlit app (`simulator/app.py`) on top.

**Phase 4 — a review caught a contamination bug, and the "edge" mostly
disappeared.** The snapshot windows used to measure a team's championship
price before/after a match had no boundary against *other* matches. This
tournament runs knockouts close together, so a team's "after" snapshot for
match A could silently include the result of match B settling inside that
window. The clearest case: Belgium's next opponent, Spain, had *also* just
beaten Portugal the same evening — inside the window used to measure
Belgium's match. Spain's own win got misattributed as "market reaction to
Belgium's win." **21 of 22 matches had this problem.** Fixed by clipping
every match's window against every other match's settlement time
(`src/pull_data.py`, `clipped_window()`). Post-fix: `excess_absorption`
collapsed to **~1.0** — no measurable edge. Full before/after numbers in
`RUN_NOTES.md`.

**Phase 5 — replaced a toy validation with a real one.** The simulator's
first backtest used a 4-node "toy" bracket (winner, loser, next-opponent,
one synthetic placeholder) that inflated predicted price swings 3-10x
versus what actually happened, because it compressed a 4-5-round tournament
into a 2-round toy. Rebuilt against the *real* confirmed bracket for the
matches where that's exactly reconstructable — mean error dropped ~7x
(`simulator/backtest_report_v2.md`).

**Phase 6 — checked the null result two more ways, so it wouldn't be a
one-off.** Averaging one number across 22 matches can hide structure, so
two follow-up studies stress-tested the pooled finding instead of trusting
it:

- `src/absorption_basket.py` — does an *optimized basket* of surviving
  teams replicate the released mass better than "all of it goes to the
  match winner"? Tested with leave-one-match-out cross-validation across
  three rules of increasing sophistication. Result: **no** — a learned rule
  is consistently *worse* out-of-sample than the naive baseline (classic
  overfitting on n≈22), and no basket rule survives Kalshi's taker fee once
  sized realistically.
- `src/absorption_by_tier.py` — does the answer depend on *who* got
  eliminated — a genuine contender (rare, large released mass) vs. a
  longshot (frequent, negligible mass)? The natural break in the data (a
  3.8x gap) splits 22 matches into 6 contender eliminations and 16
  longshot ones. Result: contender eliminations are **not** worse-priced
  than longshot ones — if anything the opposite. One genuinely suggestive
  but unconfirmed pattern turned up (a surviving team's own price
  correlates with how much it absorbs, in 5 of 6 contender matches) and is
  flagged explicitly as hypothesis-generating, not a finding, given n=6.

Every phase above has a corresponding report checked into this repo — see
[§5](#5-further-reading).

## 3. The headline finding, and why it changed

| | First pass | After the contamination fix |
|---|---|---|
| `ea_underdog` | 1.183 | **1.018** |
| `ea_favorite` | 1.011 | 0.989 |
| `next_opp_share_underdog` | 0.61 | **0.226** |

**The honest current conclusion:** at these prices, the "hold longshot champ
+ buy opponent-advances" hedge is a coin flip minus fees. Kalshi's
championship and match markets are, to measurement precision, internally
consistent with each other — winners get repriced by almost exactly what
coherence predicts, no more. That holds up when checked by strength tier,
and no smarter basket-replication rule beats the naive view out-of-sample
either. The specific trade is not live. The tooling — data pipeline,
decomposition, simulator, and both follow-up studies — is validated and
reusable for the *next* tournament round, or the next question.

## 4. Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Verify series tickers (already filled in src/config.py from this
#    tournament; re-run if tickers change or you're adapting to a new event)
python -m src.discover --find-series "world cup"
python -m src.discover --champion

# 2. Draft/refresh the knockout match list as new rounds settle
python -m src.discover --draft-matches

# 3. Pull candlesticks + build the decontaminated pre/post snapshot tables
python -m src.pull_data

# 4. Core decomposition + hedge P&L
python run_analysis.py           # or: jupyter lab notebooks/analysis.ipynb

# 5. Refit and validate the simulator
python -m simulator.fit_ea
python -m simulator.backtest_v2
python -m simulator.run_live

# 6. Interactive app (live board, match simulator, hedge builder)
streamlit run simulator/app.py

# 7. Follow-up robustness studies
python -m src.absorption_basket
python -m src.absorption_by_tier
```

No API key needed for any of the above — all market-data endpoints are
public. If rate-limited, raise `sleep_s` in `KalshiPublic`. A few
authenticated, read-only order-book pulls exist as one-off scripts; see
`.env.example` if you need those (never commit real keys — `.env` is
gitignored).

### Demo (no network needed)

`python demo/run_demo.py` runs the identical decomposition against a
synthetic bracket with known ground truth — this is what caught the
small-`released`-mass noise problem in Phase 0, before any real data was
involved.

## 5. Further reading

This repo is organized so the narrative is followable in order:

| File | What it covers |
|---|---|
| `METRICS_REFERENCE.md` | Every metric defined precisely, with worked interpretation — the doc to re-read when a number is confusing. |
| `RUN_NOTES.md` | Full run log, including the exact contamination bug and fix (Phase 4). |
| `simulator/SIMULATOR.md`, `simulator/backtest_report_v2.md` | Simulator design and its real-bracket validation (Phase 5). |
| `simulator/app_verification.md` | Streamlit app pages verified end-to-end against live data. |
| `absorption_basket_report.md` | The basket-replication null result (Phase 6a). |
| `absorption_by_tier_report.md` | The contender-vs-longshot tier analysis (Phase 6b). |
| `CLAUDE.md` | Working context/state for continuing this project with an AI pair-programmer. |

## 6. Interpretation cheatsheet

| Quantity | Meaning |
|---|---|
| `released` | The loser's championship probability just before the match — the size of the pie being redistributed. Unstable when tiny; matches with `released < 0.005` are filtered from headline conclusions. |
| `winner_share` | Fraction of the loser's released mass the match-winner's championship price absorbed. **Can exceed 1** — the winner also drains probability from its *future opponents*, whose path just got harder. Not a "split of a pie that sums to 1." |
| `implied_winner_share` | What `winner_share` *should* be under pure coherence: `p_winner_pre × (1/q − 1) / released`. The benchmark the whole hedge thesis is measured against. |
| `excess_absorption` (ea) | `winner_share ÷ implied_winner_share`. **This is the headline metric.** 1.0 = coherent, no edge. Current best clean estimate: ≈1.0. |
| `next_opponent_share` | Signed: expected negative when a favorite advances (the next opponent's path hardened), positive when the underdog does. Most sensitive to the window-contamination bug. |
| `field_share` | Everyone else's combined share. Usually negative — the field's paths tend to harden when a live team advances. |

## 7. Known estimator caveats

- Tiny `released` → tiny denominator → very noisy shares (Phase 0's
  synthetic test showed ±0.3 swings in `excess_absorption` from just 4%
  price noise). Prefer VWAP-of-several-candles, and mass-weight any
  cross-match aggregate.
- Snapshot windows are clipped against neighboring matches' settlements
  (Phase 4) — don't widen them back without re-checking for contamination.
- Vig drift between snapshots is normalized out inside the decomposition;
  `raw_vig_pre/post` columns let you flag any snapshot where that
  normalization is doing a lot of work.
- Longshot prices carry the standard favorite-longshot bias; normalized
  prices ≠ true probabilities. The decomposition is internally consistent
  regardless, but level-based conclusions (not share-based ones) need care.
- Kalshi's price-field schema (`*_dollars` strings, not cents-ints) and
  candlestick shape can change; see the verification note in
  `src/kalshi_client.py`.
- Every parameter fit in this project (`ea_params.json`, the basket rules,
  the tier comparison) is fit on ≤22 matches, in-sample. Treat all of it as
  provisional and refit as more knockouts settle — this is called out
  explicitly in every report, not just here.

## 8. Layout

```
src/
  kalshi_client.py        public API client (dollars-string price convention)
  config.py               series tickers, knockout match list, team-code crosswalk
  discover.py             find tickers, draft the match list from the bracket
  pull_data.py            candlesticks -> decontaminated pre/post snapshot tables
  decompose.py            core decomposition + hedge P&L
  plotting.py             charts
  absorption_basket.py    Phase 6a: basket-replication test (result: negative)
  absorption_by_tier.py   Phase 6b: contender-vs-longshot tier test
simulator/
  match_model.py          in-play double-Poisson match model
  bracket.py              exact bracket DP + market-anchored strength ratings
  bracket_2026.py         the real, confirmed 2026 knockout bracket
  engine.py               absorption adjustment + query API
  live_inputs.py          live Kalshi pull -> simulator inputs
  fit_ea.py               refits ea_params.json from the decomposition
  app.py                  Streamlit app (live board / match sim / hedge builder)
  backtest.py, backtest_v2.py   toy-bracket and real-bracket validation
demo/run_demo.py          synthetic end-to-end validation (Phase 0)
notebooks/analysis.ipynb
data/                     raw candles + processed snapshots/decomposition CSVs
results/, *_results.zip   plots and bundled deliverables per phase
```
