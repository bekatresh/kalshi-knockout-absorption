# Project context for Claude Code

## Goal
Measure how eliminated teams' championship probability redistributes in
Kalshi World Cup markets, to evaluate a hedge: user holds 1,000 Belgium
champ YES @ 1.28c and is considering buying USA-advances (54c, q=0.53)
against it. The trade's edge hinges on `excess_absorption` (see
src/decompose.py docstring) and exit liquidity.

## State
- Full pipeline written and validated on synthetic data (demo/run_demo.py).
- NOT yet run on real data: series tickers in src/config.py are unverified
  guesses, and KNOCKOUT_MATCHES is empty. First tasks in Claude Code:
  1. `python -m src.discover --find-series "world cup"` and fix config.
  2. `--draft-matches`, fill bracket info (next_opponent_teams).
  3. `python -m src.pull_data`, then run notebooks/analysis.ipynb.
- Candlestick endpoint shape in kalshi_client.py is from memory — verify
  against https://trading-api.readme.io/reference on first 404/KeyError.

## Key structural insight (don't "fix" this as a bug)
Winner's consistency-implied gain p_w(1/q − 1) routinely EXCEEDS the
loser's released mass when a bigger team knocks out a longshot; conservation
is restored by future opponents LOSING probability (their path hardened).
So winner_share > 1 and negative next_opponent_share are expected, not
errors. The stacked-bar version of the plot was replaced with grouped bars
for exactly this reason.

## Estimator gotchas
- Small loser_pre → noisy shares. Prefer VWAP over several candles; weight
  aggregates by released mass.
- Normalize snapshots (done inside decompose) — raw books carry ~5-10% vig.
- User's Kalshi fee model: ~0.07*p*(1-p) per contract, taker.

## User context
Georgia Tech ISyE, quant-focused; runs a Kalshi market-making bot (has
authenticated API access if order-book depth data is needed). Comfortable
with pandas/prob theory; prefers being shown the math over hand-waving.

## Simulator (`simulator/`) — bracket repricing engine, validation status

Answers "if fixture X reaches state S, how should every remaining team's
championship probability move" via a calibrated bracket DP
(`simulator/bracket.py`) + a measured absorption adjustment
(`simulator/engine.py`, params in `simulator/ea_params.json`, refit via
`python -m simulator.fit_ea`). Wired to live Kalshi data
(`simulator/live_inputs.py`) against the confirmed real 2026 bracket
(`simulator/bracket_2026.py`). Streamlit app at `simulator/app.py`
(`streamlit run simulator/app.py`), read-only, public endpoints only.

**Current best estimate**: `ea_underdog=1.018`, `ea_favorite=0.989` — i.e.
essentially **no real excess absorption** once measured cleanly. An earlier
pass had `ea_underdog=1.183` from a same-day snapshot-window bug (a
match's post-snapshot could silently include a *different* match's result
that settled inside the window — see `RUN_NOTES.md`'s Task 1 entry); most
of the apparent "winners get over-rewarded" effect was that artifact, not a
real market inefficiency.

**Validated**: `simulator/backtest_report_v2.md` — real 16-team bracket
(not a toy), 6 settled Round-of-16 matches (2026-07-04 onward, where the
true remaining bracket is exactly reconstructable). Winner-role MAE 0.012,
predicted/actual ratio mostly 1-4x. next_opponent sign agreement 67% (not
much better than a coin flip — don't trust this signal match-by-match),
field sign agreement 83%.

**Not yet validated / caveats**:
- ea is fit **in-sample** on the same matches used to validate it — no
  held-out test exists yet. Re-run both `fit_ea` and the backtest as new
  knockouts settle.
- In-play (score/minute) repricing magnitudes are untested — the backtest
  only covers settled outcomes, not partial in-play states.
- An earlier backtest (`simulator/backtest_report.md`, v1) used a 4-node
  toy bracket that inflated predicted magnitudes 3-10x; superseded by v2,
  kept for the methodology comparison.

## Absorption basket (`src/absorption_basket.py`) — replication test, result: negative

Tested whether an optimized BASKET of surviving teams (not just the match
winner) better replicates where a loser's released mass goes, and whether
any such rule generalizes out-of-sample (leave-one-match-out CV across all
22 clean knockouts, both single-snapshot and VWAP3 estimators). Full
writeup: `absorption_basket_report.md`.

**Finding: no.** A learned rule (winner_share/next_opponent_share/
field_share regressed on q_winner alone, 1 feature) is consistently
*worse* than the naive "100% to the winner" baseline out-of-sample —
2x+ higher mean squared error on the full n=22 sample, and no win-rate
comparison reaches significance (best p=0.125, n=7). This is the same
overfitting-on-small-n failure mode to watch for anywhere else in this
project that fits parameters from ≤22 matches. **Tradability check
(realized, post-fee, LOO-predicted): net negative for every rule in the
higher-confidence (`|R|≥0.005`) subsample** — consistent with `ea ≈ 1.0`:
if winners already absorb their coherent share and nothing more, there's no
structure left for a basket to profitably capture. Retire this angle too,
not just the single-hedge one.

## Absorption by tier (`src/absorption_by_tier.py`) — does it depend on who's eliminated?

Follow-up to the basket test: does averaging across all 22 matches hide a
pattern specific to eliminating a genuine contender (rare, large released
mass) vs. a longshot (frequent, negligible mass)? Full writeup:
`absorption_by_tier_report.md`.

**Tier split is data-driven, not the brief's guessed 0.03**: the largest gap
in sorted `loser_pre` is a 3.8x jump at ≈0.018, giving **6 contender
eliminations** (Brazil, Netherlands, Portugal, Mexico, **USA**, Germany —
USA clears the same bar as the other five even though the brief's example
list only named five) vs. 16 longshot eliminations.

**Finding 1 (the reliable one): contender eliminations do NOT show worse
coherence than longshots — if anything the opposite.** Mean `|ea−1|` is
0.28 (contender) vs. 0.56 (longshot) single-snapshot, 0.31 vs. 0.47 VWAP3.
The pooled `ea≈1.0` result isn't masking a hidden mispricing concentrated in
rare high-stakes eliminations. (Raw `winner_share`/`next_opponent_share`/
`field_share` are NOT reliable for this comparison — they blow up into the
hundreds for tiny-`released` longshot matches, same instability
`METRICS_REFERENCE.md` §2.1 already flags; `excess_absorption` is
structurally more robust and is what this conclusion rests on.)

**Finding 2 (hypothesis-generating only, n=6): within contender matches,
a field team's own pre-match price correlates positively with its
absorption in 5 of 6 matches** (r=0.41 to 0.90; one match, Germany, shows
no relationship at all). Suggestive of "stronger teams absorb
disproportionately," but not adjusted for the plausible mechanical
confound that bigger teams move more in absolute probability terms
regardless of any special effect — distinguishing the two needs the
bracket DP's own coherent prediction as a baseline (not done) and roughly
15-20 more contender-elimination matches. Do not treat as confirmed; do not
build a trading signal on it.
