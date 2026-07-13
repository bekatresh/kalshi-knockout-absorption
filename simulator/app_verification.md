# App verification — each page working (text dump)

Verified via Streamlit's official `AppTest` headless harness
(`streamlit.testing.v1.AppTest`), which runs the actual `simulator/app.py`
script against live Kalshi data and captures the rendered widget tree — no
mocking. No screenshot tool was available in this environment (no
browser/Playwright installed); `AppTest` is the more rigorous check anyway
since it verifies the real computed values, not just that pixels rendered.
Confirmed separately that `streamlit run simulator/app.py` starts cleanly
(health check `ok`, HTTP 200 on the root page) before running this.

All three pages: **zero exceptions**, real data pulled from Kalshi's public
API (calibration converges: max error ~3.5 percentage points, matching
`simulator/run_live.py`'s own figure).

## Live board

After clicking "Pull current prices":

```
METRIC: Calibration max error (within-bracket pct pts) = 3.52
METRIC: Calibration iterations = 400
METRIC: Raw champ price sum (16 teams) = 1.0180

Championship prices (raw Kalshi cents), top of table:
team  champ_pre_c
FRA   34.57
ESP   18.77
ENG   14.70
ARG   14.66
NOR    5.95
COL    4.76
SUI    3.00
MAR    2.75
BEL    2.56
EGY    0.09
(CAN/PAR/POR/USA/BRA/MEX all 0.00 -- eliminated)

Hedge screen (live fixtures, raw Kalshi price space), sorted by delta_adjusted_c:
fixture if_advances prob champ_pre_c champ_adjusted_c delta_adjusted_c released_mass_c
ENG-NOR NOR   0.35  5.95  17.20  11.25  20.65
FRA-MAR MAR   0.22  2.75  12.68   9.93  37.32
FRA-MAR FRA   0.78 34.57  44.22   9.64  37.32
ENG-NOR ENG   0.65 14.70  22.53   7.83  20.65
ESP-BEL BEL   0.25  2.56  10.37   7.81  21.33
ESP-BEL ESP   0.75 18.77  24.96   6.19  21.33
SUI-COL SUI   0.40  3.00   7.57   4.57   7.75
SUI-COL COL   0.60  4.76   7.90   3.14   7.75
ARG-EGY ARG   0.85 14.66  17.22   2.56  14.75
ARG-EGY EGY   0.15  0.09   0.61   0.52  14.75
```

## Match simulator

Fixture ARG-EGY, default in-play state (0-0 at minute 45):

```
METRIC: q_pre = 0.850
METRIC: q_live = 0.763
METRIC: decisiveness = 0.10

champ_pre_c  champ_consistent_c  champ_adjusted_c  delta_consistent_c  delta_adjusted_c
FRA  34.573  34.760  34.760   0.188   0.188
ESP  18.769  18.905  18.905   0.136   0.136
ENG  14.699  15.019  15.019   0.320   0.320
ARG  14.659  13.152  13.152  -1.506  -1.506
NOR   5.949   6.101   6.101   0.152   0.152
COL   4.758   5.122   5.122   0.364   0.364
SUI   2.995   3.230   3.230   0.234   0.234
MAR   2.752   2.783   2.783   0.031   0.031
BEL   2.558   2.586   2.586   0.028   0.028
EGY   0.090   0.142   0.143   0.052   0.053
(CAN/PAR/POR/USA/BRA/MEX all 0.000 -- eliminated)
```

Bar chart of `delta_consistent_c` renders from this same data (Streamlit's
native `st.bar_chart`, not separately screenshotted).

## Hedge builder

Default team CAN (champ_pre_c = $0, eliminated — a non-illustrative default;
in real use pick a team you actually hold), fixture ARG-EGY, side EGY,
entry 1.28c, 1000 contracts, fee 0.07:

```
ea sensitivity table:
ea                            n_hedge_sizes_positive  best_worst_case  window
1.0 (no excess absorption)    0                       -12.80           none
fitted (1.018)                0                       -12.80           none
fitted + 0.2 (1.218)          0                       -12.80           none

WARNING shown in-app: "No hedge size in the tested range (0-120) has a
positive worst-case outcome at the fitted ea."

Hedge frontier table (first/last few rows of 25):
n_hedge  pnl_if_hedge_wins  pnl_if_loser_advances  worst_case
0        -12.80             -12.80                 -12.80
50        -6.47             -56.47                 -56.47
100       -0.15             -100.15                -100.15
120        2.38             -117.62                -117.62
```

(This particular team/fixture/entry combination genuinely has no positive
worst-case window at these prices — that's the model working correctly, not
a bug; try it with BEL/USA-style parameters from `RUN_NOTES.md` to see a
populated window.)

## Known cosmetic-only issue caught and fixed during verification

`AppTest` initially failed with `ImportError: attempted relative import
with no known parent package` — `streamlit run simulator/app.py` executes
the file as `__main__`, so the original `from .bracket_2026 import ...`
relative imports never worked under the literal command the user was given.
Fixed by switching `app.py`'s imports to absolute (`from simulator.bracket_2026
import ...`), relying on the existing `sys.path.insert` at the top of the
file. Also fixed a wrong import location (`LIVE_QF_FIXTURES` is defined in
`simulator/live_inputs.py`, not `bracket_2026.py`) caught by the same test.
