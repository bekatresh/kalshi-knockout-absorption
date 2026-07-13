# Simulator Layer 1 backtest

Backtested 22 of 22 settled knockouts (0 skipped/errored). Methodology: minimal 4-node bracket [loser, winner, next_opponent, SHADOW] per match -- see simulator/backtest.py module docstring for why.

## Two important caveats before reading the numbers

1. **ea was fit on these same 22 matches** (`simulator/fit_ea.py` reads `decomposition_results.csv`, which covers exactly this backtest set). This is an in-sample check, not a held-out test -- there's no independent data yet to hold out. Treat the verdict below as 'does the fitted ea at least not hurt the training data' rather than genuine out-of-sample validation. Re-run this backtest as new knockouts settle and ea gets refit on a growing/rolling window.
2. **The 4-node toy bracket is shallower than the real tournament** (loser beaten in round 0, next_opponent faced in round 1 = the toy bracket's FINAL). The real tournament has 3-5 more rounds after that for early matches. This inflates the toy model's ABSOLUTE predicted deltas for winner/next_opponent well above the real observed magnitudes (see the per-match table -- predicted winner deltas are routinely 3-10x the actual). The MAE numbers below are dominated by this scale mismatch, not by whether the model gets the *direction* of the effect right. Sign agreement (does the model at least get the direction right?) is a scale-robust secondary check reported alongside MAE for this reason.

## MAE by role (absolute probability points, i.e. 0.01 = 1 percentage point)

    role  MAE_consistent  MAE_adjusted  sign_agree_consistent  sign_agree_adjusted  n
  winner          0.0883        0.0970                 0.9545               0.9545 22
next_opp          0.0591        0.0565                 0.4545               0.4545 22
   field          0.0168        0.0163                 0.1364               0.8182 22


**MAE verdict: pure consistency beats the ea adjustment on MAE** (mean MAE across roles: consistent=0.0547, adjusted=0.0566) -- read this alongside caveat 2 above; it's likely more about toy-bracket scale than about ea's real value.

**Sign-agreement verdict (scale-robust, arguably more informative):**
- winner: consistent=95%, adjusted=95% -- both essentially trivial (the winner of a match it just won almost always gains probability).
- next_opponent: consistent=45%, adjusted=45% -- close to a coin flip either way. The model does NOT reliably predict whether next_opponent gains or loses probability on a per-match basis, despite the real aggregate mass-weighted next_opponent_share being solidly positive (~0.6-0.8, see ea_params.json). Don't trust this simulator's next_opponent signal match-by-match.
- field: consistent=14%, adjusted=82% -- **this is the standout result.** Pure bracket-consistency almost always predicts the field GAINS probability when a match settles (wrong sign most of the time -- real field mass usually drops, per CLAUDE.md's structural-insight note that the field's path hardens when a bigger team advances). The ea adjustment fixes the sign on the large majority of matches. This is the one place the ea adjustment demonstrably earns its keep in this backtest.

## Per-match comparison

                 match_id winner loser next_opponent  q_winner  released  actual_winner  pred_winner_consistent  pred_winner_adjusted  actual_next_opp  pred_next_opp_consistent  pred_next_opp_adjusted  actual_field  pred_field_consistent  pred_field_adjusted
KXWCADVANCE-26JUN28RSACAN     CA   RSA            MA      0.72    0.0000         0.0009                  0.0204                0.0206          -0.0001                    0.0058                  0.0057       -0.0008                 0.0000              -0.0001
KXWCADVANCE-26JUN29NEDMAR     MA    NL            CA      0.42    0.0493         0.0252                  0.3619                0.4282           0.0010                    0.0557                  0.0388        0.0232                 0.0000              -0.0493
KXWCADVANCE-26JUN29GERPAR     PY    DE            FR      0.14    0.0329         0.0027                  0.0199                0.0235           0.0236                    0.0966                  0.0934        0.0066                 0.0000              -0.0004
KXWCADVANCE-26JUN29BRAJPN     BR    JP            NO      0.74    0.0075         0.0155                  0.1575                0.1592          -0.0001                   -0.0903                 -0.0905       -0.0080                 0.0000              -0.0015
KXWCADVANCE-26JUN30MEXECU     MX    EC            GB      0.64    0.0037         0.0198                  0.1151                0.1164          -0.0093                   -0.0810                 -0.0821       -0.0069                 0.0000              -0.0002
KXWCADVANCE-26JUN30FRASWE     FR    SE            PY      0.89    0.0019         0.0482                  0.0323                0.0327          -0.0000                   -0.0088                 -0.0088       -0.0463                -0.0169              -0.0173
KXWCADVANCE-26JUN30CIVNOR     NO   CIV            BR      0.65    0.0028         0.0050                  0.0890                0.0900           0.0020                   -0.0654                 -0.0660       -0.0043                 0.0000              -0.0003
KXWCADVANCE-26JUL01USABIH     US   BIH            BE      0.84   -0.0002         0.0034                  0.0838                0.0847           0.0021                    0.0209                  0.0207       -0.0057                 0.0000              -0.0006
KXWCADVANCE-26JUL01BELSEN     BE    SN            US      0.67    0.0055         0.0051                  0.0642                0.0649           0.0033                    0.0372                  0.0366       -0.0029                -0.0000              -0.0001
KXWCADVANCE-26JUL01ENGCOD     GB   COD            MX      0.88    0.0000         0.0091                  0.0510                0.0516          -0.0019                   -0.0059                 -0.0062       -0.0071                 0.0000              -0.0004
KXWCADVANCE-26JUL02SUIDZA     CH   DZA            CO      0.67   -0.0000         0.0012                  0.0821                0.0830           0.0009                   -0.0583                 -0.0590       -0.0021                 0.0000              -0.0002
KXWCADVANCE-26JUL02PORCRO     PT    HR            ES      0.73    0.0018         0.0157                  0.1274                0.1288           0.0246                   -0.1115                 -0.1126       -0.0385                 0.0000              -0.0003
KXWCADVANCE-26JUL02ESPAUT     ES    AT            PT      0.88    0.0009         0.0268                  0.0603                0.0610           0.0002                   -0.0559                 -0.0562       -0.0260                 0.0000              -0.0004
KXWCADVANCE-26JUL03COLGHA     CO    GH            CH      0.81   -0.0000         0.0065                  0.1156                0.1168           0.0012                   -0.0959                 -0.0961       -0.0077                 0.0000              -0.0011
KXWCADVANCE-26JUL03ARGCPV     AR   CPV           EGY      0.93    0.0009        -0.0091                  0.0427                0.0432           0.0009                   -0.0214                 -0.0214        0.0091                 0.0000              -0.0005
KXWCADVANCE-26JUL03AUSEGY    EGY    AU            AR      0.61    0.0009         0.0010                  0.0062                0.0063           0.0216                   -0.0013                 -0.0014       -0.0216                 0.0000              -0.0000
KXWCADVANCE-26JUL04PARFRA     FR    PY            MA      0.92    0.0009         0.0218                  0.0336                0.0340           0.0046                   -0.0311                 -0.0311       -0.0255                 0.0000              -0.0004
KXWCADVANCE-26JUL04CANMAR     MA    CA            FR      0.72    0.0009         0.0036                  0.0209                0.0211           0.0189                   -0.0162                 -0.0164       -0.0216                 0.0000              -0.0000
KXWCADVANCE-26JUL05MEXENG     GB    MX            NO      0.49    0.0493         0.0717                  0.3307                0.3912           0.0366                   -0.0755                 -0.0758       -0.0591                 0.0000              -0.0603
KXWCADVANCE-26JUL05BRANOR     NO    BR            GB      0.30    0.0643         0.0402                  0.1916                0.2267           0.0170                    0.2190                  0.1897        0.0070                 0.0000              -0.0058
KXWCADVANCE-26JUL06PORESP     ES    PT            BE      0.66    0.0508         0.0618                  0.2247                0.2272           0.0027                   -0.0328                 -0.0328       -0.0136                 0.0000              -0.0024
KXWCADVANCE-26JUL06USABEL     BE    US            ES      0.46    0.0346         0.0155                  0.0708                0.0838           0.0625                    0.1202                  0.1091       -0.0434                -0.0000              -0.0018