## Kalshi World Cup — System & Metrics Reference

*Last updated after the v2 (decontaminated) run. This is the document to re-read whenever a metric on the app is confusing. It explains (1) what each piece computes, (2) exactly how every metric is derived, and (3) what you should and shouldn't conclude from it.*

---

### 0. The one-paragraph summary

You built a pipeline that measures where an eliminated team's championship probability goes, and a simulator that predicts how championship prices should move when a match resolves. The original hypothesis — that the team who wins **over-absorbs**, creating a hedge edge — **did not survive clean measurement**. After fixing a window-contamination bug, the excess-absorption signal collapsed to ~1.0 (no edge). The honest current conclusion: **at these prices the cross-market hedge is a coin flip minus fees; the markets are, to measurement precision, internally consistent.** The tooling is validated and reusable; the specific trade is not live.

---

### 1. The two markets everything is built on

Every metric derives from two Kalshi market families:

- **Championship market** (`KXMENWORLDCUP`): one YES/NO contract per team, "does this team win the World Cup?" Price in cents ≈ implied probability. This is the thing whose *movements* we study.
- **Advance market** (`KXWCADVANCE`): per knockout fixture, "does team X advance?" Price ≈ implied probability that X wins the tie. We call this **q** — the pre-match win probability of a given side.

A key relationship ties them together. For a team, coherence requires:

> P(win cup) = P(advance this round) × P(win cup | advanced)

So a team's championship price should equal its advance probability times its conditional-championship value. When a match resolves, the loser's championship price goes to ~0 and that released probability must reappear somewhere. **Where it reappears is the entire subject of this project.**

---

### 2. The metrics, one by one

#### 2.1 `released` (released mass)
The loser's championship probability just before the match, in normalized units. This is the size of the pie being redistributed. **Why it matters:** it's the denominator for most shares below, so when it's tiny (a heavy favorite knocking out a no-hoper), every derived share becomes numerically unstable. Matches with `released < 0.005` are filtered out of all conclusions for this reason.

*How computed:* loser's pre-match championship snapshot, after normalizing all teams' prices to sum to 1 (raw Kalshi prices sum to ~1.05–1.11 because of the vig/house margin; normalizing removes that).

#### 2.2 `winner_share`
Of the loser's released mass, the fraction the match-winner's championship price absorbed.

*How computed:* (winner's post-match champ price − winner's pre-match champ price) ÷ released, all in normalized units.

**Interpretation warning — this can exceed 1 and that is not a bug.** If a strong team knocks out a weak one, the winner's coherent championship gain can be *larger* than the loser's entire released mass, because the winner also drains probability from its **future opponents** (their path just got harder). Conservation is restored elsewhere in the table, not within this one number. Don't read `winner_share` as "the winner's slice of a pie that sums to 1."

#### 2.3 `implied_winner_share` (the consistency benchmark)
What `winner_share` *should* be if the two markets are perfectly coherent. This is the benchmark the whole edge hypothesis is measured against.

*How computed:* from coherence, the winner's expected championship gain is `p_winner_pre × (1/q − 1)`, where q is the winner's pre-match advance probability. Divide by released to get a share. Intuitively: winning removes the "might not advance" discount, so the champ price should jump by the factor 1/q.

#### 2.4 `excess_absorption` (ea) — **the headline metric**
The ratio of what actually happened to what coherence predicts:

> ea = winner_share ÷ implied_winner_share

- **ea = 1.0** → the winner absorbed exactly the coherent amount. Markets are consistent. No edge.
- **ea > 1.0** → the winner gained *more* than coherence implies (the original hypothesis — would mean the hedge has edge).
- **ea < 1.0** → probability leaked away to future opponents / the field instead.

**This is the number the entire trade thesis rests on, and the current clean estimate is ≈ 1.0** (see §4).

#### 2.5 `next_opponent_share`
Of the released mass, the fraction that flowed to the winner's *next* opponent. **Signed:** expected negative when a favorite advances (the next opponent's path got harder, so their champ price *falls*), positive when an underdog advances. This is the metric most damaged by the contamination bug (§4).

