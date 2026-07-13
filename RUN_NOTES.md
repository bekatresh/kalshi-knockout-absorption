# Run notes — 2026-07-06 real-data pipeline execution

## Final tickers used

| Config var | Guessed (before) | Verified (now) |
|---|---|---|
| `CHAMPION_SERIES` | `KXWCUP` | `KXMENWORLDCUP` |
| `MATCH_SERIES` | `KXWCUPGAME` | `KXWCADVANCE` |

Found via `python -m src.discover --find-series "world cup"`. Both guesses were
wrong; neither ticker exists on Kalshi.

**Team-code mismatch (important):** the two series use *different*
country-code conventions for the same team — e.g. champ market suffix `US`/
`BE`/`FR`/`GB` vs match market suffix `USA`/`BEL`/`FRA`/`ENG`. Confirmed by
joining on team name (`python -m src.discover --crosswalk`). This is now
`TEAM_CODE_MAP` in `src/config.py` (32 entries); `pull_data.py` translates
`KNOCKOUT_MATCHES` winner/loser/next_opponent codes through it before joining
against championship-market snapshots. Without this translation the join
would silently produce wrong (or crash on missing-key) results — decompose.py
indexes by team code directly.

## API/endpoint fixes made

1. **Price fields are now all `<field>_dollars` string values** (e.g.
   `"0.0140"`), not the cents-integer convention (`yes_bid`, `last_price`)
   the original code assumed. This doesn't 404 — it silently returns `None`.
   Added a `dollars()` helper in `kalshi_client.py`, used everywhere a price
   is read (discover.py, pull_data.py, live pulls).
2. **`candle_price()` must prefer trade/mark price (`price.close_dollars`)
   over bid/ask mid — not the reverse.** Once a market goes quiet (thin
   trading, or right after settlement), the book snaps to Kalshi's
   no-liquidity default (`yes_bid=$0`, `yes_ask=$1`), and mid-of-bid-ask
   reads that as a fake **$0.50**. Confirmed on
   `KXMENWORLDCUP-26-RSA`'s settlement candle: `price.close=$0.001` (correct,
   South Africa is eliminated) vs bid/ask mid=`$0.50` (artifact). This was
   corrupting the raw vig sum badly (some match snapshots summed to 4.5+
   instead of the expected ~1.0–1.15).
3. **Zero-volume candles also carry a stale/synthetic price** even in the
   `price.close` field — confirmed on `KXMENWORLDCUP-26-UZB` (long
   eliminated): its only candle in the post-elimination window has
   `volume_fp=0` and `price.close=$0.50`. Now filtered out entirely
   (`candles_to_df` drops `volume == 0` rows).
4. **A just-eliminated team's champ market goes fully illiquid almost
   immediately** — no candle with real volume survives anywhere in the
   12h post-settlement window (confirmed on Ivory Coast after
   `KXWCADVANCE-26JUN30CIVNOR`). Rather than drop these rows (which either
   silently excludes the match's own loser from `field_share`, or crashes
   `decompose_match` with a `KeyError` when the loser is dropped entirely),
   `pull_data.py` now imputes `post = 0.0` for any team whose champion
   market is `status=finalized, result=no` — which is definitionally
   correct, not a guess.
5. Kalshi doesn't expose actual match **kickoff time** anywhere in the
   market/event schema (`occurrence_datetime` turned out to be an
   expiration-related field, not kickoff — it's *after* `settlement_ts` in
   the one case checked). `settlement_ts` is real and precise, so
   `kickoff_iso` is approximated as `settlement_ts − 2.5h`. This is within
   `PRE_WINDOW_S`'s 6h margin so it shouldn't bias the pre-snapshot, but
   don't trust it for anything needing the real kickoff.
6. Hit **429 rate limits** hammering `/markets` per-event during
   `draft_matches`; added exponential backoff to `KalshiPublic._get`.
7. Python 3.9's `datetime.fromisoformat` chokes on the `Z` suffix and on
   non-3/6-digit fractional seconds Kalshi sometimes returns — handled in
   both `discover.py` and `pull_data.py`.

## Matches excluded, and why

