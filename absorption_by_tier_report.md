# Does absorption structure differ by the eliminated team's strength tier?

**Yes, visibly, on the metric that's actually reliable at small n — but the
pattern is the opposite of "contender eliminations are harder to price."**
`excess_absorption` (ea) is *more* tightly clustered near 1.0 for the 6
contender eliminations (mean |ea−1| = 0.28, single-snapshot; 0.31, VWAP3)
than for the 16 longshot eliminations (mean |ea−1| = 0.56 / 0.47) — coherence
holds at least as well, if not better, for the rare high-stakes events as for
the frequent low-stakes ones. **Separately, and more speculatively:** within
the 6 contender matches, a field team's own pre-match price correlates
positively with how much of the released mass it absorbs in 5 of 6 matches
(r = 0.41 to 0.90) — consistent with "stronger surviving teams absorb more
of the field's share" — but this is 6 data points, isn't adjusted for a
plausible mechanical confound (below), and should be read as a hypothesis to
collect more data for, not a finding. **No trading claim is made anywhere in
this report.**

Per the brief: `CLAUDE.md` and `METRICS_REFERENCE.md` §2 were read first;
all definitions below match `decompose.py` and §2 exactly. This module
(`src/absorption_by_tier.py`) is new and separate from
`src/absorption_basket.py` (the pooled basket-replication test, which found
no generalizable rule *on average* — this analysis is the conditional
follow-up the brief asked for, checking whether that average hid a
tier-dependent effect).

---

## 1. Tier assignment (data-driven, not hardcoded)

The brief suggested "roughly 4-5 contender eliminations... a natural break
around 0.03." The actual natural break in the data (largest multiplicative
gap between consecutive sorted `loser_pre` values) sits at **`loser_pre` ≈
0.018**, between Germany's 0.0350 and Bosnia's 0.0093 — a **3.8x gap**, by
far the largest in the sequence (every other consecutive gap is <2x). This
threshold is identical in both the single-snapshot and VWAP3 decompositions
(0.0180 vs 0.0173), so it isn't an artifact of the estimator.