#### 2.6 `field_share`
Of the released mass, the fraction that flowed to everyone else (not winner, loser, or next opponent). Usually **negative** in aggregate — the field's paths tend to harden when a live team advances. This is the one structural regularity that survived scrutiny (sign correct ~83% of matches).

#### 2.7 App-specific display columns
- `champ_pre_c` — current championship price in **cents** (raw Kalshi price space, not normalized).
- `champ_consistent_c` — model's prediction of the price after the fixture resolves, assuming pure coherence.
- `champ_adjusted_c` — same, but with the empirical ea adjustment applied. **Right now this is nearly identical to `champ_consistent_c` because ea ≈ 1.0** — that's expected, not a display error.
- `delta_*_c` — the predicted move (post minus pre) for each of the above.
- `q_pre` / `q_live` — the winner's advance probability before the match vs. given the current in-play score/minute.
- `decisiveness` — how much of the eventual elimination has "happened" given the in-play state; scales from 0 (nothing decided) to 1 (settled). Fades the ea adjustment for in-play states, since an early goal isn't an elimination.

---

### 3. The three layers of the simulator (methodology)

**Layer 1 — In-play match model** (`match_model.py`). A double-Poisson goal model per fixture. Each team's scoring rate is calibrated by bisection so the model's pre-match advance probability exactly matches Kalshi's advance market (q). Any in-play state (score, minute) then becomes a conditional advance probability by rolling the remaining minutes forward. Knockout draws go to extra time (30 min at 1.05× intensity) then penalties (coin flip by default). *Known limits:* independent Poissons (no low-score correlation), no red-card/momentum modeling, penalties treated as skill-free.

**Layer 2 — Bracket engine** (`bracket.py`). Computes each team's championship probability **exactly** via dynamic programming over the bracket tree (no Monte Carlo noise). The clever part is **strength inversion**: rather than inventing team ratings, it fits a rating per team so that the simulator's championship probabilities reproduce the market's championship prices. Round-1 fixtures are pinned to their live advance markets, so ratings only need to explain later rounds. Result: the simulator is anchored to the market by construction, and any conditional query (pin an outcome, inject an in-play probability) re-runs the DP for the full updated championship vector.

**Layer 3 — Absorption adjustment** (`engine.py`, params in `ea_params.json`). Takes Layer 2's coherent prediction and scales the winner's delta by the empirically measured ea (split by underdog/favorite branch), fading by `decisiveness` for in-play states, and renormalizes everyone else. **When ea ≈ 1.0, this layer does almost nothing — which is the correct behavior given the clean data.**

---

### 4. The contamination bug and why the conclusion changed

This is the most important methodological event in the project, so it gets its own section.

**The bug.** The original pipeline took each match's "before" snapshot at a fixed 6 hours before kickoff and "after" snapshot at settlement, with no upper bound. This tournament runs knockout matches close together, so **a different match often settled inside that window**. The clearest case: Belgium beat the USA, and we measured how much Spain (Belgium's next opponent) moved. But Spain had beaten Portugal *the same evening, inside the window* — so Spain's own victory jump got misattributed to "Spain reacting to Belgium's win." 21 of 22 matches had windows overlapping a neighbor.

**The fix.** Clip every match's window so it never crosses another match's settlement (pre-snapshot no earlier than the last prior settlement + 30 min; post-snapshot no later than the next settlement − 30 min). Rows where clipping leaves no valid candle are flagged, not silently reverted.

**The effect — before vs after decontamination:**

| Metric | Contaminated | Clean |
|---|---|---|
| ea_underdog | 1.183 | **1.018** |
| ea_favorite | 1.011 | 0.989 |
| next_opp_share_underdog | 0.61 | **0.226** |
| mass-weighted mean ea | 1.134 | **0.996** |

The apparent ~18% over-absorption edge was **substantially a measurement artifact**. Once measured cleanly, winners get essentially their coherent share (ea ≈ 1.0), and the next-opponent flow shrank by nearly two-thirds. This is a materially different — and more pessimistic — conclusion than the first pass, and it is the current best estimate.

---