- **Group-stage eliminations**: no `KXWCADVANCE` market exists for group
  stage (there's nothing to "advance" past), and a group-stage loss doesn't
  zero a team's championship probability the way a knockout elimination
  does — the decomposition doesn't apply. `KNOCKOUT_MATCHES` only contains
  Round-of-32-onward matches (21 of them).
- **KXWCADVANCE-26JUL06USABEL (USA vs Belgium)**: not yet settled as of this
  run (kickoff tonight, ~2026-07-06 20:00 ET). This is the live trade
  decision, not backtest data — excluded from `KNOCKOUT_MATCHES` by
  construction (draft_matches only emits settled matches).
- **Spain's next match**: doesn't exist yet. Checked directly — only two
  `KXWCADVANCE` events mention Spain (`ESPAUT`, `PORESP`), both already
  settled. The QF/SF bracket slot for Spain's next opponent isn't fixed yet
  (their opponent's own match hasn't happened), so there's nothing to pull.

## Data-quality flags

- **Tiny `loser_pre` → very noisy per-match shares**, worse in the real data
  than the synthetic demo warned. Several matches have `loser_pre` of
  0.001–0.01 (heavy favorites knocking out heavy underdogs), producing
  `winner_share`/`excess_absorption` values in the hundreds with flipped
  signs when `released` rounds through ~0 (e.g. `KXWCADVANCE-26JUL01USABIH`:
  `released=-0.000`, `winner_share=-22.35`). **Don't read the unweighted
  mean or individual noisy rows as conclusions** — `decomposition_results.csv`
  keeps them for transparency, but the mass-weighted summary (weight =
  `released`) is the number to trust, per the project's own estimator
  caveats.
- The earliest match (`KXWCADVANCE-26JUN28RSACAN`) sits at the edge of the
  candle-fetch window; needed an extra 6h fetch-only buffer (not part of the
  actual pre/post snapshot logic) to avoid an all-NaN pre-snapshot that would
  have crashed the decomposition (`pre[loser]` KeyError once every team's row
  gets dropped by `dropna`).
- Raw vig sums are clean across all 22 matches now: pre ∈ [1.05, 1.11], post
  ∈ [1.00, 1.10] — within the expected 1.02–1.15 range.

## Headline numbers (see `decomposition_results.csv` / `_vwap3.csv`)

| Estimator | median excess_absorption | mass-weighted mean |
|---|---|---|
| Single pre/post snapshot | 0.943 | 1.134 |
| VWAP of 3 candles | 1.198 | 1.183 |

(Updated after USA-Belgium settled tonight, becoming observation #22 --
Belgium won as the underdog, q≈0.42-0.47 pre-match.)

**This is the main surprise**: the single-snapshot and VWAP3 estimators
disagree materially on the median (0.94 vs 1.20), though the mass-weighted
means are closer (1.13 vs 1.18) and both sit near 1 — consistent with the
project's prior that winners get roughly their consistency-implied share,
plus or minus real noise. Underdog-won matches (n=5) show *higher* median
excess_absorption (1.18) than favorite-won matches (n=17, median 0.81), but
n=5 is too small to lean on.

**Hedge P&L sensitivity** (1000 BEL champ YES @ 1.28c, BEL last 1.4c,
USA-advances 54c, q(USA)=0.53):

- At the baseline-median `ea=0.943`: **0/25 hedge sizes tested have
  worst_case > 0** — the naive hedge doesn't work under this estimate.
- At `ea=1.198` (VWAP3 median) or `ea=1.134` (mass-weighted): a narrow
  window opens around `n_hedge≈40`, worst_case barely positive
  (+$0.59 and −$1.31 respectively — i.e. still marginal).
- Note: this hedge is now moot — Belgium beat the USA tonight, so the
  USA-advances contract has settled to $0 and the hedge leg no longer
  exists. Belgium now faces Spain in the QF (KXWCADVANCE-26JUL10ESPBEL).
- **Bottom line: this hedge's viability is knife-edge and estimator-dependent
  at these prices/sizes.** It is not robustly profitable across the
  methodology choices tested here.

## Live snapshot (2026-07-06 ~23:29 UTC, `data/processed/live_prices.csv`)

| Market | yes_bid | yes_ask | last |
|---|---|---|---|
| USA-advances | 0.53 | 0.54 | 0.54 |
| Belgium-advances | 0.46 | 0.47 | 0.47 |
| USA champion | 0.033 | 0.034 | 0.034 |
| Belgium champion | 0.013 | 0.014 | 0.013 |
| Spain champion | 0.181 | 0.182 | 0.182 |

BEL championship order-book depth pulled authenticated (read-only, no orders
placed) into `data/processed/live_orderbook_bel.csv`: 13 YES levels down to
$0.001, 100 NO levels up to $0.999 — there is real resting depth on both
sides, not just top-of-book.

## What's in the bundle

```
data/processed/snapshots.csv               pre/post per (match, team), both single-snapshot and vwap3 columns
data/processed/matches.csv                 match metadata, both winner_pre_match_prob variants
data/processed/decomposition_results.csv   single-snapshot decomposition, all 21 matches
data/processed/decomposition_results_vwap3.csv   VWAP3 variant
data/processed/live_prices.csv             live snapshot, 2026-07-06 ~23:29 UTC
data/processed/live_orderbook_bel.csv      authenticated BEL champ order book depth
results/absorption_decomposition.png
results/hedge_frontier.png                 plotted at the mass-weighted excess_absorption estimate
RUN_NOTES.md                               this file
```

Raw per-team candle CSVs (`data/raw/candles_*.csv`, 48 files) were left out
of the bundle — regeneratable via `python -m src.pull_data` and not needed to
re-run the decomposition from the processed CSVs.

## Update 2026-07-06 (later): Task 1 — same-day window contamination fix

**Bug found in review**: `src/pull_data.py` took each match's "pre" snapshot
at a fixed `kickoff − 6h` and "post" at `settlement` with no upper bound.
When a *different* match settled inside that span, the team's price change
across it silently mixed both events. Concretely, `KXWCADVANCE-26JUL06USABEL`
(Belgium beat the USA): Spain is Belgium's next opponent, and
`KXWCADVANCE-26JUL06PORESP` (Spain beat Portugal) settled at 21:05:46, which
falls *inside* USABEL's naive pre-window (kickoff 23:31:52 − 6h = 17:31:52,
so the window was 17:31:52→23:31:52, and 21:05:46 sits right in the middle).
Spain's "post" snapshot for the USABEL row was taken *after* Spain had
already beaten Portugal, but its "pre" snapshot was taken *before* — so the
whole ESP-beats-POR jump got misattributed to "next-opponent reaction to
Belgium's win."

