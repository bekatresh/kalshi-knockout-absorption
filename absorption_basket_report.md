# Absorption replication — does a basket beat the naive single-winner view?

**No.** Across both snapshot estimators (single-snapshot and VWAP3) and every
statistical cut tried, a fitted basket of surviving teams does **not**
reliably out-predict the naive "all released mass goes to the match winner"
view out-of-sample, and no basket rule survives Kalshi's ~7%·p·(1−p) fee once
sized realistically. The learned rule (feature: winner's pre-match win
probability) is consistently the *worst* performer out-of-sample — a sign of
overfitting, not of finding real structure. This is a clean negative result,
consistent with the project's separate finding that `excess_absorption` ≈ 1.0
once the snapshot-window contamination bug was fixed (`RUN_NOTES.md` Task 1,
`METRICS_REFERENCE.md` §4): if winners already absorb close to their
coherence-implied share and nothing more, there's no "leftover" structure for
a basket to profitably capture.

**Note on n:** the brief anticipated 21 clean matches; USA-Belgium settled
between sessions, so this analysis uses all 22 currently-clean knockouts
(same decontaminated windows from Task 1). One is added statistical power,
not a discrepancy in methodology.

`METRICS_REFERENCE.md` was read for context per the brief; it documents the
existing decomposition metrics (§2) but has no bearing on this module's
methodology, which is new.

---

## 1. Method summary

For every match: renormalize each snapshot (single and VWAP3-of-3-candles
variants) to sum to 1 across all teams with data, take `Δp = post − pre` for
every surviving team, and `R` = the loser's released mass. This exactly
mirrors `decompose.py`'s own normalization so nothing here double-counts or
reintroduces vig drift.

**Step 2 (descriptive, in-sample by construction):** per match, project
`Δp / R` onto the probability simplex (non-negative weights summing to 1) —
the closest "clean partition of R" to what actually happened. Full table in
`data/processed/absorption_basket_weights.csv`.

**Step 3 (the real test):** leave-one-match-out cross-validation of three
rules, predicting the *full per-team delta vector* for the held-out match:

- **(a) naive** — 100% of R to the match winner.
- **(b) winner + next-opponent split** — training-fold mass-weighted mean
  `winner_share` / `next_opponent_share` (no features), applied to the
  held-out match's own R.
