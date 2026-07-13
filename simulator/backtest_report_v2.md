# Simulator Layer 1 backtest v2 -- real bracket

Backtested 6 of 6 candidate matches (0 excluded). Only Round-of-16 matches from 2026-07-04 onward are in scope -- the true remaining bracket is exactly the confirmed 16-team tree in simulator/bracket_2026.py at that point (CANMAR, PARFRA, BRANOR, MEXENG, PORESP, USABEL). Earlier Round-of-32 matches (>16 teams remaining) are excluded: we don't have confirmed bracket adjacency for them beyond immediate next-opponent, and forcing them into the same 16-team tree would misrepresent rounds that didn't structurally exist yet for those matches. A small clean sample beats a large contaminated one.

## Caveats

1. **ea is fit in-sample.** `simulator/fit_ea.py` reads `decomposition_results.csv`, which includes these same 6 matches (plus 16 others). This is not a held-out test.
2. **Not-yet-settled sibling fixtures use retrospective pre-match odds** as a stand-in for "what the market believed at this match's kickoff." All 6 matches are within a 2-3 day window, so odds likely hadn't moved much, but this is an approximation, not the literal historical snapshot at each kickoff.
3. Unlike backtest_v1's 4-node toy, **no synthetic SHADOW node is used here** -- all 16 real bracket teams are used directly, and they represent essentially the entire remaining probability mass at this stage (everyone else already priced near zero). This confirmedly fixes v1's magnitude inflation: winner MAE drops from 0.088-0.097 (v1, 4-node toy) to 0.012 (v2, real bracket) -- the predicted/actual ratio is now mostly 1-4x rather than v1's 3-10x+, and two of six matches (PORESP, BRANOR) land within ~20% of the actual magnitude. See the winner table below.
4. **Calibration needed a lower learning rate to converge for this backtest.** `Bracket.calibrate_to_market`'s default `lr=0.6` (used everywhere else in the simulator, including the live app) diverged to NaN for 2 of 6 matches here -- multiple simultaneous not-yet-settled sibling fixtures plus several hard 0/1 pins makes the joint rating fit harder than the live/production case, which typically has fewer simultaneous constraints. `lr=0.3` (with more iterations) converges cleanly to ~1e-7 error for all 6 matches. Added as an optional `Simulator(calib_lr=..., calib_iters=...)` parameter, default unchanged at 0.6/400 for every other call site.

## MAE and sign agreement by role

    role  MAE_consistent  MAE_adjusted  sign_agree_consistent  sign_agree_adjusted  n
  winner          0.0119        0.0119                 1.0000               1.0000  6
next_opp          0.0072        0.0072                 0.6667               0.6667  6
   field          0.0142        0.0142                 0.8333               0.8333  6


## Winner: predicted vs actual, per match (magnitude check)

                 match_id winner  actual_winner  pred_winner_consistent  pred_winner_adjusted  ratio_consistent  ratio_adjusted
KXWCADVANCE-26JUL04CANMAR    MAR         0.0028                  0.0086                0.0085            3.0317          2.9983
KXWCADVANCE-26JUL04PARFRA    FRA         0.0070                  0.0298                0.0295            4.2353          4.1887
KXWCADVANCE-26JUL06PORESP    ESP         0.0574                  0.0631                0.0624            1.1000          1.0879
KXWCADVANCE-26JUL06USABEL    BEL         0.0121                  0.0173                0.0176            1.4331          1.4589
KXWCADVANCE-26JUL05BRANOR    NOR         0.0398                  0.0316                0.0322            0.7952          0.8095
KXWCADVANCE-26JUL05MEXENG    ENG         0.0571                  0.0806                0.0821            1.4110          1.4364


## Full per-match comparison

                 match_id winner loser next_opponent  actual_winner  pred_winner_consistent  pred_winner_adjusted  actual_next_opp  pred_next_opp_consistent  pred_next_opp_adjusted  actual_field  pred_field_consistent  pred_field_adjusted
KXWCADVANCE-26JUL04CANMAR    MAR   CAN           FRA         0.0028                  0.0086                0.0085           0.0070                   -0.0113                 -0.0112       -0.0089                 0.0046               0.0047
KXWCADVANCE-26JUL04PARFRA    FRA   PAR           MAR         0.0070                  0.0298                0.0295          -0.0008                   -0.0044                 -0.0043       -0.0052                -0.0235              -0.0232
KXWCADVANCE-26JUL06PORESP    ESP   POR           BEL         0.0574                  0.0631                0.0624           0.0022                   -0.0004                 -0.0004       -0.0069                -0.0088              -0.0081
KXWCADVANCE-26JUL06USABEL    BEL   USA           ESP         0.0121                  0.0173                0.0176           0.0033                    0.0145                  0.0144        0.0218                 0.0065               0.0063
KXWCADVANCE-26JUL05BRANOR    NOR   BRA           ENG         0.0398                  0.0316                0.0322           0.0147                    0.0086                  0.0085        0.0122                 0.0276               0.0270
KXWCADVANCE-26JUL05MEXENG    ENG   MEX           NOR         0.0571                  0.0806                0.0821          -0.0039                   -0.0054                 -0.0055       -0.0024                -0.0233              -0.0246