**Fix** (`src/pull_data.py`, `clipped_window()`): for every match, clip
against every *other* match's settlement time using all 22 `KNOCKOUT_MATCHES`
as boundaries:
- `pre_ts  = max(kickoff − PRE_WINDOW_S, latest earlier settlement + 30min)`
- `post_upper = min(settlement + POST_WINDOW_S, next settlement − 30min)`,
  and the post-snapshot search is now capped at `post_upper` (previously
  unbounded above — it just took the first available candle after
  settlement, however far that ended up being).

If clipping leaves no candle for a team, `snapshots.csv` gets
`pre_missing_clipped` / `post_missing_clipped` = `True` for that row instead
of silently falling back to the wide (contamination-prone) window. None of
the flagged rows this run are winner/loser/next-opponent — all in the
"field" bucket, harmless (decompose.py already drops them via `dropna`).

**Scope**: 21 of 22 matches needed clipping (median clip ~4-5h off either
side) — this tournament's knockout matches happen close enough together
that the naive 6h/12h windows almost always overlapped a neighbor. One
match, `KXWCADVANCE-26JUL03COLGHA`, has an invalid clipped pre-window
(`pre_ts >= kickoff`): `KXWCADVANCE-26JUL03ARGCPV` settled only ~22 minutes
before COLGHA's (approximated) kickoff. Flagged in
`data/processed/window_clip_report.csv`, not silently patched — a real
consequence of the earlier caveat that `kickoff_iso` is itself approximated
as `settlement − 2.5h`, not the true kickoff time.

**Before/after** (`simulator/fit_ea.py` output, `data/processed/decomposition_results.csv`):

| | before (contaminated) | after (clipped) |
|---|---|---|
| `ea_underdog` | 1.183 | **1.018** |
| `ea_favorite` | 1.011 | 0.989 |
| `next_opp_share_underdog` | 0.61 | **0.226** |
| n_underdog / n_favorite | 5 / 3 | 5 / 2 |
| baseline median excess_absorption | 0.943 | 0.789 |
| baseline mass-weighted mean excess_absorption | 1.134 | 0.996 |

`next_opp_share_underdog` dropped from 0.61 to 0.226, as expected once the
contamination is removed — most of what looked like "next opponent
absorbing a meaningful share of the released mass when an underdog wins"
was actually unrelated same-day results bleeding into the window.
`ea_underdog` correspondingly collapsed from 1.183 toward ~1.0 (essentially
no excess absorption once measured cleanly), and the mass-weighted mean
excess_absorption across all matches moved from moderately >1 (1.134) to
almost exactly 1.0 (0.996) — i.e. **the aggregate evidence for "winners get
over-rewarded relative to consistency" was substantially a measurement
artifact**, not a real market inefficiency. This is a materially different
conclusion from the first pass and should be treated as the current best
estimate.

`results_bundle.zip` was rebuilt from the corrected
`decomposition_results.csv` / `_vwap3.csv` / `snapshots.csv` / `matches.csv`;
`simulator/ea_params.json` was refit and is the value `simulator.engine`
now loads.