This puts **6 matches in the "contender" tier, not 4-5**: the brief's named
five (Germany, Netherlands, Mexico, Brazil, Portugal) *plus* **USA**
(`loser_pre` = 0.0368, actually higher than Germany's 0.0350) — USA-Belgium
clears the same data-driven bar the other five do. The remaining 16 matches
are "longshot" (`loser_pre` ≤ 0.0093, more than an order of magnitude
smaller).

| tier | n | loser_pre range |
|---|---|---|
| contender | 6 | 0.0350 – 0.0652 |
| longshot | 16 | 0.0009 – 0.0093 |

Full per-match tier assignment: `data/processed/absorption_by_tier_matches_{single,vwap3}.csv`.

## 2. Absorption structure across tiers (steps 2a/2b)

**Full per-match values, both tiers, single-snapshot estimator** (sorted by
`loser_pre` descending — the brief asked these be listed individually, not
just summarized):

| match | loser | tier | loser_pre | released | winner_share | next_opp_share | field_share | ea |
|---|---|---|---|---|---|---|---|---|
| BRANOR | Brazil | contender | 0.0652 | 0.0643 | 0.626 | 0.264 | 0.110 | 1.322 |
| NEDMAR | Netherlands | contender | 0.0553 | 0.0544 | 0.444 | 0.001 | 0.555 | 1.377 |
| PORESP | Portugal | contender | 0.0518 | 0.0508 | 1.216 | 0.052 | −0.268 | 1.019 |
| MEXENG | Mexico | contender | 0.0500 | 0.0490 | 1.223 | −0.039 | −0.184 | 0.773 |
| USABEL | USA | contender | 0.0368 | 0.0358 | 0.352 | 0.267 | 0.380 | 0.759 |
| GERPAR | Germany | contender | 0.0350 | 0.0341 | 0.081 | 0.848 | 0.072 | 0.499 |
| *(16 longshot matches, `released` < 0.008 — see CSV; raw shares for these are individually unstable, see §2.3)* |

**2.1 — `excess_absorption` (the reliable metric; see §2.3 for why the
others aren't as trustworthy here):** contender values are
`{1.32, 1.38, 1.02, 0.77, 0.76, 0.50}` — mean 0.96, median 0.90, spanning
roughly 0.5–1.4. Longshot values span far wider, −1.31 to 2.15 (mean 0.68,
median 0.79). **The contender tier is not obviously worse-behaved — visually
and by mean-absolute-deviation-from-1 it's tighter.** See
`results/shares_vs_loser_pre.png` (bottom-right panel, not axis-clipped).

**2.2 — `next_opponent_share`:** contenders cluster tightly near 0
(`{0.264, 0.001, 0.052, −0.039, 0.267, 0.848}` — one outlier, Germany, where
next-opponent France absorbed a large share; the other five are all under
0.27). This is visibly tighter than the spread among longshot matches
(range −2.4 to +1.8 among the ones large enough to plot). Whether that's a
real tier effect or just fewer observations is not something 6 vs 16 points
can settle.

**2.3 — an important asymmetry the plots make obvious:** `winner_share`,
`next_opponent_share`, and `field_share` are *shares* (divided by `released`),
and for the 16 longshot matches, `released` is frequently under 0.001 —
dividing by a near-zero denominator inflates these ratios into the hundreds
(e.g. `ENGCOD` has `winner_share = 532`; this is not a data error, it's the
same instability `METRICS_REFERENCE.md` §2.1 already documents and the
project already filters out of headline conclusions). Practically, this
means the *raw share* comparison across tiers is dominated by noise for the
longshot side, while `excess_absorption` is structurally more robust (both
its numerator and denominator inflate together at small `released`, so the
ratio stays bounded — visible directly in the plot: only the `ea` panel
isn't heavily axis-clipped). **Read the shares-vs-`loser_pre` scatter's
top-left/top-right/bottom-left panels as "contenders vs. the least-extreme
longshots only"** — most longshot points are off-axis by construction, noted
in each panel's title.

## 3. Do strong surviving teams absorb the field's share disproportionately? (step 3)

Within each of the 6 contender-elimination matches, correlated each *field*
team's (i.e. not winner, not loser, not next-opponent) pre-match price
against its own `Δp`:

| match | loser (eliminated) | pearson r | field_share_total |
|---|---|---|---|
| USABEL | USA | **0.90** | 0.380 |
| NEDMAR | Netherlands | **0.79** | 0.555 |
| PORESP | Portugal | 0.61 | −0.268 |
| MEXENG | Mexico | 0.60 | −0.184 |
| BRANOR | Brazil | 0.41 | 0.110 |
| GERPAR | Germany | −0.07 | 0.072 |

**5 of 6 matches show a positive correlation, 3 of them fairly strong
(0.60–0.90).** Taken at face value this supports "stronger teams absorb more
of the field's flow." See `results/field_price_correlation.png` for the
scatter behind each number.

**The necessary caveat:** a positive price-vs-absorption correlation is not
automatically evidence of an anomalous "smart flow to the strong" effect,
because it's partly what you'd expect *mechanically* even under pure
coherent repricing — a team already priced at 25c has more room to move in
absolute probability terms than a team priced at 0.1c, for reasons that have
nothing to do with the specific match just resolving. Fully
price-proportional allocation (everyone's `Δp` exactly proportional to their
own prior price) would produce r ≈ 1.0 by construction; complete
independence from price would give r ≈ 0. The observed 0.4–0.9 sits between
those two anchors — genuinely more than "no relationship," but not so
extreme it's obviously beyond what scale alone would produce. **Distinguishing
"mechanically expected because bigger teams move more in absolute terms"
from "anomalously more than that" would require comparing against what
`simulator/bracket.py`'s coherent DP predicts for these same 6 matches — not
done here, flagged as the natural next step.**

**With n=6, and one of the six (Germany) showing no relationship at all,
this is a pattern worth collecting more data for, not a confirmed effect.**
See §5 for what "more data" means concretely.

## 4. Consistency check by tier (step 4)

| variant | tier | n | mean ea | median ea | mean \|ea−1\| | median \|ea−1\| |
|---|---|---|---|---|---|---|
| single | contender | 6 | 0.958 | 0.896 | 0.281 | 0.282 |
| single | longshot | 16 | 0.676 | 0.790 | 0.565 | 0.419 |
| vwap3 | contender | 6 | 1.033 | 1.140 | 0.311 | 0.260 |
| vwap3 | longshot | 16 | 0.945 | 0.881 | 0.467 | 0.313 |

**Answering the brief's specific question directly: no, contender
eliminations do not show larger or more systematic deviations from
coherence than longshot eliminations — if anything the opposite, in both
estimator variants.** There is no hidden residual mispricing concentrated in
the rare, high-stakes tier that the pooled n=22 average was masking. The
pooled `ea≈1.0` finding (`RUN_NOTES.md`, `METRICS_REFERENCE.md` §4) holds up
when you look at the tier where it would matter most if it didn't.

One genuine nuance: in the VWAP3 cut, contenders average `ea=1.033`
(slightly *above* coherent) while longshots average `ea=0.945` (slightly
*below*) — a small, tier-dependent directional split. With n=6 vs n=16 and
both means well within one standard deviation of 1.0, this is not a claim
of a real effect, just a description of what's in the current 22 matches.

## 5. What sample size would be needed to actually confirm any of this?

Two candidate patterns emerged: (a) contenders show tighter/no-worse
coherence than longshots, and (b) field absorption correlates with
surviving-team price within contender matches. Neither should be acted on
yet:

- **(a)** is based on 6 vs 16 points with overlapping distributions (visual
  inspection of the `ea` panel shows contender and longshot points
  interleaved, not cleanly separated) — a rough two-sample comparison at
  these sample sizes and this much within-group spread has essentially no
  power to detect anything short of a very large tier difference. Getting a
  reasonably powered read (able to detect a ~0.3 shift in mean `|ea−1|`
  with conventional power) would need on the order of **20-30 contender-tier
  matches** — i.e. roughly 4-5x the current count, meaning several more full
  tournaments' worth of knockout rounds at this contender-elimination rate
  (~6 per ~48-team, single-elimination bracket).
- **(b)** is 6 correlations, each itself computed over one match's ~33 field
  teams (not 33 independent draws — they all move in response to the same
  single event, so the effective sample size per match is closer to 1 than
  33). Treat the "5 of 6 positive" as **6 independent data points**, not 6×33.
  To distinguish a real "strong teams absorb disproportionately" effect from
  the mechanical price-scaling explanation in §3, you'd want at minimum
  **15-20 more contender-elimination matches** with the coherent-DP
  benchmark computed alongside each one, so the comparison is "observed r
  vs. DP-implied r" rather than "observed r vs. zero."

## 6. Deliverables

```
src/absorption_by_tier.py                                  this module
data/processed/absorption_by_tier_matches_{single,vwap3}.csv   per-match table with tier labels
data/processed/absorption_by_tier_summary_{single,vwap3}.csv   tier-level ea summary
data/processed/absorption_by_tier_field_correlation.csv     step 3, per-contender-match correlations
results/shares_vs_loser_pre.png                             step 2b scatter (see §2.3 for axis-clipping note)
results/field_price_correlation.png                        step 3 scatter, one panel per contender match
absorption_by_tier_report.md                                this file
```

Public market data only. No orders placed.