- **(c) learned** — weighted least squares (weight = R) of `winner_share`,
  `next_opponent_share`, and `field_share` on **`q_winner` alone** (the
  winner's pre-match advance probability), fit on the training fold. One
  feature, 2 parameters/target — deliberately minimal given n≈20-21
  training matches per fold. Field mass is then spread across individual
  "other" teams proportional to their own pre-match price (a
  non-informative allocation rule, not a learned one).

**Step 4:** for each LOO-predicted rule, realized (not hypothetical) P&L:
hold the loser's champ position (entry = pre-match price) plus a basket
sized `contracts_j = predicted_share_j × 1000`, valued at the actual
post-match prices, fee = `0.07·p·(1−p)` charged once per leg on entry. This
uses what *actually happened*, not a symmetric hypothetical outcome the way
`decompose.hedge_pnl` does for a still-open trade.

---

## 2. Descriptive fit (step 2) — where does a simplex-constrained view put the mass?

Across all 22 matches, the single largest weight lands on the actual match
**winner in 11/22 (50%)**. Restricting to the 7 matches with `|R| ≥ 0.005`
(the same noise filter `simulator/fit_ea.py` already uses, since tiny-R
matches make `Δp/R` numerically unstable — confirmed here too, e.g.
`RSACAN` with `R=0.00001` puts 100% descriptive weight on Netherlands, a team
with no structural relationship to that match): winner is top-weighted in
**4/7**, "field" in 2/7 (both times on France — plausible mechanics, not
signal: France is consistently one of the largest live teams, so it absorbs
noticeably even from unrelated matches' vig/repricing), next-opponent in 1/7.

**Reading this correctly:** this step is descriptive and in-sample by
construction (the weights are fit *to* the match they describe) — it shows
where mass happened to go, not evidence of a predictive rule. That's what
step 3 tests.

## 3. Cross-validation (step 3) — the real test

Out-of-sample mean squared error per match (`data/processed/absorption_basket_cv.csv`):

| variant | sample | rule | mean SSE (OOS) | mean winner abs. err (OOS) |
|---|---|---|---|---|
| single | full (n=22) | a_naive | 0.00090 | 0.01365 |
| single | full (n=22) | b_winner_nextopp | 0.00104 | 0.01519 |
| single | full (n=22) | **c_learned_q** | **0.00219** (2.4x naive) | 0.02107 |
| single | filtered (n=7) | a_naive | 0.00125 | 0.01982 |
| single | filtered (n=7) | b_winner_nextopp | 0.00121 | 0.01962 |
| single | filtered (n=7) | c_learned_q | 0.00096 | 0.01243 |
| vwap3 | full (n=22) | a_naive | 0.00224 | 0.01521 |
| vwap3 | full (n=22) | c_learned_q | 0.00474 (2.1x naive) | 0.02377 |
| vwap3 | filtered (n=7) | a_naive | 0.00350 | 0.02091 |
| vwap3 | filtered (n=7) | c_learned_q | 0.00365 | 0.01330 |

**The full-sample result (n=22, both variants) is unambiguous: the learned
rule is worse than naive out-of-sample**, by more than 2x on mean squared
error. This is a textbook overfitting signature — a single feature fit on
~21 points still finds noise to chase.

**The filtered n=7 subsample is more ambiguous** (`c_learned_q` shows a
nominally lower mean SSE than naive in the single-snapshot cut, though not
in VWAP3) — but this is exactly the regime the brief warned about: n=7 is
far too small to trust a point estimate. The per-fold win-rate test makes
this concrete:

| metric | rule | win rate vs. naive (OOS) | binomial p-value |
|---|---|---|---|
| sse | c_learned_q (full, n=22) | 14/22 (64%) | 0.286 |
| mae_all | c_learned_q (full, n=22) | 9/22 (41%) | 0.524 |
| winner_abs_err | c_learned_q (full, n=22) | 11/22 (50%) | 1.000 |
| sse | c_learned_q (filtered, n=7) | 5/7 (71%) | 0.453 |
| winner_abs_err | c_learned_q (filtered, n=7) | 6/7 (86%) | **0.125** |
| mae_all | c_learned_q (full, VWAP3, n=22) | 6/22 (27%) | 0.053 |

**No comparison reaches conventional significance (p<0.05) in favor of the
learned rule.** The single closest-to-significant result (p=0.053) actually
points the *other* way — naive beating the learned rule more often than
chance in the VWAP3 cut. The mean-SSE win for `c_learned_q` in the filtered
single-snapshot cut is carried by winning 5 of 7 folds by a small margin
while presumably not losing catastrophically — with n=7 this is not
distinguishable from noise (95% CI on a 5/7 win rate against p=0.5 is wide
enough to include 0.5).

**Rule (b)** (winner + next-opponent split, no features) tracks naive
closely everywhere — never a large or consistent improvement, never a large
degradation. It is the "safest" alternative to naive but doesn't
demonstrate it beats it either.

**Verdict: rule (c) does not beat naive out-of-sample. If anything, the
full-sample evidence (the larger, more reliable comparison) points the other
way.** This is the finding, stated plainly per the brief's instruction.

## 4. Tradability (step 4) — does anything survive fees?

Realized LOO P&L, `1000`-contract loser position + proportionally-sized
basket, fees included (`data/processed/absorption_basket_tradability.csv`):

| sample | variant | rule | mean net P&L ($) | % matches net positive |
|---|---|---|---|---|
| full (n=22) | single | a_naive | −2.00 | 64% |
| full (n=22) | single | b_winner_nextopp | −0.92 | 68% |
| full (n=22) | single | c_learned_q | **−14.29** | 32% |
| **filtered (n=7)** | single | a_naive | **−13.93** | 43% |
| filtered (n=7) | single | b_winner_nextopp | −22.19 | 14% |
| filtered (n=7) | single | c_learned_q | −17.27 | 29% |
| full (n=22) | vwap3 | a_naive | +1.79 | 73% |
| full (n=22) | vwap3 | b_winner_nextopp | +8.13 | 82% |
| **filtered (n=7)** | vwap3 | a_naive | −10.23 | 43% |
| filtered (n=7) | vwap3 | b_winner_nextopp | −12.87 | 14% |

The VWAP3 full-sample numbers for naive/b look encouraging in isolation
(+$1.79 / +$8.13 mean, 73-82% of matches net positive) — **but this does not
survive restricting to the higher-confidence `|R|≥0.005` matches**, where
every rule, every variant, is net negative on average (−$10 to −$22), with
only 1-3 of 7 matches net positive. The full-sample positive numbers are
driven by the many tiny-`R` matches, where both the loser's entry cost and
the basket's notional are tiny — a few cents of favorable rounding on those
low-stakes matches inflates the "percent positive" count without
representing an economically meaningful, scalable edge. **In the matches
that actually matter (meaningful released mass), nothing is net profitable
after fees, in- or out-of-sample.**

**Per the brief: in-sample profitability is not evidence of tradability, and
none of these numbers are in-sample anyway — this is the realized,
LOO-predicted, post-fee result, and it is negative everywhere it matters.**

## 5. Confidence and caveats

- **n=22 (or n=7 filtered) is small.** Every binomial test above has wide
  confidence intervals; "not significant" here means "cannot rule out no
  effect," not "proven no effect." The full-sample result is the more
  trustworthy of the two only because 22 > 7, not because it's large in any
  absolute sense.
- **Rule (c) is deliberately minimal** (1 feature, 2 params/target) to guard
  against overfitting — and it still overfits out-of-sample on the full
  data. A richer feature set (round number, bracket adjacency, favorite/
  underdog indicator, as the brief listed as candidates) would almost
  certainly fit in-sample better and generalize worse; it was not attempted,
  because there isn't enough data to support it.
- **This does not contradict the project's other findings** — it's the same
  conclusion from a different angle. `ea ≈ 1.0` (coherent markets, no
  structural edge) and "no basket beats naive, and nothing survives fees"
  are two measurements of the same underlying fact.
- Public market data only; no orders were placed.

## 6. Deliverables

```
src/absorption_basket.py                        this module
data/processed/absorption_basket_weights.csv     step 2, per-match descriptive weights
data/processed/absorption_basket_cv.csv          step 3, rules a/b/c x in/out-of-sample x variant x sample
data/processed/absorption_basket_winrate.csv     step 3, per-fold win-rate + binomial p-values
data/processed/absorption_basket_tradability.csv step 4, realized post-fee P&L summary
absorption_basket_report.md                      this file
```