### 5. What the backtest does and doesn't establish

The v2 backtest checks the simulator against 6 settled Round-of-16 matches on the real bracket. Results: winner-direction correct 6/6; winner magnitude within 1–4× (mean absolute error 0.012, down from 0.088 on the earlier broken toy-bracket version); `consistent` and `adjusted` predictions identical to 4 decimals (correct, since ea ≈ 1.0).

**Two honest caveats that limit what this proves:**
1. **In-sample.** ea was fit on the same 22 matches (of which these 6 are a subset). There's no held-out data yet — this shows the fitted parameters don't *hurt* on training data, not genuine out-of-sample validation. Refit and re-backtest as new rounds settle.
2. **Settled outcomes only.** The backtest never tests partial in-play states. **So the in-play score/minute magnitudes in the Match Simulator page are unvalidated** — treat them as directionally reasonable, not precise. This is why the app labels them so.

The per-match next-opponent *sign* is right only ~67% of the time (n=6) — close to a coin flip. **Do not trade off the per-match next-opponent prediction.** The aggregate flow is real; the match-level call is not reliable yet.

---

### 6. How to read each app page

**Live board.** Pulls current prices and shows the hedge screen: for every remaining fixture and each possible winner, the predicted championship reprice. The `delta_adjusted_c` column is the headline "how much would this team's championship price jump if they advance." **But** since ea ≈ 1.0, these are essentially coherence predictions — the jump you'd expect from removing the "might not advance" discount, *not* evidence of an exploitable edge. Big `delta_adjusted_c` values (e.g. Morocco +11, Norway +11) reflect that longshots have the most to gain by advancing, which the market already knows.

**Match simulator.** Pick a fixture, set a score and minute (or toggle "outcome settled"). Watch the championship table re-flow. Useful for "if Morocco takes an early lead, how does the board move?" Remember the in-play magnitudes are unvalidated (§5). `q_pre → q_live` shows how the match probability shifts; `decisiveness` shows how settled the outcome is.

**Hedge builder.** Enter a championship position you hold (team, size, entry price) and a hedge market. It computes the P&L in both outcomes across hedge sizes and shows whether any size is positive in *both* states (the "window"). The ea sensitivity table re-runs this at ea = 1.0, fitted, and fitted+0.2. **The fact that it usually returns "no positive window" is the tool working correctly** — with ea ≈ 1.0 there generally isn't one. That is the central negative result made concrete.

---

### 7. Bottom line for decisions

1. **The structural hedge edge is not there.** ea ≈ 1.0 after clean measurement. Retire the "buy longshot champ + opponent-advances" thesis as a systematic play — it's a coin flip minus fees.
2. **The simulator is a valid coherence calculator.** It correctly predicts winner-side repricing direction and rough magnitude. Its value is as a **deviation screen**: flagging the occasional fixture where the championship market hasn't yet caught up to the advance market — transient mispricing, not a structural premium. Those are rarer and require speed.
3. **The one untested hypothesis with possible signal** is *latency*: not "does the market misprice absorption" (answered: no) but "does the championship market lag the match result by enough minutes to trade the gap." The clean data doesn't refute this because we never measured it.
4. **Sample sizes are small** (5 underdog, 2 favorite clean matches). Every remaining round adds high-mass observations; refit `ea_params.json` and re-run the backtest after each.

---

### 8. File map

```
src/                      data pipeline
  kalshi_client.py        public API client (dollars() price convention)
  pull_data.py            candlestick snapshots + window clipping (§4 fix)
  decompose.py            the metrics in §2
  config.py               tickers + TEAM_CODE_MAP crosswalk
simulator/
  match_model.py          Layer 1 (in-play Poisson)
  bracket.py              Layer 2 (DP + strength inversion)
  engine.py               Layer 3 (ea adjustment) + query API
  fit_ea.py               refits ea_params.json from decomposition
  ea_params.json          current empirical parameters
  app.py                  Streamlit app (3 pages)
  backtest_report_v2.md   validation (§5)
data/processed/           snapshots, decompositions, live prices
RUN_NOTES.md              full run log incl. contamination fix
```
