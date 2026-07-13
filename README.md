# Kalshi Knockout Absorption Analysis

When a World Cup team is eliminated, where does its championship probability
go? Measures, per completed knockout: the winner's absorbed share vs. the
consistency-implied share, the next opponent's (signed) share, and leakage to
the field. Feeds a scenario P&L for the "hold longshot champ position + buy
opponent-advances hedge" trade.

## Workflow

```bash
pip install -r requirements.txt

# 1. Verify series tickers (edit src/config.py with what you find)
python -m src.discover --find-series "world cup"
python -m src.discover --champion

# 2. Draft the knockout match list, paste into src/config.py, fill in
#    next_opponent_teams from the bracket
python -m src.discover --draft-matches

# 3. Pull candlesticks + build snapshot tables (needs Kalshi network access)
python -m src.pull_data

# 4. Analyze
jupyter lab notebooks/analysis.ipynb
```

No API key needed — market data endpoints are public. If rate-limited,
raise `sleep_s` in `KalshiPublic`.

## Demo (no network needed)

`python demo/run_demo.py` simulates a bracket with known ground truth
(ALPHA, NEXT_BETA) and runs the identical decomposition — useful for
validating the estimator and seeing output shapes.

## Interpretation cheatsheet

| Quantity | Meaning |
|---|---|
| `winner_share` | fraction of loser's released mass the winner absorbed. **Can exceed 1** — the winner also drains future opponents whose path got harder. Can't read it as a naive "split of the pie." |
| `implied_winner_share` | what joint coherence of match + championship markets predicts (`p_w(1/q − 1)/R`) |
| `excess_absorption` | actual/implied. >1 → winners over-rewarded (hedge has extra edge). <1 → leakage (naive hedge math overstates payoff) |
| `next_opponent_share` | *signed*: expected **negative** when the favorite advances (opponent's path hardened), positive when the underdog does |

## Known estimator caveats

- Tiny `loser_pre` → tiny denominator → noisy shares (the demo shows ±0.3
  swings in excess_absorption at 4% price noise). Prefer VWAP over several
  candles, and weight cross-match aggregates by released mass.
- Vig drift between snapshots contaminates shares; `raw_vig_pre/post`
  columns let you flag bad snapshots.
- Longshot prices have known favorite–longshot bias; normalized prices ≠
  true probabilities. The *decomposition* is still internally consistent,
  but level-based conclusions need care.
- Candlestick endpoint shape can change; see note in `src/kalshi_client.py`.

## Layout

```
src/kalshi_client.py   public API client
src/config.py          series tickers + knockout match list (EDIT ME)
src/discover.py        find tickers, draft match list
src/pull_data.py       candlesticks -> pre/post snapshot tables
src/decompose.py       core decomposition + hedge P&L
src/plotting.py        charts
notebooks/analysis.ipynb
demo/run_demo.py       synthetic end-to-end validation
```
